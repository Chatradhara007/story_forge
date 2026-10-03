from pydantic import ValidationError
from models import Fact, ExtractionResult
import relationships as rel_rules
import os
import re
import threading
from llm import call_tool, run_in_parallel, JUDGING_THINKING_MODE

# Long chapters are split into pieces of about this many characters, so the
# AI's answer never gets cut off halfway (which used to crash the app).
MAX_CHARS_PER_PIECE = 12000

# Chapters are READ in short passages of about this many characters (a few paragraphs),
# several at once. The AI tends to write about the same number of facts per request
# however long the text is, so reading in small passages records far more of the detail.
# Each passage is sent with the passage before it as context, to work out what "he" or
# "it" refers to. Bigger = fewer AI calls but less detail; smaller = more calls.
READ_PASSAGE_CHARS = max(200, int(os.getenv("READ_PASSAGE_CHARS", "700")))

# A pronoun is not a name: facts "about" these can't be linked to anyone, so they're dropped.
PRONOUNS = {"he", "she", "they", "him", "her", "them", "it", "his", "hers", "their",
            "i", "me", "we", "us", "you", "someone", "somebody"}

EXTRACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "record_facts",
        "description": "Record structured facts extracted from a story chapter.",
        "parameters": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string"},
                            "entity_type": {
                                "type": "string",
                                "enum": ["character", "location", "item", "event", "other"]
                            },
                            "attribute": {"type": "string"},
                            "value": {"type": "string"},
                            "source_quote": {"type": "string"},
                            "confidence": {"type": "number"}
                        },
                        "required": ["entity", "entity_type", "attribute", "value", "source_quote", "confidence"]
                    }
                },
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "person": {"type": "string"},
                            "relation": {"type": "string"},
                            "other_person": {"type": "string"},
                            "source_quote": {"type": "string"},
                            "confidence": {"type": "number"}
                        },
                        "required": ["person", "relation", "other_person", "source_quote"]
                    }
                }
            },
            "required": ["facts"]
        }
    }
}

EXTRACTION_PROMPT = """You are extracting structured facts from a chapter of fiction for a
continuity-tracking system. Read the text and extract every concrete, checkable fact about
characters, locations, items, and events: physical descriptions, relationships, status
(alive/dead/injured), locations, dates/time references, and stated events.

Only extract facts that are explicitly stated or very strongly implied — do not infer
beyond what the text supports. Include a short exact quote for each fact so it can be
cited later. Always refer to a character by their fullest name as used in this text — never
use a pronoun (he, she, they...) as the entity; work out who it refers to instead.

Two things are easy to miss, so check for them:
- Objects: when an object is used, moved, lost, thrown away or destroyed, write the object's
  name in the fact (never just "it"), and also add a fact about the object itself, in the form
  "<object> | location | <where it now is>".
- Time: record every day, date or time the text gives for an event, including passing
  references. The entity is always the EVENT, never the day itself: "<event> | day | <day>".
  Only record a day, date, age or number that is actually written in the text. Never guess one.

Also list every RELATIONSHIP between two characters that the text states: family (parent,
child, spouse, sibling, cousin, grandparent...) and other ties (friend, ally, rival, enemy,
mentor, apprentice, employer, servant, lover). Write it as "person | relation | other_person",
read as "person is the <relation> of other_person", using both characters' fullest names.

Only extract facts from the Chapter text section below.
{context}
Chapter text:
{text}
"""

CONTEXT_BLOCK = """
EARLIER IN THE SAME CHAPTER (context only: use it to work out who or what "he", "she", "it"
or "they" refers to, but do NOT extract facts from it):
{previous}
"""


def split_into_pieces(text: str, max_chars: int = MAX_CHARS_PER_PIECE) -> list[str]:
    """Split text into pieces no longer than max_chars, breaking at line ends where possible."""
    pieces: list[str] = []
    current = ""
    for line in text.split("\n"):
        # A single enormous line: cut it into fixed-size slices.
        while len(line) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:max_chars])
            line = line[max_chars:]
        if current and len(current) + 1 + len(line) > max_chars:
            pieces.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current.strip():
        pieces.append(current)
    return pieces or [text]


def split_into_passages(text: str, max_chars: int | None = None) -> list[str]:
    """
    Split a chapter into passages of whole paragraphs, each up to about max_chars
    (default: READ_PASSAGE_CHARS). A paragraph longer than that is split between
    sentences; nothing is lost.
    """
    max_chars = max_chars or READ_PASSAGE_CHARS
    units: list[str] = []
    for paragraph in [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]:
        if len(paragraph) <= max_chars:
            units.append(paragraph)
            continue
        sentence_group = ""
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            while len(sentence) > max_chars:                   # one enormous sentence
                if sentence_group:
                    units.append(sentence_group)
                    sentence_group = ""
                units.append(sentence[:max_chars])
                sentence = sentence[max_chars:]
            if sentence_group and len(sentence_group) + 1 + len(sentence) > max_chars:
                units.append(sentence_group)
                sentence_group = ""
            sentence_group = f"{sentence_group} {sentence}".strip()
        if sentence_group:
            units.append(sentence_group)

    passages: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + 2 + len(unit) > max_chars:
            passages.append(current)
            current = ""
        current = f"{current}\n\n{unit}" if current else unit
    if current:
        passages.append(current)
    return passages or [text]


# Drop facts that aren't really in the text (see is_grounded). On by default; the automated
# tests switch it off because their pretend chapters are short markers, not real text.
CHECK_GROUNDING = True

# Words that must never be invented: if one appears in a fact's value, it must also appear in
# the text. (The AI sometimes fills in a plausible day or number that the story never says.)
_CHECKED_WORDS = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
    "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
    "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred",
}


_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
          "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
             "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
             "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
             "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20,
             "thirtieth": 30, "fortieth": 40, "fiftieth": 50, "hundredth": 100}
_NUMBER_WORDS = set(_UNITS) | set(_TENS) | set(_ORDINALS) | {"hundred", "thousand"}


def normalise_numbers(text: str) -> str:
    """
    Write every number as digits, so "twelve", "12", "12th" and "twelfth" all compare equal.
    Handles "twenty-one", "twenty one", "a hundred and five", "1,000" and ordinals.
    """
    text = text.lower()
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)               # 1,000 -> 1000
    text = re.sub(r"(\d+)(?:st|nd|rd|th)\b", r"\1", text)           # 12th -> 12
    tokens = re.findall(r"[a-z]+|\d+|[^a-z\d]+", text)
    out: list[str] = []
    i = 0
    while i < len(tokens):
        word = tokens[i]
        if word not in _NUMBER_WORDS:
            out.append(word)
            i += 1
            continue
        total, current, j, last_word_end = 0, 0, i, i
        while j < len(tokens):
            w = tokens[j]
            if w in _UNITS:
                current += _UNITS[w]
            elif w in _TENS:
                current += _TENS[w]
            elif w in _ORDINALS:
                current += _ORDINALS[w]
                last_word_end = j
                j += 1
                break
            elif w == "hundred":
                current = max(current, 1) * 100
            elif w == "thousand":
                total += max(current, 1) * 1000
                current = 0
            else:
                break
            last_word_end = j
            j += 1
            # allow "twenty-one", "twenty one", "hundred and five" to continue the number
            if (j + 1 < len(tokens) and tokens[j] in ("-", " ") and tokens[j + 1] in _NUMBER_WORDS
                    and not (tokens[j - 1] in _UNITS and tokens[j + 1] in _UNITS)):   # "two three" are two numbers
                j += 1
            elif (tokens[j - 1] in ("hundred", "thousand")
                  and j + 3 < len(tokens) and tokens[j] == " " and tokens[j + 1] == "and"
                  and tokens[j + 2] == " " and tokens[j + 3] in _NUMBER_WORDS):
                j += 3
            else:
                break
        out.append(str(total + current))
        i = last_word_end + 1
    return "".join(out)


def _words_in(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+|\d+", normalise_numbers(text)))


def is_grounded(fact: dict, text: str) -> bool:
    """
    Is this fact really in the text? Two checks, no AI needed:
    - every day, month or number in the value appears in the text. Numbers are compared
      as digits, so "12" in the value matches "twelve" in the text and the other way round;
    - most of the quote's words appear in the text (the quote isn't invented).
    """
    text_words = _words_in(text)
    value_words = _words_in(str(fact.get("value", "")))
    for word in value_words:
        if (word in _CHECKED_WORDS or word.isdigit()) and word not in text_words:
            return False
    quote_words = [w for w in _words_in(str(fact.get("source_quote", ""))) if len(w) > 3 or w.isdigit()]
    if quote_words:
        found = sum(1 for w in quote_words if w in text_words)
        if found / len(quote_words) < 0.7:
            return False
    return True


def _clean_facts(raw_facts: list) -> list[Fact]:
    """Keep only well-formed facts, tidy them up, and drop exact duplicates."""
    facts: list[Fact] = []
    seen = set()
    for raw in raw_facts:
        try:
            fact = Fact(**raw)
        except (ValidationError, TypeError):
            continue  # skip one bad fact instead of failing the whole chapter
        fact.entity = " ".join(fact.entity.split())
        if not fact.entity or fact.entity.lower() in PRONOUNS:
            continue
        fact.confidence = min(max(fact.confidence, 0.0), 1.0)
        key = (fact.entity.lower(), fact.attribute.lower().strip(), fact.value.lower().strip())
        if key in seen:
            continue
        seen.add(key)
        facts.append(fact)
    return facts


def extract_facts(chapter_id: str, text: str, on_passage=None) -> ExtractionResult:
    """on_passage(done, total) is called as each passage finishes (for progress bars)."""
    # The chapter is read in short passages, several at the same time, each with the
    # passage before it as context.
    passages = split_into_passages(text)
    jobs = [(passages[i - 1] if i > 0 else "", passage) for i, passage in enumerate(passages)]
    done = {"n": 0}
    lock = threading.Lock()

    def read(job):
        answer = call_tool(
            EXTRACTION_PROMPT.format(
                text=job[1], context=CONTEXT_BLOCK.format(previous=job[0]) if job[0] else ""),
            EXTRACTION_TOOL, max_tokens=8192,   # room for a detail-rich passage; unused room costs nothing
        )
        if on_passage:
            with lock:
                done["n"] += 1
                count = done["n"]
            on_passage(count, len(jobs))
        return answer

    answers = run_in_parallel(read, jobs)
    raw_facts: list = []
    found_relationships = []
    for (previous, passage), answer in zip(jobs, answers):
        for r in answer.get("relationships", []) or []:
            if not isinstance(r, dict):
                continue
            quote = str(r.get("source_quote", ""))
            if CHECK_GROUNDING and not is_grounded({"value": "", "source_quote": quote}, passage):
                continue
            try:
                confidence = float(r.get("confidence", 0.8))
            except (TypeError, ValueError):
                confidence = 0.8
            relationship = rel_rules.normalise(str(r.get("person", "")), str(r.get("other_person", "")),
                                               str(r.get("relation", "")), quote, confidence)
            if relationship and {relationship.from_name.lower(), relationship.to_name.lower()}.isdisjoint(PRONOUNS):
                found_relationships.append(relationship)
                raw_facts.extend(rel_rules.as_facts(relationship))
        # Drop facts whose day/number or quote isn't actually in THIS passage: the AI either
        # invented them or took them from the context passage, which belongs to the previous job.
        raw_facts.extend(f for f in answer.get("facts", [])
                         if isinstance(f, dict) and (not CHECK_GROUNDING or is_grounded(f, passage)))
    unique = {(r.from_name.lower(), r.kind, r.to_name.lower()): r for r in found_relationships}
    return ExtractionResult(chapter_id=chapter_id, facts=_clean_facts(raw_facts), relationships=list(unique.values()))


# ---------------------------------------------------------------------------
# When is this chapter set? (flashbacks and time skips)
# ---------------------------------------------------------------------------
TIMING_TOOL = {
    "type": "function",
    "function": {
        "name": "record_timing",
        "description": "Record when a chapter is set compared with the chapters before it.",
        "parameters": {
            "type": "object",
            "properties": {
                "setting": {"type": "string", "enum": ["continues", "flashback", "time skip", "unclear"]},
                "description": {"type": "string"},
            },
            "required": ["setting", "description"],
        },
    },
}

TIMING_PROMPT = """Read this chapter of a novel and say WHEN it is set compared with the
chapters before it. The notes below say when each earlier chapter is set; use them to judge
whether this chapter continues, jumps forward, or goes back.
- continues: it follows on from the story so far
- flashback: it is set EARLIER than the chapters before it
- time skip: it jumps forward in time
- unclear: the text doesn't say

In "description", give the time relationship in a few words, using the chapter's own words
where possible, e.g. "twelve years before the fire" or "three years after the fire". If the
time changes part-way through the chapter, say so briefly.

EARLIER CHAPTERS (reading order: when each is set):
{earlier}

Chapter text:
{text}
"""

# How much chapter text the timing detector sees. Very long chapters are shown as their
# opening and ending, where time shifts are usually signalled.
TIMING_TEXT_CHARS = 30000


def _timing_excerpt(text: str) -> str:
    if len(text) <= TIMING_TEXT_CHARS:
        return text
    half = TIMING_TEXT_CHARS // 2
    return f"{text[:half]}\n\n[... middle of the chapter left out ...]\n\n{text[-half:]}"


def detect_timing(text: str, earlier_notes: list[str] | None = None) -> str:
    """
    A short note such as "flashback: twelve years before the fire". earlier_notes are the
    earlier chapters' notes ("chapter 2: continues: the next morning"), so the detector can
    actually compare this chapter with the ones before it.
    """
    earlier = "\n".join(earlier_notes or []) or "(this is the first chapter)"
    answer = call_tool(TIMING_PROMPT.format(text=_timing_excerpt(text), earlier=earlier), TIMING_TOOL,
                       max_tokens=1024, thinking=JUDGING_THINKING_MODE)
    setting = str(answer.get("setting", "unclear")).strip().lower()
    description = " ".join(str(answer.get("description", "")).split())[:200]
    return f"{setting}: {description}" if description else setting

from pydantic import ValidationError
from models import Fact, ExtractionResult
import os
import re
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


def _words_in(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+|\d+", text.lower()))


def is_grounded(fact: dict, text: str) -> bool:
    """
    Is this fact really in the text? Two checks, no AI needed:
    - every day, month, number word or digit in the value appears in the text;
    - most of the quote's words appear in the text (the quote isn't invented).
    """
    text_words = _words_in(text)
    value_words = _words_in(str(fact.get("value", "")))
    for word in value_words:
        if (word in _CHECKED_WORDS or word.isdigit()) and word not in text_words:
            return False
    quote_words = [w for w in _words_in(str(fact.get("source_quote", ""))) if len(w) > 3]
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


def extract_facts(chapter_id: str, text: str) -> ExtractionResult:
    # The chapter is read in short passages, several at the same time, each with the
    # passage before it as context.
    passages = split_into_passages(text)
    jobs = [(passages[i - 1] if i > 0 else "", passage) for i, passage in enumerate(passages)]
    answers = run_in_parallel(
        lambda job: call_tool(
            EXTRACTION_PROMPT.format(
                text=job[1], context=CONTEXT_BLOCK.format(previous=job[0]) if job[0] else ""),
            EXTRACTION_TOOL, max_tokens=8192,   # room for a detail-rich passage; unused room costs nothing
        ),
        jobs,
    )
    raw_facts: list = []
    for (previous, passage), answer in zip(jobs, answers):
        # Drop facts whose day/number or quote isn't actually in this passage (or the
        # context shown with it): the AI invented them.
        source = f"{previous}\n{passage}"
        raw_facts.extend(f for f in answer.get("facts", [])
                         if isinstance(f, dict) and (not CHECK_GROUNDING or is_grounded(f, source)))
    return ExtractionResult(chapter_id=chapter_id, facts=_clean_facts(raw_facts))


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
chapters before it:
- continues: it follows on from the story so far
- flashback: it is set EARLIER than the chapters before it
- time skip: it jumps forward in time
- unclear: the text doesn't say

In "description", give the time relationship in a few words, using the chapter's own words
where possible, e.g. "twelve years before the fire" or "three years after the fire". If the
time changes part-way through the chapter, say so briefly.

Chapter text:
{text}
"""


def detect_timing(text: str) -> str:
    """A short note such as "flashback: twelve years before the fire"."""
    answer = call_tool(TIMING_PROMPT.format(text=text[:MAX_CHARS_PER_PIECE]), TIMING_TOOL,
                       max_tokens=1024, thinking=JUDGING_THINKING_MODE)
    setting = str(answer.get("setting", "unclear")).strip().lower()
    description = " ".join(str(answer.get("description", "")).split())[:200]
    return f"{setting}: {description}" if description else setting

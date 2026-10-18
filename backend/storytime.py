"""
Story time: WHEN each chapter is set, and age arithmetic, done in code (not by the AI).
Used by storyclock.py (ages) and contradictions.py (the timing block shown to the AI).

Every chapter gets a position on one story timeline, in years from the start of chapter 1.
A position is a RANGE [earliest, latest], because stories are vague ("some years later",
"three years after the fire" when we don't know exactly when the fire was). Ranges keep the
arithmetic honest: a warning is raised only when NO reading of the timing could make the
ages fit.

Where the timing comes from, most trusted first:
  1. The chapter's own OPENING words: "Two years later, ...", "Twelve years before the fire,
     ...", "The next morning ...". Novels nearly always signal a time shift in the first
     sentence or two, and these words are the author's, not a summary.
  2. The AI's timing note for the chapter ("time skip: three years after the fire").
     Only used when the opening has no time phrase.

Anchors. "Three years after the fire" needs to know when the fire was. In order:
  - the earliest earlier (non-flashback) chapter whose FIRST SENTENCE mentions it
    ("The fire began just after midnight." -> the fire is when that chapter is set);
  - an earlier timing phrase that placed it ("three days before the storm" in chapter 2
    puts the storm three days after chapter 2);
  - otherwise it is unknown, and the range is widened instead of guessed.

"Later" is measured from the last MAIN-LINE chapter: after a flashback, "four months later"
continues the main story, not the flashback.

Ages. "fourteen in chapter 3" at story time t means the character was born between
t - 15 and t - 14. Every age stated for a character gives such a birth range; if a new
age's birth range can't overlap the earlier ones, that's a mistake. Ages stated for a past
moment ("taught him when he was seven", "until Tam is twenty-five", "at seventeen") are not
the character's current age and are ignored.

The old clock added up every chapter's note as a step forward, so three chapters each
"two years after the council" counted as six years, and "fourteen years before the fall"
counted as fourteen years FORWARD. Ranges with anchors fix both.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from models import Contradiction, Fact
from extract import normalise_numbers

INF = math.inf
SLACK_YEARS = 0.25          # extra room for loosely stated ages ("fifty-two that spring")
CONTINUES_YEARS = 0.25      # "continues" is usually hours or days later; allow up to a season


@dataclass(frozen=True)
class Span:
    """A position on the story timeline, in years since chapter 1 (lo <= hi; hi may be infinite)."""
    lo: float
    hi: float

    def shift(self, lo: float, hi: float | None = None) -> "Span":
        return Span(self.lo + lo, self.hi + (lo if hi is None else hi))

    @property
    def exact(self) -> bool:
        return self.hi - self.lo < 1 / 52


@dataclass
class ChapterTime:
    span: Span | None          # None = unknown (e.g. a flashback of unknown length)
    flashback: bool
    source: str                # "first chapter", "opening", "timing note", "unknown"
    phrase: str = ""           # the words the position came from


# ------------------------------------------------------------------ phrases --
_UNIT_YEARS = {
    "decade": 10.0, "year": 1.0, "yr": 1.0, "summer": 1.0, "winter": 1.0, "spring": 1.0,
    "autumn": 1.0, "harvest": 1.0, "season": 0.25, "month": 1 / 12, "moon": 1 / 12,
    "fortnight": 2 / 52, "week": 1 / 52, "day": 1 / 365, "night": 1 / 365, "morning": 1 / 365,
    "evening": 1 / 365, "afternoon": 1 / 365, "hour": 1 / 8760,
}
_UNIT = r"(decade|year|yr|summer|winter|spring|autumn|harvest|season|month|moon|fortnight|week|day|night|morning|evening|afternoon|hour)s?"
_AMOUNT = r"(\d+(?:\.\d+)?|half an?|an?|a few|a couple of|a couple|several|some|many)"
_AMOUNTS = {"a": (1, 1), "an": (1, 1), "half a": (0.5, 0.5), "half an": (0.5, 0.5), "a few": (2, 5),
            "a couple of": (2, 3), "a couple": (2, 3), "several": (3, 7), "some": (1, 10), "many": (5, 30)}
_LATER = r"(later|afterwards?|after that|on(?=\s*[,.;:!?]|\s*$)|passed|went by|had passed)"
_AFTER = r"(after|since)"
_BEFORE = r"(before|earlier than|prior to)"
_ORDINAL_WORDS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh",
                  8: "eighth", 9: "ninth", 10: "tenth"}
# An event's name ends at punctuation, a new clause or a preposition: "the storm on Friday" -> "the storm".
_ANCHOR_END = re.compile(r"[,.;:!?()\[\]/]|\s(?:and|which|when|while|where|who|but|as|so|on|in|at|of|into|with|by|"
                         r"from|for|that|than|to|during|shortly|soon|after|before)\s")
# Anchors that are whole clauses ("after Rook went into hiding") can't be found by a keyword.
_CLAUSE_VERB = re.compile(r"\s(went|was|were|is|are|had|has|left|came|arrived|died|became|took|fled|joined|married|"
                          r"returned|began|started|ended|met|found|lost|got|did)\s")
_STOP = {"the", "a", "an", "that", "this", "those", "these", "his", "her", "their", "its", "our", "my", "your",
         "of", "in", "on", "at", "to", "into", "from", "with", "by", "for", "was", "were", "had", "has",
         "went", "set", "story", "earlier", "previous", "chapters", "chapter", "events", "event",
         "first", "last", "same", "time", "times", "day", "night", "morning", "evening", "year", "years"}


@dataclass
class Clause:
    """One time phrase: amount (years range), direction and what it is measured from."""
    lo: float
    hi: float
    direction: str            # "after" (forward) or "before" (backward)
    anchor: str               # "previous", "chapter:<n>", or event words such as "fire"
    text: str


def _amount(text: str) -> tuple[float, float]:
    text = text.strip().lower()
    if text in _AMOUNTS:
        return _AMOUNTS[text]
    value = float(text)
    return value, value


def _unit_years(unit: str) -> float:
    return _UNIT_YEARS[unit.lower().rstrip("s") if unit.lower().rstrip("s") in _UNIT_YEARS else unit.lower()]


_CHAPTER_REF = re.compile(r"\bchapter\s+(\d+)\b")
_PREVIOUS_REF = re.compile(r"\b(the )?(previous|preceding|last|earlier) (chapter|chapters|scene)s?\b")
_FIRST_REF = re.compile(r"\bthe (first|opening) chapter\b")


def _anchor_phrase(rest: str) -> str:
    """The words naming what a time phrase is measured from: 'the fire, which ...' -> 'the fire'."""
    end = _ANCHOR_END.search(" " + rest + " ")
    return ((" " + rest + " ")[:end.start()] if end else rest).strip()


def _anchor_of(rest: str) -> str:
    """'the fire, which ...' -> 'fire'; 'chapter 6' -> 'chapter:6'; 'the previous chapter' -> 'previous'."""
    phrase = _anchor_phrase(rest.strip())
    if m := _CHAPTER_REF.match(phrase):
        return f"chapter:{m.group(1)}"
    if _PREVIOUS_REF.match(phrase) or phrase in ("that", "this", "it", "then", ""):
        return "previous"
    if _FIRST_REF.match(phrase):
        return "chapter:1"
    if _CLAUSE_VERB.search(f" {phrase} "):
        return "event:unplaceable"      # "Rook went into hiding": an event told as a sentence, not a name
    words = [w for w in _words_in_order(phrase)]
    return " ".join(words) if words else "previous"


def _words_in_order(phrase: str) -> list[str]:
    words = re.findall(r"[a-z]+", phrase.lower())
    return [w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words if w not in _STOP and len(w) >= 3]


def anchor_words(phrase: str) -> set[str]:
    return set(_words_in_order(phrase))


def _head(anchor: str) -> str:
    """The word an event is known by: the last word of its name ("fleet disaster" -> "disaster")."""
    return anchor.split()[-1]


def _ordinal_number(word: str) -> int | None:
    for n, w in _ORDINAL_WORDS.items():
        if word == w:
            return n
    return None


def find_clauses(text: str) -> list[Clause]:
    """
    Every time phrase in a short text, in order. Handles:
      "two years later", "a week later", "three years after the fire", "twelve years before the
      fire", "the next morning", "the morning after the storm", "on the night of the storm",
      "in the spring of the second year after Greywater", "four months after Chapter Six",
      "continues immediately after Chapter Seven", "shortly after ...".
    """
    raw = text or ""
    # Number words -> digits, but keep ordinals ("second year") as words for the ordinal rule.
    for n, w in _ORDINAL_WORDS.items():
        raw = re.sub(rf"\b{w}\b", f"@{n}@", raw, flags=re.I)
    t = normalise_numbers(raw)
    t = re.sub(r"@(\d+)@", lambda m: _ORDINAL_WORDS[int(m.group(1))], t)
    t = re.sub(r"\bchapter (one|two|three|four|five|six|seven|eight|nine|ten)\b",
               lambda m: f"chapter {normalise_numbers(m.group(1))}", t)
    found: list[tuple[int, Clause]] = []

    def add(match, lo, hi, direction, anchor, rest_group=None):
        text = match.group(0)
        if rest_group is not None:
            text = t[match.start():match.start(rest_group)] + _anchor_phrase(match.group(rest_group))
        found.append((match.start(), Clause(lo, hi, direction, anchor, text.strip())))

    # "in the spring of the second year after Greywater", "the third year after the war"
    for m in re.finditer(rf"\bthe (first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth) year {_AFTER} (.+)", t):
        n = _ordinal_number(m.group(1))
        add(m, n - 1, n, "after", _anchor_of(m.group(3)), 3)
    # "three years after the fire", "twelve years before the fire", "four months after chapter 6"
    for m in re.finditer(rf"\b{_AMOUNT} {_UNIT} (?:and \w+ )?{_AFTER} (.+)", t):
        lo, hi = _amount(m.group(1))
        y = _unit_years(m.group(2))
        add(m, lo * y, hi * y, "after", _anchor_of(m.group(4)), 4)
    for m in re.finditer(rf"\b{_AMOUNT} {_UNIT} (?:and \w+ )?{_BEFORE} (.+)", t):
        lo, hi = _amount(m.group(1))
        y = _unit_years(m.group(2))
        add(m, lo * y, hi * y, "before", _anchor_of(m.group(4)), 4)
    # "two years later", "a week later", "three years on", "twenty years had passed"
    for m in re.finditer(rf"\b{_AMOUNT} {_UNIT} {_LATER}\b", t):
        lo, hi = _amount(m.group(1))
        y = _unit_years(m.group(2))
        add(m, lo * y, hi * y, "after", "previous")
    # "three years earlier"
    for m in re.finditer(rf"\b{_AMOUNT} {_UNIT} (earlier|before that)\b", t):
        lo, hi = _amount(m.group(1))
        y = _unit_years(m.group(2))
        add(m, lo * y, hi * y, "before", "previous")
    # "the next morning", "the following spring"
    for m in re.finditer(rf"\bthe (next|following) {_UNIT}\b", t):
        y = _unit_years(m.group(2))
        add(m, y if y < 0.25 else 0.0, y, "after", "previous")
    # "the morning after the storm", "the day after the funeral", "the week after ..."
    for m in re.finditer(rf"\bthe {_UNIT} (after|before) (.+)", t):
        y = _unit_years(m.group(1))
        add(m, y if y < 0.25 else 0.0, y, "after" if m.group(2) == "after" else "before", _anchor_of(m.group(3)), 3)
    # "on the night of the storm", "the eve of the festival", "the day of the fire"
    for m in re.finditer(rf"\b(?:on )?the (night|day|morning|evening|eve|afternoon) of (.+)", t):
        add(m, 0.0, 1 / 365, "after", _anchor_of(m.group(2)), 2)
    # "shortly after the fire", "soon after", "immediately after chapter 7", "just before ..."
    for m in re.finditer(r"\b(shortly|soon|immediately|just|right|directly) (after|before) (.+)", t):
        add(m, 0.0, 1 / 52 if m.group(1) in ("immediately", "just", "right", "directly") else 0.1,
            "after" if m.group(2) == "after" else "before", _anchor_of(m.group(3)), 3)
    # "that night", "later that day", "the same day"
    for m in re.finditer(r"\b(that same|that|later that|the same) (night|evening|morning|day|afternoon)\b", t):
        add(m, 0.0, 1 / 365, "after", "previous")

    found.sort(key=lambda item: item[0])
    # Drop clauses that are part of a longer one found at the same place.
    clauses: list[Clause] = []
    last_end = -1
    for start, clause in found:
        if start < last_end:
            continue
        clauses.append(clause)
        last_end = start + len(clause.text)
    return clauses


def note_clauses(description: str) -> list[Clause]:
    """
    Time phrases in an AI timing note. Alternatives separated by "/" or ";" that give no amount
    take the amount of the one before: "two years after the council / after the abdication"
    also says the abdication was two years ago.
    """
    clauses: list[Clause] = []
    previous: Clause | None = None
    for part in re.split(r"\s*[/;]\s*|\s+or\s+", description or ""):
        found = find_clauses(part)
        if found:
            clauses.extend(found)
            previous = found[-1]
            continue
        bare = re.match(r"^(?:also\s+)?(after|before|since)\s+(.+)$", part.strip(), re.I)
        if bare and previous is not None and previous.anchor not in ("previous",):
            anchor = _anchor_of(bare.group(2).lower())
            if anchor != "previous" and not anchor.startswith("chapter:"):
                clauses.append(Clause(previous.lo, previous.hi, "before" if bare.group(1).lower() == "before" else "after",
                                      anchor, part.strip()))
    return clauses


def opening_of(text: str, sentences: int = 2, max_chars: int = 400) -> str:
    """The first sentence or two of a chapter, after any 'Chapter Four: The Ferryman' heading."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if lines and re.match(r"^(chapter|part|book|prologue|epilogue)\b", lines[0], re.I) and len(lines[0]) < 80:
        lines = lines[1:]
    body = " ".join(lines)[: max_chars * 2]
    parts = re.split(r"(?<=[.!?])\s+", body)
    return " ".join(parts[:sentences])[:max_chars]


def first_sentence(text: str) -> str:
    return opening_of(text, sentences=1, max_chars=250)


def _split_note(note: str | None) -> tuple[str, str]:
    note = (note or "").strip()
    if ":" in note:
        setting, description = note.split(":", 1)
        setting = setting.strip().lower()
        if setting in ("continues", "flashback", "time skip", "unclear"):
            return setting, description.strip()
    lowered = note.lower()
    for setting in ("continues", "flashback", "time skip", "unclear"):
        if lowered.startswith(setting):
            return setting, note[len(setting):].strip(" :")
    return "", note


# ---------------------------------------------------------------- timeline --
def chapter_positions(chapters: list[dict]) -> dict[int, ChapterTime]:
    """
    chapters: [{"chapter_number", "time_note", "opening"}...] in any order ("opening" may be
    missing or empty: then only the timing note is used). Returns {chapter_number: ChapterTime}.
    """
    rows = sorted(chapters, key=lambda c: c["chapter_number"])
    positions: dict[int, ChapterTime] = {}
    anchors: list[tuple[str, Span]] = []                # (event word, position) from earlier time phrases
    main: Span | None = None                           # the last main-line chapter's position

    def chapter_span(ref: str) -> Span | None:
        number = int(ref.split(":")[1])
        known = positions.get(number)
        return known.span if known else None

    def event_span(anchor: str, before_number: int) -> Span | None:
        if anchor == "event:unplaceable":
            return None
        head = _head(anchor)
        # 1. The earliest earlier main-line chapter whose first sentence mentions it.
        for row in rows:
            n = row["chapter_number"]
            if n >= before_number or n not in positions:
                continue
            p = positions[n]
            if p.flashback or p.span is None:
                continue
            sentence = first_sentence(row.get("opening") or "")
            # mentioned outside a time phrase ("Twelve years before the fire" doesn't place the fire)
            for clause in find_clauses(sentence):
                sentence = sentence.lower().replace(clause.text, " ")
            if head in anchor_words(sentence):
                return p.span
        # 2. Placed by an earlier time phrase.
        for known_head, span in reversed(anchors):
            if head == known_head:
                return span
        return None

    def place(clause: Clause, setting: str, number: int) -> tuple[Span | None, bool, bool]:
        """(span, flashback?, resolved?) for one clause. resolved = the anchor was known."""
        if clause.anchor == "previous":
            base, resolved = main, main is not None
        elif clause.anchor.startswith("chapter:"):
            base = chapter_span(clause.anchor)
            resolved = base is not None
        else:
            base = event_span(clause.anchor, number)
            resolved = base is not None
        if base is not None:
            if clause.direction == "after":
                span = Span(base.lo + clause.lo, base.hi + clause.hi)
            else:
                span = Span(base.lo - clause.hi, base.hi - clause.lo)
            if setting == "continues" and clause.direction == "before" and main is not None and clause.anchor != "previous":
                # "continues: three days before the storm": the chapter continues; the clause
                # only says the storm is still to come.
                return main.shift(0, CONTINUES_YEARS), False, True
            flashback = setting == "flashback" or (main is not None and span.hi < main.lo - 1 / 365)
            return span, flashback, resolved
        # The anchor is unknown: don't guess it.
        if main is None:
            return None, setting == "flashback", False
        if clause.direction == "before" and setting != "continues":
            return None, True, False                       # a flashback of unknown length
        if clause.direction == "before":
            return main.shift(0, CONTINUES_YEARS), False, False
        if setting == "continues":
            return main.shift(0, CONTINUES_YEARS), False, False
        # "N years after <something we can't place>": the something happened no later than the
        # previous chapter, and the story doesn't go backwards, so somewhere in [main, main + N].
        return Span(main.lo, main.lo + clause.hi), False, False

    def register(clauses: list[Clause], span: Span | None, number: int):
        """Remember where the events named in this chapter's time phrases are."""
        if span is None or math.isinf(span.hi):
            return
        for clause in clauses:
            if clause.anchor in ("previous",) or clause.anchor.startswith("chapter:"):
                continue
            if clause.anchor == "event:unplaceable" or event_span(clause.anchor, number) is not None:
                continue
            head = _head(clause.anchor)
            if clause.direction == "after":
                anchors.append((head, Span(span.lo - clause.hi, span.hi - clause.lo)))
            else:
                anchors.append((head, Span(span.lo + clause.lo, span.hi + clause.hi)))

    for index, row in enumerate(rows):
        number = row["chapter_number"]
        setting, description = _split_note(row.get("time_note"))
        opening_clauses = find_clauses(opening_of(row.get("opening") or ""))
        from_note = note_clauses(description)
        if index == 0:
            span = Span(0.0, 0.0)
            positions[number] = ChapterTime(span, False, "first chapter")
            register(opening_clauses + from_note, span, number)
            main = span
            continue

        result: ChapterTime | None = None
        if opening_clauses:
            clause = opening_clauses[0]
            span, flashback, _ = place(clause, "flashback" if clause.direction == "before" and clause.anchor != "previous" else "", number)
            result = ChapterTime(span, flashback, "opening", clause.text)
        note_used = False
        if result is None:
            for clause in from_note:
                span, flashback, resolved = place(clause, setting, number)
                if span is not None or flashback:
                    result = ChapterTime(span, flashback, "timing note", clause.text)
                    note_used = True
                    break
        if result is None:
            if setting == "continues" and main is not None:
                result = ChapterTime(main.shift(0, CONTINUES_YEARS), False, "timing note", "continues")
            elif setting == "flashback":
                result = ChapterTime(None, True, "timing note", "flashback")
            elif main is not None:
                # a time skip of unknown length, or unclear: later than the last main-line chapter
                result = ChapterTime(Span(main.lo, INF), False, "unknown", setting or "not recorded")
            else:
                result = ChapterTime(None, False, "unknown", setting or "not recorded")
        positions[number] = result
        # The AI's note is used to place other events only if it is the source of this
        # chapter's position, or it agrees with the chapter's own opening words.
        trusted = note_used or (result.span is not None and any(
            span is not None and resolved and _spans_meet(span, result.span)
            for span, _, resolved in (place(c, setting, number) for c in from_note)))
        register(opening_clauses + (from_note if trusted else []), result.span, number)
        if not result.flashback:
            main = result.span if result.span is not None else (Span(main.lo, INF) if main else None)
    return positions


def _spans_meet(a: Span, b: Span) -> bool:
    return max(a.lo, b.lo) <= min(a.hi, b.hi) + 1 / 52


def describe(position: ChapterTime | None) -> str:
    """'about 2 years after chapter 1 begins', for the timing block shown to the AI."""
    if position is None or position.span is None:
        return "not placed"
    lo, hi = position.span.lo, position.span.hi

    def amount(years: float) -> str:
        years = abs(years)
        if years >= 1:
            return f"{years:.1f}".rstrip("0").rstrip(".") + " years"
        if years >= 1 / 12:
            return f"{round(years * 12)} months"
        if years >= 1 / 52:
            return f"{round(years * 52)} weeks"
        return f"{round(years * 365)} days"

    if math.isinf(hi):
        return f"at least {amount(lo)} after chapter 1 begins" if lo > 0 else "some time after chapter 1 begins"
    middle = (lo + hi) / 2
    when = "after" if middle >= 0 else "before"
    if position.span.exact:
        return f"{amount(middle)} {when} chapter 1 begins" if abs(middle) >= 1 / 365 else "when chapter 1 begins"
    return f"between {amount(lo)} and {amount(hi)} {'after' if lo >= 0 else 'from'} chapter 1 begins" if lo >= 0 \
        else f"about {amount(middle)} {when} chapter 1 begins"


# -------------------------------------------------------------------- ages --
AGE_ATTRIBUTE = re.compile(r"(^|[_\s])(age|aged)($|[_\s])|years?[_\s]old", re.I)
# "age_when_taught", "age at coronation", "age_difference", "son_age", "age_hiding": not the
# character's own current age.
_NOT_CURRENT_ATTRIBUTE = re.compile(
    r"\b(when|at|until|till|difference|relative|than|hiding|son|daughter|child|children|father|mother|"
    r"wife|husband|brother|sister|death|died|coronation|marriage|married|event|then|ago|first|joined)\b", re.I)
_NOT_CURRENT_VALUE = re.compile(r"\b(younger|older|elder|when|until|till|before|after|ago|by the time|"
                                r"not stated|unknown|nearly|almost|about|around|over|under)\b", re.I)
# Words just before the number that make it an age at another moment.
_PAST_MOMENT = re.compile(
    r"(\bwhen (?:he|she|they|i|you|we|\w+) (?:was|were|turned)\s*$|\bat (?:the age of )?$|\buntil [\w ]{0,30}\b(?:is|was|turns) $|"
    r"\bby $|\bsince (?:he|she|they|i|you) (?:was|were) $|\bbefore (?:he|she|they|i|you) (?:was|were|turned) $)", re.I)


def parse_age(attribute: str, value: str) -> int | None:
    """The age in a fact like "age | twelve years old" -> 12. None if it isn't a current age."""
    attribute, value = attribute or "", value or ""
    if not AGE_ATTRIBUTE.search(attribute):
        return None
    if _NOT_CURRENT_ATTRIBUTE.search(attribute.replace("_", " ")):
        return None
    if _NOT_CURRENT_VALUE.search(value):
        return None
    match = re.search(r"\b(\d{1,3})\b", normalise_numbers(value))
    if not match:
        return None
    age = int(match.group(1))
    return age if 0 <= age <= 150 else None


_OTHER_PERSON = re.compile(r"\b(son|sons|daughter|daughters|child|children|kid|baby|father|mother|parent|brother|"
                           r"sister|sibling|wife|husband|spouse|grandson|granddaughter|grandchild|nephew|niece|"
                           r"cousin|friend|horse|dog)\b", re.I)
_NOT_NOW = re.compile(r"\buntil\b|\bwill (be|turn)\b|\bwould (be|turn|have been)\b|\bwhen \w+ (is|turns)\b|"
                      r"\bby the time\b|\bif \w+ (were|was|is)\b", re.I)
# A figure of speech right before the number: "you look 12", "I feel about 100", "like a 5-year-old".
_FIGURATIVE = re.compile(r"\b(look|looks|looked|looking|feel|feels|felt|feeling|seem|seems|seemed|act|acts|acted|acting|"
                         r"behav\w+|sound\w*|pass(?:es|ed)? for)\b(?:\s+(?:about|like|maybe|nearly|almost|barely|"
                         r"at least|at most|older than|younger than|a good|every day of|a|an))*\s*$|"
                         r"\blike an?\s*$|\bgoing on\s*$", re.I)


def current_age(attribute: str, value: str, quote: str = "") -> int | None:
    """
    The character's age at the time of this chapter, or None. Also checks the quote, so that
    "taught Aurel to hold a blade when he was seven" or "until Tam is twenty-five" don't count.
    """
    age = parse_age(attribute, value)
    if age is not None and _OTHER_PERSON.search((attribute or "").replace("_", " ")):
        return None                      # "son_age | eight": someone else's age, filed here
    if age is not None and quote and _NOT_NOW.search(quote):
        return None                      # "the regency lasts until Tam is twenty-five"
    if age is None or not quote:
        return age
    text = normalise_numbers(quote)
    hits = [m for m in re.finditer(rf"\b{age}\b", text)]
    if not hits:
        return age                     # the quote doesn't show the number: trust the fact
    if all(_PAST_MOMENT.search(text[max(0, m.start() - 40):m.start()]) or
           _FIGURATIVE.search(text[max(0, m.start() - 40):m.start()]) for m in hits):
        return None
    return age


def birth_span(age: int, span: Span) -> Span:
    """Someone aged `age` somewhere in `span` was born in this range (lo exclusive)."""
    return Span(span.lo - age - 1, span.hi - age)


def _overlap(a: Span, b: Span) -> bool:
    return max(a.lo, b.lo) < min(a.hi, b.hi) + SLACK_YEARS


def _expected(old_age: int, old: Span, new: Span) -> tuple[float, float]:
    """The range of ages someone aged old_age at `old` can be at `new`."""
    return old_age + (new.lo - old.hi), old_age + 1 + (new.hi - old.lo) - 1e-9


def check_ages(
    chapter_id: str,
    chapter_number: int,
    new_facts: list[tuple[int, str, Fact, int]],
    earlier_facts_for: callable,
    time_notes: list[dict],
    this_time_note: str | None,
    this_opening: str | None = None,
) -> list[Contradiction]:
    """
    new_facts: [(entity_id, canonical name, fact, index of the fact in the chapter), ...]
    earlier_facts_for(entity_id) -> that entity's facts from EARLIER chapters (dicts with
      chapter_number, chapter_id, attribute, value, source_quote, fact_id).
    time_notes: every saved chapter's {chapter_number, time_note, opening (optional)}.
    this_time_note / this_opening: the chapter being checked (it may not be saved yet).
    """
    chapters = [dict(c) for c in time_notes if c["chapter_number"] != chapter_number]
    saved_self = next((c for c in time_notes if c["chapter_number"] == chapter_number), None)
    chapters.append({"chapter_number": chapter_number, "time_note": this_time_note,
                     "opening": this_opening if this_opening is not None else (saved_self or {}).get("opening")})
    positions = chapter_positions(chapters)
    here = positions.get(chapter_number)
    if here is None or here.span is None:
        return []                       # e.g. a flashback of unknown length: nothing to compare
    found: list[Contradiction] = []
    flagged_entities: set[int] = set()
    for entity_id, canonical, fact, index in new_facts:
        new_age = current_age(fact.attribute, fact.value, fact.source_quote)
        if new_age is None or entity_id in flagged_entities:
            continue
        new_birth = birth_span(new_age, here.span)
        earlier = []
        for f in earlier_facts_for(entity_id):
            age = current_age(f["attribute"], f["value"], f.get("source_quote") or "")
            where = positions.get(f["chapter_number"])
            if age is None or where is None or where.span is None:
                continue
            earlier.append((f, age, where))
        if not earlier:
            continue
        # The entity's birth range from everything earlier that agrees with itself.
        established: Span | None = None
        for _, age, where in earlier:
            b = birth_span(age, where.span)
            if established is None:
                established = b
            elif _overlap(established, b):
                established = Span(max(established.lo, b.lo), min(established.hi, b.hi))
        if established is None or _overlap(established, new_birth):
            continue
        clashing = [(f, age, where) for f, age, where in earlier
                    if not _overlap(birth_span(age, where.span), new_birth)]
        old_fact, old_age, old_where = (clashing or earlier)[-1]       # the closest earlier chapter
        # The age the timing points to: the old age plus the shortest / longest time that can
        # have passed (whole years, as people say them; the check above already allowed for birthdays).
        o, n = old_where.span, here.span
        low = max(0, math.floor(old_age + n.lo - o.hi + 1e-9))
        if math.isinf(n.hi):
            expectation = f"at least about {low}"
        else:
            high = math.floor(old_age + n.hi - o.lo + 1e-9)
            if high == low:
                expectation = f"about {low}"
            elif new_age > high:
                expectation = f"at most about {high}"
            else:
                expectation = f"at least about {low}"
        exact = here.source in ("opening", "first chapter") and old_where.source in ("opening", "first chapter")
        gap = (f"chapter {old_fact['chapter_number']} is set {describe(old_where)} and chapter "
               f"{chapter_number} {describe(here)}")
        if here.span.hi - old_where.span.lo < 1:
            gap += ", so less than a year passes in between"
        found.append(Contradiction(
            entity=canonical,
            new_chapter_id=chapter_id,
            new_attribute=fact.attribute,
            new_value=fact.value,
            new_quote=fact.source_quote,
            conflicting_chapter_id=old_fact["chapter_id"],
            conflicting_value=old_fact["value"],
            conflicting_quote=old_fact["source_quote"],
            contradiction_type="timeline",
            confidence=0.9 if exact else 0.8,
            explanation=(f"{canonical} is {old_age} in chapter {old_fact['chapter_number']}, and {gap}, so "
                         f"{canonical} should be {expectation} in chapter {chapter_number}, but the text says {new_age}."),
            source="story clock",
            new_fact_index=index,
            conflicting_fact_id=old_fact.get("fact_id"),
        ))
        flagged_entities.add(entity_id)
    return found


def timeline_lines(time_notes: list[dict], chapter_number: int | None = None,
                   this_time_note: str | None = None, this_opening: str | None = None) -> dict[int, str]:
    """{chapter_number: 'about 2 years after chapter 1 begins'} for showing next to the timing notes."""
    chapters = [dict(c) for c in time_notes if c["chapter_number"] != chapter_number]
    if chapter_number is not None:
        saved_self = next((c for c in time_notes if c["chapter_number"] == chapter_number), None)
        chapters.append({"chapter_number": chapter_number, "time_note": this_time_note,
                         "opening": this_opening if this_opening is not None else (saved_self or {}).get("opening")})
    positions = chapter_positions(chapters)
    return {n: ("flashback, " if p.flashback else "") + describe(p) for n, p in positions.items()}

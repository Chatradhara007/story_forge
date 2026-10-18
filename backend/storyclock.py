"""
The story clock: age arithmetic checked in code, not by the AI.

The AI checker reliably catches "dead, then alive", but it misses anything that needs
arithmetic (the evaluation caught "Rook's age after a three-year skip" 0 times out of 3).
Here ages are read as numbers and time skips are read from the chapter timing notes
("time skip: three years after the fire"), and the sums are done in Python:

    age in the earlier chapter + years that pass in between  ≈  age in the new chapter

Anything off by more than a year is flagged. When the timing between the two chapters
isn't known (a flashback in between, an "unclear" note), only an age going DOWN outside
a flashback is flagged, and with lower confidence.

Two more checks that need no AI:
  - one event on two different weekdays ("the storm broke on Tuesday night" / "the storm on
    Friday"); only for events, because markets and habits recur;
  - acting after death ("Bramble died" / "Bramble barked at the gulls"), except memories and
    flashbacks.
"""
import re
from models import Contradiction, Fact
from extract import normalise_numbers
import storytime

AGE_ATTRIBUTE = re.compile(r"(^|[_\s])(age|aged)($|[_\s])|years?[_\s]old", re.I)
TOLERANCE_YEARS = 1.0

_UNIT_YEARS = {"year": 1.0, "yr": 1.0, "decade": 10.0, "month": 1 / 12, "week": 1 / 52, "day": 1 / 365}


_OTHER_PERSON = re.compile(r"\b(son|sons|daughter|daughters|child|children|kid|baby|father|mother|parent|brother|"
                           r"sister|sibling|wife|husband|spouse|grandson|granddaughter|grandchild|nephew|niece|"
                           r"cousin|friend|horse|dog)\b", re.I)
# "until Tam is twenty-five", "she will be forty", "when he turns ten": a future age, not his age now.
_NOT_NOW = re.compile(r"\buntil\b|\bwill (be|turn)\b|\bwould (be|turn|have been)\b|\bwhen \w+ (is|turns)\b|"
                      r"\bby the time\b|\bif \w+ (were|was|is)\b", re.I)


def parse_age(attribute: str, value: str, quote: str = "") -> int | None:
    """The age in a fact like "age | twelve years old" -> 12. None if it isn't an age."""
    if not AGE_ATTRIBUTE.search(attribute or ""):
        return None
    # "son_age | eight years old": someone else's age, filed under this character.
    if _OTHER_PERSON.search((attribute or "").replace("_", " ")):
        return None
    if quote and _NOT_NOW.search(quote):
        return None
    # "two years younger than Aurel", "age at coronation", "nineteen when crowned": relative or
    # past ages are not the character's age NOW.
    if re.search(r"\b(younger|older|than|ago|after|before|when|at|since|until|by the time)\b", value or "", re.I) \
            or re.search(r"\b(at|when|relative|difference|gap)\b", (attribute or "").replace("_", " "), re.I):
        return None
    match = re.search(r"\b(\d{1,3})\b", normalise_numbers(value or ""))
    if not match:
        return None
    age = int(match.group(1))
    return age if 0 <= age <= 150 else None


def years_passed(time_note: str | None) -> float | None:
    """
    How many years a chapter moves the story on, from its timing note.
    "continues: the next morning" -> 0; "time skip: three years after the fire" -> 3;
    a flashback or an unclear note -> None (unknown).
    """
    note = (time_note or "").strip().lower()
    if not note or note.startswith(("flashback", "unclear")):
        return None
    if note.startswith("continues"):
        return 0.0
    if note.startswith("time skip"):
        text = normalise_numbers(note)
        match = re.search(r"(\d+(?:\.\d+)?|an?|half a|a few|few|several|a couple of|couple of)\s*"
                          r"(decade|year|yr|month|week|day)s?", text)
        if not match:
            # "still that autumn", "later that year": the same year
            return 0.25 if re.search(r"\b(same|that|this) (year|spring|summer|autumn|fall|winter|season)\b|"
                                     r"\bstill (that|the same)\b", text) else None
        amount = {"a": 1.0, "an": 1.0, "half a": 0.5, "a few": 3.0, "few": 3.0, "several": 4.0,
                  "a couple of": 2.0, "couple of": 2.0}.get(match.group(1))
        amount = amount if amount is not None else float(match.group(1))
        return amount * _UNIT_YEARS[match.group(2)]
    return None


def is_flashback(note: str | None) -> bool:
    """A flashback note, or a "time skip" that is really one ("fourteen years before the fall")."""
    note = (note or "").strip().lower()
    return note.startswith("flashback") or bool(
        re.search(r"\b(years?|months?|weeks?|days?|decades?) (before|earlier)\b", note))


def _elapsed(notes_by_number: dict[int, str | None], from_number: int, to_number: int) -> tuple[float | None, bool]:
    """
    Years passing on the MAIN timeline after chapter from_number up to chapter to_number.
    Flashback chapters in between are interludes: they don't move the main timeline (the
    chapter after a flashback is read relative to the story before it). A chapter whose note
    repeats the previous one word for word and is anchored to an event ("time skip: two years
    after the abdication" twice) is the same moment, not another skip; "two years later" twice
    is four years.
    Returns (years or None if unknown, whether either END is a flashback).
    """
    total = 0.0
    previous = (notes_by_number.get(from_number) or "").strip().lower()
    for number in sorted(n for n in notes_by_number if from_number < n <= to_number):
        note = (notes_by_number[number] or "").strip().lower()
        if is_flashback(note):
            continue
        # "two years after the abdication" twice = the same moment; "two years later" twice = four years
        anchored = bool(re.search(r"\b(after|since)\b", note)) and not re.search(r"\blater\b", note)
        step = 0.0 if note and note == previous and anchored else years_passed(note)
        if step is None:
            return None, False
        total += step
        previous = note
    ends = (notes_by_number.get(from_number), notes_by_number.get(to_number))
    return total, any(is_flashback(n) for n in ends)


def check_ages_by_notes(
    chapter_id: str,
    chapter_number: int,
    new_facts: list[tuple[int, str, Fact, int]],
    earlier_facts_for: callable,
    time_notes: list[dict],
    this_time_note: str | None,
) -> list[Contradiction]:
    """
    new_facts: [(entity_id, canonical name, fact, index of the fact in the chapter), ...]
    earlier_facts_for(entity_id) -> that entity's facts from EARLIER chapters.
    time_notes: every saved chapter's {chapter_number, time_note}.
    """
    notes = {c["chapter_number"]: c["time_note"] for c in time_notes if c["chapter_number"] != chapter_number}
    notes[chapter_number] = this_time_note
    found: list[Contradiction] = []
    flagged_entities: set[int] = set()
    for entity_id, canonical, fact, index in new_facts:
        new_age = parse_age(fact.attribute, fact.value, fact.source_quote)
        if new_age is None or entity_id in flagged_entities:
            continue
        if is_flashback(this_time_note):
            continue                       # going back in time: anything younger is expected
        # Compare with the most recent earlier age on the main timeline (ages stated inside a
        # flashback belong to another time).
        earlier = [(f, parse_age(f["attribute"], f["value"], f.get("source_quote", ""))) for f in earlier_facts_for(entity_id)]
        earlier = [(f, age) for f, age in earlier if age is not None and not is_flashback(notes.get(f["chapter_number"]))]
        if not earlier:
            continue
        # A history that goes DOWN (31, 33, then 8) holds a misread age (someone else's "my son
        # is eight" filed under him): compare with the last age that fits the ones before it.
        consistent = []
        for f, age in earlier:
            if not consistent or age >= consistent[-1][1]:
                consistent.append((f, age))
        old_fact, old_age = consistent[-1]
        years, flashback = _elapsed(notes, old_fact["chapter_number"], chapter_number)
        explicit_skip = any(years_passed(notes.get(n)) not in (None, 0.0)
                            for n in notes if old_fact["chapter_number"] < n <= chapter_number)
        if flashback:
            continue                       # going back in time: younger is expected
        if years is None:
            if new_age >= old_age:
                continue                   # unknown gap: growing older is always possible
            confidence = 0.75
            explanation = (f"{canonical} is {old_age} in chapter {old_fact['chapter_number']} but {new_age} "
                           f"in chapter {chapter_number}: younger, and no flashback is recorded in between.")
        else:
            expected = old_age + years
            if abs(new_age - expected) <= TOLERANCE_YEARS:
                continue
            if new_age > expected and not explicit_skip:
                continue                   # older with only "continues" notes: time may have passed unrecorded
            confidence = 0.9
            gap = ("no time skip is recorded in between" if years == 0
                   else "less than a year passes in between, according to the chapter timing notes" if years < 1
                   else f"the chapter timing notes say about {years:g} year{'s' if years != 1 else ''} pass in between")
            expected = round(expected) if years < 1 else expected
            explanation = (f"{canonical} is {old_age} in chapter {old_fact['chapter_number']} and {gap}, so "
                           f"{canonical} should be about {expected:g} in chapter {chapter_number}, "
                           f"but the text says {new_age}.")
        flagged_entities.add(entity_id)
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
            confidence=confidence,
            explanation=explanation,
            source="story clock",
            new_fact_index=index,
            conflicting_fact_id=old_fact["fact_id"],
        ))
    return found


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
    Ages checked against WHEN each chapter is set (storytime.py): chapters are placed on one
    timeline, as ranges, from their opening words and timing notes, measured from the events
    they name ("three years after the fire" = three years after the chapter where the fire is),
    and a new age is flagged only if no reading of the timing makes it fit.
    Replaced check_ages_by_notes (kept above for reference) on 16 Oct 2026: on the saved readings
    of all three test stories it catches the same age mistakes and more (glassmaker T2) without
    its one false alarm ("three years after the fire" in two chapters counted as six years).
    time_notes rows may carry "opening" (a chapter's first characters).
    """
    return storytime.check_ages(chapter_id, chapter_number, new_facts, earlier_facts_for,
                                time_notes, this_time_note, this_opening)


# ---------------------------------------------------------------------------
# One event, two weekdays
# ---------------------------------------------------------------------------
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_WEEKDAY = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")s?\b", re.I)


def weekday_of(fact: dict | Fact) -> str | None:
    value = fact["value"] if isinstance(fact, dict) else fact.value
    found = {m.lower().rstrip("s") for m in _WEEKDAY.findall(value or "")}
    return found.pop() if len(found) == 1 else None


def check_weekdays(chapter_id, chapter_number, new_facts, earlier_facts_for, this_time_note) -> list[Contradiction]:
    """An event (a storm, a wedding, a battle) happens on ONE day. Recurring things are skipped."""
    found, flagged = [], set()
    for entity_id, canonical, fact, index in new_facts:
        if fact.entity_type not in ("event", "other") or entity_id in flagged:
            continue
        day = weekday_of(fact)
        if day is None:
            continue
        for old in earlier_facts_for(entity_id):
            old_day = weekday_of(old)
            if old_day is None or old_day == day:
                continue
            flagged.add(entity_id)
            found.append(Contradiction(
                entity=canonical, new_chapter_id=chapter_id, new_attribute=fact.attribute,
                new_value=fact.value, new_quote=fact.source_quote,
                conflicting_chapter_id=old["chapter_id"], conflicting_value=old["value"],
                conflicting_quote=old["source_quote"], contradiction_type="timeline", confidence=0.85,
                explanation=(f"{canonical} happens on a {old_day.capitalize()} in chapter {old['chapter_number']} "
                             f"but on a {day.capitalize()} in chapter {chapter_number}: one event can't be on "
                             f"two different days."),
                source="story clock", new_fact_index=index, conflicting_fact_id=old["fact_id"]))
            break
    return found


# ---------------------------------------------------------------------------
# Acting after death
# ---------------------------------------------------------------------------
_DEATH_WORDS = r"(dead|died|dies|killed|drowned|buried|perished|deceased|slain|executed|murdered|passed away|lifeless)"
_DEATH_ATTRIBUTE = re.compile(r"(status|state|condition|fate|death|died|alive|life|health|outcome)", re.I)
_DEATH_VALUE = re.compile(r"\b" + _DEATH_WORDS + r"\b", re.I)
# "was killed", "died in the night", "drowned": the entity itself died, whatever the attribute
# ("buried Bramble", "killed a gull": the entity did it to something else, so it's not dead)
_PASSIVE_DEATH = re.compile(r"^(was|had been|is|has been|were|got) (killed|drowned|slain|executed|murdered|buried)\b|"
                            r"^(died|dies|perished|passed away)\b", re.I)
_ACTING_ATTRIBUTE = re.compile(r"(action|activit|behaviou?r|speech|said|says|movement|did|does|deed|conduct)", re.I)
_MEMORY = re.compile(r"\b(remember\w*|recall\w*|memor\w*|dream\w*|thought of|used to|once|grave|ghost|"
                     r"mourn\w*|miss(ed|es)?|portrait|picture|photograph|in the past|imagin\w*|pictured)\b", re.I)


_HEDGED = re.compile(r"\b(implied|implies|perhaps|maybe|probably|possibly|presumably|if|would|might|rumou?red|feared)\b", re.I)


def is_death(fact: dict | Fact) -> bool:
    attribute = fact["attribute"] if isinstance(fact, dict) else fact.attribute
    value = (fact["value"] if isinstance(fact, dict) else fact.value) or ""
    # A death is stated briefly ("dead", "drowned in the storm"). A long value that merely
    # contains "drowned" is usually about someone else ("your sons drowned because of me"),
    # and a hedged one ("deceased (implied)") isn't a statement.
    if len(value.split()) > 8 or _HEDGED.search(value):
        return False
    if _PASSIVE_DEATH.search(value.strip()):
        return True
    return bool(_DEATH_ATTRIBUTE.search(attribute or "") and _DEATH_VALUE.search(value))


# Backstory told in a later chapter: "When you were two years old, Oren marched on the coast".
_BACKSTORY = re.compile(r"\bwhen (?:he|she|you|i|they|we|\w+) (?:was|were)\b|\b(?:years?|months?) (?:ago|before|earlier)\b|"
                        r"\bhad (?:once |long ago |already )?\w+ed\b|\bin (?:his|her|their) (?:youth|day)\b", re.I)


_PRONOUN_START = re.compile(r"^\W*(he|she|it|they)\b", re.I)


def _names_in_quote(names: list[str], quote: str) -> bool:
    """The quote names the entity itself ("Bramble barked"), not only its men ("your father's army burned")."""
    quote = quote or ""
    if _PRONOUN_START.search(quote):
        return True
    for name in names:
        for word in re.findall(r"[A-Za-z']{3,}", name or ""):
            if re.search(r"\b" + re.escape(word) + r"\b(?!'s)", quote, re.I) and word.lower() not in (
                    "the", "king", "queen", "lord", "lady", "captain", "father", "mother", "old", "young"):
                return True
    return False


_ALIVE = re.compile(r"^\s*(alive|living|still alive|well|unharmed|safe|survived|back|returned)\b", re.I)
_PASSIVE_VERB = re.compile(r"^(buried|killed|mourned|found|carried|remembered|missed|named|called|born|loved|"
                           r"hated|feared|shot|stabbed|wounded|drowned|died|murdered|executed|hanged|cremated)$", re.I)


def _verb_attribute(fact: Fact, names: list[str]) -> bool:
    """'Walter Alcott | waved | hand' with 'Walter Alcott raised a hand and waved': he does it himself."""
    attribute = (fact.attribute or "").strip().replace("_", " ")
    verb = attribute.split()[0] if attribute.split() else ""
    if not re.fullmatch(r"[a-z]{3,}ed", verb.lower()) or _PASSIVE_VERB.match(verb):
        return False
    # "Walter Alcott's daughter collected his glasses": the daughter does it, not Walter.
    quote = re.sub(r"\b[A-Z][\w-]*(?:\s+[A-Z][\w-]*)*'s\s+\w+", " someone ", fact.source_quote or "")
    for name in names:
        for word in re.findall(r"[A-Za-z']{3,}", name or ""):
            if re.search(rf"\b{re.escape(word)}\b[^.;]{{0,60}}\b{re.escape(verb)}\b", quote, re.I):
                return True
    return False


def is_acting(fact: Fact, names: list[str] | None = None) -> bool:
    alive = bool(re.search(r"status|state|condition", fact.attribute or "", re.I) and _ALIVE.search(fact.value or ""))
    acts = (bool(_ACTING_ATTRIBUTE.search(fact.attribute or "")) or alive
            or _verb_attribute(fact, names or [fact.entity]))
    return (acts and not _MEMORY.search(fact.value or "")
            and not _MEMORY.search(fact.source_quote or "") and not _DEATH_VALUE.search(fact.value or "")
            and not _BACKSTORY.search(fact.source_quote or "") and not _BACKSTORY.search(fact.value or "")
            and (names is None or alive or _names_in_quote(names, fact.source_quote)))


def check_after_death(chapter_id, chapter_number, new_facts, earlier_facts_for, this_time_note) -> list[Contradiction]:
    """Someone dead (or buried) in an earlier chapter acts again. Flashbacks are fine."""
    if is_flashback(this_time_note):
        return []
    found, flagged = [], set()
    for entity_id, canonical, fact, index in new_facts:
        if entity_id in flagged or not is_acting(fact, [fact.entity, canonical]):
            continue
        death = next((f for f in earlier_facts_for(entity_id) if is_death(f)), None)
        if death is None:
            continue
        flagged.add(entity_id)
        found.append(Contradiction(
            entity=canonical, new_chapter_id=chapter_id, new_attribute=fact.attribute,
            new_value=fact.value, new_quote=fact.source_quote,
            conflicting_chapter_id=death["chapter_id"], conflicting_value=death["value"],
            conflicting_quote=death["source_quote"], contradiction_type="status", confidence=0.9,
            explanation=(f"{canonical} is dead from chapter {death['chapter_number']} "
                         f"(\"{death['source_quote']}\"), but acts in chapter {chapter_number}: {fact.value}."),
            source="story clock", new_fact_index=index, conflicting_fact_id=death["fact_id"]))
    return found

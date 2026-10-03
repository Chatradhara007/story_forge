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
"""
import re
from models import Contradiction, Fact
from extract import normalise_numbers

AGE_ATTRIBUTE = re.compile(r"(^|[_\s])(age|aged)($|[_\s])|years?[_\s]old", re.I)
TOLERANCE_YEARS = 1.0

_UNIT_YEARS = {"year": 1.0, "yr": 1.0, "decade": 10.0, "month": 1 / 12, "week": 1 / 52, "day": 1 / 365}


def parse_age(attribute: str, value: str) -> int | None:
    """The age in a fact like "age | twelve years old" -> 12. None if it isn't an age."""
    if not AGE_ATTRIBUTE.search(attribute or ""):
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
        match = re.search(r"(\d+(?:\.\d+)?|an?|half a)\s*(decade|year|yr|month|week|day)s?", text)
        if not match:
            return None
        amount = {"a": 1.0, "an": 1.0, "half a": 0.5}.get(match.group(1))
        amount = amount if amount is not None else float(match.group(1))
        return amount * _UNIT_YEARS[match.group(2)]
    return None


def _elapsed(notes_by_number: dict[int, str | None], from_number: int, to_number: int) -> tuple[float | None, bool]:
    """
    Years passing after chapter from_number up to and including chapter to_number.
    Returns (years or None if unknown, whether a flashback is involved).
    """
    total = 0.0
    flashback = False
    for number in sorted(n for n in notes_by_number if from_number < n <= to_number):
        note = notes_by_number[number]
        if (note or "").lower().startswith("flashback"):
            flashback = True
        step = years_passed(note)
        if step is None:
            return None, flashback
        total += step
    if (notes_by_number.get(from_number) or "").lower().startswith("flashback"):
        flashback = True
    return total, flashback


def check_ages(
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
        new_age = parse_age(fact.attribute, fact.value)
        if new_age is None or entity_id in flagged_entities:
            continue
        # Compare with the most recent earlier age: it has the shortest gap to reason about.
        earlier = [(f, parse_age(f["attribute"], f["value"])) for f in earlier_facts_for(entity_id)]
        earlier = [(f, age) for f, age in earlier if age is not None]
        if not earlier:
            continue
        old_fact, old_age = earlier[-1]
        years, flashback = _elapsed(notes, old_fact["chapter_number"], chapter_number)
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
            confidence = 0.9
            gap = ("no time skip is recorded in between" if years == 0
                   else f"the chapter timing notes say about {years:g} year{'s' if years != 1 else ''} pass in between")
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

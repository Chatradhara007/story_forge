from collections import defaultdict
from models import Fact, Contradiction
from storage import (get_time_notes, get_facts_for_entity_id, get_facts_mentioning_entity, get_facts_mentioning_names,
                     get_similar_earlier_facts)
from llm import call_tool, run_in_parallel, JUDGING_THINKING_MODE, AIServiceError

VALID_TYPES = {"attribute", "status", "timeline"}

# Safety net: how many of the closest-in-meaning earlier facts to look at per new fact,
# and how many pairs to put in one AI call.
NEIGHBOURS_PER_FACT = 3
PAIRS_PER_CALL = 40
MIN_SAME_ENTITY_CONFIDENCE = 0.7

CONTRADICTION_TOOL = {
    "type": "function",
    "function": {
        "name": "report_contradictions",
        "description": "Report any contradictions found between new facts and existing established facts about the same entity.",
        "parameters": {
            "type": "object",
            "properties": {
                "contradictions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity_number": {"type": "integer"},
                            "new_fact_index": {"type": "integer"},
                            "existing_fact_index": {"type": "integer"},
                            "contradiction_type": {
                                "type": "string",
                                "enum": ["attribute", "status", "timeline"]
                            },
                            "confidence": {"type": "number"},
                            "explanation": {"type": "string"}
                        },
                        "required": ["entity_number", "new_fact_index", "existing_fact_index", "contradiction_type", "confidence", "explanation"]
                    }
                }
            },
            "required": ["contradictions"]
        }
    }
}

# How many entities are checked in one AI request. Checking several together makes far
# fewer requests (NVIDIA limits how many we may make); each entity stays in its own
# clearly separated section and is never compared with another.
CHECK_BATCH_SIZE = 4

RULES = """Compare them and flag genuine contradictions only. A contradiction is:
- ATTRIBUTE: a stated attribute (like eye color, age, name spelling, physical trait) changed
  without in-story explanation (e.g. injury, disguise, magic).
- STATUS: an entity is described in a state that conflicts with an established state
  (e.g. described as dead in one fact, alive and acting in another, with no resurrection
  explained; described as being in two different places at the same time).
  Using something that no longer exists or is out of reach also counts (e.g. using a hand that
  was lost, or an object that was destroyed or thrown away, with no explanation).
- TIMELINE: anything about WHEN something happened or HOW LONG something took that conflicts
  with the established timeline: a different day or date for the same event, a different
  order of events, a different duration, or an age that changes by more than the time that
  has plausibly passed between the chapters.

Do NOT flag:
- New information that simply adds detail without conflicting.
- Changes that move FORWARD in time. Stories change things: a living character can die, a
  healthy one can be hurt, someone can move house, change their mind, lose or gain an object.
  If the earlier chapter describes the "before" and the new chapter the "after", that is the
  story happening, not a mistake — even if the change isn't explained.
  Ages and durations are the exception: they may only grow by about as much time as has
  plausibly passed. A character who is ten and then twelve a few weeks or months later, or a
  job held "twenty years" and later "eight years", IS a contradiction.
- Facts that could both be true at different points in the story (e.g. someone's location
  changing over time), unless the timing makes it impossible.
- Vague or ambiguous phrasing that isn't a clear conflict.

Reading order is not always story order. Use the CHAPTER TIMING notes below. A flashback
describes an EARLIER time, so its facts (someone younger, still alive, not yet injured) do not
contradict later-time facts, unless they are about something that cannot change, such as
where someone was born. After a time skip, ages and durations should grow by the time
skipped: growing by clearly more or less than that IS a contradiction.

Direction matters. A change is only a contradiction when the NEW chapter goes against
something the story established as permanent or already finished, for example the dead
acting alive, a lost body part being used, a destroyed or thrown-away object being used,
or a past event being described differently.
"""

CONTRADICTION_PROMPT = """You are checking a work of long-form fiction for continuity errors.

Below are one or more ENTITIES (characters, places, objects or events). For each entity there
is a list of NEW facts just extracted from chapter {new_chapter_number}, and a list of EXISTING
facts already established about that same entity in other chapters. All the names listed for
an entity refer to it; treat facts under any of those names as facts about that entity. Some
existing facts are filed under a different entity but mention this one (e.g. "someone | threw |
this object into the sea"); use them as evidence about this entity too. Check each entity on
its own: never compare facts from one entity section with another. Chapter numbers show
reading order: a lower number happens earlier in the book.

{rules}
For each contradiction, give the entity_number of its section, the index of the NEW fact and
of the EXISTING fact within that section, and a confidence from 0.0 (unsure) to 1.0 (certain).

CHAPTER TIMING (when each chapter is set, from its own words):
{timing}

{sections}

Only report genuine contradictions. If there are none, return an empty list.
"""

SECTION = """ENTITY {number}: This entity is "{canonical_name}". All of these names refer to it: {aliases}.
NEW facts (index: entity | attribute | value | quote):
{new_facts}

EXISTING facts (index: entity | attribute | value | chapter number | quote):
{existing_facts}
"""


def _format_new_facts(facts: list[Fact]) -> str:
    return "\n".join(
        f'{i}: {f.entity} | {f.attribute} | {f.value} | "{f.source_quote}"'
        for i, f in enumerate(facts)
    )


def _format_existing_facts(facts: list[dict]) -> str:
    return "\n".join(
        f'{i}: {f["entity"]} | {f["attribute"]} | {f["value"]} | chapter {f["chapter_number"]} | "{f["source_quote"]}"'
        for i, f in enumerate(facts)
    )


def timing_text(project_id: int, chapter_id: str, chapter_number: int, time_note: str | None) -> str:
    """The CHAPTER TIMING block: saved chapters' notes plus the chapter being checked."""
    lines = [f"chapter {c['chapter_number']}: {c['time_note'] or 'not recorded'}"
             for c in get_time_notes(project_id) if c["chapter_id"] != chapter_id]
    lines.append(f"chapter {chapter_number} (the NEW chapter): {time_note or 'not recorded'}")
    return "\n".join(lines)


def _check_entities(
    new_chapter_id: str, new_chapter_number: int, batch: list[tuple[str, list[Fact], list[dict]]],
    timing: str = "not recorded",
) -> list[Contradiction]:
    """
    Compares each entity's new facts with its previously stored facts, for several entities
    in ONE request. batch: [(canonical name, new facts, existing facts), ...]
    """
    batch = [item for item in batch if item[2]]          # entities with no history: nothing to compare
    if not batch:
        return []
    sections = "\n".join(
        SECTION.format(
            number=number,
            canonical_name=canonical_name,
            aliases=", ".join(sorted({f.entity for f in new_facts} | {f["entity"] for f in existing})),
            new_facts=_format_new_facts(new_facts),
            existing_facts=_format_existing_facts(existing),
        )
        for number, (canonical_name, new_facts, existing) in enumerate(batch, start=1)
    )
    answer = call_tool(
        CONTRADICTION_PROMPT.format(new_chapter_number=new_chapter_number, rules=RULES,
                                    timing=timing, sections=sections),
        CONTRADICTION_TOOL,
        max_tokens=4096,
        thinking=JUDGING_THINKING_MODE,
    )

    results = []
    # One warning per new fact and per existing fact (in each entity), so the same mistake
    # isn't reported several times against slightly different wordings.
    used: set[tuple] = set()
    for item in answer.get("contradictions", []):
        # The AI refers to entities and facts by their numbers above. Check they exist
        # before using them: a made-up number must never crash the chapter.
        try:
            number = int(item.get("entity_number") or 1)
            new_index = int(item["new_fact_index"])
            existing_index = int(item["existing_fact_index"])
            kind = item["contradiction_type"]
            explanation = str(item["explanation"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 1 <= number <= len(batch):
            continue
        canonical_name, new_facts, existing_facts = batch[number - 1]
        if not (0 <= new_index < len(new_facts) and 0 <= existing_index < len(existing_facts)):
            continue
        if kind not in VALID_TYPES or (number, "old", existing_index) in used or (number, "new", new_index) in used:
            continue
        used.update({(number, "old", existing_index), (number, "new", new_index)})
        try:
            confidence = min(max(float(item.get("confidence", 0.5)), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.5

        new_fact = new_facts[new_index]
        existing_fact = existing_facts[existing_index]
        results.append(Contradiction(
            entity=canonical_name,
            new_chapter_id=new_chapter_id,
            new_attribute=new_fact.attribute,
            new_value=new_fact.value,
            new_quote=new_fact.source_quote,
            conflicting_chapter_id=existing_fact["chapter_id"],
            conflicting_value=existing_fact["value"],
            conflicting_quote=existing_fact["source_quote"],
            contradiction_type=kind,
            confidence=confidence,
            explanation=explanation,
        ))
    return results


def find_contradictions_for_chapter(
    project_id: int, chapter_id: str, chapter_number: int, facts: list[Fact], resolutions: dict,
    time_note: str | None = None,
) -> list[Contradiction]:
    """
    Groups the new chapter's facts by ENTITY (not by name), using the links from
    resolve_entities(). So facts about "Captain Vale" are checked against earlier
    facts about "Marcus" and "Marcus Vale" if they're the same person.

    Several entities share one AI request (CHECK_BATCH_SIZE), to keep the number of
    requests down. Known entities are checked against their own history plus facts filed elsewhere
    that mention them. NEW entities have no history of their own, but earlier facts
    may still mention them (e.g. "Tuesday night | day | Tuesday" quoting "the storm
    broke on Tuesday night"), so they're checked against those mentions.
    """
    timing = timing_text(project_id, chapter_id, chapter_number, time_note)
    known: dict[int, list[Fact]] = defaultdict(list)
    new: dict[str, list[Fact]] = defaultdict(list)
    canonical: dict = {}
    for f in facts:
        r = resolutions[f.entity.lower()]
        if r.existing_entity_id is not None:
            known[r.existing_entity_id].append(f)
            canonical[r.existing_entity_id] = r.canonical_name
        else:
            key = r.canonical_name.lower()
            new[key].append(f)
            canonical[key] = r.canonical_name

    def evidence_known(item):
        entity_id, entity_facts = item
        existing = get_facts_for_entity_id(entity_id, exclude_chapter_id=chapter_id)
        existing += get_facts_mentioning_entity(entity_id, exclude_chapter_id=chapter_id)
        return (canonical[entity_id], entity_facts, existing)

    def evidence_new(item):
        # nothing earlier mentions a brand-new entity? then it has nothing to be checked against
        key, entity_facts = item
        names = {canonical[key]} | {f.entity for f in entity_facts}
        existing = get_facts_mentioning_names(project_id, sorted(names), exclude_chapter_id=chapter_id)
        return (canonical[key], entity_facts, existing)

    # Gather each entity's evidence from the database (no AI yet)...
    entries = [evidence_known(item) for item in known.items()] + [evidence_new(item) for item in new.items()]
    entries = [e for e in entries if e[2]]
    # ...then check them CHECK_BATCH_SIZE at a time; batches run at the same time.
    batches = [entries[i:i + CHECK_BATCH_SIZE] for i in range(0, len(entries), CHECK_BATCH_SIZE)]
    all_contradictions: list[Contradiction] = []
    for found in run_in_parallel(lambda batch: _check_entities(chapter_id, chapter_number, batch, timing), batches):
        all_contradictions.extend(found)
    return all_contradictions


# ---------------------------------------------------------------------------
# Safety net: pairs that were never compared because they're filed on different cards
# ---------------------------------------------------------------------------
CROSS_CHECK_TOOL = {
    "type": "function",
    "function": {
        "name": "report_cross_contradictions",
        "description": "Report pairs that are about the same entity AND contradict each other.",
        "parameters": {
            "type": "object",
            "properties": {
                "contradictions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pair_index": {"type": "integer"},
                            "same_entity_confidence": {"type": "number"},
                            "contradiction_type": {"type": "string", "enum": ["attribute", "status", "timeline"]},
                            "confidence": {"type": "number"},
                            "explanation": {"type": "string"},
                        },
                        "required": ["pair_index", "same_entity_confidence", "contradiction_type", "confidence", "explanation"],
                    },
                }
            },
            "required": ["contradictions"],
        },
    },
}

CROSS_CHECK_PROMPT = """You are checking a work of long-form fiction for continuity errors.

Each PAIR below is a fact from the new chapter {new_chapter_number} and an earlier fact with a
similar meaning. They are filed under DIFFERENT names, so they may or may not be about the same
character, place, object or event. Chapter numbers show reading order.

For each pair, decide two things:
1. Are they about the same entity? Different names can mean the same entity (a title, a
   nickname, a first name, a description). Judge from the names and the quotes. Different
   people who share a surname, or two different objects of the same kind, are NOT the same.
   Give same_entity_confidence from 0.0 to 1.0.
2. If they are the same entity, is it a genuine contradiction, using these rules:

{rules}

Report ONLY pairs that are both the same entity and a genuine contradiction. If none, return
an empty list.

CHAPTER TIMING (when each chapter is set, from its own words):
{timing}

PAIRS (index: NEW entity | attribute | value | quote  <->  EARLIER entity | attribute | value | chapter | quote):
{pairs}
"""


def _format_pair(i: int, new_fact: Fact, old: dict) -> str:
    return (f'{i}: {new_fact.entity} | {new_fact.attribute} | {new_fact.value} | "{new_fact.source_quote}"'
            f'  <->  {old["entity"]} | {old["attribute"]} | {old["value"]} | chapter {old["chapter_number"]} | '
            f'"{old["source_quote"]}"')


def find_cross_card_contradictions(
    project_id: int, chapter_id: str, chapter_number: int, facts: list[Fact], resolutions: dict,
    embeddings: list[list[float]], already_found: list[Contradiction], time_note: str | None = None,
) -> list[Contradiction]:
    """
    For each new fact, find the earlier facts closest in MEANING (via the search vectors)
    that are filed under a different entity, and ask the AI whether any pair is really
    the same entity contradicting itself. This catches conflicts that the per-entity
    check can't see because name linking failed. One AI call per chapter (per 40 pairs).
    """
    pairs: list[tuple[Fact, dict]] = []
    seen = set()
    for fact, vector in zip(facts, embeddings):
        r = resolutions[fact.entity.lower()]
        for old in get_similar_earlier_facts(project_id, vector, chapter_id, NEIGHBOURS_PER_FACT):
            if r.existing_entity_id is not None and old["entity_id"] == r.existing_entity_id:
                continue   # same card: already covered by the normal check
            key = (fact.source_quote, fact.attribute, old["fact_id"])
            if key not in seen:
                seen.add(key)
                pairs.append((fact, old))
    if not pairs:
        return []

    already = {(c.new_quote, c.conflicting_quote) for c in already_found}
    timing = timing_text(project_id, chapter_id, chapter_number, time_note)
    batches = [pairs[i:i + PAIRS_PER_CALL] for i in range(0, len(pairs), PAIRS_PER_CALL)]

    def check_batch(batch):
        answer = call_tool(
            CROSS_CHECK_PROMPT.format(
                new_chapter_number=chapter_number, rules=RULES, timing=timing,
                pairs="\n".join(_format_pair(i, f, o) for i, (f, o) in enumerate(batch)),
            ),
            CROSS_CHECK_TOOL, max_tokens=4096, thinking=JUDGING_THINKING_MODE,
        )
        found = []
        for item in answer.get("contradictions", []):
            try:
                index = int(item["pair_index"])
                same = float(item.get("same_entity_confidence", 0))
                kind = item["contradiction_type"]
                confidence = min(max(float(item.get("confidence", 0.5)), 0.0), 1.0)
                explanation = str(item["explanation"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (0 <= index < len(batch)) or kind not in VALID_TYPES or same < MIN_SAME_ENTITY_CONFIDENCE:
                continue
            new_fact, old = batch[index]
            found.append(Contradiction(
                entity=old["canonical_name"] or old["entity"],
                new_chapter_id=chapter_id,
                new_attribute=new_fact.attribute,
                new_value=new_fact.value,
                new_quote=new_fact.source_quote,
                conflicting_chapter_id=old["chapter_id"],
                conflicting_value=old["value"],
                conflicting_quote=old["source_quote"],
                contradiction_type=kind,
                confidence=min(confidence, same),
                explanation=explanation,
            ))
        return found

    results: list[Contradiction] = []
    used_new: set[str] = {c.new_quote for c in already_found}
    for found in run_in_parallel(check_batch, batches):
        for c in found:
            if (c.new_quote, c.conflicting_quote) in already or c.new_quote in used_new:
                continue   # the normal check already reported this new fact
            used_new.add(c.new_quote)
            results.append(c)
    return results


# ---------------------------------------------------------------------------
# Double-check: a second, focused look at every warning before it's shown
# ---------------------------------------------------------------------------
REVIEW_TOOL = {
    "type": "function",
    "function": {
        "name": "review_warnings",
        "description": "Decide, for each possible continuity error, whether to keep it.",
        "parameters": {
            "type": "object",
            "properties": {
                "reviews": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "warning_index": {"type": "integer"},
                            "keep": {"type": "boolean"},
                            "reason": {"type": "string"},
                        },
                        "required": ["warning_index", "keep", "reason"],
                    },
                }
            },
            "required": ["reviews"],
        },
    },
}

REVIEW_PROMPT = """You are double-checking possible continuity errors that were found in a novel.
Each WARNING below compares an EARLIER quote with a NEW quote from chapter {new_chapter_number}.
Chapter numbers show reading order.

Keep a warning (keep = true) only if ALL of these are true:
1. The quotes really say what the warning claims. If a value in the warning (a day, a number,
   a detail) does not appear in, or clearly follow from, its quote, it was misread.
2. Both quotes are about the same character, place, object or event.
3. It is NOT the story simply moving forward. If the earlier quote describes a "before" and the
   new quote an "after" (a living character dies, someone is hurt, the weather changes, someone
   moves, an object breaks), that is normal storytelling, even if the change isn't explained.
4. It is NOT explained by a flashback or a time skip (see the chapter timing notes).
5. The two quotes cannot both be true: the new chapter reverses something permanent (the dead
   acting alive, a lost hand in use, a destroyed object in use), changes a fixed detail (eye
   colour, a relationship, a past event), or makes the timing impossible.

If you are genuinely unsure, keep it. Give a short reason for every decision.

CHAPTER TIMING (when each chapter is set, from its own words):
{timing}

WARNINGS:
{warnings}
"""

REVIEW_BATCH_SIZE = 20


def _format_warning(i: int, c: Contradiction, numbers: dict[str, int], new_chapter_number: int) -> str:
    earlier = numbers.get(c.conflicting_chapter_id, "?")
    return (f'{i}: {c.entity} ({c.contradiction_type}). EARLIER (chapter {earlier}): value "{c.conflicting_value}", '
            f'quote "{c.conflicting_quote}". NEW (chapter {new_chapter_number}): value "{c.new_value}", '
            f'quote "{c.new_quote}". Claimed problem: {c.explanation}')


def double_check(project_id: int, chapter_id: str, chapter_number: int,
                 contradictions: list[Contradiction], time_note: str | None = None) -> list[Contradiction]:
    """
    Look at every warning a second time with one narrow question: is this a real
    contradiction, or a misreading / the story moving forward / a flashback? Warnings that
    fail are NOT deleted: they are marked "dismissed" with the reason, so the writer can see
    them under Issues -> Dismissed. If the double-check itself fails, every warning is kept.
    """
    open_ones = [c for c in contradictions if c.status == "open"]
    if not open_ones:
        return contradictions
    timing = timing_text(project_id, chapter_id, chapter_number, time_note)
    numbers = {c["chapter_id"]: c["chapter_number"] for c in get_time_notes(project_id)}
    batches = [open_ones[i:i + REVIEW_BATCH_SIZE] for i in range(0, len(open_ones), REVIEW_BATCH_SIZE)]

    def review(batch):
        try:
            answer = call_tool(
                REVIEW_PROMPT.format(
                    new_chapter_number=chapter_number, timing=timing,
                    warnings="\n".join(_format_warning(i, c, numbers, chapter_number) for i, c in enumerate(batch)),
                ),
                REVIEW_TOOL, max_tokens=4096, thinking=JUDGING_THINKING_MODE,
            )
        except AIServiceError as error:
            print(f"  [note] double-check skipped, all warnings kept: {error}", flush=True)
            return
        for item in answer.get("reviews", []):
            try:
                index = int(item["warning_index"])
                keep = item["keep"]
                reason = " ".join(str(item.get("reason", "")).split())[:300]
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= index < len(batch) and keep is False:          # only an explicit "no" dismisses
                batch[index].status = "dismissed"
                batch[index].review_note = f"Double-check: {reason}" if reason else "Double-check: not a real contradiction."

    run_in_parallel(review, batches)
    return contradictions

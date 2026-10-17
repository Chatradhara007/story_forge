import os
import re
import time
from collections import defaultdict
from models import Fact, Contradiction
import relationships as rel_rules
from storage import (get_time_notes, find_entities_by_alias, get_facts_mentioning_words, get_facts_for_entity_id, get_entity_evidence, get_facts_mentioning_entity,
                     get_facts_mentioning_names, get_similar_earlier_facts)
from llm import call_tool, run_in_parallel, JUDGING_THINKING_MODE, AIServiceError, ContextTooLongError
import storyclock
import storytime
import traits
import states
from concurrent.futures import ThreadPoolExecutor

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
                            "new_value": {"type": "string"},
                            "existing_value": {"type": "string"},
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

Facts marked [CANON] were confirmed by the writer and are always right: a new fact that
conflicts with a [CANON] fact is a contradiction.

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
of the EXISTING fact within that section, copy the two values you compared into new_value and
existing_value, and give a confidence from 0.0 (unsure) to 1.0 (certain).

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
        f'{i}: {"[CANON] " if f.get("pinned") else ""}{f["entity"]} | {f["attribute"]} | {f["value"]} | '
        f'chapter {f["chapter_number"]} | "{f["source_quote"]}"'
        for i, f in enumerate(facts)
    )


def _mean_vector(vectors: list[list[float]]) -> list[float] | None:
    vectors = [v for v in vectors if v]
    if not vectors:
        return None
    return [sum(column) / len(vectors) for column in zip(*vectors)]


def timing_text(project_id: int, chapter_id: str, chapter_number: int, time_note: str | None) -> str:
    """
    The CHAPTER TIMING block: saved chapters' notes plus the chapter being checked, each with
    where the story clock places it ("between 3 and 4 years after chapter 1 begins"), worked
    out in code (storytime.py), so the AI doesn't have to add time up.
    """
    notes = get_time_notes(project_id)
    saved = [c for c in notes if c["chapter_id"] != chapter_id]
    this_opening = next((c.get("opening") for c in notes if c["chapter_id"] == chapter_id), None)
    try:
        placed = storytime.timeline_lines(saved, chapter_number, time_note, this_opening)
    except Exception as error:                    # the timing block must never stop a check
        print(f"  [note] story clock could not place the chapters: {error}", flush=True)
        placed = {}

    def line(number, note, label=""):
        where = f" [story clock: {placed[number]}]" if number in placed else ""
        return f"chapter {number}{label}: {note or 'not recorded'}{where}"

    lines = [line(c["chapter_number"], c["time_note"]) for c in saved]
    lines.append(line(chapter_number, time_note, " (the NEW chapter)"))
    return "\n".join(lines)


def _check_entities(
    new_chapter_id: str, new_chapter_number: int, batch: list[tuple[str, list[Fact], list[dict]]],
    timing: str = "not recorded", index_of: dict[int, int] | None = None,
) -> list[Contradiction]:
    """
    Compares each entity's new facts with its previously stored facts, for several entities
    in ONE request. batch: [(canonical name, new facts, existing facts), ...]
    If the request is too long for the model, it is split and retried instead of failing
    the whole chapter: first one entity per request, then each entity's evidence in halves.
    """
    batch = [item for item in batch if item[2]]          # entities with no history: nothing to compare
    if not batch:
        return []
    try:
        return _check_entities_once(new_chapter_id, new_chapter_number, batch, timing, index_of or {})
    except ContextTooLongError:
        if len(batch) > 1:
            middle = len(batch) // 2
            return (_check_entities(new_chapter_id, new_chapter_number, batch[:middle], timing, index_of)
                    + _check_entities(new_chapter_id, new_chapter_number, batch[middle:], timing, index_of))
        name, new_facts, existing = batch[0]
        if len(existing) <= 4 and len(new_facts) <= 4:
            print(f"  [note] could not check {name}: too long for the model even after splitting", flush=True)
            return []
        if len(new_facts) > len(existing):
            middle = len(new_facts) // 2
            halves = [(name, new_facts[:middle], existing), (name, new_facts[middle:], existing)]
        else:
            middle = len(existing) // 2
            halves = [(name, new_facts, existing[:middle]), (name, new_facts, existing[middle:])]
        return [c for half in halves
                for c in _check_entities(new_chapter_id, new_chapter_number, [half], timing, index_of)]


def _check_entities_once(new_chapter_id, new_chapter_number, batch, timing, index_of) -> list[Contradiction]:
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
        thinking=JUDGING_THINKING_MODE, role="judge",
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
        located = _locate(batch, number, new_index, existing_index,
                          str(item.get("new_value") or ""), str(item.get("existing_value") or ""))
        if located is None:
            continue           # the values it compared aren't in the facts it was given: misread
        number, new_index, existing_index = located
        canonical_name, new_facts, existing_facts = batch[number - 1]
        if kind not in VALID_TYPES or (number, "old", existing_index) in used or (number, "new", new_index) in used:
            continue
        used.update({(number, "old", existing_index), (number, "new", new_index)})
        try:
            confidence = min(max(float(item.get("confidence", 0.5)), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.5

        new_fact = new_facts[new_index]
        existing_fact = existing_facts[existing_index]
        if _both_ages(new_fact.attribute, new_fact.value, existing_fact["attribute"], existing_fact["value"]):
            continue      # age arithmetic is the story clock's job (the AI got it wrong 9 times in 10)
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
            new_fact_index=index_of.get(id(new_fact)),
            conflicting_fact_id=existing_fact.get("fact_id"),
        ))
    return results


def _norm(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (value or "").lower()).split())


def _same_value(given: str, value: str) -> bool:
    a, b = _norm(given), _norm(value)
    return bool(a and b) and (a == b or (min(len(a), len(b)) >= 3 and (a in b or b in a)))


def _locate(batch, number, new_index, existing_index, new_value, existing_value):
    """
    Where a reported contradiction really is. The checker sometimes has the right idea but
    points at the wrong fact or the wrong section (4 Oct report: "twenty years vs eight"
    attached to the AGE fact; Tobias's "older vs younger brother" filed under Ines). When it
    copies the values it compared, those decide: the pair whose values match, in the section
    it named first, then in the others. Values that match no fact at all = a misreading:
    None. Without values, the numbers are used as before.
    """
    def fits(n, i, j):
        _, new_facts, existing = batch[n - 1]
        return (0 <= i < len(new_facts) and 0 <= j < len(existing)
                and (not new_value or _same_value(new_value, new_facts[i].value))
                and (not existing_value or _same_value(existing_value, existing[j]["value"])))

    if 1 <= number <= len(batch) and fits(number, new_index, existing_index):
        return number, new_index, existing_index
    if not new_value and not existing_value:
        return None
    sections = ([number] if 1 <= number <= len(batch) else []) + [n for n in range(1, len(batch) + 1) if n != number]
    for n in sections:
        _, new_facts, existing = batch[n - 1]
        new_options = [i for i in range(len(new_facts)) if not new_value or _same_value(new_value, new_facts[i].value)]
        old_options = [j for j in range(len(existing)) if not existing_value or _same_value(existing_value, existing[j]["value"])]
        if new_value and not new_options or existing_value and not old_options:
            continue
        i = new_index if new_index in new_options else (new_options[0] if new_options else new_index)
        j = existing_index if existing_index in old_options else (old_options[0] if old_options else existing_index)
        if fits(n, i, j):
            return n, i, j
    return None


# Social ties (friend, ally, rival, mentor...) are drawn on the character map but never checked:
# "apprentice" in one chapter and "ally" in another aren't a contradiction, people's relations
# grow. Family ties ARE checked (sister vs cousin).
_SOCIAL_LABELS = tuple(sorted({rel_rules.LABELS[k] for k in rel_rules.SOCIAL}
                              | {rel_rules.INVERSE_LABELS[k] for k in rel_rules.SOCIAL}, key=len, reverse=True))


def is_social_tie(fact) -> bool:
    attribute = fact["attribute"] if isinstance(fact, dict) else fact.attribute
    value = (fact["value"] if isinstance(fact, dict) else fact.value) or ""
    return (attribute or "").lower() == "relationship" and value.lower().startswith(_SOCIAL_LABELS)


def find_contradictions_for_chapter(
    project_id: int, chapter_id: str, chapter_number: int, facts: list[Fact], resolutions: dict,
    time_note: str | None = None, embeddings: list[list[float]] | None = None,
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
    index_of = {id(f): i for i, f in enumerate(facts)}
    vector_of = {id(f): v for f, v in zip(facts, embeddings or [])}
    known: dict[int, list[Fact]] = defaultdict(list)
    new: dict[str, list[Fact]] = defaultdict(list)
    canonical: dict = {}
    for f in facts:
        if is_social_tie(f):
            continue
        r = resolutions[f.entity.lower()]
        if r.existing_entity_id is not None:
            known[r.existing_entity_id].append(f)
            canonical[r.existing_entity_id] = r.canonical_name
        else:
            key = r.canonical_name.lower()
            new[key].append(f)
            canonical[key] = r.canonical_name

    # Only chapters EARLIER in reading order count as established history. (Before, every
    # other chapter did, so re-checking chapter 1 treated chapter 2 as its past.)
    def evidence_known(item):
        entity_id, entity_facts = item
        focus = _mean_vector([vector_of.get(id(f)) for f in entity_facts])
        existing = get_entity_evidence(entity_id, chapter_id, chapter_number, focus)
        existing += get_facts_mentioning_entity(entity_id, exclude_chapter_id=chapter_id,
                                                before_chapter_number=chapter_number)
        return (canonical[entity_id], entity_facts, [e for e in existing if not is_social_tie(e)])

    def evidence_new(item):
        # nothing earlier mentions a brand-new entity? then it has nothing to be checked against
        key, entity_facts = item
        names = {canonical[key]} | {f.entity for f in entity_facts}
        existing = get_facts_mentioning_names(project_id, sorted(names), exclude_chapter_id=chapter_id,
                                              before_chapter_number=chapter_number)
        return (canonical[key], entity_facts, [e for e in existing if not is_social_tie(e)])

    # Gather each entity's evidence from the database (no AI yet)...
    entries = [evidence_known(item) for item in known.items()] + [evidence_new(item) for item in new.items()]
    entries = [e for e in entries if e[2]]
    # ...then check them CHECK_BATCH_SIZE at a time; batches run at the same time.
    batches = [entries[i:i + CHECK_BATCH_SIZE] for i in range(0, len(entries), CHECK_BATCH_SIZE)]
    all_contradictions: list[Contradiction] = []
    for found in run_in_parallel(lambda batch: _check_entities(chapter_id, chapter_number, batch, timing, index_of),
                                 batches):
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


_FAMILY_ATTRIBUTE = re.compile(r"(relationship|relation|family|parent|child|sibling|brother|sister|son|daughter|"
                               r"mother|father|spouse|married|cousin|kin)", re.I)
_DESCRIPTION_NAME = re.compile(r"^(the|a|an|his|her|their|its|my|your|our|this|that)\b", re.I)


def _is_family_tie(fact) -> bool:
    """Family ties are checked on their own card and by the map's rule, not by the safety net:
    on long chapters the Reader sometimes records them the wrong way round ("Aurel parent of
    Oren"), and every such slip became a safety-net false alarm (7 on the held-out story)."""
    attribute = fact["attribute"] if isinstance(fact, dict) else fact.attribute
    return bool(_FAMILY_ATTRIBUTE.search(attribute or ""))


def _both_ages(new_attribute, new_value, old_attribute, old_value) -> bool:
    return (storyclock.parse_age(new_attribute, new_value) is not None
            and storyclock.parse_age(old_attribute, old_value) is not None)


def _name_words(name: str) -> set[str]:
    from entities import TITLE_WORDS, IGNORED_WORDS
    return {w for w in re.findall(r"[a-z']+", (name or "").lower())
            if len(w) >= 3 and w not in TITLE_WORDS and w not in IGNORED_WORDS}


_GENERIC_ATTRIBUTE_WORDS = {"status", "state", "condition", "action", "actions", "activity", "description",
                            "physical", "event", "events", "location", "role", "relationship", "relation", "detail",
                            "details", "info", "information", "fact", "note", "current", "time", "reference", "quote",
                            "about", "with", "from", "into", "over", "type", "kind", "other", "general", "trait"}


def _attribute_words(attribute: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (attribute or "").lower())
            if len(w) >= 4 and w not in _GENERIC_ATTRIBUTE_WORDS}


def _names_related(fact: Fact, canonical: str, old: dict) -> bool:
    """
    The safety net is for names that weren't linked but could be the same entity: a nickname,
    a title, a description, a secret identity. Two proper names with nothing in common, where
    neither fact mentions the other ("Venn fleet" vs "King Aurel's destination: the Venn
    isles"), are two different things, and asking the AI about them produced 28 false alarms
    and 1 catch on the held-out story. Pairs kept: the names share a word; or one name is a
    description ("the boy", "his father"); or either fact's value/quote mentions the other.
    """
    new_names = {fact.entity, canonical}
    old_names = {old["entity"], old.get("canonical_name") or old["entity"]}
    # A description or a bare title ("the boy", "Keeper") could be anyone.
    if any(_DESCRIPTION_NAME.match(n or "") or (n and n[:1].islower()) or (n and not _name_words(n))
           for n in new_names | old_names):
        return True
    if {w for n in new_names for w in _name_words(n)} & {w for n in old_names for w in _name_words(n)}:
        return True
    # The same specific detail under two unrelated names ("Rook | hands" / "Edwin Marsh | hands"):
    # possibly a secret identity. Generic attributes (status, action, description...) don't count.
    if _attribute_words(fact.attribute) & _attribute_words(old["attribute"]):
        return True
    new_text = f"{fact.value} {fact.source_quote}".lower()
    old_text = f"{old['value']} {old['source_quote']}".lower()
    return (any(n and n.lower() in new_text for n in old_names)
            or any(n and n.lower() in old_text for n in new_names))


# Concrete details that a slip changes: colours, body parts and marks, counts. Two facts about
# possibly-the-same entity are only worth an AI question when they share one of these, or when
# the new fact is plainly ABOUT the other entity ("Ember, the black stallion" under Aurel).
_DETAIL_WORDS = re.compile(
    r"\b(red|blue|green|grey|gray|black|white|brown|golden|gold|silver|chestnut|auburn|dark|fair|pale|"
    r"eyes?|hair|beard|scar\w*|hands?|fingers?|arms?|legs?|feet|foot|blind\w*|deaf|limp\w*|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|\d+|left|right|"
    r"dead|died|drowned|buried|lost|broken|burned|burnt|sank|sunk)\b", re.I)


def _shares_detail(fact: Fact, old: dict) -> bool:
    if _attribute_words(fact.attribute) & _attribute_words(old["attribute"]):
        return True
    new_details = {w.lower() for w in _DETAIL_WORDS.findall(f"{fact.attribute} {fact.value}")}
    old_details = {w.lower() for w in _DETAIL_WORDS.findall(f"{old['attribute']} {old['value']}")}
    if new_details & old_details:
        return True
    colours = re.compile(r"\b(red|blue|green|grey|gray|black|white|brown|golden|gold|silver|chestnut|auburn)\b", re.I)
    if colours.search(fact.value or "") and colours.search(old["value"] or ""):
        return True                                   # grey vs black: the classic slip
    # The new fact's VALUE names the earlier entity: it is about that entity ("read the letter").
    names = [n for n in {old["entity"], old.get("canonical_name") or ""} if n and len(n) >= 3]
    return any(re.search(r"(^|\W)" + re.escape(n.lower()) + r"($|\W)", (fact.value or "").lower())
               and not re.search(re.escape(n.lower()) + r"'s\b", (fact.value or "").lower()) for n in names)


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
    index_of = {id(f): i for i, f in enumerate(facts)}
    neighbours = get_similar_earlier_facts(project_id, embeddings, chapter_id, chapter_number, NEIGHBOURS_PER_FACT)
    for fact, near in zip(facts, neighbours):
        if is_social_tie(fact) or _is_family_tie(fact):
            continue
        r = resolutions[fact.entity.lower()]
        for old in near:
            if is_social_tie(old) or _is_family_tie(old):
                continue
            if _both_ages(fact.attribute, fact.value, old["attribute"], old["value"]):
                continue
            if not _names_related(fact, r.canonical_name, old) or not _shares_detail(fact, old):
                continue
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
            CROSS_CHECK_TOOL, max_tokens=4096, thinking=JUDGING_THINKING_MODE, role="judge",
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
            if _SAYS_DIFFERENT.search(explanation):
                continue      # its own explanation says they're different people (5 Oct report)
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
                source="safety net",
                new_fact_index=index_of.get(id(new_fact)),
                conflicting_fact_id=old["fact_id"],
            ))
        return found

    # One warning per new FACT (not per quote: one sentence can hold two real mistakes,
    # e.g. "the one-handed keeper read the burned letter").
    def fact_key(c: Contradiction):
        return (c.new_quote, c.new_attribute.lower(), c.new_value.lower())

    results: list[Contradiction] = []
    used_new = {fact_key(c) for c in already_found}
    for found in run_in_parallel(check_batch, batches):
        for c in found:
            if (c.new_quote, c.conflicting_quote) in already or fact_key(c) in used_new:
                continue   # the normal check already reported this new fact
            used_new.add(fact_key(c))
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

REVIEW_BATCH_SIZE = 8      # warnings per double-check call; calls run in parallel


def _format_warning(i: int, c: Contradiction, numbers: dict[str, int], new_chapter_number: int) -> str:
    earlier = numbers.get(c.conflicting_chapter_id, "?")
    names = (" The two facts were filed under DIFFERENT names: keep it only if the quotes show they are the "
             "same character, place or object." if c.source == "safety net" else "")
    return (f'{i}: {c.entity} ({c.contradiction_type}). EARLIER (chapter {earlier}): value "{c.conflicting_value}", '
            f'quote "{c.conflicting_quote}". NEW (chapter {new_chapter_number}): value "{c.new_value}", '
            f'quote "{c.new_quote}". Claimed problem: {c.explanation}{names}')


def double_check(project_id: int, chapter_id: str, chapter_number: int,
                 contradictions: list[Contradiction], time_note: str | None = None) -> list[Contradiction]:
    """
    Look at every warning a second time with one narrow question: is this a real
    contradiction, or a misreading / the story moving forward / a flashback? Warnings that
    fail are NOT deleted: they are marked "dismissed" with the reason, so the writer can see
    them under Issues -> Dismissed. If the double-check itself fails, every warning is kept.
    """
    # Warnings from checks done in code (story clock, trait check) are exact: the AI isn't asked to
    # second-guess them. (17 Oct 2026: the AI double-check dismissed a real catch, the scar on the other hand.)
    open_ones = [c for c in contradictions if c.status == "open" and c.source not in ("story clock", "trait check")]
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
                REVIEW_TOOL, max_tokens=4096, thinking=JUDGING_THINKING_MODE, role="judge",
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


# ---------------------------------------------------------------------------
# The whole check for one chapter (used when adding a chapter AND when re-checking)
# ---------------------------------------------------------------------------
def find_age_conflicts(project_id: int, chapter_id: str, chapter_number: int, facts: list[Fact],
                       resolutions: dict, time_note: str | None, text: str | None = None) -> list[Contradiction]:
    """The story clock (see storyclock.py): age arithmetic done in code."""
    known = [(resolutions[f.entity.lower()].existing_entity_id, resolutions[f.entity.lower()].canonical_name, f, i)
             for i, f in enumerate(facts) if resolutions[f.entity.lower()].existing_entity_id is not None]
    if not known:
        return []
    cache: dict[int, list[dict]] = {}

    def earlier(entity_id):
        if entity_id not in cache:
            cache[entity_id] = get_facts_for_entity_id(entity_id, exclude_chapter_id=chapter_id,
                                                       before_chapter_number=chapter_number)
        return cache[entity_id]

    found = []
    if any(storyclock.parse_age(f.attribute, f.value) is not None for _, _, f, _ in known):
        found += storyclock.check_ages(chapter_id, chapter_number, known, earlier, get_time_notes(project_id), time_note,
                                       text)
    found += storyclock.check_weekdays(chapter_id, chapter_number, known, earlier, time_note)
    found += storyclock.check_after_death(chapter_id, chapter_number, known, earlier, time_note)
    # One story-clock warning per new fact.
    unique: dict = {}
    for c in found:
        unique.setdefault(c.new_fact_index, c)
    return list(unique.values())


# Fixed-trait checks in code (traits.py). On by default; TRAIT_CHECKS=off turns them off
# (the older automated tests use eye colour as their example of an AI-checker warning).
TRAIT_CHECKS = os.getenv("TRAIT_CHECKS", "on").strip().lower() not in ("off", "false", "0", "no")
# The safety net (AI comparisons across different entries) is OFF by default: on the free models it
# raised half of all false alarms and caught nothing on The Fallen King (16 Oct 2026), and took ~7 of
# the 35 minutes. SAFETY_NET=on turns it back on (e.g. with a stronger paid judge).
SAFETY_NET = os.getenv("SAFETY_NET", "off").strip().lower() in ("on", "true", "1", "yes")
# The AI checker. CHECKER=off leaves only the checks done in code ("Confirmed"): far fewer AI
# requests per chapter. Compare both with eval/sweep.py before choosing.
CHECKER = os.getenv("CHECKER", "on").strip().lower() not in ("off", "false", "0", "no")


def find_trait_conflicts(project_id: int, chapter_id: str, chapter_number: int, facts: list[Fact],
                         resolutions: dict) -> list[Contradiction]:
    """Fixed traits compared as values in code (see traits.py): eyes, coat, scar side, handedness, who is older."""
    if not TRAIT_CHECKS:
        return []
    new_facts = [(resolutions[f.entity.lower()].existing_entity_id, resolutions[f.entity.lower()].canonical_name, f, i)
                 for i, f in enumerate(facts)]
    lookups: dict[str, int | None] = {}

    def find_entity(name: str) -> int | None:
        key = name.lower().strip()
        if key in resolutions and resolutions[key].existing_entity_id is not None:
            return resolutions[key].existing_entity_id
        if key not in lookups:
            found = find_entities_by_alias(project_id, [key])
            lookups[key] = found[key][0] if key in found else None
        return lookups[key]

    def earlier(entity_id):
        return [{**f, "entity_id": entity_id} for f in
                get_facts_for_entity_id(entity_id, exclude_chapter_id=chapter_id, before_chapter_number=chapter_number)]

    return traits.check_traits(chapter_id, chapter_number, new_facts, earlier, find_entity)


def find_code_conflicts(project_id: int, chapter_id: str, chapter_number: int, facts: list[Fact],
                        resolutions: dict, time_note: str | None = None, text: str | None = None) -> list[Contradiction]:
    """Fixed traits (traits.py) and lasting states of objects and abilities (states.py), all in code."""
    if not TRAIT_CHECKS:
        return []
    found = find_trait_conflicts(project_id, chapter_id, chapter_number, facts, resolutions)
    reported = {c.new_fact_index for c in found}
    found += [c for c in find_state_conflicts(project_id, chapter_id, chapter_number, facts, resolutions, time_note, text)
              if c.new_fact_index not in reported]
    return found


def find_state_conflicts(project_id: int, chapter_id: str, chapter_number: int, facts: list[Fact],
                         resolutions: dict, time_note: str | None = None, text: str | None = None) -> list[Contradiction]:
    """Objects given away or destroyed and then used; abilities lost and then used (states.py)."""
    new_facts = [(resolutions[f.entity.lower()].existing_entity_id, resolutions[f.entity.lower()].canonical_name, f, i)
                 for i, f in enumerate(facts)]
    notes = get_time_notes(project_id)
    saved = [c for c in notes if c["chapter_id"] != chapter_id]
    if text is None:
        text = next((c.get("opening") for c in notes if c["chapter_id"] == chapter_id), None)
    placed = storytime.chapter_positions(saved + [{"chapter_id": chapter_id, "chapter_number": chapter_number,
                                                   "time_note": time_note, "opening": (text or "")[:600]}])
    flashbacks = {n for n, p in placed.items() if p.flashback}
    nouns = sorted({noun for f in facts for noun, _ in states.object_mentions(f"{f.value} {f.source_quote}")})
    object_facts = (get_facts_mentioning_words(project_id, nouns, exclude_chapter_id=chapter_id,
                                               before_chapter_number=chapter_number) if nouns else [])
    lookups: dict[str, int | None] = {}

    def find_entity(name: str) -> int | None:
        key = name.lower().strip()
        if key in resolutions and resolutions[key].existing_entity_id is not None:
            return resolutions[key].existing_entity_id
        if key not in lookups:
            found = find_entities_by_alias(project_id, [key])
            lookups[key] = found[key][0] if key in found else None
        return lookups[key]

    def earlier(entity_id):
        return [{**f, "entity_id": entity_id} for f in
                get_facts_for_entity_id(entity_id, exclude_chapter_id=chapter_id, before_chapter_number=chapter_number)]

    return states.check_states(chapter_id, chapter_number, new_facts, object_facts, earlier, find_entity, flashbacks)


def check_chapter(project_id: int, chapter_id: str, chapter_number: int, facts: list[Fact],
                  resolutions: dict, embeddings: list[list[float]], time_note: str | None,
                  timings: dict | None = None, progress=None, text: str | None = None) -> list[Contradiction]:
    """
    Every check, in order: per-entity AI check, story clock, safety net, double-check.
    timings: filled with seconds per stage. progress(stage): called as each stage starts.
    """
    timings = timings if timings is not None else {}

    def stage(name, function, *args, **kwargs):
        if progress:
            progress(name)
        started = time.perf_counter()
        value = function(*args, **kwargs)
        timings[name] = round(time.perf_counter() - started, 1)
        return value

    # Checks done in code come first: they are exact ("Confirmed" on the website), so for a
    # fact they report, an AI warning about the same fact is dropped rather than the other way round.
    found = stage("story clock", find_age_conflicts, project_id, chapter_id, chapter_number,
                  facts, resolutions, time_note, text)
    reported = {c.new_fact_index for c in found}
    found += [c for c in stage("trait check", find_code_conflicts, project_id, chapter_id, chapter_number,
                               facts, resolutions, time_note, text)
              if c.new_fact_index not in reported]
    reported = {c.new_fact_index for c in found}
    # The AI checker (and the optional safety net) run at the same time; their warnings are
    # "Worth a look" on the website.
    with ThreadPoolExecutor(max_workers=1) as pool:
        safety = (pool.submit(stage, "safety-net check", find_cross_card_contradictions, project_id, chapter_id,
                              chapter_number, facts, resolutions, embeddings, [], time_note)
                  if SAFETY_NET else None)
        checked = (stage("checking for mistakes", find_contradictions_for_chapter, project_id, chapter_id,
                         chapter_number, facts, resolutions, time_note, embeddings) if CHECKER else [])
        cross = safety.result() if safety else []        # wait inside the block; errors surface here
    found += [c for c in checked if c.new_fact_index not in reported]
    # Safety net: conflicts hidden because the two facts are filed under different names.
    found += _dedupe_against(cross, found)
    # Rules in code: drop what the checker itself doubts, set aside normal story changes.
    found = set_aside_by_rule(found, time_note)
    # Double-check every warning; ones that fail are kept but marked dismissed, with the reason.
    return stage("double-checking", double_check, project_id, chapter_id, chapter_number, found, time_note)


# ---------------------------------------------------------------------------
# Rules in code, applied before the double-check (from the Oct 2026 evaluation reports)
# ---------------------------------------------------------------------------
# The checker's own explanation says there is no contradiction ("this is mathematically
# consistent. However..."): low confidence -> dropped; otherwise set aside with the reason.
_ADMITS_NONE = re.compile(
    r"\b(no (real |genuine |actual |clear )?(contradiction|conflict|inconsistency)|"
    r"not (a |an |actually a |really a |necessarily a )?(contradiction|inconsistency|conflict)|"
    r"cannot (assert|confirm|establish|claim|determine)|can't (assert|confirm|establish)|"
    r"(is|are|remains?|seems?|appears?) (mathematically |fully |entirely |perfectly |logically |still |therefore |actually )?consistent\b|"
    r"does not contradict|doesn't contradict|do not contradict|don't contradict)", re.I)
# The safety net's explanation says the two names are different people.
_SAYS_DIFFERENT = re.compile(
    r"\b((cannot|can't|could not|couldn't|can not) be the same|not the same (person|people|entity|character|thing|object|one)|"
    r"(are|is) (two |a )?(different|separate|distinct) (people|persons|person|entities|entity|characters|character|objects|things)|"
    r"different (people|persons|characters|individuals))\b", re.I)
# Things that happen to someone or something as a story moves on, and don't undo themselves.
_FORWARD = re.compile(
    r"\b(dead|died|dies|killed|drowned|buried|perished|deceased|slain|shattered|smashed|broken|broke|"
    r"pieces|cracked|crack|burned|burnt|ash|ashes|destroyed|sank|sunk|collapsed|ruined|lost|injured|"
    r"wounded|scar|scarred|scars|blind|maimed|amputated|missing|torn|sold|gave|given)\b", re.I)
_INJURY_OR_DAMAGE = re.compile(
    r"\b(scar|scarred|scars|burn|burned|burnt|cut|wound|wounded|injur\w*|lost|missing|blind|broken|broke|"
    r"shattered|cracked|dead|died|buried|destroyed|mended|repaired|healed)\b", re.I)


# --- Ages: the story clock's job (13 Oct, run B on The Fallen King: 7 of 14 false alarms) ---
# The checker kept pairing an age with something that isn't this character's age NOW:
# "son_age | eight" vs "thirty-one", "until Tam is twenty-five", "at seventeen" vs "two years
# younger than Aurel", "six years" (a duration) vs "six years old". Two clean current ages are
# compared by the story clock with the chapter timing, so a checker/safety-net warning where
# an age is involved is only kept when BOTH sides are clean current ages.
_AGE_IN_VALUE = re.compile(r"\b(years?[- ]old|years? of age|aged \w+)\b", re.I)
_AGE_VERB = r"(is|was|turned|turns|turning|at|aged|be|now)"


def _mentions_age(attribute: str | None, value: str, quote: str) -> bool:
    from extract import normalise_numbers
    value_n = normalise_numbers(value or "").strip().lower()
    if _AGE_IN_VALUE.search(value_n):
        return True
    if attribute and storyclock.AGE_ATTRIBUTE.search(attribute) and re.search(r"\d", value_n):
        return True
    number_only = re.fullmatch(r"(about |nearly |almost |only |just )?(\d{1,3})", value_n)
    if number_only:
        quote_n = normalise_numbers(quote or "").lower()
        return bool(re.search(_AGE_VERB + r"\s+" + number_only.group(2) + r"\b", quote_n))
    return False


def _current_age(attribute: str | None, value: str, quote: str) -> int | None:
    if not _mentions_age(attribute, value, quote):
        return None                      # "six years" (how long something took) is not an age
    attribute = attribute or ""
    if attribute and storyclock._OTHER_PERSON.search(attribute.replace("_", " ")):
        return None
    if not storyclock.AGE_ATTRIBUTE.search(attribute):
        attribute = "age"
    return storyclock.parse_age(attribute, value, quote)


def _age_mismatch(c: Contradiction) -> bool:
    if not (_mentions_age(c.new_attribute, c.new_value, c.new_quote)
            or _mentions_age(None, c.conflicting_value, c.conflicting_quote)):
        return False
    new_age = _current_age(c.new_attribute, c.new_value, c.new_quote)
    if new_age is None:
        return True
    if _current_age(None, c.conflicting_value, c.conflicting_quote) is not None:
        return False
    # The earlier side is a bare number ("ten") under an age the new side clearly states: an age too,
    # unless its own quote says it isn't one now ("until he is ten").
    from extract import normalise_numbers
    bare = re.fullmatch(r"\s*(about |nearly |almost )?\d{1,3}\s*", normalise_numbers(c.conflicting_value or ""))
    return not (bare and storyclock.parse_age("age", c.conflicting_value, c.conflicting_quote) is not None)


# --- Family ties (run B: 2 false alarms) ---
_TIE = re.compile(r"^\s*(?:the\s+|a\s+|an\s+)?(?P<kind>[a-z][a-z' -]*?)\s+(?:of|to|with)\s+(?P<target>.+?)\s*$", re.I)
_TIE_GROUPS = [
    ("parent", re.compile(r"\b(parent|father|mother|stepfather|stepmother|mum|mom|dad)\b", re.I)),
    ("child", re.compile(r"\b(child|son|daughter|stepson|stepdaughter|heir)\b", re.I)),
    ("spouse", re.compile(r"\b(married|wife|husband|spouse|consort|widow|widower|betrothed)\b", re.I)),
    ("sibling", re.compile(r"\b(sibling|brother|sister|twin)\b", re.I)),
    ("cousin", re.compile(r"\b(cousin)\b", re.I)),
]


def _tie(value: str):
    m = _TIE.match(value or "")
    if not m:
        return None
    kind = next((name for name, pattern in _TIE_GROUPS if pattern.search(m.group("kind"))), None)
    return (kind, _name_words(m.group("target")) or {m.group("target").lower()}) if kind else None


def _family_compatible(c: Contradiction) -> str | None:
    """Two family ties that can both be true, or a parent/child tie recorded the wrong way round."""
    if not _FAMILY_ATTRIBUTE.search(c.new_attribute or ""):
        return None
    new, old = _tie(c.new_value), _tie(c.conflicting_value)
    if not new or not old:
        return None
    same_target = bool(new[1] & old[1])
    if not same_target and new[0] != old[0]:
        return ("Set aside: two different family ties to two different people can both be true "
                f"('{c.new_value}' and '{c.conflicting_value}').")
    if same_target and {new[0], old[0]} == {"parent", "child"}:
        return ("Set aside: a parent/child tie recorded the other way round; the reader sometimes "
                "files these backwards, so it isn't reported as a mistake.")
    return None


# --- "Alive" only contradicts a death (run B: "poles a ferry" vs "alive") ---
_ALIVE_ONLY = re.compile(r"^\s*(still\s+)?(alive|living|lives|survived|survives|survivor)\s*\.?\s*$", re.I)
_DEATH_WORD = re.compile(r"\b(dead|died|dies|death|killed|drowned|buried|perished|deceased|slain|grave|ghost)\b", re.I)


def _alive_without_death(c: Contradiction) -> bool:
    for this, other in ((c.new_value, c.conflicting_value), (c.conflicting_value, c.new_value)):
        if _ALIVE_ONLY.match(this or "") and not _DEATH_WORD.search(other or ""):
            return True
    return False


# --- Growing up and growing old (run B: "grey colt" in a flashback; decoy D4 "white muzzle") ---
_YOUNG_ANIMAL = re.compile(r"\b(colt|foal|filly|pup|puppy|whelp|kitten|calf|cub|lamb|fawn|chick|duckling|cygnet)\b", re.I)
_GROWN_ANIMAL = re.compile(r"\b(stallion|mare|horse|gelding|steed|dog|hound|cat|bull|cow|ox|bear|wolf|"
                           r"ram|ewe|sheep|deer|stag|doe|hen|rooster|duck|swan)\b", re.I)
_COLOUR = re.compile(r"\b(red|blue|green|grey|gray|black|white|brown|golden|gold|silver|chestnut|auburn|roan|piebald|dappled)\b", re.I)
_AGEING = re.compile(r"\b(muzzle|temples|greying|graying|grizzled|silvered|white-muzzled|grey-muzzled|"
                     r"(grown|turned|gone|going|turning) (white|grey|gray|silver|hoary))\b", re.I)


def _colours(text: str) -> set[str]:
    return {w.lower().replace("gray", "grey") for w in _COLOUR.findall(text or "")}


def _growing(c: Contradiction, flashback: bool) -> str | None:
    new, old = c.new_value or "", c.conflicting_value or ""
    new_colours, old_colours = _colours(new), _colours(old)
    colours_agree = not new_colours or not old_colours or new_colours == old_colours
    # The young animal must be EARLIER in story time: the earlier chapter, or this chapter if it's a flashback.
    young_earlier = (_YOUNG_ANIMAL.search(old) and _GROWN_ANIMAL.search(new) and not _YOUNG_ANIMAL.search(new)
                     and not flashback)
    young_now_flashback = (flashback and _YOUNG_ANIMAL.search(new) and _GROWN_ANIMAL.search(old)
                           and not _YOUNG_ANIMAL.search(old))
    if (young_earlier or young_now_flashback) and colours_agree:
        return "Set aside: a young animal grown up (or seen young in a flashback), not a different animal."
    if not flashback and _AGEING.search(new) and not _AGEING.search(old):
        return (f"Set aside: '{_AGEING.search(new).group(0)}' is ageing, the story moving forward, "
                "not a change of colour.")
    return None


def _dedupe_against(new_ones: list[Contradiction], found: list[Contradiction]) -> list[Contradiction]:
    """Safety-net warnings for a new fact (or a pair of quotes) another check already reported are dropped."""
    pairs = {(c.new_quote, c.conflicting_quote) for c in found}
    keys = {(c.new_quote, c.new_attribute.lower(), c.new_value.lower()) for c in found}
    return [c for c in new_ones if (c.new_quote, c.conflicting_quote) not in pairs
            and (c.new_quote, c.new_attribute.lower(), c.new_value.lower()) not in keys]


def set_aside_by_rule(contradictions: list[Contradiction], time_note: str | None) -> list[Contradiction]:
    """
    Before the AI double-check, rules that need no AI:
    - the checker's explanation admits there's no contradiction: dropped if it was unsure
      (confidence < 0.5), otherwise set aside, with the reason;
    - a flashback showing someone BEFORE an injury or loss the earlier chapter describes
      ("palms unmarked" twelve years before "a pale scar"): set aside;
    - an age paired with something that isn't this character's age now (left to the story clock);
    - two family ties that can both be true, or a parent/child tie the wrong way round;
    - "alive" against anything but a death;
    - a young animal grown up, or hair/coat greying with age;
    - the story moving forward: the new side is a death, breakage, injury or loss and the
      earlier side mentions nothing of the kind (alive -> buried; whole -> in pieces). Only the
      reverse is a mistake, and "scar on the right palm" vs "scar on the left palm" (both
      sides scarred) or "mended" vs "still cracked" (the earlier side mentions breaking) stay.
    Story-clock and trait-check warnings are done in code and are never set aside here (the
    AI double-check still reviews trait-check warnings).
    """
    flashback = (time_note or "").lower().startswith("flashback")
    kept = []
    for c in contradictions:
        if c.source in ("story clock", "trait check") or c.status != "open":
            kept.append(c)
            continue
        family = _family_compatible(c)
        growing = _growing(c, flashback)
        if _ADMITS_NONE.search(c.explanation or ""):
            if c.confidence < 0.5:
                continue
            c.status, c.review_note = "dismissed", "Set aside: the warning's own explanation says the two facts are consistent."
        elif _age_mismatch(c):
            c.status, c.review_note = "dismissed", (
                "Set aside: ages are compared by the story clock, which does the arithmetic with the chapter "
                "timing; here one side isn't this character's age now (someone else's age, a past or future "
                "age, a relative age, or a length of time).")
        elif family:
            c.status, c.review_note = "dismissed", family
        elif _alive_without_death(c):
            c.status, c.review_note = "dismissed", ("Set aside: being alive only conflicts with a death, and the "
                                                    "other fact doesn't mention one.")
        elif growing:
            c.status, c.review_note = "dismissed", growing
        elif flashback and _INJURY_OR_DAMAGE.search(c.conflicting_value or ""):
            word = _INJURY_OR_DAMAGE.search(c.conflicting_value).group(0).lower()
            c.status, c.review_note = "dismissed", (f"Set aside: this chapter is a flashback, set before the "
                                                    f"earlier chapter's '{word}'.")
        else:
            forward = _FORWARD.search(c.new_value or "")
            if forward and not _FORWARD.search(c.conflicting_value or "") and not _INJURY_OR_DAMAGE.search(c.conflicting_value or ""):
                c.status, c.review_note = "dismissed", (
                    f"Set aside: the story moving forward (something that existed earlier in story time has "
                    f"'{forward.group(0).lower()}' later). Only the reverse would be a mistake.")
        kept.append(c)
    return kept

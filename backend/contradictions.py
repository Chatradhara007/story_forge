from collections import defaultdict
from models import Fact, Contradiction
from storage import get_facts_for_entity_id
from llm import call_tool

VALID_TYPES = {"attribute", "status", "timeline"}

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
                            "new_fact_index": {"type": "integer"},
                            "existing_fact_index": {"type": "integer"},
                            "contradiction_type": {
                                "type": "string",
                                "enum": ["attribute", "status", "timeline"]
                            },
                            "confidence": {"type": "number"},
                            "explanation": {"type": "string"}
                        },
                        "required": ["new_fact_index", "existing_fact_index", "contradiction_type", "confidence", "explanation"]
                    }
                }
            },
            "required": ["contradictions"]
        }
    }
}

CONTRADICTION_PROMPT = """You are checking a work of long-form fiction for continuity errors.

Below is a list of NEW facts just extracted from chapter {new_chapter_number}, and a list of
EXISTING facts already established about the same entity from other chapters.
This entity is "{canonical_name}". All of these names refer to it: {aliases}.
Treat facts under any of those names as facts about the same entity. Chapter
numbers show reading order: a lower number happens earlier in the book.

Compare them and flag genuine contradictions only. A contradiction is:
- ATTRIBUTE: a stated attribute (like eye color, age, name spelling, physical trait) changed
  without in-story explanation (e.g. injury, disguise, magic).
- STATUS: an entity is described in a state that conflicts with an established state
  (e.g. described as dead in one fact, alive and acting in another, with no resurrection
  explained; described as being in two different places at the same time).
- TIMELINE: a stated event ordering or duration conflicts with an already-established
  timeline.

Do NOT flag:
- New information that simply adds detail without conflicting.
- Facts that could both be true at different points in the story (e.g. someone's location
  changing over time is normal, not a contradiction, unless the timing makes it impossible).
- Vague or ambiguous phrasing that isn't a clear conflict.

For each contradiction, give a confidence from 0.0 (unsure) to 1.0 (certain).

NEW facts (index: entity | attribute | value | quote):
{new_facts}

EXISTING facts (index: entity | attribute | value | chapter number | quote):
{existing_facts}

Only report genuine contradictions. If there are none, return an empty list.
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


def _check_entity_contradictions(
    new_chapter_id: str, new_chapter_number: int, canonical_name: str,
    new_facts: list[Fact], existing_facts: list[dict],
) -> list[Contradiction]:
    """Compares one entity's new facts against its previously stored facts."""
    if not existing_facts:
        return []

    answer = call_tool(
        CONTRADICTION_PROMPT.format(
            new_chapter_number=new_chapter_number,
            canonical_name=canonical_name,
            aliases=", ".join(sorted({f.entity for f in new_facts} | {f["entity"] for f in existing_facts})),
            new_facts=_format_new_facts(new_facts),
            existing_facts=_format_existing_facts(existing_facts),
        ),
        CONTRADICTION_TOOL,
        max_tokens=2048,
    )

    results = []
    for item in answer.get("contradictions", []):
        # The AI refers to facts by their number in the lists above. Check that
        # those numbers actually exist before using them — before this check, one
        # made-up number crashed the whole request.
        try:
            new_index = int(item["new_fact_index"])
            existing_index = int(item["existing_fact_index"])
            kind = item["contradiction_type"]
            explanation = str(item["explanation"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= new_index < len(new_facts) and 0 <= existing_index < len(existing_facts)):
            continue
        if kind not in VALID_TYPES:
            continue
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
    chapter_id: str, chapter_number: int, facts: list[Fact], resolutions: dict
) -> list[Contradiction]:
    """
    Groups the new chapter's facts by ENTITY (not by name), using the links from
    resolve_entities(). So facts about "Captain Vale" are checked against earlier
    facts about "Marcus" and "Marcus Vale" if they're the same person.
    One AI call per entity that already has history; brand-new entities cost nothing.
    """
    by_entity: dict[int, list[Fact]] = defaultdict(list)
    canonical: dict[int, str] = {}
    for f in facts:
        r = resolutions[f.entity.lower()]
        if r.existing_entity_id is not None:          # new entities have no history yet
            by_entity[r.existing_entity_id].append(f)
            canonical[r.existing_entity_id] = r.canonical_name

    all_contradictions: list[Contradiction] = []
    for entity_id, entity_facts in by_entity.items():
        existing = get_facts_for_entity_id(entity_id, exclude_chapter_id=chapter_id)
        all_contradictions.extend(
            _check_entity_contradictions(chapter_id, chapter_number, canonical[entity_id], entity_facts, existing)
        )
    return all_contradictions

import os
import json
from collections import defaultdict
from openai import OpenAI
from models import Fact, Contradiction
from storage import get_facts_for_entity

nim_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],
)

MODEL = "nvidia/nemotron-3-super-120b-a12b"

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
                            "explanation": {"type": "string"}
                        },
                        "required": ["new_fact_index", "existing_fact_index", "contradiction_type", "explanation"]
                    }
                }
            },
            "required": ["contradictions"]
        }
    }
}

CONTRADICTION_PROMPT = """You are checking a work of long-form fiction for continuity errors.

Below is a list of NEW facts just extracted from a new chapter, and a list of EXISTING facts
already established about the same entity from earlier chapters.

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

NEW facts (index: entity | attribute | value | quote):
{new_facts}

EXISTING facts (index: entity | attribute | value | chapter | quote):
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
        f'{i}: {f["entity"]} | {f["attribute"]} | {f["value"]} | ch:{f["chapter_id"]} | "{f["source_quote"]}"'
        for i, f in enumerate(facts)
    )


def _check_entity_contradictions(
    new_chapter_id: str, new_facts: list[Fact], existing_facts: list[dict]
) -> list[Contradiction]:
    """Compares one entity's new facts against its previously stored facts."""
    if not existing_facts:
        return []

    response = nim_client.chat.completions.create(
        model=MODEL,
        max_tokens=2048,
        tools=[CONTRADICTION_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_contradictions"}},
        messages=[{
            "role": "user",
            "content": CONTRADICTION_PROMPT.format(
                new_facts=_format_new_facts(new_facts),
                existing_facts=_format_existing_facts(existing_facts),
            )
        }]
    )

    tool_call = response.choices[0].message.tool_calls[0]
    raw = json.loads(tool_call.function.arguments)["contradictions"]

    results = []
    for item in raw:
        new_fact = new_facts[item["new_fact_index"]]
        existing_fact = existing_facts[item["existing_fact_index"]]
        results.append(Contradiction(
            entity=new_fact.entity,
            new_chapter_id=new_chapter_id,
            new_attribute=new_fact.attribute,
            new_value=new_fact.value,
            new_quote=new_fact.source_quote,
            conflicting_chapter_id=existing_fact["chapter_id"],
            conflicting_value=existing_fact["value"],
            conflicting_quote=existing_fact["source_quote"],
            contradiction_type=item["contradiction_type"],
            explanation=item["explanation"],
        ))
    return results


def find_contradictions_for_chapter(chapter_id: str, facts: list[Fact]) -> list[Contradiction]:
    """
    Entry point called from /chapters. Groups the new chapter's facts by entity,
    pulls each entity's previously stored facts (excluding this chapter), and
    checks for contradictions per entity. One LLM call per distinct entity that
    already has prior history — entities appearing for the first time cost nothing.
    """
    by_entity: dict[str, list[Fact]] = defaultdict(list)
    for f in facts:
        by_entity[f.entity].append(f)

    all_contradictions: list[Contradiction] = []
    for entity, entity_facts in by_entity.items():
        existing = [
            row for row in get_facts_for_entity(entity)
            if row["chapter_id"] != chapter_id
        ]
        all_contradictions.extend(
            _check_entity_contradictions(chapter_id, entity_facts, existing)
        )
    return all_contradictions

"""
Entity resolution: working out that different names refer to the same thing.

"Marcus", "Marcus Vale" and "Captain Vale" should all be ONE character, so that
facts about each of them get compared with each other.

How a name gets linked, cheapest first:
  1. Known name   – we've seen this exact name before (stored as an alias). Instant, no AI.
  2. AI match     – a new name; the AI compares it with the known entities, using
                    quotes from the chapter and known facts as evidence.
  3. New entity   – nothing matched confidently, so it's someone/something new.

We only accept an AI match when it is confident, because a WRONG merge is worse
than a missed one: merging two different people creates fake "contradictions".
"""
import re
from dataclasses import dataclass
from models import Fact
from llm import call_tool
from storage import find_entities_by_alias, get_all_entities_with_context

MIN_CONFIDENCE_TO_MERGE = 0.7   # AI must be at least this sure to link to a known entity
MAX_KNOWN_TO_SEND_ALL = 150      # small story: show the AI every known entity
MAX_CANDIDATES = 60              # big story: show only the most plausible ones
NAMES_PER_CALL = 40              # how many new names to resolve in one AI call

# Small words that shouldn't count as a "shared word" between two names.
IGNORED_WORDS = {"the", "a", "an", "of", "and", "de", "la", "le", "von", "van"}


@dataclass
class Resolution:
    name: str                       # the name as written in this chapter
    entity_type: str
    existing_entity_id: int | None  # set if linked to an entity we already know
    canonical_name: str             # main name of the entity it belongs to
    method: str                     # "known name" | "AI match" | "new"
    confidence: float

    @property
    def is_new(self) -> bool:
        return self.existing_entity_id is None


RESOLUTION_TOOL = {
    "type": "function",
    "function": {
        "name": "link_names",
        "description": "Decide, for each new name, which known entity it refers to, if any.",
        "parameters": {
            "type": "object",
            "properties": {
                "resolutions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "existing_entity_id": {"type": "integer"},
                            "canonical_name": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["name", "existing_entity_id", "canonical_name", "confidence"],
                    },
                }
            },
            "required": ["resolutions"],
        },
    },
}

RESOLUTION_PROMPT = """You are keeping track of who is who in a novel.

A new chapter mentions the NEW NAMES below. Decide for each one whether it refers to one of
the KNOWN ENTITIES from earlier chapters.

For each new name return:
- existing_entity_id: the [number] of the known entity it refers to, or 0 if it is someone
  or something new.
- canonical_name: the fullest proper name for this entity (e.g. "Marcus Vale" rather than
  "Marcus" or "the captain"). If several NEW names refer to the same new entity, give them
  exactly the same canonical_name so they are grouped together.
- confidence: 0.0 (guess) to 1.0 (certain).

Rules:
- Link only when the quotes and facts make it clear or highly likely.
- A shared surname alone is NOT enough: family members share surnames.
- A title alone ("the captain", "the old man") links only if exactly one known entity fits.
- Never link a person to a place or an item.
- If unsure, use 0. Wrongly merging two different entities is worse than missing a link.

NEW NAMES (name | type | quotes from this chapter):
{new_names}

KNOWN ENTITIES ([number] main name | type | also called | some known facts):
{known_entities}
"""


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in IGNORED_WORDS and len(w) > 1}


def _looks_related(name: str, entity: dict) -> bool:
    """Cheap pre-filter: do the names share a word, or does one word start another (Marc/Marcus)?"""
    name_words = _words(name)
    for alias in [entity["canonical_name"], *entity["aliases"]]:
        for a in _words(alias):
            for n in name_words:
                if a == n or (len(a) >= 3 and len(n) >= 3 and (a.startswith(n) or n.startswith(a))):
                    return True
    return False


def _pick_candidates(names: list[str], known: list[dict]) -> list[dict]:
    """Which known entities to show the AI. Small story: all of them. Big story: likely ones only."""
    if len(known) <= MAX_KNOWN_TO_SEND_ALL:
        return known
    related = [e for e in known if any(_looks_related(n, e) for n in names)]
    return related[:MAX_CANDIDATES]


def _types_compatible(a: str, b: str) -> bool:
    return a == b or "other" in (a, b)


def _format_new_names(batch: list[dict]) -> str:
    return "\n".join(
        f'- {n["name"]} | {n["type"]} | ' + " / ".join(f'"{q}"' for q in n["quotes"])
        for n in batch
    )


def _format_known(candidates: list[dict]) -> str:
    if not candidates:
        return "(none yet)"
    return "\n".join(
        f'[{e["id"]}] {e["canonical_name"]} | {e["entity_type"]} | '
        f'{", ".join(e["aliases"]) or "-"} | {"; ".join(e["sample_facts"]) or "-"}'
        for e in candidates
    )


def resolve_entities(facts: list[Fact]) -> dict[str, Resolution]:
    """
    Returns {lowercase name as written: Resolution} for every name in the chapter.
    Nothing is saved here; saving happens later, all at once, with the rest of the chapter.
    """
    # Collect each distinct name once, with a couple of quotes as evidence.
    names: dict[str, dict] = {}
    for f in facts:
        info = names.setdefault(f.entity.lower(), {"name": f.entity, "type": f.entity_type, "quotes": []})
        if len(info["quotes"]) < 2 and f.source_quote not in info["quotes"]:
            info["quotes"].append(f.source_quote)

    results: dict[str, Resolution] = {}

    # 1. Names we already know: link instantly.
    known_aliases = find_entities_by_alias(list(names))
    unmatched = []
    for key, info in names.items():
        if key in known_aliases:
            entity_id, canonical = known_aliases[key]
            results[key] = Resolution(info["name"], info["type"], entity_id, canonical, "known name", 1.0)
        else:
            unmatched.append(info)

    if not unmatched:
        return results

    known = get_all_entities_with_context()

    # One brand-new name and nothing known yet: nothing to compare with, skip the AI.
    if not known and len(unmatched) == 1:
        info = unmatched[0]
        results[info["name"].lower()] = Resolution(info["name"], info["type"], None, info["name"], "new", 1.0)
        return results

    # 2. Ask the AI about the rest.
    candidates = _pick_candidates([u["name"] for u in unmatched], known)
    candidates_by_id = {e["id"]: e for e in candidates}

    for start in range(0, len(unmatched), NAMES_PER_CALL):
        batch = unmatched[start:start + NAMES_PER_CALL]
        answer = call_tool(
            RESOLUTION_PROMPT.format(new_names=_format_new_names(batch), known_entities=_format_known(candidates)),
            RESOLUTION_TOOL,
            max_tokens=4096,
        )

        decisions: dict[str, tuple[int, str, float]] = {}
        for item in answer.get("resolutions", []):
            try:
                name = str(item["name"]).strip().lower()
                entity_id = int(item.get("existing_entity_id") or 0)
                canonical = " ".join(str(item.get("canonical_name") or "").split())
                confidence = min(max(float(item.get("confidence", 0.5)), 0.0), 1.0)
            except (KeyError, TypeError, ValueError):
                continue
            decisions[name] = (entity_id, canonical, confidence)

        # 3. Check every AI decision before trusting it.
        for info in batch:
            entity_id, canonical, confidence = decisions.get(info["name"].lower(), (0, "", 0.0))
            entity = candidates_by_id.get(entity_id)
            if (
                entity is not None                                       # a real, offered entity
                and confidence >= MIN_CONFIDENCE_TO_MERGE                # confident enough
                and _types_compatible(info["type"], entity["entity_type"])  # person≠place
            ):
                results[info["name"].lower()] = Resolution(
                    info["name"], info["type"], entity_id, entity["canonical_name"], "AI match", confidence
                )
            else:
                results[info["name"].lower()] = Resolution(
                    info["name"], info["type"], None, canonical or info["name"], "new", confidence
                )
    return results

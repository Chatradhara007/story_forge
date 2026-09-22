"""
Entity resolution: working out that different names refer to the same thing.

"Marcus", "Marcus Vale" and "Captain Vale" should all be ONE character, so that
facts about each of them get compared with each other.

How a name gets linked, cheapest first:
  1. Known name   – we've seen this exact name before (stored as an alias). Instant, no AI.
  2. Name match   – one name is the start of the other ("Tobias" / "Tobias Calloway"), or a
                    title + surname matches a full name ("Captain Crane" / "Aldous Crane"),
                    and only one known entity fits. Instant, no AI.
  3. AI match     – a new name; the AI compares it with the known entities, using
                    quotes from the chapter and known facts as evidence.
  4. New entity   – nothing matched confidently, so it's someone/something new.

We only accept an AI match when it is confident, because a WRONG merge is worse
than a missed one: merging two different people creates fake "contradictions".
"""
import re
from dataclasses import dataclass
from models import Fact
from llm import call_tool, JUDGING_THINKING_MODE
from storage import find_entities_by_alias, get_all_entities_with_context

MIN_CONFIDENCE_TO_MERGE = 0.7   # AI must be at least this sure to link to a known entity
MAX_KNOWN_TO_SEND_ALL = 150      # small story: show the AI every known entity
MAX_CANDIDATES = 60              # big story: show only the most plausible ones
NAMES_PER_CALL = 40              # how many new names to resolve in one AI call

# Small words that shouldn't count as a "shared word" between two names.
IGNORED_WORDS = {"the", "a", "an", "of", "and", "de", "la", "le", "von", "van"}

# Titles and descriptions: "Keeper" or "Captain" alone doesn't identify one person.
TITLE_WORDS = {"captain", "keeper", "harbourmaster", "harbormaster", "doctor", "dr", "mr", "mrs",
               "ms", "miss", "lord", "lady", "sir", "king", "queen", "prince", "princess",
               "old", "young", "little", "big", "father", "mother", "uncle", "aunt", "brother",
               "sister", "master", "mistress", "professor", "officer", "sergeant", "general"}


@dataclass
class Resolution:
    name: str                       # the name as written in this chapter
    entity_type: str
    existing_entity_id: int | None  # set if linked to an entity we already know
    canonical_name: str             # main name of the entity it belongs to
    method: str                     # "known name" | "name match" | "AI match" | "new"
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


def _without_article(name: str) -> list[str]:
    """Words of a name without a leading "the"/"a"/"an": "the storm on Friday" -> storm, on, friday."""
    words = name.lower().split()
    while words and words[0] in ("the", "a", "an"):
        words = words[1:]
    return words


def _name_rule_match(name: str, entity_type: str, known: list[dict]) -> dict | None:
    """
    Link without the AI when one name is exactly the START of the other, e.g.
    "Tobias" and "Tobias Calloway", or "Pip Aldane" and "Pip", and exactly one known
    entity of a compatible type fits. Never used when the shared part starts with a
    title ("Keeper", "Captain") or when it's only a surname ("Calloway" alone), so
    family members and titled strangers still go to the AI.
    """
    words = _without_article(name)
    if not words:
        return None
    matches = {}
    for entity in known:
        if not _types_compatible(entity_type, entity["entity_type"]):
            continue
        for alias in [entity["canonical_name"], *entity["aliases"]]:
            other = _without_article(alias)
            if not other or len(other) == len(words):     # a name that's only "the"/"a" matches nothing
                continue
            shorter, longer = (words, other) if len(words) < len(other) else (other, words)
            if (longer[:len(shorter)] == shorter
                    and shorter[0] not in IGNORED_WORDS | TITLE_WORDS
                    and len(shorter[0]) >= 3):
                matches[entity["id"]] = entity
                break
    return next(iter(matches.values())) if len(matches) == 1 else None


def _title_surname_match(name: str, entity_type: str, known: list[dict]) -> dict | None:
    """
    Link a title + surname ("Captain Crane", "Harbourmaster Rudd") with a known full name
    ("Aldous Crane", "Silas Rudd"), or the other way round, but only when exactly ONE known
    entity of a compatible type has that surname. With several people sharing a surname
    ("Keeper Calloway" when Ines, Tobias and Mara are all Calloways) it's left to the AI.
    """
    words = name.lower().split()
    if len(words) < 2:
        return None
    surname = words[-1]
    new_is_titled = len(words) == 2 and words[0] in TITLE_WORDS
    holders: dict[int, dict] = {}
    first_names: dict[int, set] = {}          # the non-title first names each holder is known by
    for entity in known:
        if not _types_compatible(entity_type, entity["entity_type"]):
            continue
        for alias in [entity["canonical_name"], *entity["aliases"]]:
            other = alias.lower().split()
            if len(other) >= 2 and other[-1] == surname:
                holders[entity["id"]] = entity
                if other[0] not in TITLE_WORDS:
                    first_names.setdefault(entity["id"], set()).add(other[0])
    if len(holders) != 1:
        return None
    entity_id, entity = next(iter(holders.items()))
    if new_is_titled:
        return entity            # "Captain Crane" -> the only Crane
    # "Aldous Crane" -> only if the known Crane has no OTHER first name ("Elena Vale" must
    # not join "Marcus Vale", even if he's also known as "Captain Vale")
    known_firsts = first_names.get(entity_id, set())
    if known_firsts - {words[0]}:
        return None
    return entity if not known_firsts or words[0] in known_firsts else None


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


def resolve_entities(project_id: int, facts: list[Fact]) -> dict[str, Resolution]:
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
    known_aliases = find_entities_by_alias(project_id, list(names))
    unmatched = []
    for key, info in names.items():
        if key in known_aliases:
            entity_id, canonical = known_aliases[key]
            results[key] = Resolution(info["name"], info["type"], entity_id, canonical, "known name", 1.0)
        else:
            unmatched.append(info)

    if not unmatched:
        return results

    known = get_all_entities_with_context(project_id)

    # One brand-new name and nothing known yet: nothing to compare with, skip the AI.
    if not known and len(unmatched) == 1:
        info = unmatched[0]
        results[info["name"].lower()] = Resolution(info["name"], info["type"], None, info["name"], "new", 1.0)
        return results

    # 2. Obvious cases by name alone ("Tobias" -> "Tobias Calloway").
    still_unmatched = []
    for info in unmatched:
        entity = (_name_rule_match(info["name"], info["type"], known)
                  or _title_surname_match(info["name"], info["type"], known))
        if entity is not None:
            results[info["name"].lower()] = Resolution(
                info["name"], info["type"], entity["id"], entity["canonical_name"], "name match", 0.9
            )
        else:
            still_unmatched.append(info)
    unmatched = still_unmatched
    if not unmatched:
        return results

    # 3. Ask the AI about the rest.
    candidates = _pick_candidates([u["name"] for u in unmatched], known)
    candidates_by_id = {e["id"]: e for e in candidates}

    for start in range(0, len(unmatched), NAMES_PER_CALL):
        batch = unmatched[start:start + NAMES_PER_CALL]
        answer = call_tool(
            RESOLUTION_PROMPT.format(new_names=_format_new_names(batch), known_entities=_format_known(candidates)),
            RESOLUTION_TOOL,
            max_tokens=4096,
            thinking=JUDGING_THINKING_MODE,
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

        # 4. Check every AI decision before trusting it.
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

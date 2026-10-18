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
import os
import re
import threading
import time
from dataclasses import dataclass
from models import Fact
from llm import call_tool, run_in_parallel, JUDGING_THINKING_MODE, AIServiceError
import storage
from storage import find_entities_by_alias, get_all_entities_with_context

MIN_CONFIDENCE_TO_MERGE = 0.7   # AI must be at least this sure to link to a known entity
MAX_KNOWN_TO_SEND_ALL = 150      # small story: show the AI every known entity
MAX_CANDIDATES = 60              # big story: show only the most plausible ones
# NAME_LINKING=rules skips step 3 (the AI) entirely: names are linked by the name rules and by
# names the story itself states ("his real name was Edwin Marsh"). Much faster on a slow API.
NAME_LINKING = os.getenv("NAME_LINKING", "ai").strip().lower()
# After the AI linking calls fail (an outage), don't ask again for this many seconds: on the free
# tier one outage otherwise costs every following chapter ~10 minutes of timeouts.
LINKING_PAUSE_SECONDS = float(os.getenv("NAME_LINKING_PAUSE", "900"))
_paused_until = [0.0]
_pause_lock = threading.Lock()
NAMES_PER_CALL = 12              # new names per AI call; calls run in parallel (one 40-name call took ~20s on Ultra)

# Small words that shouldn't count as a "shared word" between two names.
IGNORED_WORDS = {"the", "a", "an", "of", "and", "de", "la", "le", "von", "van"}

# Titles and descriptions: "Keeper" or "Captain" alone doesn't identify one person.
TITLE_WORDS = {"captain", "keeper", "harbourmaster", "harbormaster", "doctor", "dr", "mr", "mrs",
               "ms", "miss", "lord", "lady", "sir", "king", "queen", "prince", "princess",
               "old", "young", "little", "big", "father", "mother", "uncle", "aunt", "brother",
               "sister", "master", "mistress", "professor", "officer", "sergeant", "general",
               "duke", "duchess", "baron", "baroness", "emperor", "empress", "abbot", "abbess"}


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


def _without_titles(words: list[str]) -> list[str]:
    while words and words[0] in TITLE_WORDS:
        words = words[1:]
    return words


def _titled_name_match(name: str, entity_type: str, known: list[dict]) -> dict | None:
    """
    Link a titled name with the same name without the title, without the AI:
    "King Aurel" / "Aurel", "Duke Corvin" / "Corvin", "Queen Liesl" / "Liesl Oren". The title
    is set aside and the rest must be the same name (or its start), and exactly one known
    entity of a compatible type may fit. A title alone ("the Keeper") or a bare surname shared
    by a family is never linked this way.
    """
    original = _without_article(name)
    words = _without_titles(original)
    if not words or words[0] in IGNORED_WORDS or len(words[0]) < 3:
        return None
    matches = {}
    for entity in known:
        if not _types_compatible(entity_type, entity["entity_type"]):
            continue
        for alias in [entity["canonical_name"], *entity["aliases"]]:
            other_original = _without_article(alias)
            other = _without_titles(other_original)
            if not other or (len(other) == len(other_original) and len(words) == len(original)):
                continue                          # no title on either side: the other rules decide
            shorter, longer = (words, other) if len(words) <= len(other) else (other, words)
            if longer[:len(shorter)] == shorter:
                matches[entity["id"]] = entity
                break
    if len(matches) != 1:
        return None
    # A single word that is someone's surname ("Calloway") could be anyone in that family.
    if len(words) == 1:
        families = {e["id"] for e in known for alias in [e["canonical_name"], *e["aliases"]]
                    if len(_without_titles(alias.lower().split())) >= 2 and alias.lower().split()[-1] == words[0]}
        if families:
            return None
    return next(iter(matches.values()))


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
    # A full name ("Aldous Crane") links by rule only to someone already known by that SAME
    # first name. If the only Crane is known purely by a title ("Captain Crane"), a full name
    # could be anyone in the family ("Mara Calloway" vs "Keeper Calloway" = Ines), so the AI
    # decides, with the quotes as evidence. ("Elena Vale" must never join "Marcus Vale".)
    known_firsts = first_names.get(entity_id, set())
    return entity if words[0] in known_firsts and not (known_firsts - {words[0]}) else None


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
    Saving happens later, all at once, with the rest of the chapter. The one exception: when
    THIS chapter says two existing entries are one person ("Rook's real name was Edwin
    Marsh"), they're merged now, so the chapter is checked against the combined history.
    """
    results = _resolve_names(project_id, facts)
    _apply_stated_identities(project_id, facts, results)
    prefer_same_chapter_full_names(results)
    join_same_chapter_titled_names(results)
    return results


def join_same_chapter_titled_names(results: dict[str, Resolution]) -> None:
    """
    "King Aurel" and "Aurel" in the SAME chapter are one person. The name rules only compare a
    name with earlier chapters, so when both first appear together they'd become two entries
    for good (later chapters link "Aurel" by its exact name). Join them: onto whichever is
    already known, else both under the titled name. Only when exactly one titled name fits.
    """
    titled = [r for r in results.values()
              if len(_without_article(r.name)) >= 2 and len(_without_titles(_without_article(r.name))) == 1]
    for key, r in list(results.items()):
        words = _without_article(r.name)
        if len(words) != 1 or words[0] in TITLE_WORDS | IGNORED_WORDS or len(words[0]) < 3:
            continue
        matching = [t for t in titled if _without_titles(_without_article(t.name)) == words
                    and _types_compatible(r.entity_type, t.entity_type)]
        if len(matching) != 1:
            continue
        t = matching[0]
        if r.existing_entity_id is not None and t.existing_entity_id is not None:
            continue                                  # both already known: a merge is for the writer
        if (t.existing_entity_id, t.canonical_name.lower()) == (r.existing_entity_id, r.canonical_name.lower()):
            continue
        if r.existing_entity_id is not None:          # "Aurel" known, "King Aurel" new: join Aurel
            results[t.name.lower()] = Resolution(t.name, t.entity_type, r.existing_entity_id, r.canonical_name,
                                                 "name match", 0.9)
        else:                                         # join the titled one (known or both new)
            results[key] = Resolution(r.name, r.entity_type, t.existing_entity_id, t.canonical_name,
                                      "name match", 0.9)


def prefer_same_chapter_full_names(results: dict[str, Resolution]) -> None:
    """
    A bare first name means the full name THIS chapter uses. Two Toms: "Tom Fenner" drowned in
    chapter 2; chapter 5 introduces "Tom Brisk" and then says "Tom". That "Tom" is Tom Brisk,
    not the drowned man the name rule would pick. With two full names starting "Tom" in the
    chapter it's ambiguous, so the link is left as it was.
    """
    full_names = [r for r in results.values() if len(_without_article(r.name)) >= 2]
    for key, r in results.items():
        words = _without_article(r.name)
        if len(words) != 1 or words[0] in TITLE_WORDS:
            continue
        matching = [f for f in full_names if _without_article(f.name)[0] == words[0]
                    and _types_compatible(r.entity_type, f.entity_type)]
        if len(matching) != 1:
            continue
        target = matching[0]
        if (target.existing_entity_id, target.canonical_name.lower()) == (r.existing_entity_id, r.canonical_name.lower()):
            continue
        results[key] = Resolution(r.name, r.entity_type, target.existing_entity_id, target.canonical_name,
                                  "name match", 0.9)


def _apply_stated_identities(project_id: int, facts: list[Fact], results: dict[str, Resolution]) -> None:
    """
    "Rook | real name | Edwin Marsh" in this chapter: Edwin Marsh IS Rook. If Edwin Marsh is
    already a separate entry, it's merged into Rook now (before the chapter is checked, so his
    facts are compared with Rook's); if Edwin Marsh is new in this chapter, it joins Rook.
    """
    for f in facts:
        stated = storage.stated_name(f.attribute, f.value)
        subject = results.get(f.entity.lower())
        if not stated or subject is None or stated.lower() == f.entity.lower():
            continue
        target = results.get(stated.lower())
        target_id = target.existing_entity_id if target else None
        if target is None:
            known = find_entities_by_alias(project_id, [stated]).get(stated.lower())
            target_id = known[0] if known else None
        if subject.existing_entity_id is not None and target_id is not None:
            if target_id == subject.existing_entity_id:
                continue
            keep, other = storage.get_entity(project_id, subject.existing_entity_id), storage.get_entity(project_id, target_id)
            if keep is None or other is None or not _types_compatible(keep["entity_type"], other["entity_type"]):
                continue
            storage.merge_entities(project_id, keep["id"], other["id"])
            print(f"  [names] '{stated}' is {keep['canonical_name']} (the chapter says so): merged", flush=True)
            for key, r in list(results.items()):
                if r.existing_entity_id == other["id"]:
                    results[key] = Resolution(r.name, r.entity_type, keep["id"], keep["canonical_name"], "name match", 0.95)
        elif subject.existing_entity_id is not None and target is not None:
            # A new name in this chapter joins the subject.
            results[stated.lower()] = Resolution(target.name, target.entity_type, subject.existing_entity_id,
                                                 subject.canonical_name, "name match", 0.95)
        elif subject.existing_entity_id is None and target_id is not None:
            entity = storage.get_entity(project_id, target_id)
            if entity and _types_compatible(subject.entity_type, entity["entity_type"]):
                for key, r in list(results.items()):
                    if r.is_new and r.canonical_name.lower() == subject.canonical_name.lower():
                        results[key] = Resolution(r.name, r.entity_type, entity["id"], entity["canonical_name"],
                                                  "name match", 0.95)
        elif target is not None and target.is_new:
            # Both new: one entry, under the subject's name.
            results[stated.lower()] = Resolution(target.name, target.entity_type, None, subject.canonical_name,
                                                 "name match", 0.95)


def _resolve_names(project_id: int, facts: list[Fact]) -> dict[str, Resolution]:
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

    # 2. Obvious cases by name alone ("Tobias" -> "Tobias Calloway"), and names an earlier
    #    chapter said belong to someone ("his real name was Edwin Marsh").
    stated = storage.find_stated_identities(project_id, [u["name"] for u in unmatched])
    by_id = {e["id"]: e for e in known}
    still_unmatched = []
    for info in unmatched:
        claimed = stated.get(info["name"].lower())
        entity = by_id.get(claimed[0]) if claimed else None
        if entity is not None and not _types_compatible(info["type"], entity["entity_type"]):
            entity = None
        entity = (entity
                  or _name_rule_match(info["name"], info["type"], known)
                  or _title_surname_match(info["name"], info["type"], known)
                  or _titled_name_match(info["name"], info["type"], known))
        if entity is not None:
            results[info["name"].lower()] = Resolution(
                info["name"], info["type"], entity["id"], entity["canonical_name"], "name match", 0.9
            )
        else:
            still_unmatched.append(info)
    unmatched = still_unmatched
    if not unmatched:
        return results

    # 3. Ask the AI about the rest (unless switched off, or paused after an outage).
    if NAME_LINKING in ("rules", "off", "no", "false", "0") or time.monotonic() < _paused_until[0]:
        for info in unmatched:
            results[info["name"].lower()] = Resolution(info["name"], info["type"], None, info["name"], "new", 1.0)
        return results
    candidates = _pick_candidates([u["name"] for u in unmatched], known)
    candidates_by_id = {e["id"]: e for e in candidates}

    # The answer is mostly output (one line per name), so smaller batches side by side
    # finish much sooner than one long answer.
    batches = [unmatched[start:start + NAMES_PER_CALL] for start in range(0, len(unmatched), NAMES_PER_CALL)]
    def ask(batch):
        # If every AI model is down, the chapter is NOT lost: the names that need the AI are
        # treated as new for now (the name rules above already linked the easy ones), and the
        # checks done in code still run. Linking can be fixed later with a merge.
        try:
            return call_tool(
                RESOLUTION_PROMPT.format(new_names=_format_new_names(batch), known_entities=_format_known(candidates)),
                RESOLUTION_TOOL,
                max_tokens=4096,
                thinking=JUDGING_THINKING_MODE, role="judge",
            )
        except AIServiceError as error:
            text = str(error)
            if any(k in text for k in ("API key", "check_models", "reembed", "retired")):
                raise                    # a setup problem, not an outage: stop with the clear message
            with _pause_lock:
                first = time.monotonic() >= _paused_until[0]
                if LINKING_PAUSE_SECONDS > 0:
                    _paused_until[0] = time.monotonic() + LINKING_PAUSE_SECONDS
            print(f"  [note] linking names without the AI this time ({len(batch)} names left unlinked): {text}",
                  flush=True)
            if first and LINKING_PAUSE_SECONDS > 0:
                print(f"  [note] the AI is struggling: names are linked by the name rules only for the next "
                      f"{LINKING_PAUSE_SECONDS / 60:.0f} minutes (NAME_LINKING_PAUSE)", flush=True)
            return {"resolutions": []}

    answers = run_in_parallel(ask, batches)

    for batch, answer in zip(batches, answers):
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

    # 5. A "new" entity whose canonical name is already a KNOWN name is not new: the AI gave
    #    the right name but id 0. Link it instead of creating a duplicate "Marcus Vale".
    new_ones = [r for r in results.values() if r.is_new]
    known_canonicals = find_entities_by_alias(project_id, sorted({r.canonical_name for r in new_ones}))
    types_by_id = {e["id"]: e["entity_type"] for e in known}
    for r in new_ones:
        match = known_canonicals.get(r.canonical_name.lower())
        if match and _types_compatible(r.entity_type, types_by_id.get(match[0], r.entity_type)):
            r.existing_entity_id, r.canonical_name, r.method = match[0], match[1], "name match"
    return results

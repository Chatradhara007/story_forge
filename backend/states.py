"""
Lasting states checked in code: what happens to OBJECTS and what a character CAN'T do.

Objects are scattered across entries (the Reader files "turned the signet ring on his finger"
under Aurel, "slid the signet ring onto his own finger" under Corvin, "threw the brass key into
the sea" under Tobias), so objects are followed by NAME through every fact of the book, in
reading order:

  gone      "threw the brass key into the sea", "the green ledger burned to ash"
            -> anyone using it later is a mistake (unless it is found, mended or remembered);
  given     "took the signet ring off his finger and pushed it across the table"
            -> the one who gave it away can't wear or use it later, until it is given back;
  held      "turned his father's signet ring on his finger", "Corvin slid the ring onto his finger"
            -> who has it now.

Abilities a character has lost, from their own entry:

  blind     "nearly blind"           -> later reading, writing or seeing is a mistake;
  lost hand "lost his left hand"     -> later using that hand, or both hands, is a mistake.

Only clear wording counts; memories, hopes and flashbacks never do. A missed warning is
cheaper than a false one, and the AI checker still sees every fact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from models import Contradiction, Fact

CONFIDENCE = 0.85

# Things that exist once and move from hand to hand.
_OBJECT_NOUNS = ("ring", "key", "sword", "crown", "ledger", "locket", "necklace", "amulet", "seal", "dagger",
                 "lens", "map", "medal", "brooch", "pendant", "watch", "diary", "journal", "compass", "talisman",
                 "chalice", "sceptre", "scepter", "pistol", "revolver", "violin", "letter opener")
_OBJECT = re.compile(r"\b(?:(?P<adj>[a-z]+(?:-[a-z]+)?)\s+)?(?P<noun>" + "|".join(_OBJECT_NOUNS) + r")s?\b", re.I)
_NOT_ADJ = {"the", "a", "an", "his", "her", "their", "its", "my", "your", "our", "father's", "mother's", "own",
            "old", "same", "this", "that", "of", "and", "with", "every", "one", "no", "any", "little", "small"}

_MEMORY = re.compile(r"\b(remember\w*|recall\w*|memor\w*|dream\w*|imagin\w*|used to|once had|wish\w*|hop(e|ed|ing)|"
                     r"would have|might have|if only|missed|mourn\w*|picture\w*|thought of)\b", re.I)
_RECOVERED = re.compile(r"\b(found|recovered|retrieved|fished out|dug up|returned|mended|repaired|restored|"
                        r"remade|reforged|rewrote|copied|reassembled|whole again|glued|another|a new|new|second|replica|duplicate)\b", re.I)

_GONE = re.compile(r"\b(threw|thrown|tossed|flung|hurled|dropped|cast)\b[^.]{0,40}\binto the (sea|river|lake|fire|"
                   r"flames|furnace|well|abyss|chasm|harbou?r|ocean|water|deep)\b|"
                   r"\b(burn(ed|t)?_?(to)?_?ash(es)?|burn(ed|t) to (ash|ashes|nothing)|reduced to ash|melted down|"
                   r"destroyed|smashed to pieces|crushed to dust|lost forever|lost for good|sank with)\b|"
                   r"\b(smashed|shattered|crushed|stamped on)\b[^.]{0,40}\b(against|on|under|beneath|to pieces|into pieces|"
                   r"beyond repair)\b", re.I)
_GIVEN = re.compile(r"\boff (his|her|their) finger\b|"
                    r"\b(gave|handed|passed|pushed|slid|surrendered|offered|sold|traded)\b[^.]{0,40}\b(to|toward|towards|"
                    r"across|over to)\b", re.I)
_HELD = re.compile(r"\bon (his|her|their) (own )?finger\b|\b(wore|wears|wearing|turned|twisted|clutched|gripped|"
                   r"carried|carries|drew|unsheathed|brandished|slid [^.]{0,20}onto)\b", re.I)
_USED = re.compile(r"\b(unlocked|unlocks|unlock|opened|opens|read|reads|reading|wrote|writes|turned the pages|"
                   r"looked through|consulted|leafed|wore|wears|wearing|used|uses|using)\b", re.I)


def object_mentions(text: str) -> list[tuple[str, str]]:
    """[(noun, adjective or '')]: 'the old brass key' -> [('key', 'brass')]."""
    found = []
    for m in _OBJECT.finditer(text or ""):
        adj = (m.group("adj") or "").lower()
        if adj in _NOT_ADJ:
            adj = ""
        found.append((m.group("noun").lower(), adj))
    return found


def _same_object(a: tuple[str, str], b: tuple[str, str]) -> bool:
    return a[0] == b[0] and (not a[1] or not b[1] or a[1] == b[1])


@dataclass
class _Object:
    key: tuple[str, str]
    gone: dict | None = None                     # the fact that destroyed / threw it away
    gave_away: dict[int, dict] = field(default_factory=dict)   # entity id -> the fact where they gave it away


def _subject(fact: dict, find_entity) -> int | None:
    """Who does the thing in this fact: the entry it's filed under if that is a person, else the first named person in the quote."""
    if fact.get("entity_type") == "character" and fact.get("entity_id") is not None:
        return fact["entity_id"]
    for name in re.findall(r"\b([A-Z][a-z]{2,})\b", fact.get("source_quote") or ""):
        entity_id = find_entity(name)
        if entity_id is not None:
            return entity_id
    return fact.get("entity_id") if fact.get("entity_type") == "character" else None


def _apply(objects: list[_Object], fact: dict, find_entity) -> list[tuple[str, _Object, dict]]:
    """Update object states from one fact; return [(problem, object, earlier fact)] it reveals."""
    text = f"{fact.get('value') or ''} || {fact.get('source_quote') or ''}"
    plain = text.replace("_", " ")
    problems = []
    mentions = object_mentions(plain)
    if not mentions or _MEMORY.search(plain):
        return problems
    for mention in mentions:
        obj = next((o for o in objects if _same_object(o.key, mention)), None)
        if obj is None:
            obj = _Object(mention if mention[1] else mention)
            objects.append(obj)
        elif mention[1] and not obj.key[1]:
            obj.key = mention
        if _GONE.search(plain):
            obj.gone = fact
            continue
        if obj.gone is not None and (_USED.search(plain) or _HELD.search(plain)) and not _RECOVERED.search(plain):
            problems.append(("gone", obj, obj.gone))
            continue
        who = _subject(fact, find_entity)
        if _GIVEN.search(plain):
            if who is not None:
                obj.gave_away[who] = fact
            continue
        if _HELD.search(plain) or _USED.search(plain):
            if who is not None and who in obj.gave_away and not _RECOVERED.search(plain):
                problems.append(("given", obj, obj.gave_away[who]))
    # A hand-back: someone who holds it gives it away -> everyone who gave it away before may hold it again.
    if _GIVEN.search(plain) and mentions:
        who = _subject(fact, find_entity)
        for obj in objects:
            if any(_same_object(obj.key, m) for m in mentions):
                obj.gave_away = {k: v for k, v in obj.gave_away.items() if k == who}
    return problems


# ------------------------------------------------------------ abilities --
_BLIND = re.compile(r"\b(blind|sightless|lost (his|her|their) sight|could not see|cannot see|can't see)\b", re.I)
_SEEING = re.compile(r"\b(read|reads|reading|wrote|writes|writing|written in (his|her|their) own|saw|sees|"
                     r"recogni[sz]ed (him|her|them) by sight|by sight|watched|studied the)\b", re.I)
_NOT_SEEING = re.compile(r"\b(read to (her|him)|read [^.]{0,40}\bto (her|him|them)\b|had \w+ read|was read|were read|had (it|them|the \w+) read|dictat\w+|by touch|"
                         r"by (his|her) footsteps|could not read|couldn't read|cannot read|blind|felt)\b", re.I)
_LOST_HAND = re.compile(r"\blost (his|her|their|the)? ?(?P<side>left|right) hand\b|\blost[_ ](?P<side2>left|right)[_ ]hand\b", re.I)
_USES_HAND = re.compile(r"\b(both (of )?(his|her|their) hands|both hands|(his|her|their) (?P<side>left|right) hand)\b", re.I)
_HAND_HEDGE = re.compile(r"\b(stump|hook|missing|lost|where (his|her) \w+ hand had been|false hand|wooden hand)\b", re.I)


def _abilities(fact: dict) -> list[tuple[str, str]]:
    """[('blind', ''), ('hand', 'left')] lost abilities this fact states about its own entity."""
    if fact.get("entity_type") not in (None, "character"):
        return []
    text = f"{(fact.get('attribute') or '').replace('_', ' ')} {fact.get('value') or ''}"
    out = []
    attribute = (fact.get("attribute") or "").lower()
    if _BLIND.search(fact.get("value") or "") and re.search(r"(health|condition|status|sight|eye|description|disab|blind)", attribute + " health"):
        if not re.search(r"\b(not|never|no longer|cured|healed)\b", fact.get("value") or "", re.I):
            out.append(("blind", ""))
    m = _LOST_HAND.search(text)
    if m:
        out.append(("hand", (m.group("side") or m.group("side2")).lower()))
    return out


def _violates(kind: str, side: str, fact: Fact) -> bool:
    value, quote = fact.value or "", fact.source_quote or ""
    if _MEMORY.search(value) or _MEMORY.search(quote):
        return False
    if kind == "blind":
        return bool(_SEEING.search(value)) and not _NOT_SEEING.search(value) and not _NOT_SEEING.search(quote)
    if kind == "hand":
        both = f"{value} {quote}"
        if _HAND_HEDGE.search(both):
            return False
        for m in _USES_HAND.finditer(both):
            if m.group("side") is None or m.group("side").lower() == side:
                return True
    return False


# ------------------------------------------------------------------ check --
def check_states(
    chapter_id: str,
    chapter_number: int,
    new_facts: list[tuple[int | None, str, Fact, int]],
    earlier_object_facts: list[dict],
    earlier_facts_for: callable,
    find_entity: callable,
    flashback_chapters: set[int] | None = None,
) -> list[Contradiction]:
    """
    new_facts: [(entity_id, canonical name, fact, index in the chapter), ...] in reading order.
    earlier_object_facts: earlier facts (any entry) that mention an object, in reading order
      (dicts with entity_id, entity_type, entity, attribute, value, source_quote, chapter_id,
      chapter_number, fact_id).
    earlier_facts_for(entity_id): that entity's earlier facts (for lost abilities).
    flashback_chapters: chapter numbers set in the past; they neither change states nor get flagged.
    """
    flashbacks = flashback_chapters or set()
    if chapter_number in flashbacks:
        return []
    found: list[Contradiction] = []
    used = set()

    def warn(entity, fact, index, old, explanation, kind):
        if index in used:
            return
        used.add(index)
        found.append(Contradiction(
            entity=entity, new_chapter_id=chapter_id, new_attribute=fact.attribute, new_value=fact.value,
            new_quote=fact.source_quote, conflicting_chapter_id=old["chapter_id"],
            conflicting_value=old["value"], conflicting_quote=old.get("source_quote") or "",
            contradiction_type="status", confidence=CONFIDENCE, explanation=explanation,
            source="trait check", new_fact_index=index, conflicting_fact_id=old.get("fact_id")))

    # Objects: replay every earlier mention, then this chapter's facts in order.
    objects: list[_Object] = []
    warned_objects: set[tuple[str, str]] = set()          # one warning per object per chapter
    for old in earlier_object_facts:
        if old["chapter_number"] in flashbacks:
            continue
        _apply(objects, old, find_entity)
    for entity_id, canonical, fact, index in new_facts:
        row = {"entity_id": entity_id, "entity_type": fact.entity_type, "entity": fact.entity,
               "attribute": fact.attribute, "value": fact.value, "source_quote": fact.source_quote,
               "chapter_id": chapter_id, "chapter_number": chapter_number, "fact_id": None}
        for problem, obj, old in _apply(objects, row, find_entity):
            if old.get("chapter_number") == chapter_number or obj.key in warned_objects:
                continue                          # both in this chapter: leave it to the checker
            warned_objects.add(obj.key)
            name = " ".join(x for x in (obj.key[1], obj.key[0]) if x)
            if problem == "gone":
                text = (f"The {name} is gone from chapter {old['chapter_number']} (\"{old.get('source_quote') or old['value']}\"), "
                        f"but it is used in chapter {chapter_number}.")
            else:
                text = (f"{canonical} gave the {name} away in chapter {old['chapter_number']} "
                        f"(\"{old.get('source_quote') or old['value']}\"), but has it again in chapter {chapter_number}, "
                        f"with no sign of getting it back.")
            warn(canonical if problem == "given" else name, fact, index, old, text + " (Checked in code.)", problem)

    # Abilities a character has lost.
    lost: dict[int, list[tuple[str, str, dict]]] = {}
    for entity_id, canonical, fact, index in new_facts:
        if entity_id is None or fact.entity_type != "character":
            continue
        if entity_id not in lost:
            lost[entity_id] = [(kind, side, f) for f in earlier_facts_for(entity_id)
                               if f["chapter_number"] not in flashbacks for kind, side in _abilities(f)]
        for kind, side, old in lost[entity_id]:
            if _violates(kind, side, fact):
                what = "is blind" if kind == "blind" else f"lost the {side} hand"
                warn(canonical, fact, index, old,
                     f"{canonical} {what} from chapter {old['chapter_number']} (\"{old.get('source_quote') or old['value']}\"), "
                     f"but in chapter {chapter_number}: {fact.value}. (Checked in code.)", kind)
                break
    return found

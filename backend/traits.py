"""
Fixed traits checked in code: things a character can't change, compared as values, not prose.

The AI checker is shown up to 60 free-text facts per character and misses conflicts that are
plain value clashes: grey eyes then brown eyes, a scar on the left hand then the right, an
older brother then a younger one. Here each such fact is turned into a small typed claim, and
two claims about the same entity clash by a rule:

  eye colour       grey-green  vs  dark brown          (colours share nothing)
  animal colour    grey stallion vs the black stallion (the coat; a white muzzle is ageing)
  side of a mark   scar on the left hand vs right hand  (same mark, same body part, other side)
  handedness       left-handed vs signs with her right hand
  who is older     "her older brother Tobias" vs "Tobias, my younger brother"
  family tie       sister vs cousin                     (relationships.conflict)
  height           a tall, stooping man vs the short captain
  beard            a white beard vs his clean-shaven chin
  boat colour      the red-painted launch vs its blue hull
  where from       born in Varrow and never left vs came to Varrow at nineteen

Claims are only made from clear wording; anything unclear makes no claim (a missed warning is
cheaper than a false one, and the AI checker still sees every fact). Warnings found here go
through the AI double-check like the checker's own, so a misread quote can still be dismissed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from models import Contradiction, Fact
import relationships as rel_rules

CONFIDENCE = 0.85

# ------------------------------------------------------------------ colours --
_COLOURS = {
    "grey": "grey", "gray": "grey", "green": "green", "blue": "blue", "brown": "brown", "hazel": "hazel",
    "amber": "amber", "black": "black", "violet": "violet", "golden": "gold", "gold": "gold",
    "chestnut": "chestnut", "bay": "bay", "white": "white", "red": "red", "roan": "roan", "dun": "dun",
    "silver": "grey", "dappled": "grey", "piebald": "piebald", "palomino": "palomino", "sorrel": "chestnut",
}
_COLOUR = r"(?:grey|gray|green|blue|brown|hazel|amber|black|violet|golden|gold|chestnut|bay|white|red|roan|dun|silver|dappled|piebald|palomino|sorrel)"
_COLOUR_GROUP = rf"(?:(?:dark|light|pale|deep|bright|steel|iron|ice|sea|storm|jet|coal|snow)[- ]?)?{_COLOUR}(?:[- ](?:and[- ])?{_COLOUR})*"
_ANIMAL = r"(?:stallion|mare|horse|gelding|pony|colt|filly|mount|hound|dog|cat|mule|ox|bull|cow|wolfhound|mastiff|bitch|tomcat)"
_VESSEL = r"(?:launch|boat|ship|skiff|barge|cutter|ketch|sloop|schooner|galley|dinghy|rowboat|ferry|hull|carriage|coach|wagon|cart)"
_CHANGE = re.compile(r"\b(dyed|dye|painted|repainted|bleached|greying|graying|turned|turning|faded|fading|whitening|"
                     r"around the muzzle|at the muzzle|muzzle|grey coming|going grey|in the light|seemed|looked)\b", re.I)


def _colours(text: str) -> set[str]:
    return {_COLOURS[w] for w in re.findall(_COLOUR, text.lower())}


def eye_colours(attribute: str, value: str) -> set[str]:
    """'grey-green eyes' -> {grey, green}; attribute 'eye color' + 'green' -> {green}."""
    text = f"{attribute} {value}".lower()
    if _CHANGE.search(value or ""):
        return set()
    m = re.search(rf"({_COLOUR_GROUP})[- ]eyed\b|({_COLOUR_GROUP})\s+eyes\b", text)
    if m:
        return _colours(m.group(1) or m.group(2))
    if re.search(r"\beyes?\b", (attribute or "").lower()) and len(value or "") < 40:
        return _colours(value)
    return set()


def quoted_eye_colours(entity: str, quote: str) -> set[str]:
    """"Thessaly's dark brown eyes filled" on Thessaly's own entry -> {brown}. Only her own eyes."""
    first = entity.split()[-1] if entity.split() else ""
    names = {w for w in entity.split() if w[:1].isupper()} | ({first} if first[:1].isupper() else set())
    if not names or _CHANGE.search(quote or ""):
        return set()
    for name in names:
        m = re.search(rf"\b{re.escape(name)}'s\s+({_COLOUR_GROUP})\s+eyes\b", quote or "", re.I)
        if m:
            return _colours(m.group(1))
    return set()


def animal_colour_claims(entity: str, attribute: str, value: str) -> list[tuple[str, set[str]]]:
    """
    [(animal's name, colours)]: "Ember, the black stallion" -> [("Ember", {black})];
    on the animal's own entry, "type | grey stallion" -> [(entity, {grey})].
    """
    if _CHANGE.search(value or ""):
        return []
    claims = []
    for m in re.finditer(rf"\b([A-Z][a-z]+),?\s+(?:the|a|an|his|her|their|my)\s+(?:[\w']+\s+){{0,3}}?({_COLOUR_GROUP})\s+{_ANIMAL}\b", value or ""):
        claims.append((m.group(1), _colours(m.group(2))))
    for m in re.finditer(rf"\b({_COLOUR_GROUP})\s+{_ANIMAL}\s+(?:called|named)\s+([A-Z][a-z]+)", value or ""):
        claims.append((m.group(2), _colours(m.group(1))))
    if not claims:
        m = re.fullmatch(rf"\s*(?:an?\s+|the\s+)?(?:old\s+|young\s+|big\s+|great\s+)?({_COLOUR_GROUP})\s+{_ANIMAL}\s*", value or "", re.I)
        if m:
            claims.append((entity, _colours(m.group(1))))
    return [(name, colours) for name, colours in claims if colours]


def vessel_colours(entity_type: str, value: str, quote: str) -> set[str]:
    """
    A boat's (or cart's) own colour, on its own entry: "blue hull freshly scrubbed",
    "the harbour's little red-painted launch". Never on a person's entry (they may ride in it).
    """
    if (entity_type or "").lower() == "character":
        return set()
    for text in (value or "", quote or ""):
        if re.search(r"\b(repaint\w*|new coat of paint|fresh(?:ly)? painted|painted (?:it|her|him|over))\b", text, re.I):
            return set()
        found = [m.group(1) for m in re.finditer(rf"\b({_COLOUR_GROUP})(?:-painted| painted)?\s+{_VESSEL}\b", text, re.I)]
        colours = set().union(*(_colours(f) for f in found)) if found else set()
        if colours:
            return colours if len(found) == 1 else set()      # two boats in one sentence: unclear
    return set()


_DESCRIBES_BODY = re.compile(r"\b(physical|appearance|description|describ|build|height|looks?|figure|stature|body)", re.I)
_STATURE = re.compile(r"\b(tall|short)\b(?![- ](?:of|time|while|walk|distance|story|notice|tempered|lived|haired|hair|"
                      r"beard|sword|bow|glass|ships?|grass|tale|list|way|stop|breath|supply|step|steps|trip|reply|answer|"
                      r"laugh|sleeves?|cloak|coat|skirt|knife|blade|staff|candle|order|work))", re.I)


def stature(attribute: str, value: str) -> str | None:
    """'tall, stooping man' -> 'tall'; 'short captain had to stand on his toes' -> 'short'. Grown-ups only."""
    if not _DESCRIBES_BODY.search((attribute or "").replace("_", " ")):
        return None
    text = value or ""
    if re.search(r"\b(not|neither|nor|boy|girl|child|lad|lass|baby|grew|grown|growing|shrunk|shrank|stooped with age)\b", text, re.I):
        return None
    found = {m.group(1).lower() for m in _STATURE.finditer(text)}
    return found.pop() if len(found) == 1 else None


_BEARDED = re.compile(r"\b(bearded|(?:with|has|had|wore|wears|his|a|an|long|white|grey|gray|black|red|brown|thick|full|"
                      r"bushy|forked|short|neat|trimmed)\b[^.;]{0,25}?\bbeard)\b", re.I)
_SHAVEN = re.compile(r"\b(clean[- ]shaven|beardless|smooth[- ]chinned|smooth[- ]shaven)\b", re.I)
_BEARD_CHANGE = re.compile(r"\b(shaved|shaving|shave off|grew|grow|growing|grown|stubble|trimmed off|razor|"
                           r"for the first time|no longer|used to)\b", re.I)


def beard(attribute: str, value: str) -> str | None:
    """'a broad man with a white beard' -> 'bearded'; 'rubbing his clean-shaven chin' -> 'clean-shaven'."""
    text = value or ""
    if _BEARD_CHANGE.search(text) or re.search(r"\b\w+'s\b[^.;]{0,15}\bbeard", text):
        return None                                   # shaving it off, or someone else's beard
    shaven, bearded = bool(_SHAVEN.search(text)), bool(_BEARDED.search(text))
    if shaven != bearded:
        return "clean-shaven" if shaven else "bearded"
    return None


# --------------------------------------------------------- sides and hands --
_MARK = r"(scar|scarred|burn|burned|burnt|tattoo|birthmark|brand|branded|mole|wound|missing (?:two |three |\w+ )?fingers?|lost (?:two |three |\w+ )?fingers?|lost (?:his |her |their )?(?:left |right )?(?:hand|arm|eye|leg|foot))"
_REGIONS = {"hand": "hand", "palm": "hand", "wrist": "hand", "finger": "hand", "fingers": "hand", "thumb": "hand",
            "knuckle": "hand", "knuckles": "hand", "cheek": "face", "temple": "face", "brow": "face", "eyebrow": "face",
            "eye": "eye", "ear": "ear", "arm": "arm", "forearm": "arm", "elbow": "arm", "shoulder": "shoulder",
            "leg": "leg", "thigh": "leg", "knee": "leg", "shin": "leg", "foot": "foot", "ankle": "foot", "side": "side"}
_SIDE_PART = re.compile(r"\b(left|right)[- ](hand|palm|wrist|fingers?|thumb|knuckles?|cheek|temple|brow|eyebrow|eye|ear|"
                        r"arm|forearm|elbow|shoulder|leg|thigh|knee|shin|foot|ankle|side)\b", re.I)
_NEGATED = re.compile(r"\b(no|without|unmarked|unscarred|not yet|never had|free of|smooth)\b", re.I)


def mark_sides(attribute: str, value: str) -> list[tuple[str, str, str]]:
    """[(mark, body region, side)]: 'scar across the back of his left hand' -> [('scar', 'hand', 'left')]."""
    text = f"{attribute.replace('_', ' ')} {value}"
    marks = re.findall(_MARK, text, re.I)
    if not marks or _NEGATED.search(text):
        return []
    mark = marks[0].lower()
    mark = ("scar" if mark.startswith("scar") else "burn" if mark.startswith("burn") else
            "lost" if mark.startswith(("lost", "missing")) else mark.split()[0])
    found = []
    for m in _SIDE_PART.finditer(text):
        found.append((mark, _REGIONS[m.group(2).lower()], m.group(1).lower()))
    sides = {f[2] for f in found}
    return found if len(sides) == 1 else []          # both sides in one fact: unclear


_HANDED = re.compile(r"\b(left|right)[- ]handed\b", re.I)
_USES_HAND = re.compile(r"\b(writes?|wrote|writing|signs?|signed|signing|draws?|drew|throws?|threw|eats?|ate|"
                        r"fights?|fought|holds? (?:a|the|her|his) (?:pen|quill|sword|brush))\b[^.]{0,30}?\b"
                        r"(?:with|in) (?:his|her|their) (left|right) hand", re.I)


def handedness(attribute: str, value: str) -> str | None:
    """'left-handed' -> 'left'; 'signed the lease with her right hand, as she always had' -> 'right'."""
    text = f"{attribute.replace('_', ' ')} {value}"
    if m := _HANDED.search(text):
        return m.group(1).lower()
    if m := _USES_HAND.search(text):
        return m.group(2).lower()
    if "handed" in (attribute or "").lower() and (m := re.fullmatch(r"\s*(left|right)(?:[- ]hand(?:ed)?)?\s*", value or "", re.I)):
        return m.group(1).lower()
    return None


# ---------------------------------------------------------- who is older --
_ORDER_WORDS = {"older": "older", "elder": "older", "eldest": "older", "oldest": "older", "big": "older",
                "younger": "younger", "youngest": "younger", "little": "younger", "baby": "younger", "kid": "younger"}
_SIBLING_PHRASE = re.compile(r"\b(older|elder|eldest|oldest|big|younger|youngest|little|baby|kid) (brother|sister|sibling)\b", re.I)
_THAN = re.compile(r"\b(?:\w+ years? |a few years |some years |a year |much |a little )?(younger|older|elder) than ([A-Z][\w'-]*(?: [A-Z][\w'-]*)*|him|her|them|me|you)\b")
_PRONOUN = {"him", "her", "them", "me", "you"}


@dataclass
class Order:
    older: str            # names as written
    younger: str


def _first(name: str) -> str:
    return name.split()[0].lower() if name.split() else ""


def order_claims(entity: str, attribute: str, value: str, quote: str) -> list[Order]:
    """Who is older, from one fact. Only clear wording makes a claim."""
    claims = []
    attr = (attribute or "").replace("_", " ")
    # "Corvin | age_difference | two years younger than Aurel", "Mira | age relative to Aurel | four years younger than him"
    for m in _THAN.finditer(value or ""):
        other = m.group(2)
        if other.lower() in _PRONOUN:
            ref = re.search(r"\b(?:relative to|than|to|vs|versus)\s+([A-Z][\w'-]*)", attr)
            if not ref:
                continue
            other = ref.group(1)
        older, younger = (entity, other) if m.group(1) in ("older", "elder") else (other, entity)
        claims.append(Order(older, younger))
    # "Ines | relationship | sibling of Tobias" with quote "Her older brother Tobias": who is the brother?
    rel = re.match(r"^sibling of (.+)$", (value or "").strip(), re.I)
    if rel and (attr.lower().startswith("relation")):
        other = rel.group(1).strip()
        phrase = _SIBLING_PHRASE.search(other)
        if phrase:                                    # "sibling of elder sister of Aurel"
            who = other
        else:
            who = _who_is_described(quote or "", entity, other)
        if who:
            direction = _ORDER_WORDS[(phrase or _SIBLING_PHRASE.search(quote or "")).group(1).lower()]
            rest = entity if who == other else other
            claims.append(Order(who, rest) if direction == "older" else Order(rest, who))
    # "Rose Halloway | relation | Orla's younger sister"
    possessive = re.search(r"\b([A-Z][\w-]*)'s (older|elder|eldest|oldest|big|younger|youngest|little|baby) (brother|sister|sibling)\b", value or "")
    if possessive and possessive.group(1).lower() != _first(entity):
        direction = _ORDER_WORDS[possessive.group(2).lower()]
        claims.append(Order(entity, possessive.group(1)) if direction == "older" else Order(possessive.group(1), entity))
    return claims


def _who_is_described(quote: str, a: str, b: str) -> str | None:
    """In 'Her older brother Tobias' or 'Tobias, my younger brother', which of a, b is the brother?"""
    m = _SIBLING_PHRASE.search(quote)
    if not m:
        return None
    after = quote[m.end():m.end() + 30]
    before = quote[max(0, m.start() - 30):m.start()]
    hits = []
    for name in (a, b):
        first = re.escape(name.split()[0]) if name.split() else None
        if not first:
            continue
        if re.match(rf"^[,\s]*(?:was\s+|is\s+|named\s+|called\s+)?{first}\b", after):
            hits.append(name)
        elif re.search(rf"\b{first}\b[,\s]+(?:was\s+|is\s+)?(?:my|his|her|their|our|the)\s*$", before):
            hits.append(name)
    return hits[0] if len(hits) == 1 else None


# ------------------------------------------------------------- family ties --
_SPECIFIC_RELATIVE = re.compile(r"\b(cousin|uncle|aunt|niece|nephew|grand\w*|in-law)\b", re.I)
_LABEL_KIND = {label: kind for kind, label in rel_rules.LABELS.items()}
_LABEL_KIND.update({label: kind for kind, label in rel_rules.INVERSE_LABELS.items()})


_KIN_WORD = re.compile(r"\b(father|mother|son|sons|daughter|daughters|sister|sisters|brother|brothers|sibling|siblings|"
                       r"parent|parents|child|children|twin|cousin|uncle|aunt|niece|nephew|grand\w*|"
                       r"\w+-in-law|mum|mama|papa|da|dad|ma|pa|heir|kin|wife|husband|widow|widower)\b", re.I)


def family_tie(attribute: str, value: str, quote: str) -> tuple[str, str, bool] | None:
    """
    'relationship | sibling of Tobias' -> ('sibling', 'Tobias', forward). Only family kinds, and
    only when the quote itself names a family tie: "Her blind eyes looked somewhere past him"
    filed as "parent of Oren" is the Reader guessing, not the story saying it.
    """
    if not (attribute or "").lower().startswith("relation"):
        return None
    if not _KIN_WORD.search(quote or ""):
        return None
    for label, kind in sorted(_LABEL_KIND.items(), key=lambda item: -len(item[0])):
        if (value or "").lower().startswith(label + " ") and kind in rel_rules.FAMILY:
            other = value[len(label) + 1:].strip()
            if kind == "relative" and not _SPECIFIC_RELATIVE.search(quote or ""):
                return None                         # "related to" is too vague to clash with anything
            forward = label != rel_rules.INVERSE_LABELS.get(kind) or kind not in rel_rules.DIRECTIONAL
            return kind, other, forward
    return None


_DESCRIPTION = re.compile(r"^(his|her|their|my|our|your|its|the|a|an|one|some|every|each)\b", re.I)


def _is_name(name: str) -> bool:
    """'Tobias' or 'elder sister of Aurel' are usable; 'his son', 'the boy' are descriptions."""
    return bool(name) and not _DESCRIPTION.match(name.strip())


# ------------------------------------------------------------------ check --
def _claims(entity_id: int | None, name: str, attribute: str, value: str, quote: str, find,
            specific_kin: str | None = None, entity_type: str = "") -> list[tuple]:
    """
    Every typed claim in one fact: (kind, key, value) where key names the entities involved.
    specific_kin: a kin word ("cousin") this entity's other facts in the same chapter give,
    for a vague "related to X".
    """
    out = []
    if entity_id is not None:
        colours = eye_colours(attribute, value) or quoted_eye_colours(name, quote)
        if colours:
            out.append(("eyes", (entity_id,), frozenset(colours)))
        for mark, region, side in mark_sides(attribute, value):
            out.append(("side", (entity_id, mark, region), side))
        if hand := handedness(attribute, value):
            out.append(("hand", (entity_id,), hand))
        tie = family_tie(attribute, value, f"{quote} {specific_kin or ''}") if _is_name(name) else None
        if tie and _is_name(tie[1]):
            kind, other, forward = tie
            other_id = find(other)
            if other_id is not None and other_id != entity_id:
                a, b = sorted((entity_id, other_id))
                out.append(("family", (a, b), (kind, forward == (a == entity_id))))
    if entity_id is not None:
        if height := stature(attribute, value):
            out.append(("height", (entity_id,), height))
        if has_beard := beard(attribute, value):
            out.append(("beard", (entity_id,), has_beard))
        if paint := vessel_colours(entity_type, value, quote):
            out.append(("paint", (entity_id,), frozenset(paint)))
    for animal, colours in animal_colour_claims(name, attribute, value):
        animal_id = entity_id if animal == name else find(animal)
        if animal_id is not None:
            out.append(("coat", (animal_id,), frozenset(colours)))
    for order in order_claims(name, attribute, value, quote):
        if not (_is_name(order.older) and _is_name(order.younger)):
            continue
        older = entity_id if order.older == name else find(order.older)
        younger = entity_id if order.younger == name else find(order.younger)
        if older is not None and younger is not None and older != younger:
            a, b = sorted((older, younger))
            out.append(("order", (a, b), older))
    return out


def _clash(kind: str, old, new) -> bool:
    if kind in ("eyes", "coat", "paint"):
        return not (old & new)
    if kind == "family":
        (old_kind, old_dir), (new_kind, new_dir) = old, new
        return rel_rules.conflict(old_kind, new_kind, old_dir == new_dir)
    return old != new


_WHAT = {"eyes": "eye colour", "coat": "colour", "side": "side", "hand": "handedness",
         "order": "older/younger order", "family": "family tie", "height": "height", "beard": "beard",
         "paint": "colour"}


def _say(kind: str, key: tuple, value, names: dict) -> str:
    """The claim in a few words: 'grey-green', 'left hand', 'Tobias is the older'."""
    if kind in ("eyes", "coat", "paint"):
        return " / ".join(sorted(value))
    if kind == "side":
        return f"{value} {key[2]}"
    if kind == "hand":
        return f"{value}-handed"
    if kind == "order":
        return f"{names.get(value, 'the first')} is the older"
    if kind == "family":
        return {"relative": "relatives (cousin, aunt...)", "parent": "parent and child"}.get(value[0], value[0] + "s")
    return str(value)


_KIN_DESCRIPTION = re.compile(r"^(?:(?:the|his|her|my|their)\s+)?(?:elder|older|eldest|oldest|younger|youngest|little|big|"
                              r"baby|twin)?\s*(sister|brother|sibling) of (.+)$", re.I)


def _with_kin_descriptions(find_entity, earlier_facts_for, new_facts):
    """
    "elder sister of Aurel" is the Reader's name for someone the story already introduced: if
    Aurel has exactly one known sibling, it is them (Mira). Otherwise the description stays its own entry.
    """
    def resolve(name: str):
        entity_id = find_entity(name)
        m = _KIN_DESCRIPTION.match((name or "").strip())
        if not m:
            return entity_id
        of = find_entity(m.group(2).strip())
        if of is None:
            return entity_id
        siblings = set()
        for f in earlier_facts_for(of):
            value = (f.get("value") or "").strip()
            if (f.get("attribute") or "").lower().startswith("relation") and value.lower().startswith("sibling of "):
                other = value[len("sibling of "):].strip()
                if not _KIN_DESCRIPTION.match(other):
                    sibling = find_entity(other)
                    if sibling is not None and sibling != of:
                        siblings.add(sibling)
        return siblings.pop() if len(siblings) == 1 else entity_id
    return resolve


def check_traits(
    chapter_id: str,
    chapter_number: int,
    new_facts: list[tuple[int | None, str, Fact, int]],
    earlier_facts_for: callable,
    find_entity: callable,
) -> list[Contradiction]:
    """
    new_facts: [(entity_id, canonical name, fact, index in the chapter), ...]
    earlier_facts_for(entity_id) -> the entity's facts from EARLIER chapters (dicts with
      entity_id, entity, attribute, value, source_quote, chapter_id, chapter_number, fact_id).
    find_entity(name) -> entity id for a name, or None.
    """
    find_entity = _with_kin_descriptions(find_entity, earlier_facts_for, new_facts)
    names = {}
    for entity_id, canonical, _, _ in new_facts:
        if entity_id is not None:
            names[entity_id] = canonical
    # "Rose | relation | cousin" + "Rose | relationship | related to Orla": Rose is Orla's cousin.
    kin_words: dict[int, set[str]] = {}
    vague_ties: dict[int, int] = {}
    for entity_id, _, fact, _ in new_facts:
        if entity_id is None or not (fact.attribute or "").lower().startswith("relation"):
            continue
        if fact.value.lower().startswith("related to "):
            vague_ties[entity_id] = vague_ties.get(entity_id, 0) + 1
        elif len(fact.value) < 40 and (m := _SPECIFIC_RELATIVE.search(fact.value)):
            kin_words.setdefault(entity_id, set()).add(m.group(1).lower())
    specific = {eid: next(iter(words)) for eid, words in kin_words.items()
                if len(words) == 1 and vague_ties.get(eid) == 1}

    new_claims = []
    for entity_id, canonical, fact, index in new_facts:
        for claim in _claims(entity_id, fact.entity, fact.attribute, fact.value, fact.source_quote, find_entity,
                             specific.get(entity_id), fact.entity_type):
            new_claims.append((claim, fact, index))
    changes = check_changes(chapter_id, chapter_number, new_facts, earlier_facts_for)
    if not new_claims:
        return changes

    involved = {eid for (kind, key, _), _, _ in new_claims for eid in key if isinstance(eid, int)}
    earlier_claims = []
    seen_facts = set()
    for eid in involved:
        for f in earlier_facts_for(eid):
            if f.get("fact_id") in seen_facts:
                continue
            seen_facts.add(f.get("fact_id"))
            for claim in _claims(f.get("entity_id", eid), f["entity"], f["attribute"], f["value"],
                                 f.get("source_quote") or "", find_entity, None, f.get("entity_type") or ""):
                earlier_claims.append((claim, f))

    found: list[Contradiction] = []
    used_new, used_old = set(), set()
    for (kind, key, value), fact, index in new_claims:
        if index in used_new:
            continue
        clashes = [(f, old) for (k, old_key, old), f in earlier_claims if k == kind and old_key == key and _clash(kind, old, value)]
        agrees = [f for (k, old_key, old), f in earlier_claims if k == kind and old_key == key and not _clash(kind, old, value)]
        if not clashes:
            continue
        old_fact, old_value = clashes[-1]
        if old_fact.get("fact_id") in used_old:
            continue
        label = dict(names)
        label.setdefault(old_fact.get("entity_id"), old_fact.get("canonical_name") or old_fact["entity"])
        # The most recent earlier statement agrees with the new one: the clash is with an
        # older, already-superseded statement; leave it to the checker.
        if agrees and agrees[-1]["chapter_number"] > old_fact["chapter_number"]:
            continue
        used_new.add(index)
        used_old.add(old_fact.get("fact_id"))
        entity_id = key[0] if kind != "order" else value
        who = names.get(entity_id) or old_fact.get("canonical_name") or old_fact["entity"]
        if kind == "order":
            who = f"{names.get(key[0], '')} / {names.get(key[1], '')}".strip(" /") or who
        new_value = fact.value
        kin = specific.get(entity_id) if kind == "family" else None
        if kin is None and kind == "family":
            kin = specific.get(key[1]) if key[1] != entity_id else None
        if kin and new_value.lower().startswith("related to "):
            new_value = f"{kin} of {new_value[len('related to '):]}"      # say which kind of relative
        found.append(Contradiction(
            entity=who,
            new_chapter_id=chapter_id,
            new_attribute=fact.attribute,
            new_value=new_value,
            new_quote=fact.source_quote,
            conflicting_chapter_id=old_fact["chapter_id"],
            conflicting_value=old_fact["value"],
            conflicting_quote=old_fact.get("source_quote") or "",
            contradiction_type="attribute",
            confidence=CONFIDENCE,
            explanation=(f"The {_WHAT[kind]} doesn't match: chapter {old_fact['chapter_number']} has "
                         f"{_say(kind, key, old_value, label)}, chapter {chapter_number} has "
                         f"{_say(kind, key, value, label)}. (Checked in code: {_WHAT[kind]} can't simply change.)"),
            source="trait check",
            new_fact_index=index,
            conflicting_fact_id=old_fact.get("fact_id"),
        ))
    taken = {c.new_fact_index for c in found}
    return found + [c for c in changes if c.new_fact_index not in taken]


# -------------------------------------------------- mended, and where from --
_MENDED = re.compile(r"\b(whole (?:and seamless )?again|mended|repaired|made whole|seamless|good as new|"
                     r"fixed|restored|sealed (?:together|whole))\b", re.I)
_STILL_BROKEN = re.compile(r"\bstill (cracked|broken|shattered|split|in pieces|damaged|chipped)\b|"
                           r"\b(cracked|broken|shattered)\b[^.]{0,40}\b(as it had been|ever since|since the)\b", re.I)
_BROKE_AGAIN = re.compile(r"\b(broke|shattered|smashed|cracked|dropped|split)\b", re.I)
_NEVER_LEFT = re.compile(r"\bnever (?:once |ever )?(?:left|been away from|set foot outside)\b", re.I)
_BORN_IN = re.compile(r"\bborn (?:in|at) ([A-Z][\w'-]+(?: [A-Z][\w'-]+)?)")
_CAME_TO = re.compile(r"\b(?:came|come|arrived|moved|went|travell?ed)\s+(?:back\s+)?(?:to|in|into)\s+([A-Z][\w'-]+(?: [A-Z][\w'-]+)?)")


def _text(f) -> str:
    if isinstance(f, Fact):
        return f"{f.value} {f.source_quote}"
    return f"{f.get('value') or ''} {f.get('source_quote') or ''}"


def native_place(f) -> str | None:
    """'Orla had been born in Varrow and had never once left it.' -> 'Varrow'."""
    quote = f.source_quote if isinstance(f, Fact) else (f.get("source_quote") or "")
    for sentence in re.split(r"(?<=[.!?])\s+", quote):
        m = _BORN_IN.search(sentence)
        if m and _NEVER_LEFT.search(sentence):
            return m.group(1)
    return None


def arrival_place(f) -> str | None:
    """'She had come to Varrow as a girl of nineteen' / 'arrival location | Varrow' -> 'Varrow'."""
    attribute = f.attribute if isinstance(f, Fact) else (f.get("attribute") or "")
    value = f.value if isinstance(f, Fact) else (f.get("value") or "")
    if re.search(r"arriv|came to|moved to|origin of travel", attribute, re.I) and re.fullmatch(r"\s*[A-Z][\w' -]{1,40}", value or ""):
        return value.strip()
    m = _CAME_TO.search(_text(f))
    return m.group(1) if m else None


def check_changes(chapter_id: str, chapter_number: int, new_facts, earlier_facts_for) -> list[Contradiction]:
    """Mended earlier but 'still cracked' now; born somewhere and never left, but 'came to' it later."""
    found = []
    reported = set()
    for entity_id, canonical, fact, index in new_facts:
        if entity_id is None or entity_id in reported:
            continue
        earlier = earlier_facts_for(entity_id)
        if not earlier:
            continue
        if _STILL_BROKEN.search(fact.source_quote or "") or _STILL_BROKEN.search(fact.value or ""):
            mends = [f for f in earlier if _MENDED.search(_text(f))]
            if mends:
                mend = mends[-1]
                broke_since = [f for f in earlier if f["chapter_number"] > mend["chapter_number"]
                               and _BROKE_AGAIN.search(_text(f)) and not _MENDED.search(_text(f))]
                if not broke_since:
                    reported.add(entity_id)
                    found.append(_change(chapter_id, canonical, fact, index, mend, "status",
                                         f"{canonical} was mended in chapter {mend['chapter_number']} "
                                         f"(\"{(mend.get('source_quote') or mend['value'])[:160]}\"), but in chapter "
                                         f"{chapter_number} it is still broken, with nothing breaking it again. (Checked in code.)"))
                    continue
        place = arrival_place(fact)
        if place:
            natives = [f for f in earlier if (native_place(f) or "").lower() == place.lower()]
            if natives:
                old = natives[-1]
                reported.add(entity_id)
                found.append(_change(chapter_id, canonical, fact, index, old, "attribute",
                                     f"{canonical} was born in {place} and never left it (chapter "
                                     f"{old['chapter_number']}), but in chapter {chapter_number} comes to {place} from "
                                     f"somewhere else. (Checked in code.)"))
    return found


def _change(chapter_id, canonical, fact, index, old, kind, explanation) -> Contradiction:
    return Contradiction(
        entity=canonical, new_chapter_id=chapter_id, new_attribute=fact.attribute, new_value=fact.value,
        new_quote=fact.source_quote, conflicting_chapter_id=old["chapter_id"], conflicting_value=old["value"],
        conflicting_quote=old.get("source_quote") or "", contradiction_type=kind, confidence=CONFIDENCE,
        explanation=explanation, source="trait check", new_fact_index=index, conflicting_fact_id=old.get("fact_id"),
    )

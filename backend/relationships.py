"""
Relationships between characters, for the family tree and the relationship web.

The AI describes a relationship in its own words ("father of", "Ines's husband", "sworn
enemy"). Here that wording is turned into a small fixed set of kinds, so the charts can draw
it and code can spot impossible combinations (sisters in chapter 1, cousins in chapter 5).

Directional kinds read "FROM is the ___ of TO": parent, mentor, employer.
Everything else is symmetric.
"""
import re
from models import Relationship

FAMILY = {"parent", "spouse", "sibling", "relative"}
SOCIAL = {"friend", "ally", "rival", "enemy", "mentor", "employer", "romance"}
KINDS = FAMILY | SOCIAL
DIRECTIONAL = {"parent", "mentor", "employer"}
LABELS = {"parent": "parent of", "spouse": "married to", "sibling": "sibling of", "relative": "related to",
          "friend": "friends with", "ally": "allied with", "rival": "rival of", "enemy": "enemy of",
          "mentor": "mentor of", "employer": "employs", "romance": "in love with"}

# How the OTHER person sees it: "Ines parent of Rook" -> Rook is "child of" Ines.
INVERSE_LABELS = {**LABELS, "parent": "child of", "mentor": "student of", "employer": "works for"}

# (pattern, kind, reversed?) checked in order. reversed = the text names the OTHER direction
# ("child of X" means X is the parent).
_RULES = [
    (r"\b(grand|great)", "relative", False),
    (r"\b(father|mother|parent|dad|mum|mom)\b", "parent", False),
    (r"\b(son|daughter|child)\b", "parent", True),
    (r"\b(husband|wife|spouse|married|widow(er)?)\b", "spouse", False),
    (r"\b(brother|sister|sibling|twin)\b", "sibling", False),
    (r"\b(cousin|uncle|aunt|niece|nephew|in-law|relative|kin|related)\b", "relative", False),
    (r"\b(betrothed|fianc|lover|sweetheart|in love|beloved|romance)\b", "romance", False),
    (r"\b(apprentice|student|pupil|protege|protégé|trained by|mentored by)\b", "mentor", True),
    (r"\b(mentor|teacher|master of|trains|tutor)\b", "mentor", False),
    (r"\b(servant|employee|works for|worked for|crew of|serves|maid|steward of)\b", "employer", True),
    (r"\b(employer|employs|boss|captain of|master)\b", "employer", False),
    (r"\b(enemy|enemies|nemesis|foe|hates)\b", "enemy", False),
    (r"\b(rival|rivals|competitor)\b", "rival", False),
    (r"\b(ally|allies|allied|partner)\b", "ally", False),
    (r"\b(friend|friends|companion|confidant)\b", "friend", False),
]


def normalise(person: str, other: str, relation: str, quote: str, confidence: float = 0.8) -> Relationship | None:
    """
    "Rook | son | Ines" -> Ines parent Rook. Unrecognised wording returns None (it stays a
    plain fact, so nothing is lost).
    The AI's relation reads "PERSON is the ___ of OTHER".
    """
    person, other = " ".join(person.split()), " ".join(other.split())
    if not person or not other or person.lower() == other.lower():
        return None
    text = relation.lower().replace("_", " ")
    for pattern, kind, reverse in _RULES:
        if re.search(pattern, text):
            a, b = (other, person) if reverse else (person, other)
            return Relationship(from_name=a, to_name=b, kind=kind,
                                category="family" if kind in FAMILY else "social",
                                source_quote=quote, confidence=min(max(confidence, 0.0), 1.0))
    return None


def conflict(kind_a: str, kind_b: str, same_direction: bool) -> bool:
    """
    Can these two relationships between the SAME two people both be true?
    Sister then cousin: no. Parent then sibling: no. A parent of B and B parent of A: no.
    Married cousins are possible, so spouse + relative is fine; social kinds never conflict.
    """
    if kind_a == kind_b:
        return kind_a == "parent" and not same_direction
    pair = {kind_a, kind_b}
    return pair <= FAMILY and pair != {"relative", "spouse"}


def as_facts(rel: Relationship) -> list[dict]:
    """The relationship as plain facts about both people, so the contradiction checker sees it too."""
    def one(name, label, other):
        return {"entity": name, "entity_type": "character", "attribute": "relationship",
                "value": f"{label} {other}", "source_quote": rel.source_quote, "confidence": rel.confidence}
    return [one(rel.from_name, LABELS[rel.kind], rel.to_name), one(rel.to_name, INVERSE_LABELS[rel.kind], rel.from_name)]

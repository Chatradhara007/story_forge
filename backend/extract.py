from pydantic import ValidationError
from models import Fact, ExtractionResult
from llm import call_tool

# Long chapters are split into pieces of about this many characters, so the
# AI's answer never gets cut off halfway (which used to crash the app).
MAX_CHARS_PER_PIECE = 12000

# A pronoun is not a name: facts "about" these can't be linked to anyone, so they're dropped.
PRONOUNS = {"he", "she", "they", "him", "her", "them", "it", "his", "hers", "their",
            "i", "me", "we", "us", "you", "someone", "somebody"}

EXTRACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "record_facts",
        "description": "Record structured facts extracted from a story chapter.",
        "parameters": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string"},
                            "entity_type": {
                                "type": "string",
                                "enum": ["character", "location", "item", "event", "other"]
                            },
                            "attribute": {"type": "string"},
                            "value": {"type": "string"},
                            "source_quote": {"type": "string"},
                            "confidence": {"type": "number"}
                        },
                        "required": ["entity", "entity_type", "attribute", "value", "source_quote", "confidence"]
                    }
                }
            },
            "required": ["facts"]
        }
    }
}

EXTRACTION_PROMPT = """You are extracting structured facts from a chapter of fiction for a
continuity-tracking system. Read the text and extract every concrete, checkable fact about
characters, locations, items, and events: physical descriptions, relationships, status
(alive/dead/injured), locations, dates/time references, and stated events.

Only extract facts that are explicitly stated or very strongly implied — do not infer
beyond what the text supports. Include a short exact quote for each fact so it can be
cited later. Always refer to a character by their fullest name as used in this text — never
use a pronoun (he, she, they...) as the entity; work out who it refers to instead.

Chapter text:
{text}
"""


def split_into_pieces(text: str, max_chars: int = MAX_CHARS_PER_PIECE) -> list[str]:
    """Split text into pieces no longer than max_chars, breaking at line ends where possible."""
    pieces: list[str] = []
    current = ""
    for line in text.split("\n"):
        # A single enormous line: cut it into fixed-size slices.
        while len(line) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:max_chars])
            line = line[max_chars:]
        if current and len(current) + 1 + len(line) > max_chars:
            pieces.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current.strip():
        pieces.append(current)
    return pieces or [text]


def _clean_facts(raw_facts: list) -> list[Fact]:
    """Keep only well-formed facts, tidy them up, and drop exact duplicates."""
    facts: list[Fact] = []
    seen = set()
    for raw in raw_facts:
        try:
            fact = Fact(**raw)
        except (ValidationError, TypeError):
            continue  # skip one bad fact instead of failing the whole chapter
        fact.entity = " ".join(fact.entity.split())
        if not fact.entity or fact.entity.lower() in PRONOUNS:
            continue
        fact.confidence = min(max(fact.confidence, 0.0), 1.0)
        key = (fact.entity.lower(), fact.attribute.lower().strip(), fact.value.lower().strip())
        if key in seen:
            continue
        seen.add(key)
        facts.append(fact)
    return facts


def extract_facts(chapter_id: str, text: str) -> ExtractionResult:
    raw_facts: list = []
    for piece in split_into_pieces(text):
        answer = call_tool(EXTRACTION_PROMPT.format(text=piece), EXTRACTION_TOOL, max_tokens=4096)
        raw_facts.extend(answer.get("facts", []))
    return ExtractionResult(chapter_id=chapter_id, facts=_clean_facts(raw_facts))

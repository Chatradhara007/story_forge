from pydantic import BaseModel
from typing import Literal

class Fact(BaseModel):
    entity: str          # e.g. "Marcus"
    entity_type: Literal["character", "location", "item", "event", "other"]
    attribute: str        # e.g. "eye_color", "status", "location"
    value: str             # e.g. "blue", "alive", "the tavern"
    source_quote: str      # short quote from the text supporting this fact
    confidence: float      # 0.0-1.0, how certain the model is

class ExtractionResult(BaseModel):
    chapter_id: str
    facts: list[Fact]

class Contradiction(BaseModel):
    entity: str
    new_chapter_id: str
    new_attribute: str
    new_value: str
    new_quote: str
    conflicting_chapter_id: str
    conflicting_value: str
    conflicting_quote: str
    contradiction_type: Literal["attribute", "status", "timeline"]
    confidence: float = 0.5   # 0.0-1.0, how sure the model is this is a real mistake
    explanation: str

class EntityLink(BaseModel):
    """How one name in the chapter was linked, e.g. "Captain Vale" → Marcus Vale (AI match)."""
    name: str
    entity_id: int
    canonical_name: str
    method: Literal["known name", "AI match", "new"]
    confidence: float

class ChapterIngestResult(BaseModel):
    chapter_id: str
    chapter_number: int
    facts: list[Fact]
    entity_links: list[EntityLink]
    contradictions: list[Contradiction]

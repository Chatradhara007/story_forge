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

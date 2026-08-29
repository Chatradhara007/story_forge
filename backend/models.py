from pydantic import BaseModel
from typing import Literal

class Fact(BaseModel):
    entity: str         
    entity_type: Literal["character", "location", "item", "event", "other"]
    attribute: str       
    value: str            
    source_quote: str      
    confidence: float      

class ExtractionResult(BaseModel):
    chapter_id: str
    facts: list[Fact]

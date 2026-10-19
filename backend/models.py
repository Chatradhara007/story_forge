import re
from pydantic import BaseModel, field_validator, model_validator
from typing import Literal

_TYPE_WORDS = {"character": "character", "person": "character", "people": "character", "human": "character",
               "animal": "character", "location": "location", "place": "location", "setting": "location",
               "item": "item", "object": "item", "thing": "item", "vehicle": "item", "event": "event",
               "time": "event", "other": "other"}
_BODY_PART_OWNER = re.compile(
    r"^([A-Z][\w.-]*(?: [A-Z][\w.-]*){0,2})['\u2019]s ((?:(?:left|right|upper|lower) )?"
    r"(?:hand|arm|forearm|leg|foot|ankle|knee|wrist|shoulder|hip|eye|ear|face|hair|head|back|shin|thigh|finger|fingers))$")


class Fact(BaseModel):
    entity: str          # e.g. "Marcus"
    entity_type: Literal["character", "location", "item", "event", "other"]
    attribute: str        # e.g. "eye_color", "status", "location"
    value: str             # e.g. "blue", "alive", "the tavern"
    source_quote: str      # short quote from the text supporting this fact
    confidence: float      # 0.0-1.0, how certain the model is

    @field_validator("entity_type", mode="before")
    @classmethod
    def _tolerant_type(cls, value):
        # Some models write "person" or "object": keep the fact instead of losing it.
        return _TYPE_WORDS.get(str(value).strip().lower(), "other") if isinstance(value, str) else value

    @model_validator(mode="after")
    def _fold_body_part(self):
        """'Ana's right leg | condition | broken' is a fact about Ana, not about a separate thing."""
        m = _BODY_PART_OWNER.match(self.entity or "")
        if m:
            part = m.group(2).lower()
            self.entity, self.entity_type = m.group(1), "character"
            self.attribute = f"{part} {self.attribute}".strip()
        return self

class Relationship(BaseModel):
    """One relationship the text states, normalised: "Edmund | parent | Ines" = Edmund is Ines's parent."""
    from_name: str
    to_name: str
    kind: str                 # see relationships.KINDS
    category: Literal["family", "social"]
    source_quote: str
    confidence: float = 0.8


class ExtractionResult(BaseModel):
    chapter_id: str
    facts: list[Fact]
    relationships: list[Relationship] = []

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
    status: Literal["open", "dismissed", "resolved"] = "open"
    review_note: str | None = None   # why the double-check dismissed it, if it did
    severity: Literal["high", "medium", "low"] = "medium"
    source: Literal["checker", "safety net", "story clock", "trait check"] = "checker"
    new_fact_index: int | None = None        # position of the new fact in the chapter's facts
    new_fact_id: int | None = None           # the two facts compared (set once saved)
    conflicting_fact_id: int | None = None
    fingerprint: str | None = None

class EntityLink(BaseModel):
    """How one name in the chapter was linked, e.g. "Captain Vale" → Marcus Vale (AI match)."""
    name: str
    entity_id: int
    canonical_name: str
    method: Literal["known name", "name match", "AI match", "new"]
    confidence: float

class ChapterIngestResult(BaseModel):
    chapter_id: str
    chapter_number: int
    time_note: str | None = None          # e.g. "flashback: twelve years before the fire"
    facts: list[Fact]
    relationships: list[Relationship] = []
    entity_links: list[EntityLink]
    contradictions: list[Contradiction]
    timings_seconds: dict[str, float] = {}   # how long each stage took
    rechecking_chapters: list[str] = []      # later chapters being re-checked because of this one

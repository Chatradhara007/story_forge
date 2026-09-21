from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from pydantic import BaseModel
from extract import extract_facts
from models import ExtractionResult, ChapterIngestResult
from storage import (
    store_facts,
    get_facts_for_entity,
    semantic_search,
    store_contradictions,
    get_all_contradictions,
)
from contradictions import find_contradictions_for_chapter

app = FastAPI()

class ChapterInput(BaseModel):
    chapter_id: str
    text: str

@app.post("/extract", response_model=ExtractionResult)
def extract(chapter: ChapterInput):
    """Extract facts only — does not store them. Useful for testing extraction in isolation."""
    return extract_facts(chapter.chapter_id, chapter.text)

@app.post("/chapters", response_model=ChapterIngestResult)
def ingest_chapter(chapter: ChapterInput):
    """
    Full pipeline: extract facts, store them, check for contradictions against
    existing story memory, and persist any contradictions found. This is the
    main endpoint — use this one for real ingestion.
    """
    result = extract_facts(chapter.chapter_id, chapter.text)
    store_facts(chapter.chapter_id, result.facts)
    contradictions = find_contradictions_for_chapter(chapter.chapter_id, result.facts)
    store_contradictions(contradictions)
    return ChapterIngestResult(
        chapter_id=chapter.chapter_id,
        facts=result.facts,
        contradictions=contradictions,
    )

@app.get("/facts/{entity}")
def facts_for_entity(entity: str):
    """Everything currently known about a named entity, across all ingested chapters."""
    return {"entity": entity, "facts": get_facts_for_entity(entity)}

@app.get("/search")
def search(q: str, top_k: int = 5):
    """Semantic search across all stored facts — finds relevant facts even with different wording."""
    return {"query": q, "results": semantic_search(q, top_k)}

@app.get("/contradictions")
def list_contradictions():
    """All contradictions flagged so far, most recent first."""
    return {"contradictions": get_all_contradictions()}

@app.get("/health")
def health():
    return {"status": "ok"}

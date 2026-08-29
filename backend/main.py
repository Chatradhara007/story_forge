from fastapi import FastAPI
from pydantic import BaseModel
from extract import extract_facts
from models import ExtractionResult
from storage import store_facts, get_facts_for_entity, semantic_search

app = FastAPI()

class ChapterInput(BaseModel):
    chapter_id: str
    text: str

@app.post("/extract", response_model=ExtractionResult)
def extract(chapter: ChapterInput):
    """Extract facts only — does not store them. Useful for testing extraction in isolation."""
    return extract_facts(chapter.chapter_id, chapter.text)

@app.post("/chapters", response_model=ExtractionResult)
def ingest_chapter(chapter: ChapterInput):
    """Extract facts AND persist them to story memory. Use this one for real ingestion."""
    result = extract_facts(chapter.chapter_id, chapter.text)
    store_facts(chapter.chapter_id, result.facts)
    return result

@app.get("/facts/{entity}")
def facts_for_entity(entity: str):
    """Everything currently known about a named entity, across all ingested chapters."""
    return {"entity": entity, "facts": get_facts_for_entity(entity)}

@app.get("/search")
def search(q: str, top_k: int = 5):
    """Semantic search across all stored facts — finds relevant facts even with different wording."""
    return {"query": q, "results": semantic_search(q, top_k)}

@app.get("/health")
def health():
    return {"status": "ok"}

from fastapi import FastAPI
from pydantic import BaseModel
from extract import extract_facts
from models import ExtractionResult

app = FastAPI()

class ChapterInput(BaseModel):
    chapter_id: str
    text: str

@app.post("/extract", response_model=ExtractionResult)
def extract(chapter: ChapterInput):
    return extract_facts(chapter.chapter_id, chapter.text)

@app.get("/health")
def health():
    return {"status": "ok"}

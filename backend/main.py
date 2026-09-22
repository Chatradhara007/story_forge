import os
import time
from contextlib import asynccontextmanager
from typing import Literal
from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from extract import extract_facts, detect_timing
from models import ExtractionResult, ChapterIngestResult, EntityLink
from entities import resolve_entities
from llm import AIServiceError, ask_text, run_in_parallel
import storage
from storage import (
    resolve_chapter_number,
    embed_facts,
    save_chapter_results,
    get_facts_for_entity_id,
    find_entities_by_alias,
    get_entity,
    list_entities,
    merge_entities,
    detach_alias,
    list_chapters,
    semantic_search,
    get_all_contradictions,
    set_contradiction_status,
    get_chapter,
    delete_chapter,
    update_fact,
    delete_fact,
    get_timeline,
    apply_schema,
)
from contradictions import find_contradictions_for_chapter, find_cross_card_contradictions, double_check


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create any missing database tables on start-up (and upgrade old databases),
    # so there's no manual setup step.
    if os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true":
        apply_schema()
    yield


app = FastAPI(title="StoryForge", lifespan=lifespan)

# Lets a web page on a DIFFERENT address talk to this backend (browsers block that
# by default). The built-in website is served from this same address, so it doesn't
# need this. Set ALLOWED_ORIGINS in .env (comma-separated) to restrict it when deploying.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AIServiceError)
def ai_service_error(request: Request, error: AIServiceError):
    """If the AI service keeps failing, return a clear message instead of a bare crash."""
    return JSONResponse(status_code=502, content={"detail": str(error)})


class ChapterInput(BaseModel):
    chapter_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    # Reading order (1, 2, 3...). Optional: if left out, a new chapter goes after
    # the last one, and a re-submitted chapter keeps its old number.
    chapter_number: int | None = Field(default=None, ge=1)


# ---------------------------------------------------------------------------
# Books (projects)
# ---------------------------------------------------------------------------
class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@app.get("/projects")
def projects():
    """Every book, with its chapter count and number of open warnings."""
    return {"projects": storage.list_projects()}


@app.post("/projects", status_code=201)
def create_project(body: ProjectInput):
    """Start a new, empty book."""
    if storage.project_name_taken(body.name):
        raise HTTPException(status_code=409, detail=f"There's already a book called '{body.name.strip()}'.")
    return storage.create_project(body.name)


def _existing_project(project_id: int) -> dict:
    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"No book with id {project_id}.")
    return project


@app.get("/projects/{project_id}")
def project_detail(project_id: int):
    return _existing_project(project_id)


@app.patch("/projects/{project_id}")
def rename_project(project_id: int, body: ProjectInput):
    _existing_project(project_id)
    if storage.project_name_taken(body.name, except_id=project_id):
        raise HTTPException(status_code=409, detail=f"There's already a book called '{body.name.strip()}'.")
    return storage.rename_project(project_id, body.name)


@app.delete("/projects/{project_id}")
def delete_project(project_id: int):
    """Delete a book and everything in it: chapters, facts, characters and warnings."""
    _existing_project(project_id)
    storage.delete_project(project_id)
    return {"deleted": project_id}


def current_project(request: Request) -> int:
    """
    Which book a request is about. Addresses under /projects/{id}/... use that book.
    The short addresses without a book (e.g. /chapters) use the first book, which is
    created as "My story" if there isn't one yet.
    """
    raw = request.path_params.get("project_id")
    if raw is None:
        return storage.default_project_id()
    try:
        project_id = int(raw)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"No book with id {raw}.")
    _existing_project(project_id)
    return project_id


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------
def ingest(project_id: int, chapter: ChapterInput) -> ChapterIngestResult:
    """
    Full pipeline for one chapter of one book. All the slow AI work happens first; only
    if it all succeeds is everything saved to the database in one go. Re-submitting the
    same chapter_id replaces that chapter's old results.
    """
    timings: dict[str, float] = {}

    def timed(stage, function, *args):
        started = time.perf_counter()
        value = function(*args)
        timings[stage] = round(time.perf_counter() - started, 1)
        return value

    chapter_number = resolve_chapter_number(project_id, chapter.chapter_id, chapter.chapter_number)
    # Read the facts and work out when the chapter is set, at the same time.
    result, time_note = timed("reading facts", lambda: run_in_parallel(lambda job: job(), [
        lambda: extract_facts(chapter.chapter_id, chapter.text),
        lambda: detect_timing(chapter.text),
    ]))
    resolutions = timed("linking names", resolve_entities, project_id, result.facts)
    embeddings = timed("preparing search", embed_facts, result.facts)
    contradictions = timed(
        "checking for mistakes", find_contradictions_for_chapter,
        project_id, chapter.chapter_id, chapter_number, result.facts, resolutions, time_note,
    )
    # Safety net: conflicts hidden because the two facts are filed under different names.
    contradictions += timed(
        "safety-net check", find_cross_card_contradictions,
        project_id, chapter.chapter_id, chapter_number, result.facts, resolutions, embeddings,
        contradictions, time_note,
    )
    # Double-check every warning; ones that fail are kept but marked dismissed, with the reason.
    contradictions = timed(
        "double-checking", double_check,
        project_id, chapter.chapter_id, chapter_number, contradictions, time_note,
    )
    new_entity_ids = timed(
        "saving", save_chapter_results,
        project_id, chapter.chapter_id, chapter_number, chapter.text,
        result.facts, embeddings, contradictions, resolutions, time_note,
    )
    entity_links = [
        EntityLink(
            name=r.name,
            entity_id=r.existing_entity_id or new_entity_ids[r.canonical_name.lower()],
            canonical_name=r.canonical_name,
            method=r.method,
            confidence=r.confidence,
        )
        for r in resolutions.values()
    ]
    return ChapterIngestResult(
        chapter_id=chapter.chapter_id,
        chapter_number=chapter_number,
        time_note=time_note,
        facts=result.facts,
        entity_links=entity_links,
        contradictions=contradictions,
        timings_seconds=timings,
    )


@app.post("/extract", response_model=ExtractionResult)
def extract(chapter: ChapterInput):
    """Extract facts only — does not store them. Useful for testing extraction in isolation."""
    return extract_facts(chapter.chapter_id, chapter.text)


# ---------------------------------------------------------------------------
# Everything inside one book. These addresses exist twice:
#   /projects/{project_id}/chapters, /projects/{project_id}/entities, ...  (any book)
#   /chapters, /entities, ...                                             (the first book)
# ---------------------------------------------------------------------------
book = APIRouter()


@book.post("/chapters", response_model=ChapterIngestResult)
def ingest_chapter(chapter: ChapterInput, project_id: int = Depends(current_project)):
    """Add (or re-check) a chapter: read its facts, link names, check for mistakes, save."""
    return ingest(project_id, chapter)


@book.get("/chapters")
def chapters(project_id: int = Depends(current_project)):
    """All chapters of the book, in reading order."""
    return {"chapters": list_chapters(project_id)}


@book.get("/chapters/{chapter_id}")
def chapter_detail(chapter_id: str, project_id: int = Depends(current_project)):
    """One chapter's text and every fact taken from it."""
    chapter = get_chapter(project_id, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"No chapter called '{chapter_id}'.")
    return chapter


@book.delete("/chapters/{chapter_id}")
def remove_chapter(chapter_id: str, project_id: int = Depends(current_project)):
    """Delete a chapter, its facts and its warnings."""
    if not delete_chapter(project_id, chapter_id):
        raise HTTPException(status_code=404, detail=f"No chapter called '{chapter_id}'.")
    return {"deleted": chapter_id}


class FactUpdate(BaseModel):
    attribute: str | None = Field(default=None, min_length=1)
    value: str | None = Field(default=None, min_length=1)
    entity_type: Literal["character", "location", "item", "event", "other"] | None = None


@book.patch("/facts/{fact_id}")
def edit_fact(fact_id: int, body: FactUpdate, project_id: int = Depends(current_project)):
    """
    Correct a fact the AI got wrong. Changes are logged. Existing warnings aren't
    re-checked automatically: dismiss them, or re-submit the chapter.
    """
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Send at least one of: attribute, value, entity_type.")
    fact = update_fact(project_id, fact_id, changes)
    if fact is None:
        raise HTTPException(status_code=404, detail=f"No fact with id {fact_id}.")
    return fact


@book.delete("/facts/{fact_id}")
def remove_fact(fact_id: int, project_id: int = Depends(current_project)):
    """Delete a fact the AI shouldn't have extracted. Logged as a correction."""
    if not delete_fact(project_id, fact_id):
        raise HTTPException(status_code=404, detail=f"No fact with id {fact_id}.")
    return {"deleted": fact_id}


@book.get("/facts/{name}")
def facts_for_entity(name: str, project_id: int = Depends(current_project)):
    """
    Everything known about an entity, looked up by ANY of its names — asking for
    "Captain Vale" also returns facts written about "Marcus". In reading order.
    """
    match = find_entities_by_alias(project_id, [name]).get(name.lower())
    if match is None:
        raise HTTPException(status_code=404, detail=f"No entity is known by the name '{name}'.")
    entity = get_entity(project_id, match[0])
    return {**entity, "facts": get_facts_for_entity_id(match[0])}


@book.get("/entities")
def entities(project_id: int = Depends(current_project)):
    """Every character, place, item and event, with all the names each one goes by."""
    return {"entities": list_entities(project_id)}


@book.get("/entities/{entity_id}")
def entity_detail(entity_id: int, project_id: int = Depends(current_project)):
    entity = get_entity(project_id, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"No entity with id {entity_id}.")
    return {**entity, "facts": get_facts_for_entity_id(entity_id)}


class MergeInput(BaseModel):
    keep_entity_id: int
    merge_entity_id: int


@book.post("/entities/merge")
def merge(body: MergeInput, project_id: int = Depends(current_project)):
    """
    Fix a MISSED link: the system thinks two entities are different, but they're the
    same. Everything from merge_entity_id moves into keep_entity_id.
    Re-submit later chapters afterwards to re-check them for contradictions.
    """
    if body.keep_entity_id == body.merge_entity_id:
        raise HTTPException(status_code=400, detail="Those are the same entity.")
    if get_entity(project_id, body.keep_entity_id) is None or get_entity(project_id, body.merge_entity_id) is None:
        raise HTTPException(status_code=404, detail="One of those entity ids doesn't exist in this book.")
    merge_entities(project_id, body.keep_entity_id, body.merge_entity_id)
    return get_entity(project_id, body.keep_entity_id)


class DetachInput(BaseModel):
    name: str = Field(min_length=1)


@book.post("/entities/{entity_id}/detach")
def detach(entity_id: int, body: DetachInput, project_id: int = Depends(current_project)):
    """
    Fix a WRONG link: one of this entity's names actually belongs to someone else.
    That name (and the facts written under it) is split off into a new entity.
    """
    entity = get_entity(project_id, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"No entity with id {entity_id}.")
    if body.name.lower() not in [a.lower() for a in entity["aliases"]]:
        raise HTTPException(status_code=400, detail=f"'{body.name}' is not one of this entity's names.")
    if len(entity["aliases"]) < 2:
        raise HTTPException(status_code=400, detail="This entity only has one name; nothing to split off.")
    new_id = detach_alias(project_id, entity_id, body.name)
    return {"kept": get_entity(project_id, entity_id), "split_off": get_entity(project_id, new_id)}


@book.get("/search")
def search(q: str = Query(min_length=1), top_k: int = Query(default=5, ge=1, le=50),
           project_id: int = Depends(current_project)):
    """Semantic search across the book's facts — finds relevant facts even with different wording."""
    return {"query": q, "results": semantic_search(project_id, q, top_k)}


@book.get("/contradictions")
def list_contradictions(status: Literal["open", "dismissed"] | None = None,
                        project_id: int = Depends(current_project)):
    """Contradictions flagged so far, most recent first. Filter with ?status=open or ?status=dismissed."""
    return {"contradictions": get_all_contradictions(project_id, status)}


class StatusInput(BaseModel):
    status: Literal["open", "dismissed"]


@book.patch("/contradictions/{contradiction_id}")
def update_contradiction(contradiction_id: int, body: StatusInput, project_id: int = Depends(current_project)):
    """Dismiss a warning the writer says is fine (or re-open it)."""
    if not set_contradiction_status(project_id, contradiction_id, body.status):
        raise HTTPException(status_code=404, detail=f"No contradiction with id {contradiction_id}.")
    return {"id": contradiction_id, "status": body.status}


@book.get("/timeline")
def timeline(project_id: int = Depends(current_project)):
    """Story events in reading order."""
    return {"events": get_timeline(project_id)}


ASK_PROMPT = """You answer questions about a novel using ONLY the facts below, which were
extracted from its chapters. Cite the chapter for each claim like (ch. 3). If the facts don't
answer the question, say so plainly instead of guessing. Keep it to a short paragraph.

Question: {question}

Facts (entity | attribute | value | chapter number | quote):
{facts}
"""


class AskInput(BaseModel):
    question: str = Field(min_length=1)


@book.post("/ask")
def ask(body: AskInput, project_id: int = Depends(current_project)):
    """
    "What do we know about X?" Finds the most relevant facts in this book by meaning,
    then has the AI write a short answer from them, with the facts as sources.
    """
    sources = semantic_search(project_id, body.question, top_k=12)
    if not sources:
        return {"question": body.question, "answer": "No chapters have been added yet.", "sources": []}
    facts_text = "\n".join(
        f'{f["canonical_name"] or f["entity"]} | {f["attribute"]} | {f["value"]} | '
        f'ch. {f["chapter_number"]} | "{f["source_quote"]}"'
        for f in sources
    )
    answer = ask_text(ASK_PROMPT.format(question=body.question, facts=facts_text))
    return {"question": body.question, "answer": answer, "sources": sources}


app.include_router(book, prefix="/projects/{project_id}")
app.include_router(book, include_in_schema=False)        # short addresses: the first book


@app.get("/health")
def health():
    return {"status": "ok"}


# ---- The website ----------------------------------------------------------
# The frontend folder sits next to the backend folder. It's served at /app,
# and visiting the bare address (/) sends you there.
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse(url="/app/")

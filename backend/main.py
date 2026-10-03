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
from extract import extract_facts
from models import ExtractionResult, ChapterIngestResult
from llm import AIServiceError, AI_CONFIGURED, ask_text
import auth
import jobs
import pipeline
import storage
from storage import (
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
from entities import _types_compatible


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create any missing database tables on start-up (and upgrade old databases),
    # so there's no manual setup step.
    if os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true":
        apply_schema()
    yield
    storage.close_pool()


app = FastAPI(title="StoryForge", lifespan=lifespan)

# Lets a web page on a DIFFERENT address talk to this backend (browsers block that
# by default). The built-in website is served from this same address, so it doesn't
# need this. Set ALLOWED_ORIGINS in .env (comma-separated) to restrict it when deploying.
# With sign-in switched on, other websites are NOT allowed by default (set ALLOWED_ORIGINS
# to allow some); locally, anything goes, as before.
_origins = os.getenv("ALLOWED_ORIGINS", "" if auth.AUTH_REQUIRED else "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AIServiceError)
def ai_service_error(request: Request, error: AIServiceError):
    """If the AI service keeps failing, return a clear message instead of a bare crash."""
    return JSONResponse(status_code=502, content={"detail": str(error)})


class ChapterInput(BaseModel):
    # Used in web addresses (/chapters/ch1), so "/", "?" and "#" aren't allowed.
    chapter_id: str = Field(min_length=1, max_length=100, pattern=r"^[^/\\?#]+$")
    text: str = Field(min_length=1, max_length=400_000)
    # Reading order (1, 2, 3...). Optional: if left out, a new chapter goes after
    # the last one, and a re-submitted chapter keeps its old number.
    chapter_number: int | None = Field(default=None, ge=1)


# ---------------------------------------------------------------------------
# Books (projects)
# ---------------------------------------------------------------------------
BOOK_KINDS = Literal["novel", "novella", "short stories", "screenplay", "serial", "other"]
COVER = Field(default=None, pattern=r"^(sage|slate|plum|ochre|oxblood|moss|ink)$")


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: BOOK_KINDS = "novel"
    synopsis: str | None = Field(default=None, max_length=2000)
    cover_color: str | None = COVER


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: BOOK_KINDS | None = None
    synopsis: str | None = Field(default=None, max_length=2000)
    cover_color: str | None = COVER


def _owner(user: dict | None) -> int | None:
    return user["id"] if user else None


@app.get("/projects")
def projects(user: dict | None = Depends(auth.current_user)):
    """Every book (of the signed-in user), with its chapter count and number of open warnings."""
    return {"projects": storage.list_projects(_owner(user))}


@app.post("/projects", status_code=201)
def create_project(body: ProjectInput, user: dict | None = Depends(auth.current_user)):
    """Start a new, empty book."""
    if storage.project_name_taken(body.name, owner_id=_owner(user)):
        raise HTTPException(status_code=409, detail=f"There's already a book called '{body.name.strip()}'.")
    return storage.create_project(body.name, _owner(user), body.kind, body.synopsis, body.cover_color)


def _existing_project(project_id: int, user: dict | None) -> dict:
    project = storage.get_project(project_id, _owner(user))
    if project is None:
        raise HTTPException(status_code=404, detail=f"No book with id {project_id}.")
    return project


@app.get("/projects/{project_id}")
def project_detail(project_id: int, user: dict | None = Depends(auth.current_user)):
    return _existing_project(project_id, user)


@app.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate, user: dict | None = Depends(auth.current_user)):
    """Rename a book, or change its kind, synopsis or cover colour."""
    _existing_project(project_id, user)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name") and storage.project_name_taken(changes["name"], except_id=project_id, owner_id=_owner(user)):
        raise HTTPException(status_code=409, detail=f"There's already a book called '{changes['name'].strip()}'.")
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    return storage.update_project(project_id, changes)


@app.get("/activity")
def activity(user: dict | None = Depends(auth.current_user)):
    """Recent work across all your books (the shelf's side panel)."""
    return {"activity": storage.recent_activity(_owner(user))}


@app.delete("/projects/{project_id}")
def delete_project(project_id: int, user: dict | None = Depends(auth.current_user)):
    """Delete a book and everything in it: chapters, facts, characters and warnings."""
    _existing_project(project_id, user)
    storage.delete_project(project_id)
    return {"deleted": project_id}


def current_project(request: Request, user: dict | None = Depends(auth.current_user)) -> int:
    """
    Which book a request is about. Addresses under /projects/{id}/... use that book (it
    must belong to the signed-in user). The short addresses without a book (e.g.
    /chapters) use the user's first book, created as "My story" if there isn't one yet.
    """
    raw = request.path_params.get("project_id")
    if raw is None:
        return storage.default_project_id(_owner(user))
    try:
        project_id = int(raw)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"No book with id {raw}.")
    _existing_project(project_id, user)
    return project_id


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
class RegisterInput(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=80)
    invite_code: str | None = None


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


@app.get("/auth/config")
def auth_config():
    """What the sign-in screen needs to know (public)."""
    return {"auth_required": auth.AUTH_REQUIRED, "registration_open": auth.ALLOW_REGISTRATION,
            "invite_required": bool(auth.INVITE_CODE), "daily_chapter_limit": auth.DAILY_CHAPTER_LIMIT}


@app.post("/auth/register", status_code=201)
def register(body: RegisterInput):
    user = auth.register(body.email, body.password, body.display_name, body.invite_code)
    return {"user": user, "token": auth.make_token(user["id"])}


@app.post("/auth/login")
def login(body: LoginInput, request: Request):
    user = auth.login(body.email, body.password, request.client.host if request.client else "?")
    return {"user": user, "token": auth.make_token(user["id"])}


@app.get("/auth/me")
def me(user: dict | None = Depends(auth.current_user)):
    if user is None:
        return {"user": None, "auth_required": False}
    return {"user": user, "auth_required": True, "chapters_today": auth.usage_today(user["id"]),
            "daily_chapter_limit": auth.DAILY_CHAPTER_LIMIT}


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------
@app.post("/extract", response_model=ExtractionResult)
def extract(chapter: ChapterInput, user: dict | None = Depends(auth.current_user)):
    """Extract facts only — does not store them. Useful for testing extraction in isolation."""
    auth.charge_chapter(user)
    return extract_facts(chapter.chapter_id, chapter.text)


# ---------------------------------------------------------------------------
# Everything inside one book. These addresses exist twice:
#   /projects/{project_id}/chapters, /projects/{project_id}/entities, ...  (any book)
#   /chapters, /entities, ...                                             (the first book)
# ---------------------------------------------------------------------------
book = APIRouter()


@book.post("/chapters", response_model=ChapterIngestResult)
def ingest_chapter(chapter: ChapterInput, project_id: int = Depends(current_project),
                   user: dict | None = Depends(auth.current_user)):
    """
    Add (or re-check) a chapter and wait for the answer: read its facts, link names, check
    for mistakes, save. Takes minutes for long chapters; the website uses /chapters/jobs.
    Later chapters affected by this one are re-checked in the background afterwards.
    """
    auth.charge_chapter(user)
    with jobs.book_lock(project_id):
        result, later = pipeline.ingest(project_id, chapter.chapter_id, chapter.text, chapter.chapter_number)
    jobs.submit_rechecks(project_id, later, f"{chapter.chapter_id} changed")
    return result


@book.post("/chapters/jobs", status_code=202)
def ingest_chapter_job(chapter: ChapterInput, project_id: int = Depends(current_project),
                       user: dict | None = Depends(auth.current_user)):
    """
    Add (or re-check) a chapter in the BACKGROUND. Returns a job id at once; follow it at
    GET /jobs/{job_id}. When it's done the job's result is the same as POST /chapters.
    """
    auth.charge_chapter(user)

    def work(progress):
        result, later = pipeline.ingest(project_id, chapter.chapter_id, chapter.text, chapter.chapter_number,
                                        progress=progress)
        recheck_job = jobs.submit_rechecks(project_id, later, f"{chapter.chapter_id} changed")
        return {**result.model_dump(), "recheck_job_id": recheck_job}

    return {"job_id": jobs.submit(project_id, "ingest", chapter.chapter_id, work)}


@book.get("/jobs")
def list_jobs(project_id: int = Depends(current_project)):
    """Recent background jobs for this book, newest first."""
    return {"jobs": jobs.recent(project_id)}


@book.get("/jobs/{job_id}")
def job_status(job_id: str, project_id: int = Depends(current_project)):
    """Progress of a background job: status (queued/running/done/failed), stage, progress 0-1, result."""
    job = jobs.get(project_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job.")
    return job


@book.post("/chapters/{chapter_id}/recheck", status_code=202)
def recheck(chapter_id: str, project_id: int = Depends(current_project),
            user: dict | None = Depends(auth.current_user)):
    """Check a saved chapter again against the story as it is now (no re-reading)."""
    if storage.chapter_number_of(project_id, chapter_id) is None:
        raise HTTPException(status_code=404, detail=f"No chapter called '{chapter_id}'.")
    auth.charge_chapter(user)
    return {"job_id": jobs.submit_rechecks(project_id, [chapter_id], "asked by the writer")}


class ChapterUpdate(BaseModel):
    story_order: float | None = None


@book.patch("/chapters/{chapter_id}")
def update_chapter(chapter_id: str, body: ChapterUpdate, project_id: int = Depends(current_project)):
    """Set where a chapter sits in STORY time (for flashbacks); null = work it out automatically."""
    if not storage.set_chapter_story_order(project_id, chapter_id, body.story_order):
        raise HTTPException(status_code=404, detail=f"No chapter called '{chapter_id}'.")
    return get_chapter(project_id, chapter_id)


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
    """Delete a chapter, its facts and its warnings. Later chapters are re-checked without it."""
    number = storage.chapter_number_of(project_id, chapter_id)
    if number is None or not delete_chapter(project_id, chapter_id):
        raise HTTPException(status_code=404, detail=f"No chapter called '{chapter_id}'.")
    job = jobs.submit_rechecks(project_id, storage.chapters_after(project_id, number), f"{chapter_id} deleted")
    return {"deleted": chapter_id, "recheck_job_id": job}


class FactUpdate(BaseModel):
    attribute: str | None = Field(default=None, min_length=1)
    value: str | None = Field(default=None, min_length=1)
    entity_type: Literal["character", "location", "item", "event", "other"] | None = None
    pinned: bool | None = None          # true = canon: this fact always wins


@book.patch("/facts/{fact_id}")
def edit_fact(fact_id: int, body: FactUpdate, project_id: int = Depends(current_project)):
    """
    Correct a fact the AI got wrong (logged), and/or pin it as canon. Open warnings built on
    the old version are closed, and the affected chapters are re-checked in the background.
    """
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Send at least one of: attribute, value, entity_type, pinned.")
    fact = storage.get_fact(project_id, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail=f"No fact with id {fact_id}.")
    if "pinned" in changes:
        fact = storage.set_fact_pinned(project_id, fact_id, changes.pop("pinned"))
    if changes:
        fact = update_fact(project_id, fact_id, changes)
        later = storage.chapters_after(project_id, storage.chapter_number_of(project_id, fact["chapter_id"]))
        fact["recheck_job_id"] = jobs.submit_rechecks(
            project_id, fact.pop("recheck_chapters") + later, "a fact was corrected")
    return fact


@book.delete("/facts/{fact_id}")
def remove_fact(fact_id: int, project_id: int = Depends(current_project)):
    """Delete a fact the AI shouldn't have extracted. Logged; warnings built on it are closed."""
    affected = delete_fact(project_id, fact_id)
    if affected is None:
        raise HTTPException(status_code=404, detail=f"No fact with id {fact_id}.")
    return {"deleted": fact_id,
            "recheck_job_id": jobs.submit_rechecks(project_id, affected, "a fact was deleted")}


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
    keep, other = get_entity(project_id, body.keep_entity_id), get_entity(project_id, body.merge_entity_id)
    if keep is None or other is None:
        raise HTTPException(status_code=404, detail="One of those entity ids doesn't exist in this book.")
    if not _types_compatible(keep["entity_type"], other["entity_type"]):
        raise HTTPException(status_code=400, detail=f"Can't merge a {other['entity_type']} into a "
                                                    f"{keep['entity_type']}: they can't be the same thing.")
    merge_entities(project_id, body.keep_entity_id, body.merge_entity_id)
    # Facts that were never compared (they were on two cards) are compared now.
    job = jobs.submit_rechecks(project_id, storage.chapters_with_entity(project_id, body.keep_entity_id),
                               "two entries were merged")
    return {**get_entity(project_id, body.keep_entity_id), "recheck_job_id": job}


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
    chapters = storage.chapters_with_entity(project_id, entity_id) + storage.chapters_with_entity(project_id, new_id)
    job = jobs.submit_rechecks(project_id, sorted(set(chapters), key=lambda c: storage.chapter_number_of(project_id, c)),
                               "a name was split off")
    return {"kept": get_entity(project_id, entity_id), "split_off": get_entity(project_id, new_id),
            "recheck_job_id": job}


@book.get("/search")
def search(q: str = Query(min_length=1), top_k: int = Query(default=5, ge=1, le=50),
           project_id: int = Depends(current_project)):
    """Semantic search across the book's facts — finds relevant facts even with different wording."""
    return {"query": q, "results": semantic_search(project_id, q, top_k)}


@book.get("/contradictions")
def list_contradictions(status: Literal["open", "dismissed", "resolved"] | None = None,
                        project_id: int = Depends(current_project)):
    """Contradictions flagged so far, most recent first. Filter with ?status=open|dismissed|resolved."""
    return {"contradictions": get_all_contradictions(project_id, status)}


class StatusInput(BaseModel):
    status: Literal["open", "dismissed"]
    reason: str | None = Field(default=None, max_length=500)   # why it's fine (feeds the evaluation set)


@book.patch("/contradictions/{contradiction_id}")
def update_contradiction(contradiction_id: int, body: StatusInput, project_id: int = Depends(current_project)):
    """Dismiss a warning the writer says is fine (or re-open it). Remembered across re-checks."""
    if not set_contradiction_status(project_id, contradiction_id, body.status, body.reason):
        raise HTTPException(status_code=404, detail=f"No contradiction with id {contradiction_id}.")
    return {"id": contradiction_id, "status": body.status}


@book.get("/timeline")
def timeline(order: Literal["reading", "story"] = "reading", project_id: int = Depends(current_project)):
    """Story events in reading order, or in story time (?order=story: flashbacks placed first)."""
    return {"order": order, "events": get_timeline(project_id, order)}


@book.get("/overview")
def overview(project_id: int = Depends(current_project)):
    """Dashboard numbers for one book."""
    chapters = list_chapters(project_id)
    warnings = get_all_contradictions(project_id)
    entities_ = list_entities(project_id)
    open_ = [w for w in warnings if w["status"] == "open"]
    count = lambda items, key: {k: sum(1 for i in items if i[key] == k) for k in sorted({i[key] for i in items})}
    return {
        "chapters": len(chapters),
        "words": sum(c["word_count"] or 0 for c in chapters),
        "facts": sum(c["fact_count"] for c in chapters),
        "entities": count(entities_, "entity_type"),
        "open_issues": len(open_),
        "open_by_severity": count(open_, "severity"),
        "open_by_type": count(open_, "contradiction_type"),
        "dismissed": sum(1 for w in warnings if w["status"] == "dismissed"),
        "resolved": sum(1 for w in warnings if w["status"] == "resolved"),
        "most_flagged": sorted(count(open_, "entity").items(), key=lambda kv: -kv[1])[:5],
        "jobs": jobs.recent(project_id, 5),
    }


@book.get("/characters/map")
def characters_map(project_id: int = Depends(current_project)):
    """Characters and their relationships, chapter by chapter: the family tree and relationship web."""
    return storage.character_map(project_id)


@book.get("/presence")
def presence(project_id: int = Depends(current_project)):
    """Which people, places and objects appear in which chapters, and where their open issues are."""
    return storage.presence(project_id)


@book.get("/export")
def export(project_id: int = Depends(current_project)):
    """The whole book as JSON lore (entities, names, facts, chapters, warnings)."""
    return storage.export_book(project_id)


@book.get("/feedback")
def feedback(project_id: int = Depends(current_project)):
    """The writer's dismissals with reasons: material for growing the evaluation set."""
    return {"dismissals": storage.dismissal_feedback(project_id)}


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
    """Liveness check. Always 200 if the web server runs; says whether the database and AI are set up."""
    return {"status": "ok", "database": storage.database_ok(), "ai_configured": AI_CONFIGURED,
            "auth_required": auth.AUTH_REQUIRED}


# ---- The website ----------------------------------------------------------
# The frontend folder sits next to the backend folder. It's served at /app,
# and visiting the bare address (/) sends you there.
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse(url="/app/")

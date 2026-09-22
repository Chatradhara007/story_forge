# StoryForge AI — Project Status & Setup

**Last updated:** 21 September 2026 (Steps 3–7: evaluation, website, features, deployment, tests)

A continuity-tracking system for long-form fiction. Writers ingest chapters; the system extracts
structured facts (characters, locations, items, events), builds up a persistent "story memory,"
and automatically flags contradictions when new content conflicts with something already
established — with a citation pointing to exactly where.

**Quick start:** `docker compose up -d`, start the backend (see [Setup](#setup)), then open
http://127.0.0.1:8000 for the website.

---

## ✅ What's done

### 1. Extraction pipeline
**What it does:** Takes raw chapter text and pulls out structured facts (entity, attribute,
value, supporting quote, confidence score) using an LLM.

**How it works:** One call to an NVIDIA NIM chat model (`nvidia/nemotron-3-super-120b-a12b`),
using forced tool/function calling so the model *must* return valid structured JSON matching
our schema, rather than free text we'd have to parse with regex. The schema is defined once in
`models.py` (the `Fact` class) and reused everywhere else in the pipeline.

**Why this approach:** Forced tool calling is dramatically more reliable than prompting for JSON
and hoping — the model literally cannot return malformed output because the API enforces the
schema. We considered spaCy for NER but skipped it: one well-prompted LLM call does NER +
relation extraction together, which was faster to build and iterate on for a project this size.

**File:** `backend/extract.py`

---

### 2. Story memory (storage layer)
**What it does:** Persists every extracted fact so the system "remembers" across chapters, and
supports two ways of retrieving facts: exact lookup by entity name, and semantic search by
meaning.

**How it works:** A local Postgres database (via Docker, with the `pgvector` extension) holds a
single `facts` table: entity, attribute, value, source quote, confidence, chapter ID, and an
embedding vector. Every fact gets embedded (`nvidia/nemotron-3-embed-1b`, 2048-dim vectors) at
storage time, enabling semantic search later — e.g. searching "who has died in the story" can
surface a fact phrased as "collapsed and did not rise again" even without exact keyword overlap.

**Why this approach:** We originally planned Neo4j (graph DB) + a separate vector DB, per the
original spec. We simplified to one Postgres instance doing both structured lookup and semantic
search — much faster to stand up, and for a project this size a graph database was more
infrastructure than the problem needed. We also moved from Supabase (hosted Postgres) to a local
Dockerized Postgres partway through, for zero-dependency setup across teammates' machines.

**File:** `backend/storage.py`, `backend/schema.sql`, `docker-compose.yml`

---

### 3. Contradiction detection
**What it does:** Every time a new chapter is ingested, the system automatically checks its new
facts against everything previously known about the same characters/places/items, and flags
genuine contradictions with a human-readable explanation and citations to both the new and
conflicting source text.

**How it works:** New facts are grouped by entity. For each entity that already has prior
history, one LLM call compares the new facts against the stored ones and returns (via forced
tool calling again) a list of contradictions, each tagged as one of three types:
- **Attribute** — a stated trait changed without explanation (eye color, age, name spelling)
- **Status** — an impossible state (dead but acting alive, in two places at once)
- **Timeline** — event ordering/duration conflicts with the established timeline

Contradictions are persisted to their own table and returned in the API response immediately,
so ingesting a chapter and seeing flagged issues happens in one call.

**Why this approach:** Scoping to three concrete contradiction types (instead of open-ended
"find any contradiction") made this buildable in the time we have, and keeps detection quality
measurable — see the evaluation section below, which is still to-do.

**File:** `backend/contradictions.py`

---

### 4. Entity resolution ("who is who")
**What it does:** Recognises that different names refer to the same entity, so "Marcus",
"Marcus Vale" and "Captain Vale" are one character and their facts are checked against each other.

**How it works:** Every entity gets one row in `entities`, and every name it's been called is stored
in `entity_aliases`. Each fact records which entity it's about (`facts.entity_id`). For each new
chapter, names are linked cheapest-first: (1) a name seen before links instantly with no AI call;
(2) new names go to one AI call per chapter, which sees quotes from the chapter plus the known
entities with their names and a few facts, and decides which known entity each name is (or that
it's new, grouping new names that belong together); (3) anything not confidently matched becomes a
new entity. Contradiction checking then groups facts by entity instead of by name.

**Why this approach:** A wrong merge (two different people treated as one) creates fake
contradictions, which is worse than a missed link. So AI links are only accepted at confidence
≥ 0.7, must point at an entity that was actually offered, and must be the same type (a person
can't merge into a place). Mistakes can be fixed by hand with `/entities/merge` and
`/entities/{id}/detach`. For big stories (150+ entities) only entities sharing a word with the new
name are shown to the AI, to keep the prompt small.

**File:** `backend/entities.py` (plus changes in `storage.py`, `contradictions.py`, `main.py`)

---

### 5. Infrastructure decisions & lessons learned
- **Switched from Supabase to local Docker Postgres + pgvector** — no cloud account needed, works
  identically across every teammate's machine regardless of OS.
- **Vector index removed (Sept 2026).** pgvector can only index vectors up to 2000 dimensions and
  our embeddings are 2048, so the old `ivfflat` index silently failed to build. Search works fine
  without it at this scale; `schema.sql` explains how to add a `halfvec` index if it ever gets slow.
- **Hardening pass (Sept 2026):** chapters now have a `chapter_number` (reading order) stored in a
  new `chapters` table; re-submitting a chapter replaces its old facts instead of duplicating them;
  each `/chapters` call saves everything in one transaction (all or nothing); AI calls retry and
  bad AI output is filtered; long chapters are split into pieces; embeddings are sent in batches;
  CORS is enabled for the frontend; contradictions now carry a confidence score. Model names and
  the AI connection live in one file, `backend/llm.py`, and can be overridden in `.env`.
- **NVIDIA NIM model IDs are not stable long-term.** We hit two rounds of `410 Gone` errors from
  models being retired mid-project (`meta/llama-3.1-70b-instruct`, `meta/llama-3.3-70b-instruct`,
  and the original embedding model `nvidia/nv-embedqa-e5-v5` all got retired within days of each
  other). We're now on `nvidia/nemotron-3-super-120b-a12b` (chat/tool-calling) and
  `nvidia/nemotron-3-embed-1b` (embeddings, 2048-dim). **If either of these ever breaks with a
  410 error again**, run this to see every model currently live on your API key, rather than
  guessing a new name:
  ```powershell
  $headers = @{ Authorization = "Bearer $env:NVIDIA_API_KEY" }
  (Invoke-RestMethod -Uri "https://integrate.api.nvidia.com/v1/models" -Headers $headers).data | Select-Object id
  ```

---

### 6. Evaluation harness
**What it does:** Measures how well the system actually catches mistakes. `eval/story/` is an
original six-chapter test story ("The Gullstone Light") with **12 planted contradictions**
(5 attribute, 4 status, 3 timeline) and **3 decoys** — changes that look like mistakes but aren't
(a character moving house, an injury healing). Several mistakes deliberately use a *different
name* for the character, to test entity resolution too.

**How it works:** `python eval/run_eval.py` wipes a separate `storyforge_eval` database (your real
story is never touched), feeds in the chapters with the real AI, and compares every warning with
the answer key in `eval/ground_truth.json`. It reports precision (how many warnings were real),
recall (how many planted mistakes were caught), F1, per-type recall, false alarms, whether the
type label was right, and name-linking checks (e.g. "Keeper Calloway" = "Ines Calloway", but
"Mara Calloway" ≠ "Ines Calloway"). Each run is saved to `eval/results/` as a Markdown report.

**Why this approach:** Keyword matching against a hand-written answer key is simple, transparent
and cheap, and the decoys make sure the system isn't rewarded for flagging everything.

**Files:** `eval/`

---

### 7. Website
**What it does:** A browser interface at http://127.0.0.1:8000, served by the backend itself (no
separate install). Pages:
- **Add chapter:** paste text, see facts, name links and possible mistakes.
- **Issues:** every contradiction as two facing quotes with the conflicting words underlined, a
  confidence badge (Sure / Likely / Unsure), and a *Dismiss* button for intentional changes.
- **Characters & places:** the auto-generated story bible: every entity, all its names, and a
  sheet of everything the story says about it. Merge or split entries here.
- **Timeline:** events in reading order.
- **Ask:** natural-language questions answered only from stored facts, with sources.
- **Chapter history** (left sidebar): open any chapter to read it, correct or delete wrongly
  extracted facts (corrections are logged), re-check it, or delete it.

**How it works:** One plain HTML/CSS/JavaScript file, `frontend/index.html`, with no build step.
It calls the same API documented below.

**Files:** `frontend/index.html`, new endpoints in `backend/main.py` and `backend/storage.py`

---

### 8. Deployment, tests and tidy-up
- **Deployment:** `Dockerfile` (backend + website in one container), `render.yaml` for Render,
  and step-by-step instructions in [DEPLOY.md](DEPLOY.md). Tables are created automatically on
  start-up, so a fresh hosted database needs no manual setup.
- **Automated tests:** 19 tests in `backend/tests/` using a fake AI and a separate test database.
  They run on GitHub automatically on every push (`.github/workflows/tests.yml`).
- **Pinned dependencies:** exact versions in `requirements.txt`, so everyone installs the same thing.

---

## 🚧 What's left

Everything in the original build plan is done. What remains is running and improving it:

1. **Run the evaluation with the real AI** (`python eval/run_eval.py`), commit the report in
   `eval/results/`, and record the scores here. Then improve prompts where it misses and re-run.
2. **Deploy** following [DEPLOY.md](DEPLOY.md).

### Future work / explicitly out of scope for now
- Login / user accounts (needed before sharing a deployed link publicly)
- Multi-author collaboration mode
- Export to game-engine-friendly lore format (JSON)
- Tone/voice consistency checking
- Checking contradictions *within* a single chapter, and between different entities
- Story-time ordering (flashbacks) — the timeline currently follows reading order
- Neo4j-based graph storage (currently using Postgres + pgvector instead)

---

## Current endpoints

| Endpoint | Purpose |
|---|---|
| `POST /extract` | Extract facts only, don't store — for testing extraction in isolation |
| `POST /chapters` | Full pipeline: extract, check for contradictions, then save everything. Body: `chapter_id`, `text`, optional `chapter_number`. Re-sending a `chapter_id` replaces it |
| `GET /chapters` | All submitted chapters in reading order, with fact counts |
| `GET /chapters/{id}` | One chapter's text and all its facts |
| `DELETE /chapters/{id}` | Delete a chapter with its facts and warnings |
| `PATCH /facts/{id}` | Correct a fact: `{"attribute": ..., "value": ..., "entity_type": ...}` (logged) |
| `DELETE /facts/{id}` | Delete a wrongly extracted fact (logged) |
| `GET /facts/{name}` | Everything known about an entity, looked up by any of its names, in reading order |
| `GET /entities` | Every entity with all the names it goes by and its fact count |
| `GET /entities/{id}` | One entity with all its facts |
| `POST /entities/merge` | Fix a missed link: `{"keep_entity_id": 1, "merge_entity_id": 2}` |
| `POST /entities/{id}/detach` | Fix a wrong link: `{"name": "The Stranger"}` splits that name off into its own entity |
| `GET /search?q=...` | Semantic search across all stored facts |
| `GET /contradictions` | Contradictions, most recent first; filter with `?status=open` or `?status=dismissed` |
| `PATCH /contradictions/{id}` | Dismiss or reopen a warning: `{"status": "dismissed"}` |
| `GET /timeline` | Event facts in reading order |
| `POST /ask` | `{"question": "..."}` → an answer written from stored facts, plus the facts used |
| `GET /health` | Sanity check |

Interactive documentation for every endpoint: http://127.0.0.1:8000/docs

---

## Folder layout

```
storyforge/
├── README.md
├── DEPLOY.md              # how to put it online
├── Dockerfile             # backend + website in one container
├── render.yaml            # Render deployment blueprint
├── docker-compose.yml     # local Postgres + pgvector (and optionally the app)
├── .github/workflows/tests.yml   # runs the tests on every push
├── frontend/
│   └── index.html         # the website
├── eval/
│   ├── story/ch1-ch6.txt  # test story with planted mistakes
│   ├── ground_truth.json  # the answer key
│   ├── run_eval.py        # scores the system against the answer key
│   └── results/           # saved reports
└── backend/
    ├── .env.example
    ├── requirements.txt / requirements-dev.txt
    ├── schema.sql          # database tables (applied automatically on start-up)
    ├── llm.py              # AI connection, model names, retries, batched embeddings
    ├── models.py           # Fact / Contradiction / EntityLink / ...
    ├── extract.py          # extraction pipeline
    ├── entities.py         # entity resolution (which names are the same entity)
    ├── contradictions.py   # contradiction detection
    ├── storage.py          # database access
    ├── main.py             # FastAPI app, all endpoints, serves the website
    └── tests/              # automated tests (fake AI, separate test database)
```

---

## Setup

You need **Docker Desktop** and **Python 3.10 or newer**. Commands are shown for Windows
(PowerShell) and Mac/Linux (Terminal); run them from the project folder.

### 1. Start the database
```
docker compose up -d
```
The app creates its tables automatically when it starts. If you set up the database before
September 2026, reset it once (this deletes stored test data): `docker compose down -v`, then
`docker compose up -d`.

### 2. Start the backend and website
Windows (PowerShell):
```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then paste your NVIDIA_API_KEY into .env (get one at build.nvidia.com)
uvicorn main:app --reload
```
Mac/Linux:
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then paste your NVIDIA_API_KEY into .env (get one at build.nvidia.com)
uvicorn main:app --reload
```
Open **http://127.0.0.1:8000** for the website, or http://127.0.0.1:8000/docs for the API.

### 3. Run the automated tests (no API key needed)
With the database running and the virtual environment active, in `backend/`:
```
pip install -r requirements-dev.txt
pytest
```

### 4. Run the evaluation (uses the real AI and your NVIDIA credits)
From the project folder, with the virtual environment active:
```
python eval/run_eval.py
```

---

## How to keep this file updated
Whenever you or a teammate finishes something:
1. Move it from **What's left** to **What's done**, with a short "what it does / how it works /
   why this approach" writeup like the ones above — future-you and your teammates will thank you
   when writing the final report.
2. Update the **Last updated** line at the top.
3. If you change a core decision (swap a model, change a DB, alter the schema), add a line under
   **Infrastructure decisions & lessons learned** so nobody re-discovers the same bug twice.
# StoryForge AI — Project Status & Setup

**Last updated:** [update this line whenever you edit the doc — just the date is fine]

A continuity-tracking system for long-form fiction. Writers ingest chapters; the system extracts
structured facts (characters, locations, items, events), builds up a persistent "story memory,"
and automatically flags contradictions when new content conflicts with something already
established — with a citation pointing to exactly where.

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

### 4. Infrastructure decisions & lessons learned
- **Switched from Supabase to local Docker Postgres + pgvector** — no cloud account needed, works
  identically across every teammate's machine regardless of OS.
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

## 🚧 What's left

### Step 4: Minimal frontend
A page to paste in chapter text, view extracted facts (auto-generated character/world bible),
and see flagged contradictions with citations. Not started yet.

### Evaluation harness — **do this before the frontend if possible**
Write or find a short multi-chapter test story, deliberately plant 10-15 contradictions across
all three types, run them through `/chapters`, and measure precision/recall against what
`/contradictions` actually flags. This is the single highest-value thing left to do — it's what
turns "we built a demo" into "we built and measured a system," and is the strongest resume line
this project can produce. Nothing else is blocked on this; it can be done in parallel with the
frontend.

### Timeline visualization
A view showing story events in chronological order, derived from the facts already being
extracted (entity_type: "event" facts). Frontend work, depends on Step 4's base page existing.

### Character sheet auto-generation
A per-character view aggregating all known facts about them — this is largely already possible
via the existing `/facts/{entity}` endpoint; mainly needs a frontend view built on top of it.

### Deployment
Not started. Options: Render/Fly.io for the backend, a hosted Postgres (or keep local Docker for
demo day only). Independent of other work — can happen anytime once the app runs locally.

### Future work / explicitly out of scope for now
These are mentioned in the writeup as future directions, not built:
- Multi-author collaboration mode
- Export to game-engine-friendly lore format (JSON)
- Tone/voice consistency checking
- Neo4j-based graph storage (currently using Postgres + pgvector instead)

---

## 💡 Planned frontend features

Core loop (chapter upload → facts view → contradiction dashboard → character bible → timeline →
search) is described under **Step 4** above. These are additional features layered on top, in
priority order:

### Confidence/severity indicator
Every extracted fact and flagged contradiction already carries a confidence score from the LLM.
Surface it in the UI (e.g. a color-coded badge) so low-confidence extractions or shaky
contradiction calls are visually distinct from high-confidence ones, instead of presenting
everything with equal certainty.

### Chapter history sidebar
A simple list of all chapters ingested so far, letting you click back into what's already been
submitted. Becomes necessary once testing goes beyond 2-3 chapters — otherwise there's no way to
see what the system has "read" without re-querying the API directly.

### Manual fact correction
Lets a user edit or dismiss a wrongly-extracted fact directly in the UI. Matters for two reasons:
it's a realistic feature a real writer would want (extraction won't be perfect), and it's the
seed of a feedback loop — logged corrections are free signal for improving prompts or, later,
for the evaluation harness's ground truth.

### "What do we know about X" query box
A natural-language query interface on top of the existing semantic search — instead of returning
raw matched facts as a list, retrieve the relevant facts and have the LLM compose a short answer
from them. This directly implements the original spec's "searchable story memory" feature and
showcases the retrieval pipeline doing more than returning a list.



## Current endpoints

| Endpoint | Purpose |
|---|---|
| `POST /extract` | Extract facts only, don't store — for testing extraction in isolation |
| `POST /chapters` | Full pipeline: extract, store, check for contradictions, store any found |
| `GET /facts/{entity}` | Everything currently known about a named entity |
| `GET /search?q=...` | Semantic search across all stored facts |
| `GET /contradictions` | All contradictions flagged so far, most recent first |
| `GET /health` | Sanity check |

---

## Folder layout

```
storyforge/
├── .gitignore
├── README.md
├── docker-compose.yml   # local Postgres + pgvector
└── backend/
    ├── .env.example
    ├── requirements.txt
    ├── schema.sql
    ├── models.py          # Fact / Contradiction / ExtractionResult / ChapterIngestResult
    ├── extract.py          # extraction pipeline
    ├── storage.py          # persistence + embeddings + semantic search
    ├── contradictions.py   # contradiction detection
    └── main.py             # FastAPI app + all endpoints
```

---

## Setup

### 1. Database (local Postgres + pgvector, via Docker)
```powershell
docker compose up -d
Get-Content backend/schema.sql | docker exec -i $(docker compose ps -q db) psql -U storyforge -d storyforge
```

### 2. Backend
```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then paste your NVIDIA_API_KEY into .env — get one at build.nvidia.com
uvicorn main:app --reload
```

### 3. Test it
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/chapters" -Method Post -ContentType "application/json" -Body '{"chapter_id": "ch1", "text": "Marcus stood at the edge of the tavern, his blue eyes scanning the room."}'
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
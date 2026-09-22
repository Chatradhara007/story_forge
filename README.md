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
- **Reasoning models don't always answer in the structured format (Sept 2026).** Nemotron-3-super
  occasionally writes its answer as plain text, or uses up its token budget "thinking". `llm.py`
  now accepts JSON from a plain-text answer, doubles the token budget after a cut-off answer,
  retries 4 times, and reports what the model actually said. If failures continue, set
  `CHAT_DISABLE_THINKING=true` in `.env`.
- **Speed and first real evaluation (Sept 2026).** The first real run scored precision 100%,
  recall 67% (8/12), name linking 6/6, but took 27 minutes, because the per-entity checks ran
  one after another on a slow reasoning model. Checks (and pieces of long chapters) now run in
  parallel (`MAX_PARALLEL_AI_CALLS`, default 6), each stage is timed, and the evaluation report
  shows where the time went. Accuracy fixes aimed at the four misses: the extractor now records
  physical states revealed by actions, passing dates/ages, and what happens to objects; the
  checker also sees facts filed under other entities that mention this one; and the prompt spells
  out impossible actions and age/date conflicts. Duplicate warnings for the same earlier fact are
  merged.
- **Second run: thinking is the real bottleneck.** The second run still took 27 minutes, with
  reading facts at 1118s of 1635s (about 3 minutes per ~200-word chapter), so the time was the
  model's thinking, not the text. Recall also fell to 50% (6/12), mostly because "Harbourmaster
  Rudd" wasn't linked to "Silas Rudd", and the longer extraction instructions made output longer.
  Changes: the model's thinking is now **off by default** (`CHAT_THINKING=off|low|on`, sent as
  `chat_template_kwargs.enable_thinking`), which NVIDIA documents for Nemotron 3 Super; the
  extra extraction instructions were reverted; retries are printed so wasted time is visible.
  LLM output varies between runs, so compare settings over at least two runs each.
- **Third run: 15x faster.** With thinking off: 111s instead of 27 minutes, precision 100%,
  recall 50%. The report showed "Tobias" and "Tobias Calloway" filed as two entities, so
  facts about him were never compared. Changes: (1) a name rule links a name to a known one
  when one is exactly the start of the other ("Tobias" / "Tobias Calloway") and only one known
  entity fits (not for surnames or titles alone); (2) separate thinking settings: reading facts
  stays `off` (`CHAT_THINKING`), while the short judgement steps, linking names and checking,
  use `low` (`CHAT_THINKING_JUDGING`), falling back to `off` automatically if the service
  rejects it; (3) the evaluation report now diagnoses each missed mistake as *not read*,
  *split* (name linking) or *checker*.
- **Fourth run: best so far.** Precision 83%, recall 83% (10/12), name linking 6/6, 171s.
  Both false alarms were a character dying after being alive (a normal forward change), and
  Rudd's one mistake was reported three times. Remaining misses: the key (recorded as
  "threw it into the sea", so never linked to the key) and a passing "on Friday". Changes:
  the checker is told that forward changes (dying, injury, moving, ageing) are normal and only
  reversals of permanent changes are mistakes; one warning per new fact as well as per
  earlier fact; the Reader names objects instead of writing "it" and records passing day/date
  mentions; default parallel AI calls lowered from 6 to 4 after NVIDIA returned 429 errors.
- **Fifth run: F1 0.86, precision back to 100%.** Recall 75% (9/12), 156s. The forward-change
  rule fixed the false alarms but also let "ten, then twelve" through (A5), because "growing
  older" was listed as normal; ages and durations now may only grow by the time plausibly
  passed. T2 was split because the Reader filed "Tuesday night" as its own entity and the new
  "storm" entity in chapter 6 was never checked (new entities had no history). New entities
  are now checked against earlier facts that mention their name, and the Reader is told the
  entity of a time fact is the event, not the day. S3 remains hard: "threw it into the sea"
  needs the Reader to resolve "it" to the key.
- **Change of approach: structure over prompt tweaks.** Results varied between identical runs
  (A1 caught four times, then missed when "Keeper Calloway" wasn't linked), showing the real
  weakness: a mistake is only found if extraction, name linking AND the checker all succeed.
  Instead of rewording prompts: (1) a **safety-net check** compares every new fact with the
  earlier facts closest in meaning (via the embeddings) that are filed under a *different*
  entity, and asks whether each pair is the same entity contradicting itself: one AI call per
  chapter, independent of name linking; (2) **lower randomness** (`CHAT_TEMPERATURE`, default
  0.2) so identical input gives the same result; (3) `--runs N` in the evaluation reports how
  often each mistake is caught across runs; (4) a scoring bug fixed: a correct warning filed
  under another entity name (e.g. "the storm" for Tobias's arrival) was counted as a miss plus
  a false alarm.
- **First run on the untuned glassmaker story (3 runs):** average recall 51%, precision 80%,
  against 75-83% recall on the tuned lighthouse story, confirming the earlier tuning fit that
  story. It also exposed a loose evaluator: a flashback false alarm was scored as a catch
  because its quote contained the keyword "never". Structural changes (no rewording of
  existing instructions):
  (1) **stricter evaluation**: each answer-key item now has keywords for its NEW side and its
  EARLIER side, a warning must match both (in values/quotes, never the AI's explanation),
  and the miss diagnosis uses the same sides;
  (2) **reading in passages**: the Reader produced ~15 facts per chapter regardless of length,
  dropping side details; chapters are now read in ~700-character passages
  (`READ_PASSAGE_CHARS`) in parallel, each with the previous passage as context for "he"/"it";
  (3) **chapter timing**: one small AI call per chapter records when it is set ("flashback:
  twelve years before the fire", "time skip: three years after"), stored on the chapter,
  shown on the website, and given to the checker, whose rules now say reading order is not
  always story order;
  (4) **title + surname linking**: "Captain Crane" links to "Aldous Crane" when only one known
  character has that surname, and a full name only links if the known character has no other
  first name (so "Elena Vale" never joins "Marcus Vale / Captain Vale").
- **Result of the structural changes (glassmaker, untuned, strict scoring, 3 runs):** average
  recall 51% → 72%, precision 80% → 86%, mistakes caught every run 5 → 7 of 13, flashback traps
  flagged: none in any run, name linking 7/7. Still missed: an age after a time skip (needs
  arithmetic) and an inferred season ("midsummer fire" when the fire was on the autumn festival
  night). Remaining false alarms are forward changes such as an object shattering.
- **Reliability under a flaky AI service.** NVIDIA's free endpoint returned many 500/502/429
  errors; one call failed four times and crashed a whole evaluation. Fixes: (1) a single gate
  that every request passes through, so `MAX_PARALLEL_AI_CALLS` is a true app-wide limit (before,
  nested parallel steps could exceed it, causing 429s); optional `MAX_REQUESTS_PER_MINUTE`;
  (2) patient retries: 6 attempts (`AI_RETRY_ATTEMPTS`), waits of 2, 4, 8, 16, 32 s plus random
  jitter, honouring NVIDIA's Retry-After; (3) problems that can't be fixed by retrying (bad API
  key, retired model, invalid request) stop at once with a clear message; (4) the evaluation
  records a failed run and continues instead of losing all results; (5) the Reader starts with
  8192 tokens of answer space, avoiding slow "ran out of space" retries.
- **NVIDIA usage limit.** After many evaluation runs in one day, every request was refused with
  429 "Too Many Requests", even with only two requests in flight: an account usage quota, not a
  concurrency problem. Fixes: requests are paced by default (`MAX_REQUESTS_PER_MINUTE=30`);
  one refusal pauses ALL requests together (10 s, doubling for refusals in a row, up to 2 min,
  honouring Retry-After); 429s are retried for up to 5 minutes (`AI_RATE_LIMIT_PATIENCE`)
  instead of 6 attempts, then fail with a plain "usage limit is probably used up" message;
  evaluation reports show AI requests per run, so each feature's cost is visible.
- **Precision and waiting (lighthouse run: precision 67%, recall 83%, 18 minutes).** Causes: the
  checker flagged normal forward changes (a dog dying, the weather changing) and a misread
  timing; the Reader invented "Monday", copied from an example in its own instructions; the
  30/minute pacing was above NVIDIA's real limit that day; and the checker made one request per
  character. Fixes: (1) **no copyable examples** in the Reader's instructions, and facts whose
  day/month/number or quote isn't actually in the text are dropped automatically (no AI call);
  (2) a **double-check** step re-examines every warning (do the quotes say this? is it just the
  story moving forward, or a flashback?). Rejected warnings are kept as *dismissed* with the
  reason, never deleted, and the evaluation reports whether the double-check removed any real
  mistake; (3) **batched checking**: up to 4 characters per request (`CHECK_BATCH_SIZE`);
  (4) **pacing that learns**: requests are spaced evenly, each refusal halves the rate (minimum
  4/min) and it rises again as requests succeed; (5) the name rule ignores a leading
  "the/a/an", so "the storm on Friday" links to "the storm"; (6) reports count accepted and
  refused requests separately.
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
**What it does:** Measures how well the system actually catches mistakes. `eval/stories/lighthouse/` is an
original six-chapter test story ("The Gullstone Light") with **12 planted contradictions**
(5 attribute, 4 status, 3 timeline) and **3 decoys** — changes that look like mistakes but aren't
(a character moving house, an injury healing). Several mistakes deliberately use a *different
name* for the character, to test entity resolution too.

A second, harder story, `eval/stories/glassmaker/` ("The Glassmaker's Ledger", 5 chapters,
13 planted mistakes, 8 traps), was written after all tuning, so it measures how the system does
on a story it was never tuned on. It adds a flashback, a time skip, a secret identity, magic that
legitimately reverses damage, two characters named Tom, and a character called Rose next to
real roses. Run it with `python eval/run_eval.py --story glassmaker`.

**How it works:** `python eval/run_eval.py` wipes a separate `storyforge_eval` database (your real
story is never touched), feeds in the chapters with the real AI, and compares every warning with
the story's answer key (`ground_truth.json` in its folder). It reports precision (how many warnings were real),
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

### 8. Multiple books (projects)
**What it does:** Keeps several books in one StoryForge, each with its own chapters, characters,
facts and warnings. Nothing crosses between books: "Tom" in one book is never linked to "Tom" in
another, and both books can have a "ch1". The website has a book switcher in the sidebar and a
Books page to create, rename and delete books (deleting a book removes everything in it).

**How it works:** A `projects` table; every other table carries a `project_id`, chapters are
keyed by (book, chapter name), and names are unique per book. Every query is scoped to one
book. Book-specific addresses live under `/projects/{id}/...`; the short addresses without a
book (`/chapters`, `/entities`, ...) keep working and use the first book, created as "My story"
if none exists. Databases created before books existed are upgraded automatically on start-up:
their data moves into a book called "My story".

**Files:** `backend/schema.sql` (tables and upgrade), `backend/storage.py`, `backend/main.py`,
`frontend/index.html`, `backend/tests/test_projects.py`

---

### 9. Deployment, tests and tidy-up
- **Deployment:** `Dockerfile` (backend + website in one container), `render.yaml` for Render,
  and step-by-step instructions in [DEPLOY.md](DEPLOY.md). Tables are created automatically on
  start-up, so a fresh hosted database needs no manual setup.
- **Automated tests:** 74 tests in `backend/tests/` using a fake AI and a separate test database.
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
- Multi-author collaboration mode (books exist now, but there are no user accounts yet)
- Export to game-engine-friendly lore format (JSON)
- Tone/voice consistency checking
- Checking contradictions *within* a single chapter, and between different entities
- Story-time ordering (flashbacks) — the timeline currently follows reading order
- Neo4j-based graph storage (currently using Postgres + pgvector instead)

---

## Current endpoints

Books:

| Method & path | What it does |
|---|---|
| `GET /projects` | Every book, with chapter and open-issue counts |
| `POST /projects` | Create a book: `{"name": "The Glassmaker's Ledger"}` (names must be unique) |
| `GET /projects/{id}` | One book |
| `PATCH /projects/{id}` | Rename a book: `{"name": "..."}` |
| `DELETE /projects/{id}` | Delete a book and everything in it |

Everything below works inside one book. Use it under `/projects/{id}` (e.g.
`POST /projects/2/chapters`), or without the prefix for the first book (e.g. `POST /chapters`).


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
│   ├── stories/
│   │   ├── lighthouse/    # 6 chapters + ground_truth.json (answer key); tuned on
│   │   └── glassmaker/    # 5 chapters + ground_truth.json; never tuned on
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
python eval/run_eval.py                      # the lighthouse story
python eval/run_eval.py --story glassmaker   # the harder, untuned story
python eval/run_eval.py --runs 3             # run 3 times: how consistently is each mistake caught?
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
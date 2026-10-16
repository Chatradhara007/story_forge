# StoryForge AI — Project Status & Setup

**Last updated:** 16 October 2026 (story clock with ranges, fixed traits checked in code, `eval/stage_eval.py`: section 18). Before that, 12 October 2026 (two branches merged: the measured model setup, "lasting
facts", story-clock rules and evaluation tools from 4–5 October (section 14), plus finished
accounts and audit fixes (section 13). See section 15 for what the merge changed.)

A continuity-tracking system for long-form fiction. Writers ingest chapters; the system extracts
structured facts (characters, locations, items, events), builds up a persistent "story memory,"
and automatically flags contradictions when new content conflicts with something already
established — with a citation pointing to exactly where.

**Quick start:** `docker compose up -d`, start the backend (see [Setup](#setup)), then open
http://127.0.0.1:8000 for the website. To put it online, follow [DEPLOY.md](DEPLOY.md).

---

## ✅ What's done

### 1. Extraction pipeline
**What it does:** Takes raw chapter text and pulls out structured facts (entity, attribute,
value, supporting quote, confidence score) using an LLM.

**How it works:** Calls to an NVIDIA NIM chat model (the *reading* model, see section 13),
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
separate install, no build step). Pages:
- **Overview:** the book in one sentence (chapters, words, facts, open issues), a chapter strip
  showing each chapter's length and open issues, the most-flagged characters, and recent work.
- **Add chapters:** paste one chapter, or **upload many `.txt`/`.md` files at once** (added in
  filename order, names and numbers editable). Each chapter runs as a background job with a
  live progress bar, so long chapters never time out in the browser.
- **Issues:** every contradiction as two facing quotes with the conflicting words underlined,
  a severity (Serious / Worth a look / Unsure), and where it came from (checker, safety net,
  story clock). Show open, dismissed, resolved or all; group by severity, character or chapter.
  "It's intentional" dismisses with an optional reason (remembered across re-checks);
  "Keep the earlier version as canon" pins the earlier fact.
- **Story bible:** every entity laid out like a book's index, by type and letter. An entry
  shows all its names and everything the story says about it; pin facts as canon, merge
  entries (same type only) or split a name off. Merges and splits re-check affected chapters.
- **Timeline:** events in reading order or **story order** (flashbacks first, or the position
  you set on a chapter's page).
- **Ask:** natural-language questions answered only from stored facts, with sources.
- **Chapter pages:** the text, when it's set, its open issues, and its facts: correct, delete
  or pin them. Re-check, edit and re-check, or delete the chapter.
- **Books:** create, rename, delete, and **export a book as JSON lore**.
- **Sign-in** (when switched on): accounts, private books, and a daily chapter allowance shown
  in the sidebar.

Background work (re-checks after an edit, merge or correction) shows in the sidebar while it
runs, and the Issues page refreshes when it finishes.

**How it works:** Plain HTML/CSS/JavaScript in `frontend/` (`index.html`, `styles.css`,
`app.js`), calling the same API documented below.

**Files:** `frontend/`

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
- **Automated tests:** 219 tests in `backend/tests/` using a fake AI and a separate test database.
  They run on GitHub automatically on every push (`.github/workflows/tests.yml`).
- **Pinned dependencies:** exact versions in `requirements.txt`, so everyone installs the same thing.

---

### 10. Review fixes and new features (October 2026)
A code review (*StoryForge Review and Fix Plan*, 22 Sept 2026) confirmed nine bugs. Each now
has a test of the fixed behaviour in `backend/tests/test_review_fixes.py`; every one of those
tests fails on the code before the fixes.

| # | Was | Now |
|---|---|---|
| 1 | "Earlier" facts = any other chapter | Only chapters with a lower chapter number count as history |
| 2 | Re-submitting lost dismissals and deleted later chapters' warnings | Warnings have a fingerprint (entity, attribute, both values); the writer's dismissals (with reasons) survive re-checks; later chapters are re-checked automatically |
| 3 | "12" vs "twelve" dropped as invented | Numbers normalised to digits (twenty-one, 12th, a hundred and five, 1,000); grounding checked against the passage only |
| 4 | "Mara Calloway" auto-merged into "Keeper Calloway" | A full name links by rule only to someone known by the same first name; otherwise the AI decides |
| 5 | AI's id 0 + known canonical name created a duplicate | Linked to the existing entity |
| 6 | Correcting a fact left its warning open | Warnings store both fact ids; editing or deleting a fact resolves them and re-checks |
| 7 | Every fact ever recorded sent to the checker | At most `MAX_EVIDENCE_FACTS` (60): pinned and permanent-state facts plus the most relevant; a too-long prompt is split and retried |
| 8 | Token budget doubled on every retry | Grows only after a cut-off answer |
| 9 | Place mergeable into a character; no re-check | Type-checked; merges and splits re-check affected chapters |

Other review findings fixed: the timing detector now sees earlier chapters' timing notes and
up to 30,000 characters (opening and ending of longer chapters); adding a chapter runs as a
**background job** with progress (`POST /chapters/jobs`, `GET /jobs/{id}`) and **one job per
book at a time**; a **connection pool**; the safety net makes **one query per chapter** and uses
a **halfvec HNSW index** when pgvector ≥ 0.7; a rejected request no longer switches "low"
thinking off for good (only if "off" then works); the safety net keeps two real warnings from
one sentence; the app starts without an API key and `/health` says what's missing; chapter
names can't contain `/ \ ? #`; tests **fail** (not skip) when the database is down
(`SKIP_DB_TESTS=1` to skip on purpose); the stale `eval/story/` copy is gone.

New features (review Phases 5 and 6):
- **Story clock** (`storyclock.py`): ages and time skips checked by arithmetic in code, e.g.
  nine in chapter 1, "three years after the fire", fourteen in chapter 3: flagged ("should be
  about 12"). Targets the 0-of-3 misses. Not second-guessed by the double-check.
- **Canon facts:** pin a fact; the checker sees it as `[CANON]` and conflicts become serious.
- **Severity** (high / medium / low) on every warning, and **dismiss reasons**, collected at
  `GET /feedback` for growing the evaluation set.
- **Accounts** (`auth.py`, off by default): sign-in, private books per user, a daily chapter
  allowance (`DAILY_CHAPTER_LIMIT`), no cross-site API access, slowed password guessing.
- **Story-order timeline** and **JSON lore export** (`GET /export`).

**Deployment:** `Dockerfile` runs as a non-root user with a health check and ONE worker
(background jobs live in the web process); `render.yaml` switches sign-in on and generates
`SECRET_KEY`. See [DEPLOY.md](DEPLOY.md).

**Files:** `backend/pipeline.py`, `jobs.py`, `auth.py`, `storyclock.py` (new), changes in every
other backend file, `backend/tests/test_review_fixes.py`, `frontend/`

---

### 11. Character map, cream theme and book shelf (October 2026)
- **Relationships are recorded properly.** The Reader now also lists every stated relationship
  ("person | relation | other person"). `backend/relationships.py` turns the AI's wording into a
  fixed set of kinds: family (parent, spouse, sibling, relative) and social (friend, ally, rival,
  enemy, mentor, employer, romance); "son of" is turned round into "parent of", grandparents and
  cousins become "relative". They're stored in a `relationships` table (re-submitting a chapter
  replaces them; merges and splits move them) AND as plain facts on both people, so the
  contradiction checker sees "sister of Ines" vs "cousin of Ines" too.
- **Character map page** (`frontend/charts.js`, no chart library):
  - *Family tree*: generations from parent links, siblings kept together, spouses joined by a
    double line, children centred under their parents.
  - *Relationship web*: a deterministic force layout; line style AND colour show the kind
    (solid family, long-dash friendly, short-dash hostile), arrows show direction (parent,
    mentor, employer). Selecting someone labels their ties and fades everyone else.
  - *Chapter slider and Play*: "as of chapter N" reveals people and ties as the story
    introduces them; anyone who has died by then is drawn dashed. Layouts are computed once for
    the whole book so nothing jumps while you scrub, and the slider doubles as spoiler control.
  - *Impossible family ties* (sister in one chapter, cousin in another; A parent of B and B
    parent of A) are found by a rule in code and drawn in red, with both quotes in the panel.
  - *Who appears where*: the presence map, people/places/objects by chapter, dot size = facts,
    red = open issues.
- **Cream theme** with a bottle-green accent (parchment page, vellum sheets, iron-gall ink),
  correction red for issues, and bookbinding cover colours.
- **Book shelf home page**: cover tiles with initials, kind (novel, novella, short stories,
  screenplay, serial), synopsis, issue status, sort, and a Recent work panel across all books.

**Endpoints:** `GET /characters/map`, `GET /presence`, `GET /activity`; `POST/PATCH /projects`
accept `kind`, `synopsis`, `cover_color`. **Tests:** `backend/tests/test_charts.py`.

**Existing books:** relationships are only recorded for chapters read after this change.
Re-submit a book's chapters (Edit and re-check) to fill in its map.

---

### 12. Welcome page and top navigation (October 2026)
- **Welcome page** (product name, what it does, a real example of a caught mistake), then
  **sign-in**, then the app. With sign-in switched off, the welcome page shows on the first visit.
  The product name and tagline appear only on these two pages.
- **Top bar** instead of a left panel: a small mark (back to your books), the book switcher, the
  page tabs (Books, Overview, Chapters, Issues, Character map, Story bible, Timeline, Ask), a
  "checking…" indicator for background work, and an account menu with today's allowance.
  On phones the tabs become a swipeable strip.
- **Chapters**: a dropdown in the bar to jump to any chapter, a Chapters page (every chapter with
  when it's set, words, facts and open issues), and previous/next links on each chapter page.
- Page introductions rewritten in plainer words.
- **Typography:** headings in **Amatic SC**; all other text in **Avenir Light** where the device
  has Avenir (Apple devices), otherwise **Nunito Sans Light**, its closest open-licence match
  (Avenir is a commercial font and can't be shipped without a web licence; if you buy one, add
  its files to `frontend/fonts/` and an `@font-face` for "Avenir Next" at the top of `styles.css`).
  Both open fonts are served by the app itself from `frontend/fonts/` (SIL Open Font License,
  licence files alongside): no requests to Google, faster first load, works offline. Amatic SC is
  only used at heading sizes; small labels stay in the text font so they remain readable.

---

### 13. New models, finished accounts and an audit (12 October 2026)

**The model problem.** NVIDIA retired `nvidia/nemotron-3-super-120b-a12b` from its hosted API on
3 October 2026. The model setup that replaced it was measured on 4–5 October and is described in
section 14 and `docs/FINAL-CONFIGURATION.md`: Nemotron 3.5 Lightning reads, Nemotron 3 Ultra
judges (without thinking). Added on 12 October, on top of that setup:
- **Thinking settings per model family.** Nemotron/Qwen/Kimi use `enable_thinking`, gpt-oss uses
  `reasoning_effort`, DeepSeek uses `thinking`, Llama/Mistral/Gemma get none.
- **Timeouts and retries.** Each request gives up after `AI_REQUEST_TIMEOUT` (180 s; the library
  default was 10 minutes), and the OpenAI library's hidden retries are off (they tripled every
  attempt and ignored StoryForge's pacing).
- **An API-key problem never triggers failover** (no other model would do better): it stops at
  once with a clear message.
- **`eval/probe_models.py`**: sends each candidate StoryForge's real reading and judging requests
  several times and prints speed, reliability, mistakes caught and false alarms. Use it to pick
  candidates, then `run_eval.py --judges` to compare judges on the full answer key.

**Accounts, finished** (`auth.py`, `main.py`, `frontend/app.js`):
- Sign-in page with show/hide password, inline errors and a busy state; sign-up with a password
  check (8+ characters, not a common password, not the email); **forgotten password**: a
  one-time link valid for 60 minutes, emailed when `SMTP_HOST` is set, otherwise printed in the
  server log; the link opens a "choose a new password" page that signs you in.
- **Account page** (`#/account`, from the account menu): change your name; see today's
  allowance; change password; **sign out everywhere**; **delete account** (type your email and
  password; deletes every book).
- Sessions carry a version number: a password change, a reset or "sign out everywhere" ends
  every older session at once.
- Hardening: failed sign-ins are limited per account (10 per 15 min) as well as per address,
  and unknown emails take as long as wrong passwords (no account fishing); with
  `BEHIND_PROXY=true` the address comes from the proxy's own `X-Forwarded-For` entry, which
  visitors can't fake; sign-ups are limited per address (each account gets its own AI
  allowance); the "first account adopts old books" step can't run twice at once; Ask and search
  are limited per user (`HOURLY_QUESTION_LIMIT`, 60/hour), since they also use the AI;
  chapter checks that fail because the AI is down are given back to the daily allowance;
  security headers on every page (Content-Security-Policy allowing only the site's own
  scripts, so an injected script couldn't read the sign-in token; no framing; no referrer).
- New endpoints: `PATCH /auth/me`, `POST /auth/password`, `POST /auth/logout-everywhere`,
  `POST /auth/delete-account`, `POST /auth/forgot`, `POST /auth/reset`.

**Audit fixes:**
- **Database connections could run out for good.** If the database was unreachable when the
  connection pool was created, the request's pool slot was never returned. Ten failures (e.g.
  `/health` checks while the database restarted) and every later request hung, even after the
  database came back.
- **Changing a book while a chapter was being checked** (merge, split, delete a chapter or
  fact, correct a fact, delete the book) changed it underneath the check, which then failed
  at the very end, after minutes of AI work. These now wait briefly for the book and otherwise
  answer 409 "a chapter is being checked right now".
- **Word counts** only counted spaces, so line breaks between words were missed.
- Signing out now clears the previous user's book, chapters and background polling; an
  expired stored sign-in is cleared instead of looping back to the welcome page; a corrupted
  saved Issues view no longer breaks the Issues page.
- Tests: 23 new (`test_auth.py`, `test_models.py`); retired-model state no longer leaks
  between tests.

### 14. Measured model setup and accuracy work (4–5 October 2026)

From the branch merged on 12 October; details and measurements in `docs/FINAL-CONFIGURATION.md`
and `docs/CHAPTERS-AND-TIMING.md`, reports in `eval/results/`.

- **Two jobs, two model lists** (`CHAT_MODEL` = reader, `JUDGE_MODEL` = judge; comma-separated,
  best first). Measured on identical facts (lighthouse): Ultra as judge 71% precision / 83%
  recall vs Lightning 40% / 33%. A retired model (404/410) is never asked again; a model failing
  twice in a row is set aside for 10 minutes while the next one works; when every judge is gone,
  the readers judge; a model that crashes twice while thinking answers without thinking from
  then on. `/health` shows `chat_model`, `judge_model`, `chat_models_retired`,
  `chat_models_struggling`. `backend/check_models.py` tests what your key can use.
- **Embedding model guard.** The database remembers which embedding model made the stored
  vectors (`app_settings`). If `EMBED_MODEL` changes, saving and searching stop with a clear
  message (and `/health` says `embeddings_ok: false`) until `python reembed.py` has re-indexed
  every fact, resizing the column if the new model's vectors are a different size.
- **Lasting facts only** (`backend/lasting.py`). On realistic ~900-word chapters the Reader
  records 60–90 facts per chapter, most of them passing (moods, plans, actions, whereabouts), and
  comparing new facts with all of them made false alarms grow with chapter length. Earlier facts
  are now evidence only if they can't simply change: fixed traits, lasting states, past events
  pinned to a time; pinned canon always counts.
- **Rules in code before the double-check** (`contradictions.set_aside_by_rule`): a warning whose
  own explanation says the facts are consistent is set aside (or dropped when the checker was
  unsure); the story moving forward (alive → buried, whole → in pieces) is set aside, but not
  when the earlier side already mentions the same kind of change (scar on the right palm vs the
  left; mended vs still cracked); a flashback showing someone before an injury is set aside;
  the safety net drops pairs its own explanation calls different people.
- **The checker's indices are checked against its values.** It now copies the two values it
  compared; a right idea attached to the wrong fact or section is moved to the facts whose
  values match, and values that match no fact at all are dropped as misreadings.
- **Story clock additions:** vague time skips ("a few weeks later, still that autumn" = less
  than a year); one event on two weekdays (events only: markets recur); acting after death
  (memories and flashbacks excepted; "buried Bramble" doesn't make Ines dead).
- **Names:** a bare first name means the full name this chapter introduces (two Toms); names the
  text declares ("his real name was Edwin Marsh") link the two, merging existing entries before
  the chapter is checked; social ties (ally, mentor...) are drawn on the map but not checked.
- **Evaluation:** a third, held-out story (`eval/stories/fallenking`, 8 chapters of 725–1,080
  words, 11 planted mistakes, 5 traps, never tuned on); `--judges "a,b"` compares judges on the
  same saved reading; `--reuse-reading` skips reading; a time-per-chapter table; "check by hand"
  items; `eval/analyze_without_ai.py` replays the lasting-facts filter over the last run for free.
- **Held-out test protocol** (decided in advance, see `docs/FINAL-CONFIGURATION.md`): run The
  Fallen King once with the final configuration and record the numbers without tuning on them.

### 15. What the 12 October merge changed

The two branches were combined by copying files, and the 4–5 October branch's core files
(`llm.py`, `storage.py`, `contradictions.py`, `entities.py`, `storyclock.py`, `pipeline.py`,
`eval/run_eval.py`, this README) were overwritten by the 12 October versions. Only its new files
survived (`lasting.py`, `reembed.py`, `check_models.py`, its tests, docs, the third story and the
results), so 30 of its tests failed and 8 errored. Its features were rebuilt on top of the 12
October code, with its tests as the specification: **all 219 tests pass**. Decisions:
- **Settings:** the measured configuration's names (`CHAT_MODEL`, `JUDGE_MODEL`, lists) are the
  main ones; the 12 October names (`CHAT_MODEL_READING`, `CHAT_MODEL_JUDGING`,
  `CHAT_MODEL_FALLBACKS`) still work and go first in their list.
- **Chapter timing** is done by the reader (as in the measured setup), not the judge.
- **Randomness** is 0 for both jobs (the measured setup), so `test_safety_net` now expects 0.
- **"Alive, then dead"** is set aside by a rule before the double-check, so the double-check
  test in `test_precision.py` now uses a change no rule recognises (moving house).
- **Reading cache:** the old files in `eval/cache/` (keyed by hashes whose recipe was lost) are
  still read, using the newest reading per chapter; chapter timing is detected again once and
  saved in the new format.
- `eval/story/` and `eval/ground_truth.json` were stale copies of the lighthouse story: removed.

### 16. Fixes from the first held-out run (12 October 2026, evening)

The Fallen King with Ultra judging (saved Lightning reading): precision 5%, recall 27%, F1 0.09,
52 false alarms, 1,234 s of judging. The false alarms came from: the safety net 28 (1 catch),
the AI checker 19 (2 catches), the story clock 5 (0 catches). Causes and general fixes:
- **Chapter timing was misread** ("the next day" became "two years after the council";
  "Fourteen years before the fall" became a time skip), so ages "didn't add up". Now a timing
  the chapter's opening states ("Two years later", "the next day", "N years before ...") is used
  directly, without the AI (5 of 8 Fallen King chapters, 3 of 5 glassmaker); the AI prompt
  judges against the PREVIOUS chapter; "N years before" is always a flashback.
- **Story clock:** flashbacks no longer move the main timeline (the chapter after one is read
  against the story before it); an anchored note repeated word for word ("two years after the
  abdication") is the same moment; relative, past, future and other people's ages ("two years
  younger than Aurel", "age at coronation", "until Tam is twenty-five", "son_age") aren't
  ages; a misread age that breaks an otherwise rising history is skipped; an age going UP with
  only "continues" notes isn't flagged (time may have passed unrecorded); a death must be
  stated briefly and without hedging ("deceased (implied)" isn't one); backstory ("When you
  were two, Oren marched...") isn't acting after death.
- **The AI no longer judges ages** (wrong 9 times in 10): the story clock does the arithmetic.
- **Safety net:** only names that could be the same entity are compared (a shared word, a
  description or bare title, a mention of one in the other's fact, or the same specific
  detail, e.g. "hands" for a secret identity); family ties are left to the checker and the
  map's rule. 1,535 compared pairs became 205 (40 requests became 7).
- **The checker and the safety net run at the same time.**

Measured without AI (`analyze`-style replay of that run, and offline runs with a stand-in AI):
35 of the 52 false alarms are removed by these rules; the code-only checks went from 13 false
alarms and 0 catches to 0 false alarms and 1 catch (T3, Bram's age, by the story clock); total
AI requests per run 109 → 71 (offline count). Expected with the real AI: F1 around 0.3 instead
of 0.09 and judging roughly 40–50% faster. **Not yet measured with the real AI.**

**Second run with the fixes** (same saved reading): 21 false alarms instead of 52, 2 catches
plus T1 under "check by hand" (Aurel 33 → 38 in about 2.4 years: the story clock's warning is
T1, only worded against a different earlier age), judging **571 s instead of 1,234 s**. But Ultra
answered two 500 errors in a row in chapter 3, was set aside for 10 minutes, and **Lightning
judged chapters 3–8 and the double-check**, so the run didn't measure the intended setup. Fixes:
- **Patience for the judge:** a model gets 4 tries (`AI_FAILOVER_AFTER`) before the next one takes
  over, and is set aside for 2 minutes (`AI_SET_ASIDE_SECONDS`), not 10: Ultra's 500s are brief.
- **`--judges` never falls back** to a reader model, so a judge is never scored on another
  model's answers (it is retried patiently instead).
- **Safety net, stricter:** besides related names, the two facts must share a concrete detail
  (a colour, a body part or mark, a count, the same specific attribute) or the new fact must be
  plainly about the other entity. The double-check is told when a warning comes from two
  different names and keeps it only if the quotes show they are the same entity.
- **Acting after death** must be the entity itself acting ("your father's army burned the
  fields" is not King Oren acting).
Replaying that run's 21 warnings through these rules: 9 false alarms and 3 catches remain
(precision 25%, recall 27%, F1 0.26, with Lightning's judging; Ultra judging throughout should do
better, not yet measured).

**The Fallen King is no longer held out**: these fixes were found by looking at its results,
so its scores now flatter StoryForge like the other two stories. An honest number needs a new
story nobody has tuned on.

### 17. Fixes from the Ultra runs (13 October 2026)

Two runs with Ultra judging throughout, same saved reading: run A F1 0.19 (17 false alarms,
721 s), run B **F1 0.28** (precision 22%, recall 36%, 14 false alarms, **545 s**), catching A1,
A2, S1, T3, plus T1 under "check by hand". The same setup varies a lot from run to run, so
compare setups with `--runs 2` or more.

Twelve of run B's 14 false alarms fit five patterns, now set aside by rules in code before the
double-check (`set_aside_by_rule`; set-aside warnings stay visible under Dismissed, with the reason):
- **An age paired with something that isn't this character's age now:** someone else's age
  (`son_age`), a future age ("until Tam is twenty-five"), a past age ("at seventeen"), a relative
  age ("two years younger than Aurel"), or a length of time ("six years" vs "six years old"). Ages
  are left to the story clock unless both sides are clean current ages. Relative against relative
  ("younger sister" vs "elder sister") is still checked.
- **Family ties that can both be true:** "child of Mother" vs "married to Thessaly" (different
  kinds of tie to different people), and a parent/child tie recorded the other way round.
  Different ties to the same person ("sister of Orla" vs "cousin of Orla") are still checked.
- **"Alive" against anything but a death** ("poles a ferry" vs "alive").
- **Growing up:** a colt in a flashback vs a stallion now, same colour.
- **Growing old:** "white around the muzzle" is ageing, not a colour change (decoy D4).

Replaying the four saved runs through the rules: no real catch is set aside. Run B goes to
**4 catches, 2 false alarms: precision 67%, F1 0.47** (0.59 if T1 is counted). Run A goes to
F1 0.26. Unit tests cover each rule and the planted mistakes it must keep (`test_noise_rules_v4.py`).

**Faster judging:**
- Name linking (141 s of run B) sends 12 names per AI call, side by side, instead of one
  40-name call.
- The double-check sends 8 warnings per call, side by side, instead of 20.
- With fewer warnings reaching the double-check, it has less to do.

Not yet measured with the real AI.

**Comparing judges:** `--judges` takes real model names from `python check_models.py --list`:
`python run_eval.py --story fallenking --runs 2 --judges "nvidia/nemotron-3-ultra-550b-a55b,deepseek-ai/deepseek-v4.1-flash,z-ai/glm-5.3"`

### 18. A story clock with ranges, fixed traits in code, a 1-second evaluation (16 October 2026)

**Why.** A mistake is caught only if reading, name linking AND the AI checker all succeed, and
the last held-out run (13 Oct) scored precision 38%, recall 27%: the noise rules removed false
alarms, but plain value clashes (grey stallion, then black; a scar on the left hand, then the
right; 64, 66, then 62) were still left to an AI shown up to 60 facts.

**1. Story clock (`backend/storytime.py`; `storyclock.check_ages` now calls it).** Every chapter
gets a position on one timeline, in years, as a range [earliest, latest]: from its opening words
first, then its timing note. "N years after <event>" is measured from the event (the earliest
chapter whose first sentence names it, or an earlier phrase that placed it); unknown events
widen the range instead of being guessed; "later" after a flashback continues the main story.
Ages become birth ranges, flagged only when no reading of the timing fits. The weekday and
acting-after-death checks are unchanged. The timing block the AI sees now also says where the
clock puts each chapter (`[story clock: between 3 years and 4 years after chapter 1 begins]`).
The previous version (`check_ages_by_notes`) is kept for reference.

**2. Fixed traits in code (`backend/traits.py`, stage "trait check").** Eye colour, an animal's
colour, the side of a scar or lost limb, handedness, who is older, and family ties are compared
as values, also when the Reader filed them under someone else ("Ember, the black stallion"
under Aurel). Only clear wording makes a claim. `set_aside_by_rule` leaves them alone; the AI
double-check still reviews them. `TRAIT_CHECKS=off` turns them off (the automated tests do).

**3. `eval/stage_eval.py`: every check done in code, from a saved reading, in about a second,
free.** Per planted mistake: was each side read, are both on one entry (name rules only, and
with the answer key's linking), did the code checks catch it.

    python eval/stage_eval.py --all

**Measured** (saved readings, answer-key linking, code checks only):

| Story | 13 Oct clock: caught / false alarms | Now: caught / false alarms |
|---|---|---|
| Lighthouse (12) | 1 / 0 | 3 / 0 (A1, A2, A5) |
| Glassmaker (13) | 0 / 1 | 4 / 0 (A1, A3, A4, T2) |
| Fallen King (11) | 2 / 0 | 5 / 0 (A1, A2, A3, T1, T3) |

The AI checker and safety net still run on top. **The Fallen King has been used for tuning
(12–16 Oct), so it is no longer held out: write a new story before quoting a held-out score.**

**Files:** `backend/storytime.py`, `backend/traits.py` (new), `backend/storyclock.py`,
`backend/contradictions.py`, `backend/pipeline.py`, `backend/storage.py` (`get_time_notes`
also returns `opening`), `backend/models.py` (source `"trait check"`), `frontend/app.js`,
`eval/stage_eval.py`, `backend/tests/test_storytime.py`, `backend/tests/test_traits.py`,
`backend/tests/conftest.py`, `backend/tests/test_speed_and_evidence.py`.

### 19. Lasting states in code, two warning levels, safety net off (16 October 2026, evening)

**What the 16 Oct baseline showed** (Fallen King, Lightning judge): every real catch came from the
checks done in code (5, 0 false alarms); every false alarm came from the AI checker (6) and the
safety net (6), which caught nothing and took ~7 of the 35 minutes.

1. **`backend/states.py`**: objects followed by name through every fact of the book: *gone*
   ("threw the brass key into the sea", "burned to ash") then used; *given away* ("took the signet
   ring off his finger and pushed it across") then worn by the giver again (a hand-back clears it).
   Abilities: *blind* then reading/writing; *lost the left hand* then using it or both hands.
   Memories and flashbacks never count. Runs in the "trait check" stage.
2. **"elder sister of Aurel"** is linked to Aurel's only known sibling (Mira) in the trait check.
3. **Two levels on the website:** "Confirmed" (story clock, trait check: done in code) and
   "Worth a look" (the AI). Code checks now run first and win when both flag the same fact.
   `run_eval.py` reports precision/recall/F1 for each level.
4. **Safety net off by default** (`SAFETY_NET=on` to turn it back on; the tests do).
5. Answer key: Fallen King T1 also accepts Aurel's chapter 2 age as the earlier side (same mistake).

**Measured** (`stage_eval.py`, saved readings, answer-key linking, code checks only, 0 false alarms):
Fallen King 5 → **8**/11, Glassmaker 4 → **5**/13, Lighthouse 3 → **5**/12 (**18/36** in total).
Re-scored, the 16 Oct run's "Confirmed" level was precision 100%, recall 45%, F1 0.62.

## 🚧 What's left

0. **The held-out test:** `cd eval`, `python analyze_without_ai.py --story fallenking` (free),
   then `python run_eval.py --story fallenking --judges "nvidia/nemotron-3-ultra-550b-a55b" --runs 1`.
   Record the numbers here and in `docs/FINAL-CONFIGURATION.md` without tuning on them.
1. **Re-run the evaluation with the real AI** on both tuning stories, 3 runs each
   (`python eval/run_eval.py --runs 3` and `--story glassmaker --runs 3`). The last saved numbers
   predate the double-check, the story clock and the bug fixes. Record the scores here.
2. **A third test story with realistic ~4,000-word chapters**, to prove the Phase 4 scale work
   end to end (the review's "done when" for Phase 4).
3. **Contradictions within a single chapter** (review Phase 3) are still not checked.
4. **Permanent-state ledger** (review Phase 5): permanent states are always shown to the checker
   now (bug 7 fix), but reversals aren't yet caught by a rule in code the way ages are.
5. **Series** (books that share characters, so a sequel is checked against book one).
6. **Deploy** following [DEPLOY.md](DEPLOY.md).

### Future work / explicitly out of scope for now
- Multi-author collaboration mode (accounts exist, but a book belongs to one account)
- Tone/voice consistency checking
- Checking contradictions *within* a single chapter, and between different entities
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
| `PATCH /facts/{id}` | Correct a fact: `{"attribute": ..., "value": ..., "entity_type": ...}` (logged; resolves its warnings and re-checks), or pin it as canon: `{"pinned": true}` |
| `DELETE /facts/{id}` | Delete a wrongly extracted fact (logged) |
| `GET /facts/{name}` | Everything known about an entity, looked up by any of its names, in reading order |
| `GET /entities` | Every entity with all the names it goes by and its fact count |
| `GET /entities/{id}` | One entity with all its facts |
| `POST /entities/merge` | Fix a missed link: `{"keep_entity_id": 1, "merge_entity_id": 2}` |
| `POST /entities/{id}/detach` | Fix a wrong link: `{"name": "The Stranger"}` splits that name off into its own entity |
| `GET /search?q=...` | Semantic search across all stored facts |
| `GET /contradictions` | Contradictions, most recent first; filter with `?status=open`, `dismissed` or `resolved` |
| `PATCH /contradictions/{id}` | Dismiss or reopen a warning: `{"status": "dismissed", "reason": "..."}` (remembered across re-checks) |
| `GET /timeline` | Event facts in reading order, or `?order=story` for story time |
| `POST /ask` | `{"question": "..."}` → an answer written from stored facts, plus the facts used |
| `POST /chapters/jobs` | Same as `POST /chapters`, in the background: returns `{"job_id"}` at once (the website uses this) |
| `GET /jobs`, `GET /jobs/{id}` | Background jobs: status (queued/running/done/failed), stage, progress 0–1, result |
| `POST /chapters/{id}/recheck` | Check a saved chapter again against the story as it is now (no re-reading) |
| `PATCH /chapters/{id}` | Set its story position: `{"story_order": 0.5}` (null = automatic) |
| `GET /overview` | Dashboard numbers for the book |
| `GET /export` | The whole book as JSON lore |
| `GET /feedback` | The writer's dismissals with reasons |
| `GET /health` | Always 200; says whether the database and AI key are set up |

Accounts (only needed when `AUTH_REQUIRED=true`): `GET /auth/config`, `POST /auth/register`,
`POST /auth/login` (both return a token to send as `Authorization: Bearer ...`), `GET /auth/me`,
`PATCH /auth/me` (name), `POST /auth/password`, `POST /auth/logout-everywhere`,
`POST /auth/delete-account`, `POST /auth/forgot`, `POST /auth/reset`.

Interactive documentation for every endpoint: http://127.0.0.1:8000/docs

---

## Folder layout

```
storyforge/
├── README.md
├── DEPLOY.md              # how to put it online
├── docs/                # FINAL-CONFIGURATION.md (models, measurements, held-out test), CHAPTERS-AND-TIMING.md
├── Dockerfile             # backend + website in one container
├── render.yaml            # Render deployment blueprint
├── docker-compose.yml     # local Postgres + pgvector (and optionally the app)
├── .github/workflows/tests.yml   # runs the tests on every push
├── frontend/
│   ├── index.html         # the website (no build step)
│   ├── styles.css
│   ├── app.js
│   └── charts.js          # family tree, relationship web, presence map
├── eval/
│   ├── stories/
│   │   ├── lighthouse/    # 6 chapters + ground_truth.json (answer key); tuned on
│   │   ├── glassmaker/    # 5 chapters + ground_truth.json; partly tuned on
│   │   └── fallenking/    # 8 longer chapters + ground_truth.json; HELD OUT
│   ├── run_eval.py        # scores the system against the answer key (--judges, --reuse-reading)
│   ├── probe_models.py    # compare candidate models on StoryForge's real requests
│   ├── analyze_without_ai.py  # replay the lasting-facts filter over the last run (no AI)
│   ├── cache/             # saved readings, so judges are compared on identical facts
│   └── results/           # saved reports
└── backend/
    ├── .env.example
    ├── requirements.txt / requirements-dev.txt
    ├── schema.sql          # database tables (applied automatically on start-up)
    ├── llm.py              # AI connection, model names, retries, batched embeddings
    ├── pipeline.py         # add a chapter / re-check a saved chapter
    ├── jobs.py             # background jobs, one per book at a time
    ├── auth.py             # accounts, sessions, daily allowance
    ├── storyclock.py       # ages, time skips, weekdays, acting after death
    ├── lasting.py          # which earlier facts can be contradicted (vs. simply change)
    ├── check_models.py     # which models your NVIDIA key can use right now
    ├── reembed.py          # re-index stored facts after changing EMBED_MODEL
    ├── relationships.py    # relationship wording -> fixed kinds; impossible family ties
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
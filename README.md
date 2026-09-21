# StoryForge AI — Steps 1–3: Extraction + Story Memory + Contradiction Detection

## Folder layout

```
storyforge/
├── .gitignore
├── README.md
├── docker-compose.yml  # local Postgres + pgvector
└── backend/
    ├── .env.example       # copy to .env and fill in your keys
    ├── requirements.txt
    ├── schema.sql         # run this in Supabase's SQL editor (re-run after updates — it's idempotent)
    ├── models.py          # Fact / Contradiction / ExtractionResult / ChapterIngestResult schemas
    ├── extract.py         # NVIDIA NIM extraction logic
    ├── storage.py         # embeddings + Postgres persistence + semantic search + contradiction storage
    ├── contradictions.py  # contradiction detection logic
    └── main.py            # FastAPI app + all endpoints
```

## Setup

### 1. Database (local Postgres + pgvector, via Docker)
No cloud account needed — this runs identically for every teammate regardless of OS.

1. Install Docker Desktop if you don't have it: https://www.docker.com/products/docker-desktop
2. From the repo root:
```bash
docker compose up -d
```
This starts a Postgres instance with pgvector pre-installed, on `localhost:5432`, with credentials `storyforge` / `storyforge` (fine for local dev — change them in `docker-compose.yml` if this ever runs anywhere shared).

3. Apply the schema:
```bash
docker exec -i $(docker compose ps -q db) psql -U storyforge -d storyforge < backend/schema.sql
```
(Re-run this any time `schema.sql` changes — every statement uses `if not exists`, so it's safe to run repeatedly.)

**Stopping/restarting:** `docker compose stop` to pause, `docker compose up -d` to resume — your data persists in a Docker volume between restarts. `docker compose down -v` wipes the database entirely if you ever want a clean slate.

### 2. Backend
```bash
cd storyforge/backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # edit .env: paste your NVIDIA_API_KEY (DATABASE_URL default already matches docker-compose.yml)
uvicorn main:app --reload
```

Get an NVIDIA NIM API key at https://build.nvidia.com (click "Get API Key" on any model page).

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /extract` | Extract facts only, don't store — use for testing extraction |
| `POST /chapters` | Full pipeline: extract, store, check for contradictions, store any found — use this for real ingestion |
| `GET /facts/{entity}` | Everything currently known about a named entity |
| `GET /search?q=...` | Semantic search across all stored facts |
| `GET /contradictions` | All contradictions flagged so far, most recent first |
| `GET /health` | Sanity check |

## Test it

**Ingest a chapter (extracts + stores):**
```bash
curl -X POST http://127.0.0.1:8000/chapters \
  -H "Content-Type: application/json" \
  -d '{
    "chapter_id": "ch1",
    "text": "Marcus stood at the edge of the tavern, his blue eyes scanning the room. He had not seen his sister Elena since the war ended three years ago. The old innkeeper, Tomas, nodded at him from behind the bar."
  }'
```

**Look up everything known about Marcus:**
```bash
curl "http://127.0.0.1:8000/facts/Marcus"
```

**Ingest a second, contradicting chapter:**
```bash
curl -X POST http://127.0.0.1:8000/chapters \
  -H "Content-Type: application/json" \
  -d '{
    "chapter_id": "ch5",
    "text": "Marcus looked up, his green eyes catching the torchlight as he entered the old inn."
  }'
```

The response from this call should already include a populated `contradictions` array — flagging that Marcus's eye color changed from blue (ch1) to green (ch5) with no in-story explanation. That's the contradiction-detection pipeline firing automatically as part of `/chapters`.

**Confirm it persisted:**
```bash
curl "http://127.0.0.1:8000/contradictions"
```

**Also try a status contradiction** — ingest a "death," then a later chapter where the same character acts normally:
```bash
curl -X POST http://127.0.0.1:8000/chapters \
  -H "Content-Type: application/json" \
  -d '{"chapter_id": "ch8", "text": "Tomas collapsed behind the bar and did not rise again. The innkeeper was dead."}'

curl -X POST http://127.0.0.1:8000/chapters \
  -H "Content-Type: application/json" \
  -d '{"chapter_id": "ch12", "text": "Tomas poured Marcus another drink and laughed at his joke."}'
```
The second call's response should flag a `status` contradiction — Tomas acting alive after being established as dead.

**Try semantic search:**
```bash
curl "http://127.0.0.1:8000/search?q=who%20has%20died%20in%20the%20story"
```

## Troubleshooting

**Extraction / tool calling fails or returns empty:**
1. Remove the `tool_choice` line in `extract.py` — let the model decide to call the only tool offered.
2. Still unreliable? Use the commented-out fallback function at the bottom of `extract.py`, which prompts for raw JSON instead of using function calling.
3. Try swapping `MODEL` in `extract.py` to `meta/llama-3.3-70b-instruct` or `nvidia/llama-3.1-nemotron-70b-instruct`.

**Storage fails / can't connect to Postgres:**
- Confirm the Docker container is actually running: `docker compose ps` should show `db` as `Up`.
- Confirm `DATABASE_URL` in `.env` matches `docker-compose.yml`'s credentials/port — the `.env.example` default already matches, so this only matters if you changed one and not the other.
- If port 5432 is already taken by another Postgres install on your machine, change the host port in `docker-compose.yml` (e.g. `"5433:5432"`) and update `DATABASE_URL` to match.

**Embedding calls fail:**
- Confirm `nvidia/nv-embedqa-e5-v5` is enabled for your NVIDIA API key (some models require separate opt-in on build.nvidia.com).
- Make sure you're passing `input_type` via `extra_body` — the plain OpenAI SDK doesn't have a native param for it, so it's easy to accidentally drop when refactoring.

## Checklist before moving to Step 4
- [ ] `/chapters` extracts, stores, and checks for contradictions in one call without errors
- [ ] The eye-color test above correctly flags an `attribute` contradiction
- [ ] The Tomas test above correctly flags a `status` contradiction
- [ ] `/contradictions` shows persisted results after ingesting the tests above
- [ ] Ingesting a chapter with genuinely new, non-conflicting info does NOT get flagged (test a false-positive case too — this matters as much as catching real ones)
- [ ] Repo pushed to GitHub with `.env` excluded

## A note on evaluation (don't skip this)
Once the pipeline works on hand-picked examples, build a small seeded test set: write or find a short multi-chapter story, deliberately plant 10-15 contradictions of each type, run them all through `/chapters`, and measure precision/recall against `/contradictions`. This is what turns "we built a demo" into "we built and measured a system" — the single highest-value addition for a capstone writeup, and worth doing before moving to the frontend.

## Next (Step 4)
Minimal frontend: a page to paste in chapter text, see extracted facts (auto-generated character/world bible), and see flagged contradictions with citations — wired up against the endpoints already built here.

# StoryForge AI — Steps 1 & 2: Extraction + Story Memory

## Folder layout

```
storyforge/
├── .gitignore
├── README.md
└── backend/
    ├── .env.example      # copy to .env and fill in your keys
    ├── requirements.txt
    ├── schema.sql        # run this in Supabase's SQL editor once
    ├── models.py         # Fact / ExtractionResult schema
    ├── extract.py        # NVIDIA NIM extraction logic
    ├── storage.py         # embeddings + Postgres persistence + semantic search
    └── main.py           # FastAPI app + all endpoints
```

## Setup

### 1. Supabase project
1. Go to https://supabase.com, create a free project.
2. Open **SQL Editor** in the left sidebar, paste the contents of `schema.sql`, click **Run**. This enables pgvector and creates the `facts` table.
3. Go to **Project Settings > Database > Connection string**, copy the URI (use the direct connection, port 5432 — not the pooler, for this simple setup). It looks like:
   `postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres`

### 2. Backend
```bash
cd storyforge/backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # edit .env: paste your NVIDIA_API_KEY and SUPABASE_DB_URL
uvicorn main:app --reload
```

Get an NVIDIA NIM API key at https://build.nvidia.com (click "Get API Key" on any model page).

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /extract` | Extract facts only, don't store — use for testing extraction |
| `POST /chapters` | Extract facts AND persist to story memory — use this for real ingestion |
| `GET /facts/{entity}` | Everything currently known about a named entity |
| `GET /search?q=...` | Semantic search across all stored facts |
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

**Check `/facts/Marcus` again** — you should now see two conflicting `eye_color` entries (`blue` from ch1, `green` from ch5) with different `chapter_id`s and `source_quote`s. This is exactly the raw material Step 3 (contradiction detection) will consume.

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
- Double-check `SUPABASE_DB_URL` — it's easy to copy the pooler URL by mistake. Use the direct connection string (port 5432).
- If your network blocks outbound Postgres connections, Supabase also offers a connection pooler on port 6543 as a fallback — swap the port in the URL if 5432 times out.

**Embedding calls fail:**
- Confirm `nvidia/nv-embedqa-e5-v5` is enabled for your NVIDIA API key (some models require separate opt-in on build.nvidia.com).
- Make sure you're passing `input_type` via `extra_body` — the plain OpenAI SDK doesn't have a native param for it, so it's easy to accidentally drop when refactoring.

## Checklist before moving to Step 3
- [ ] `/chapters` extracts and stores facts without errors
- [ ] `/facts/{entity}` correctly returns facts across multiple ingested chapters for the same entity
- [ ] The deliberate-contradiction test above actually shows two conflicting facts stored side by side
- [ ] `/search` returns semantically relevant results, not just exact keyword matches
- [ ] Repo pushed to GitHub with `.env` excluded

## Next (Step 3)
Contradiction detection: given a newly ingested chapter's facts, retrieve conflicting prior facts (like the `/facts/Marcus` example above) and use an LLM call to decide whether it's a real contradiction, then generate a human-readable explanation with a citation.

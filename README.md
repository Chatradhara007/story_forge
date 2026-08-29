# StoryForge AI — Step 1: Extraction Skeleton

## Folder layout

```
storyforge/
├── .gitignore
├── README.md
└── backend/
    ├── .env.example      # copy to .env and fill in your key
    ├── requirements.txt
    ├── models.py         # Fact / ExtractionResult schema
    ├── extract.py        # NVIDIA NIM extraction logic
    └── main.py           # FastAPI app + /extract endpoint
```

## Setup

```bash
cd storyforge/backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then edit .env and paste your NVIDIA NIM API key
uvicorn main:app --reload
```

Get an NVIDIA NIM API key at https://build.nvidia.com (click "Get API Key" on any model page).

## Test it

```bash
curl -X POST http://127.0.0.1:8000/extract \
  -H "Content-Type: application/json" \
  -d '{
    "chapter_id": "ch1",
    "text": "Marcus stood at the edge of the tavern, his blue eyes scanning the room. He had not seen his sister Elena since the war ended three years ago. The old innkeeper, Tomas, nodded at him from behind the bar."
  }'
```

You should get back structured JSON facts (Marcus's eye color, his relationship to Elena, the war ending three years ago, Tomas being the innkeeper, etc.).

## If tool calling fails / empty response

1. First try removing the `tool_choice` line in `extract.py` — let the model decide to call the only tool offered.
2. If still unreliable, use the commented-out fallback function at the bottom of `extract.py`, which prompts for raw JSON instead of using function calling.
3. Try swapping `MODEL` in `extract.py` to `meta/llama-3.3-70b-instruct` or `nvidia/llama-3.1-nemotron-70b-instruct` — tool-calling reliability varies across NIM catalog models.

## Checklist before moving to Step 2
- [ ] `/extract` returns valid structured facts on multiple test inputs
- [ ] `source_quote` fields actually match text in the chapter (spot-check a few)
- [ ] Confidence scores look reasonable (not everything at 1.0 or 0.5)
- [ ] Repo pushed to GitHub with `.env` excluded

## Next (Step 2)
Supabase (Postgres + pgvector) setup to persist these extracted facts across chapters, so the system builds up story memory instead of extracting fresh each time.

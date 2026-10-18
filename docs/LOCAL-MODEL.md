# Running the Reader on your own GPU (Ollama)

The free NVIDIA tier spends most of a run waiting in a queue (13 minutes for one chapter on
18 Oct 2026). A model on your own NVIDIA GPU has no queue, no rate limit and no daily cap.
StoryForge talks to it the same way it talks to NVIDIA (an OpenAI-style API), so it is a
settings change.

## 1. Install and pick a model (Windows)

1. Install Ollama from https://ollama.com/download and open it once.
2. See how much GPU memory you have (PowerShell): `nvidia-smi` (look at the "MiB" total).
3. Download a model that fits (it must fit in GPU memory, with some room to spare):

   | GPU memory | Model | Download |
   |---|---|---|
   | 8 GB | Qwen2.5 7B Instruct | `ollama pull qwen2.5:7b-instruct` |
   | 12-16 GB | Qwen2.5 14B Instruct | `ollama pull qwen2.5:14b-instruct` |
   | 24 GB or more | Qwen2.5 32B Instruct | `ollama pull qwen2.5:32b-instruct` |

   Qwen2.5 follows structured output well and doesn't "think" first (thinking models are
   slower and StoryForge doesn't need it for reading). Bigger reads better and slower.
4. Check it works: `ollama run qwen2.5:14b-instruct "Say hello"`.

## 2. Point StoryForge at it (`backend/.env`)

```
AI_BASE_URL=http://localhost:11434/v1
CHAT_MODEL=qwen2.5:14b-instruct
JUDGE_MODEL=qwen2.5:14b-instruct
MAX_PARALLEL_AI_CALLS=2
AI_REQUEST_TIMEOUT=300
AI_RETRY_ATTEMPTS=2
```

- No key and no pacing are needed for a local server (`MAX_REQUESTS_PER_MINUTE` is off).
- **Embeddings** stay on NVIDIA by default (`EMBED_MODEL` unchanged: no re-indexing). To be
  fully local: `ollama pull nomic-embed-text`, set `EMBED_MODEL=nomic-embed-text`, then run
  `python reembed.py` in `backend/` once. Smaller vectors are padded to the stored size.
- `MAX_PARALLEL_AI_CALLS=2` matches Ollama's default; for more, set the Windows environment
  variable `OLLAMA_NUM_PARALLEL=4` and restart Ollama.
- Name linking with the AI is free now: try `NAME_LINKING=ai` as well and compare.

## 3. Measure it against NVIDIA

Readings are saved per reader model, so the NVIDIA readings stay. Run each story once:

```powershell
python eval/run_eval.py --story fallenking --reuse-reading
python eval/run_eval.py --story glassmaker --reuse-reading
python eval/run_eval.py --story lighthouse --reuse-reading
python eval/run_eval.py --story nightshift --reuse-reading
python eval/run_eval.py --story kestrel --reuse-reading
```

Compare the time and the caught / false-alarm counts with the Lightning runs. Keep the local
model only if it reads at least as well; speed alone is not enough.

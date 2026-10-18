# The best free setup: chaining free AI services

No single free service is reliable and unlimited, so StoryForge can use several in one chain.
Each model name can carry its provider in front; the first one that works is used, and one
that fails or runs out of free requests hands over to the next at once.

```
CHAT_MODEL=ollama:qwen2.5:7b-instruct,groq:llama-3.3-70b-versatile,nvidia:nvidia/nemotron-3.5-lightning-30b-a3b
JUDGE_MODEL=ollama:qwen2.5:7b-instruct,groq:llama-3.3-70b-versatile,nvidia:nvidia/nemotron-3.5-lightning-30b-a3b
```

## The free services (checked 19 Oct 2026; free tiers change often)

| Label | What's free | Key setting in backend/.env | Notes |
|---|---|---|---|
| `ollama:` | Unlimited, on your own GPU | none | Install Ollama; `docs/LOCAL-MODEL.md` |
| `groq:` | About 30 requests/min, 1,000/day per model | `GROQ_API_KEY` (console.groq.com) | Very fast; daily token caps per model |
| `cerebras:` | About 30 requests/min, ~1M tokens/day | `CEREBRAS_API_KEY` (cloud.cerebras.ai) | Very fast; terms have changed before |
| `nvidia:` | About 1,000 requests/day, often slow at busy times | `NVIDIA_API_KEY` | What we used so far |
| `gemini:` | Flash models; limits shown in AI Studio | `GEMINI_API_KEY` (aistudio.google.com) | **Free-tier prompts may be used for training**: test stories only, never users' books |
| `openrouter:` | `:free` models, 20/min, **50/day** (1,000/day after a one-off $10 top-up) | `OPENROUTER_API_KEY` | Too few requests for whole books without the top-up |
| `github:` | 15/min, 150-1,000/day | `GITHUB_TOKEN` | GitHub Models |
| `mistral:` | Experiment plan | `MISTRAL_API_KEY` | Requires opting in to training |

A request is one ~700-character passage: a short chapter is 2-5 requests, a long one 10-15.
Each provider is paced on its own (`GROQ_RPM=30` etc. to change it).

## Find the best chain: the reader sweep

1. Put the keys you have in `backend/.env` (any subset; missing ones are skipped).
2. Pull the local models you want to try (`ollama pull qwen2.5:7b-instruct` ...).
3. Run:
   ```powershell
   python eval/reader_sweep.py
   ```
   Every candidate reads every test story once (saved per model), then the checks run. The
   ranking in `eval/results/reader-sweep.md` puts the fewest false alarms first, then most
   mistakes caught, then reliability (failed runs, fallbacks), then time, and suggests a chain.
   Try other model names with `--readers "groq:...,ollama:..."`; fewer stories with
   `--stories kestrel,fallenking`; it can be stopped and restarted.
4. Copy the suggested `CHAT_MODEL` / `JUDGE_MODEL` lines into `backend/.env`.

Pick the reader on all five stories, not one: a reader that is best on one story by luck is
the same overfitting problem as a rule fitted to one story.

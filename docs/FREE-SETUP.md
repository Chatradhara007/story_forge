# Free AI setup: what we tried and what we decided

## Decision (19 Oct 2026): one free NVIDIA model reads and judges; the checks run in code

```
CHAT_MODEL=nvidia:nvidia/nemotron-3.5-lightning-30b-a3b
JUDGE_MODEL=nvidia:nvidia/nemotron-3.5-lightning-30b-a3b
CHECKER=off
SAFETY_NET=off
NAME_LINKING=rules
MAX_PARALLEL_AI_CALLS=2
```

Why: it was the only free option that never ran out of requests, gave the same kind of reading
every run, and handled StoryForge's forced-tool format. A reading that changes from run to run
makes every score meaningless, so a single steady reader beats a faster one that hands over
between models mid-book. It is slower (about 20-25 s per short chapter, with occasional
timeouts that are retried).

## What we tried and why it was dropped

| Option | Result |
|---|---|
| Ollama on a local GPU (qwen2.5 7B) | 5-12 minutes per short chapter (likely running on the CPU). Not usable here; see `docs/LOCAL-MODEL.md` if a stronger GPU is available. |
| Groq `llama-3.3-70b-versatile` | Retired by Groq (404 "not available any more"). |
| Groq `openai/gpt-oss-20b` / `-120b`, `qwen/qwen3.8-27b` | Free plan: **8,000 tokens per minute**, so requests were refused (413/429) and chapters waited minutes. `gpt-oss` models also broke forced tool calls (malformed JSON, wrong fact types, "tool choice required"). Best result: gpt-oss-120b caught 5/12 on Lighthouse with 0 false alarms, but needed many waits. |
| Mixed chains (Groq first, NVIDIA fallback) | The reading changed with every hand-over (2-4 of 9 on the same story between runs): unreliable for measuring. |
| Cerebras, Gemini, Mistral, OpenRouter, GitHub Models | Supported in code (`PROVIDERS` in `backend/llm.py`) but **not measured**: no keys were tried. Gemini's free tier may train on prompts: test stories only. |

Lessons built into the code: a rejected key skips that model at once; a provider's answer room is
capped (`GROQ_MAX_OUTPUT_TOKENS`); non-NVIDIA providers get plain-JSON requests; a fact type like
"person" is accepted as "character"; "Ana's right leg" is read as a fact about Ana.

## Trying another provider later

`python eval/try_model.py <label:model>` sends one real reading request and prints the full
answer or error. `python eval/reader_sweep.py --readers "label:model,..."` ranks readers on all
five stories. Only change the decision above if a candidate beats NVIDIA on **all** stories
with no false alarms, and never reads the same story differently between runs.

---

# The free services we know of

No single free service is reliable and unlimited, so StoryForge can use several in one chain.
Each model name can carry its provider in front; the first one that works is used, and one
that fails or runs out of free requests hands over to the next at once.

```
CHAT_MODEL=<provider>:<model>,nvidia:nvidia/nemotron-3.5-lightning-30b-a3b
```

## The free services (checked 19 Oct 2026; free tiers change often)

| Label | What's free | Key setting in backend/.env | Notes |
|---|---|---|---|
| `ollama:` | Unlimited, on your own GPU | none | Install Ollama; `docs/LOCAL-MODEL.md` |
| `groq:` | About 30 requests/min but **8,000 tokens/min** | `GROQ_API_KEY` (console.groq.com) | Very fast; daily token caps per model |
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

# Final configuration

The setup StoryForge is deployed with, why it was chosen, and the one test that decides it.

## The models

| Job | Model | Settings |
|---|---|---|
| **Reader** (facts from every passage, chapter timing, the Ask box) | `nvidia/nemotron-3.5-lightning-30b-a3b` | no thinking, no randomness |
| **Judge** (name linking, contradiction check, safety net, double-check) | `nvidia/nemotron-3-ultra-550b-a55b` | **no thinking**, no randomness |
| Embeddings (search) | `nvidia/nemotron-3-embed-1b` | 2048 numbers per fact |
| Backups | Reader: `nemotron-3-nano-omni-30b-a3b-reasoning`. Judge: falls back to Lightning | used automatically if a model is retired or keeps failing |

`.env` / host settings:

```
CHAT_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning
JUDGE_MODEL=nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3.5-lightning-30b-a3b
CHAT_THINKING_JUDGING=off
```

## Why these

Measured with `eval/run_eval.py --judges`, both judges on **identical** facts (lighthouse):

| Judge | Precision | Recall | False alarms |
|---|---|---|---|
| Nemotron 3.5 Lightning | 40% | 33% | 6 |
| **Nemotron 3 Ultra** | **71%** | **83%** | 4 |

Ultra crashed (500 errors) whenever asked to think, and was fast without thinking, so it judges
without thinking. Lightning reads: reading is most of the requests, and it is fast. Kimi K3 was
rejected (177 s to answer one test question).

## How well it works (before the held-out test)

| Story | Precision | Recall | Notes |
|---|---|---|---|
| Lighthouse (tuned on) | 77–80% | 78–83% | 3 runs each |
| Glassmaker (partly tuned on) | 66% | 62% | 3 of its 5 misses are details the Reader never recorded |

These two stories were used to find and fix weaknesses, so their scores flatter StoryForge.
**The real measure is the held-out story below.**

## What is general and what is a rule of thumb

General (works the same for any story):
- Two models with separate jobs, automatic fallback, retries and failover.
- Checks only against chapters earlier in reading order; story order for flashbacks.
- One warning per new fact; the writer's dismissals survive re-checks.
- The story clock's arithmetic (ages against time skips, an event's weekday).
- Links from names the text itself states ("his real name was…"), and a first name meaning the
  full name the same chapter introduces.

Rules of thumb (English word lists; good for typical prose, not exhaustive):
- What counts as dying, breaking or injury ("the story moving forward").
- What counts as acting after death, and what is only a memory.
- Phrases where the AI admits there is no contradiction.

Each was checked against every report so far: none removed a real catch.

## The structural fix found by the held-out story (5 October 2026)

The first held-out run was stopped after six chapters. On ~900-word chapters the Reader records
60–90 facts per chapter (15–35 on the tuning stories), and warnings grew with them: 9–17 per
chapter, including chapters with no planted mistake, and 4–12 minutes per chapter. Cause: every new
fact was compared with every earlier fact about the same character, including passing ones
(moods, plans, actions, roles, whereabouts, how full the granaries are). A story about change,
like any novel, then "contradicts" itself constantly.

Fix (`backend/lasting.py`): earlier facts are evidence only if they **can't simply change**:
fixed traits (eyes, scars, birthplace, family, ages, dates, counts), lasting states (dead, blind,
lost a hand, destroyed, given away, left behind, repaired) and past events pinned to a time
("the whole night of the storm"). Unrecognised attributes are kept, to be safe; anything the
writer pins as canon is always kept. New facts of every kind are still checked against these.
Tested on 36 real extracted facts from the three stories: the earlier side of every planted
mistake stays evidence; passing facts don't.

**Free check before spending credits:** `python analyze_without_ai.py --story fallenking` replays
the filter over the warnings the interrupted run left in the evaluation database, with no AI
requests: how many false alarms would disappear, and whether any real catch would be lost.

## The held-out test (run once, then freeze)

`eval/stories/fallenking/` is *The Fallen King* with 11 planted mistakes and 5 traps, written
before StoryForge was ever run on it, with chapters of 725–1,080 words (four times longer than the
tuning stories). Its answer key covers kinds of mistakes the tuning stories don't (a horse's
colour, a ring that's somewhere it can't be, a blind mother reading, a changed season).

```
cd eval
python analyze_without_ai.py --story fallenking          # free: replays the fix on the stopped run
python run_eval.py --story fallenking --judges "nvidia/nemotron-3-ultra-550b-a55b" --runs 1
```

**Decision rule, fixed in advance:**
- Precision ≥ 70% and recall ≥ 65% → deploy as is.
- Most misses are "not read" (the Reader skipped the detail) → one more run with Ultra as the
  Reader too (`$env:CHAT_MODEL="nvidia/nemotron-3-ultra-550b-a55b"`), compare accuracy against
  time, pick one, deploy.
- Otherwise → deploy anyway with the numbers documented: StoryForge's warnings are suggestions
  the writer reviews, and the held-out score tells writers honestly how far to trust them.

No code is changed in response to this test's results before deploying: that is what keeps its
score honest. Record the numbers here and in the README.

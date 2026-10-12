# Chapter size and how long checking takes

What StoryForge can take, how long it needs, and how to measure it on your own setup.
All times are for the final configuration (reader: Nemotron 3.5 Lightning; judge: Nemotron 3
Ultra, judging without thinking) on **NVIDIA's free API**, whose speed varies through the day.

## Limits

| What | Limit | Why |
|---|---|---|
| One chapter | **400,000 characters** (about 65,000 words) | Request size limit (`ChapterInput`). Anything longer: split it. |
| Chapter name | 100 characters, no `/ \ ? #` | Used in web addresses. |
| Facts an earlier character brings to each check | 60 (`MAX_EVIDENCE_FACTS`) | Keeps each AI request small however long the book gets: pinned facts and permanent states first, then the most relevant. |
| Text the timing detector reads | First and last 15,000 characters | Time shifts ("three years later", flashbacks) are signalled at a chapter's start or end. |
| Chapters per user per day (when sign-in is on) | 40 (`DAILY_CHAPTER_LIMIT`) | Every chapter uses requests on your NVIDIA key. |

There is no lower limit, but a chapter of a few lines gives the AI little to work with.

## Recommended size

**1,000 to 6,000 words per chapter** (typical novel chapters are 2,000 to 5,000).

- Longer chapters work, but they take proportionally longer to read (see below), and the
  writer waits longer for one result. Above about 10,000 words, consider splitting a chapter
  into its scenes: results arrive sooner and warnings point at a smaller piece of text.
- Chapters are checked one at a time per book, in the background: the website shows a
  progress bar, and nothing times out however long a chapter takes.

## How long it takes

Two parts:

1. **Reading** (finding the facts): grows with the length of the chapter. The text is read in
   ~700-character passages (about 120 words), up to 4 at a time.
2. **Judging** (linking names, checking for mistakes, safety net, double-check): roughly
   constant per chapter, because each character's history is capped at 60 facts. The first
   chapter of a book is quicker: there is nothing earlier to compare it with.

### Measured so far (free NVIDIA API, October 2026)

| Story | Words per chapter | Reading | Judging per chapter |
|---|---|---|---|
| Lighthouse (6 chapters) | 175–240 | ~160 s per 1,000 words | 35–65 s |
| Glassmaker (5 chapters) | 205–310 | ~130 s per 1,000 words | 35–55 s |
| The Fallen King (8 chapters, held-out test) | 725–1,080 | *fill in from the held-out run* | *fill in* |

Rule of thumb from these measurements:

> **time per chapter ≈ 2½ minutes per 1,000 words of reading + about 1 minute of judging**

| Chapter length | Expected time on the free API |
|---|---|
| 1,000 words | about 3–4 minutes |
| 3,000 words | about 8–10 minutes |
| 5,000 words | about 13–15 minutes |

These are estimates from short chapters; the held-out run on ~900-word chapters will confirm or
correct them. Treat them as an order of magnitude: the free API's speed changes through the day,
and an occasional server error adds a retry.

### Making it faster

| Change | Effect | Cost |
|---|---|---|
| `MAX_PARALLEL_AI_CALLS=8` (default 4) | Reading up to ~2× faster | NVIDIA may refuse some requests; StoryForge then slows itself down |
| `MAX_REQUESTS_PER_MINUTE=40` (default 30, per model) | Same | Same |
| `READ_PASSAGE_CHARS=1200` (default 700) | ~40% fewer reading requests | The reader may miss small details |
| A paid AI provider (`AI_BASE_URL` + its key) | Several times faster and steadier | Paid per use |

Measure any change with the evaluation before keeping it.

## Measuring it yourself

Every evaluation report has a **Time per chapter** table (words, facts, reading and judging
seconds) and a summary line with seconds per 1,000 words:

```
cd eval
python run_eval.py --story fallenking --runs 1
```

The first run of a story reads it; later runs with `--reuse-reading` or `--judges` reuse that
reading and show only judging time.

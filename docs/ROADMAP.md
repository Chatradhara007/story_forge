# StoryForge roadmap and checkpoints

Updated 19 Oct 2026. Each step has a **checkpoint**: what must be true before moving on.
Numbers come from `eval/run_eval.py`; "held-out" means a story nobody tuning the checks has seen.

## Where we are (19 Oct 2026)

| | Caught | False alarms | Time |
|---|---|---|---|
| Tuned stories (Fallen King, Glassmaker, Lighthouse) | 21 / 36 | 0 | ~10 s per chapter once read |
| Development stories (Night Shift, Kestrel), after fixes | ~7 / 19 | 0 expected | |
| First honest held-out run (Night Shift, Kestrel) | 2 / 19 | 3 | 20-25 min (free NVIDIA tier) |

Warnings from the code checks are precise; how many mistakes they catch on new stories is the
open problem (reading quality, plus mistake kinds no rule covers). Reading on the free NVIDIA
tier is ~95% of the time.

---

## Step 1: Reader on your own GPU (now)

Guide: `docs/LOCAL-MODEL.md`.
1. Install Ollama, open a NEW PowerShell window, `ollama --version`.
2. `nvidia-smi` (GPU memory), then `ollama pull qwen2.5:7b-instruct` (8 GB) or
   `qwen2.5:14b-instruct` (12 GB+).
3. `backend/.env`: `AI_BASE_URL=http://localhost:11434/v1`, `CHAT_MODEL` / `JUDGE_MODEL` = that
   model, `MAX_PARALLEL_AI_CALLS=2`, `AI_REQUEST_TIMEOUT=300`, `AI_RETRY_ATTEMPTS=2`.
   Keep `NVIDIA_API_KEY` (search vectors), `CHECKER=off`, `SAFETY_NET=off`, `NAME_LINKING=rules`.
4. `python eval/run_eval.py --story kestrel --reuse-reading`, then `--story fallenking`.

Then the free-setup search (`docs/FREE-SETUP.md`): add any free keys you have (Groq, Cerebras,
Gemini for test stories only...) and run `python eval/reader_sweep.py`; it ranks every free reader
on all five stories and suggests a chain (best first, reliable fallbacks after it).

**Checkpoint 1:** local reading is within ~1 catch of NVIDIA Lightning (Fallen King 8/11,
Kestrel 3/9) with no new false alarms. Expected time: Kestrel 1-3 min, Fallen King 5-12 min
on the first run; about a minute after that.
- Pass: use the local model for all development and evaluation runs; run the other 3 stories.
- Fail: try the 14B model; otherwise keep NVIDIA for final readings.

## Step 2: Honest measurement that scales

- **Automatic test cases** (built 19 Oct): `python eval/make_cases.py --run` plants mistakes
  (eye/hair colour, side of a scar, an age going down, the dead acting again, older/younger,
  sister to cousin, counts, street names) into the stories with the answer key written
  automatically, and reports recall per kind plus false alarms. Only plainly stated facts about a
  named person anchor a case (a wrong answer key is worse than none).
- **Real books as a base:** `python eval/add_book.py 1342 --name pride` adds the first chapters
  of a public-domain novel. On its own it measures false alarms on real prose; with
  `make_cases.py --stories pride --run` it gives many more planted cases.
- **New held-out stories written by a teammate** (`eval/HOW-TO-WRITE-A-TEST-STORY.md`).
- **Release gate in GitHub Actions:** tests plus the offline story replay on every push; fail if
  a catch is lost or a false alarm appears.

**Checkpoint 2:** one command prints caught / false alarms per mistake kind over all
stories and generated cases; CI runs it.

## Step 3: General checking: one fact format, one comparison

From the research (FACTTRACK, SCORE; see the 19 Oct conversation):
- The Reader labels every fact with *what it is about* (eye colour, location, owns X, count
  of Y, date, family tie...), *how it changes* (permanent / state / event) and *when it holds*
  (now / flashback / hypothetical).
- One comparison in code: permanent facts can't change; states need an event in between;
  numbers and dates are checked against the story clock. New mistake kinds become new labels,
  not new code. Today's rules become tests.
- Objects tracked as active / lost / destroyed (SCORE's biggest single gain).

**Checkpoint 3:** held-out recall clearly above today's (2/19 first run), false alarms still
at or near 0, on stories nobody tuned for.

## Step 4: A catch-all for kinds no label covers

- A small contradiction model (DeBERTa NLI, runs on CPU/GPU locally, free) compares pairs of
  facts about the same thing in the same stretch of story time, as FACTTRACK does.
- Shown as "Worth a look", separate from "Confirmed".

**Checkpoint 4:** "Worth a look" precision measured on all stories; kept only if most of its
warnings are real.

## Step 5: Speed for everyone (not just a local GPU)

- Read all chapters of a book at the same time, then link and check them in order.
- Whole-chapter reading calls (fewer requests), measured against passage reading.
- Search vectors from a small local model (no NVIDIA call), one-off re-index.
- Fast failover: one try, then the backup model.

**Checkpoint 5:** a 10-chapter book checked in under ~3 minutes on a paid API, with the
same scores.

## Step 6: Beta deployment

- Paid AI provider through the OpenAI-style setting (hosted open models: Together,
  Fireworks, DeepInfra, Groq or NVIDIA paid; one that does not train on your data).
- Background work in a separate worker with a queue (survives restarts, scales).
- Staging and production, each with its own database (Neon); Render or similar for the app.
- Sentry error tracking, health alerts, backups, monthly AI spend alert.
- Privacy page; account deletion removes books (tested).
- **Google sign-in** added to the existing accounts (OpenID Connect; links by verified
  email; email/password keeps working). Needs a Google Cloud OAuth client, consent screen,
  privacy policy link and a custom domain.
- Invite-only (`INVITE_CODE`), daily limits per user.

**Checkpoint 6:** a teammate outside the dev setup signs in with Google, uploads a book,
gets warnings, and nothing needs fixing by hand for a week.

## Step 7: Public launch

Scale the worker, usage-based billing (Stripe) if charging, feedback button on each warning
(confirm / dismiss, fed back into the evaluation set), support page.

---

## Demo / pitch (any time)

`docs/DEMO.md`: rehearse with `READING_CACHE` (or the local model) so the demo needs no
internet AI. Lead with precision ("every warning comes with both quotes and the rule"); quote
held-out numbers only once Step 2 exists.

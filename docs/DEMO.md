# Showing StoryForge (demo and pitch run sheet)

The free NVIDIA tier is sometimes slow or down for minutes at a time. A live demo must not
depend on it, so: **rehearse once with the reading cache on; on the day, the same chapters are
checked in seconds with no AI request for reading.** Everything else (name linking, the
checks, the warnings) runs live, exactly as for any user.

## The quickest way: a demo account with two finished books

From `backend/` (database running, `NVIDIA_API_KEY` set):
```
python seed_demo.py --email demo@storyforge.app --password "pick-a-demo-password"
```
It creates the account and adds **The Fallen King** (fantasy) and **Kestrel** (science fiction)
through the normal pipeline, so the warnings shown are real results. Readings saved by the
evaluation are reused (about a minute); otherwise each chapter is read by the AI (several
minutes). Then set `AUTH_REQUIRED=true` and a `SECRET_KEY` in `backend/.env`, restart, and sign
in as the demo account: the shelf shows both books. `--fresh` adds them again;
`--stories fallenking,glassmaker` picks others.

To also show adding a chapter live, use the reading cache below.

## Once, the day before

1. In `backend/.env` add:
   ```
   READING_CACHE=reading-cache
   NAME_LINKING=rules
   CHECKER=off
   SAFETY_NET=off
   JUDGE_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
   ```
2. Start the app (`docker compose up -d`, then `uvicorn main:app` in `backend/`), create a
   book, and add the demo chapters one by one (e.g. `eval/stories/fallenking/ch1.txt` to
   `ch8.txt`). This reads them with the AI once and fills `backend/reading-cache/`.
3. Delete that book. Add the chapters again into a new book: each should take a few seconds.
   That is what the audience will see. Keep the `reading-cache` folder.

## On the day

- Add the chapters in order. The warnings appear as **Confirmed** (checked in code: the
  exact rule is in each explanation) with the two quotes side by side.
- Good ones to point at (The Fallen King): the signet ring he gave away is on his finger
  again (ch4); Ember the grey stallion is "the black stallion" (ch5); Bram is 66, then
  "sixty-two now" years later (ch7); Aurel's scar moves from his left hand to his right (ch7);
  the blind queen "read every one of her son's letters" (ch7); Thessaly's grey-green eyes are
  brown (ch8).
- Point out what it did NOT flag, the traps in the story: a flashback where Aurel has no scar
  yet and Bram is fifty-two (ch6); the king now living as a ferryman called Rell (ch4); Ember
  white around the muzzle with age (ch8); the ring handed back and worn again (ch8).

## Numbers you can quote honestly (18 Oct 2026, free tier, code checks only)

| Story | Caught | False alarms |
|---|---|---|
| The Fallen King | 8 of 11 | 0 |
| The Glassmaker | 7 of 13 | 0 |
| The Lighthouse | 6 of 12 | 0 |
| Held-out stories (Night Shift, Kestrel) | see `eval/results` | |

Say it plainly: **every warning it raises has been a real mistake; it catches about 60% of
planted mistakes so far**, the kinds it checks in code (appearance, family, ages and dates,
objects that were destroyed or given away, injuries). The held-out stories were written
after the checks and are the honest measure; quote their numbers once run.

## If something goes wrong

- A chapter takes long: NVIDIA is slow and the text isn't in the cache (a changed character
  or chapter). Use the exact rehearsed files.
- `/health` shows `"database": false`: Docker isn't running (`docker compose up -d`).

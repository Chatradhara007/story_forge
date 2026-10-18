# Writing a held-out test story

The honest measure of StoryForge is a story **nobody tuning the checks has seen**. Best
written by someone on the team who has not read `backend/traits.py`, `states.py` or
`storytime.py`. Once the checks are changed because of a story's results, it stops being
held out (set `"held_out": false` and write a new one).

1. Make a folder `eval/stories/<name>/` with `ch1.txt` ... `chN.txt` (5-8 chapters,
   250-500 words each, any genre).
2. Plant 8-12 continuity mistakes, of whatever kinds real writers make. Write them down
   BEFORE you look at any results. Also add 3-5 traps: changes that are NOT mistakes
   (an injury that heals with time, dyed hair, a flashback, a replacement object, someone
   using a nickname).
3. Write `ground_truth.json` (copy the shape of `nightshift/ground_truth.json`):
   - `planted`: id, type (`attribute` / `status` / `timeline`), the chapter where the mistake
     appears, `entity_contains` (lower-case words from the names involved), `description`,
     `new_keywords` (words in the wrong sentence), `old_keywords` (words in the earlier one).
   - `decoys`: the traps, same fields (`old_keywords` may be empty).
   - `same_entity` / `different_entities`: name groups, for the name-linking score.
   - `"held_out": true`.
4. Run it once: `python eval/run_eval.py --story <name> --reuse-reading`.
   That first result is the number to quote.

# Consistency over 3 runs

Average precision 77% · average recall 83% · average F1 0.80 · average false alarms 3.0 · average time 386s

| Run | Precision | Recall | F1 | False alarms | Time | AI requests |
|---|---|---|---|---|---|---|
| 1 | 71% | 83% | 0.77 | 4 | 268s | 35 (+0 refused) |
| 2 | 83% | 83% | 0.83 | 2 | 542s | 35 (+0 refused) |
| 3 | 77% | 83% | 0.80 | 3 | 347s | 35 (+0 refused) |

## How often each planted mistake was caught

| Mistake | Type | Caught | Why missed (per run) | Description |
|---|---|---|---|---|
| A1 | attribute | 3/3 (always) | ✓, ✓, ✓ | Ines's eyes: grey (ch1) vs green (ch4). Uses a different name, 'Keeper Calloway'. |
| A2 | attribute | 3/3 (always) | ✓, ✓, ✓ | Tobias is Ines's older brother (ch1) but her younger brother (ch5). |
| A3 | attribute | 3/3 (always) | ✓, ✓, ✓ | The Merrow is red-painted (ch2) but has a blue hull (ch5). |
| A4 | attribute | 3/3 (always) | ✓, ✓, ✓ | Rudd has a long white beard (ch2) but a clean-shaven chin (ch6). Uses 'Harbourmaster Rudd'. |
| A5 | attribute | 3/3 (always) | ✓, ✓, ✓ | Pip is ten (ch3) but twelve (ch6), within one autumn. |
| S1 | status | 3/3 (always) | ✓, ✓, ✓ | Bramble dies (ch3) but barks at gulls (ch5). |
| S2 | status | 3/3 (always) | ✓, ✓, ✓ | Tobias lost his left hand (ch2) but claps both hands over a latch (ch4). |
| S3 | status | 3/3 (always) | ✓, ✓, ✓ | The brass key is thrown into the sea (ch3) but used to unlock the lamp room (ch6). |
| S4 | status | 3/3 (always) | ✓, ✓, ✓ | Rudd spent the whole storm night in the harbour office (ch4) but rowed out to the Gullstone that night (ch5). |
| T1 | timeline | 3/3 (always) | ✓, ✓, ✓ | Ines has kept the light twenty years (ch1) but eight years (ch5). |
| T2 | timeline | 0/3 (never) | not read (later), not read (later), not read (later) | The storm broke on Tuesday (ch4) but was 'on Friday' (ch6). |
| T3 | timeline | 0/3 (never) | split, split, split | Tobias arrived three days before the storm (ch2) but the morning after it (ch5). |

## Traps wrongly flagged

None, in any run.

---

# Details of the last run

# StoryForge evaluation — lighthouse — 2026-10-05 12:45

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3-ultra-550b-a55b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 386s · AI requests per run: 35 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: reader 0.0, judge 0.0 · Reading passage size: 700 characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 0 |
| linking names | 68 |
| preparing search | 6 |
| story clock | 0 |
| checking for mistakes | 128 |
| safety-net check | 168 |
| double-checking | 61 |
| saving | 8 |

*Checking, story clock and safety net run at the same time, so their times overlap: the rows add up to more than the total time.*

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 77% | 83% | 0.80 | 10 / 12 | 3 | 1 | 100% |

| Type | Planted | Caught | Recall |
|---|---|---|---|
| attribute | 5 | 5 | 100% |
| status | 4 | 4 | 100% |
| timeline | 3 | 1 | 33% |

## Missed mistakes

- **T2** (ch6): The storm broke on Tuesday (ch4) but was 'on Friday' (ch6).
- **T3** (ch5): Tobias arrived three days before the storm (ch2) but the morning after it (ch5).

## Why each mistake was missed

Causes: *not read* = the Reader didn't record the detail; *split* = the details were filed under different entries (a name-linking problem); *checker* = both were on the same entry but weren't flagged.

- **T2** → **not read (later)**: No fact from ch6 mentions this detail.
    - ch4: [storm] storm | day | Tuesday night
- **T3** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch2: [storm] storm | time_reference | Three days before the storm
    - ch3: [storm] week before the storm | description | quiet and sad in its own way
    - ch5: [Reporter's visit / Thursday event] event | time of Tobias's arrival | the morning after the storm

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| false alarm | - | ch2 | Gullstone Light | attribute | In chapter 1, Gullstone Light is established as a lighthouse standing on a rock two miles offshore. In chapter 2, 'the Gullstone' is described as a harbour launch (a small boat). These are fundamentally different entities — a fixed lighthouse vs. a movable boat — and cannot both be true for the same named entity without explanation. |
| false alarm | - | ch2 | Tobias Calloway | status | Chapter 1 establishes Tobias lives on the mainland and writes letters from there. Chapter 2 shows him physically present at the kitchen table on the rock/island. This is a status contradiction (location) unless travel is explained, but the new chapter presents his arrival as already having happened without showing the transition from mainland to island. |
| correct | A1 | ch4 | Ines Calloway | attribute | Ines Calloway's eye color is established as grey in chapter 1 ('grey eyes that the fishermen said could spot a sail through fog'), but chapter 4 describes Keeper Calloway (the same person) as having 'green eyes'. This is a direct attribute contradiction with no in-story explanation for the change. |
| correct | S2 | ch4 | Tobias Calloway | status | Chapter 2 establishes Tobias Calloway lost his left hand in a winch accident and keeps the empty sleeve pinned to his coat. Chapter 4 describes him using 'both hands' to clap over a broken latch, which is impossible given his established physical condition with no explanation for a prosthetic or regrowth. |
| correct | A2 | ch5 | Tobias Calloway | attribute | Chapter 1 explicitly states Tobias is Ines's older brother. In chapter 5, Ines refers to him as 'my younger brother'. This is a direct contradiction in their sibling age order, which is a fixed biographical fact. |
| correct | A3 | ch5 | Merrow | attribute | In chapter 2, the Merrow is described as the harbour's little red-painted launch. In chapter 5, it is described as having a blue hull freshly scrubbed. The color of the boat contradicts directly unless repainted, which is not mentioned or plausible in a few weeks. |
| correct | S4 | ch5 | Silas Rudd | status | Chapter 4 states Silas Rudd spent the entire night of the storm in the harbour office sending telegrams and did not leave until dawn. Chapter 5 claims he rowed out to the Gullstone and sat with Ines in the lamp room until dawn. He cannot be in two places at once during the same event. |
| correct | S1 | ch5 | Bramble | status | Bramble was buried in chapter 3, but in chapter 5 (a few weeks later) he is barking at gulls from the rocks, with no explanation of resurrection or survival. |
| correct | T1 | ch5 | Ines Calloway | attribute | In chapter 1, Ines is stated to have kept the light burning for twenty years. In chapter 5 (a few weeks later), she says she has been keeper for eight years. This is a direct contradiction in the duration of her role that cannot be explained by the passage of a few weeks. |
| duplicate | S4 | ch5 | storm | status | Chapter 4 states Silas Rudd spent the whole night of the storm in the harbour office. Chapter 5 (Ines's account) says Silas rowed out to the Gullstone and sat with her in the lamp room until dawn on the night of the storm. He cannot be in two places at once for the entire night. This is a direct status contradiction about location during a specific timeframe. |
| correct | S3 | ch6 | brass key | status | Chapter 3 establishes that Tobias found the old brass key to the lamp room and threw it into the sea. Chapter 6 states Ines unlocks the lamp room with the old brass key each evening. This is a status contradiction because the key was destroyed/discarded in chapter 3, yet is being used in chapter 6 with no explanation of recovery or replacement. |
| correct | A4 | ch6 | Silas Rudd | attribute | The new fact describes Silas Rudd as having a 'clean-shaven chin' while the existing fact from chapter 2 describes him with 'a white beard that reached the second button of his coat'. These are mutually exclusive physical descriptions with no in-story explanation for the change (such as shaving off a long beard). Since chapter 6 occurs only 'a few weeks after the storm' (same time skip as chapter 5), there hasn't been enough time for a beard to grow back if he had shaved it, nor is there any mention of him shaving. This is a clear attribute contradiction. |
| false alarm | - | ch6 | Tobias Calloway | status | Tobias lost his left hand in a winch accident many years ago (existing fact 7) and keeps the empty sleeve pinned to his coat (existing fact 8). Existing fact 15 describes him using 'both hands' to clasp a broken latch during the storm, which is physically impossible with only one hand. The new fact (chapter 6) shows him performing a two-handed action (reading a letter twice and putting it in his pocket) without any explanation of how he manages this with one hand. Both chapters 4 and 6 are set after the accident, so the inability to use two hands should be consistent. |
| correct | A5 | ch6 | storm | attribute | Pip's age changes from 10 in chapter 3 to 12 in chapter 6. Both chapters are set 'a few weeks after the storm' (chapters 5 and 6 share the same time skip), so only weeks have passed. A two-year age jump in weeks is impossible without explanation. |

Decoys wrongly flagged: none



## What the double-check removed

5 warnings dismissed: 5 were false alarms; real mistakes wrongly removed: none.

- ch3 · Ines Calloway: Set aside: the story moving forward (something that existed earlier in story time has 'buried' later). Only the reverse would be a mistake.
- ch3 · Silas Rudd: Set aside: the story moving forward (something that existed earlier in story time has 'thrown' later). Only the reverse would be a mistake.
- ch3 · empty sleeve: Double-check: The two quotes describe completely different objects: an empty sleeve pinned to a coat (chapter 2) and a brass key hanging on a nail (chapter 3). There is no textual link between them, and the warning's claimed contradiction relies on an unsupported inference about physical limitations and key acces
- ch5 · Ines Calloway: Double-check: Normal progression: A dish towel wrap immediately after injury (Chapter 4) can become a clean white bandage after weeks of healing and proper care (Chapter 5). This is plausible medical progression, not a contradiction.
- ch6 · Ines Calloway: Double-check: This is normal story progression: Ines moves to the village for winter and delegates duties to an assistant, which the text explicitly says keepers sometimes do. Her role changes, but this is explained and plausible, not a contradiction.

## Name linking

6 of 6 testable checks passed.

- same: Ines Calloway, Keeper Calloway, Ines → pass
- same: Silas Rudd, Harbourmaster Rudd → pass
- same: Tobias Calloway, Tobias → pass
- different: Mara Calloway, Ines Calloway → pass
- different: Mara Calloway, Tobias Calloway → pass
- different: Tobias Calloway, Ines Calloway → pass

# Consistency over 3 runs

Average precision 80% · average recall 78% · average F1 0.79 · average false alarms 2.3 · average time 217s

| Run | Precision | Recall | F1 | False alarms | Time | AI requests |
|---|---|---|---|---|---|---|
| 1 | 77% | 83% | 0.80 | 3 | 214s | 36 (+0 refused) |
| 2 | 82% | 75% | 0.78 | 2 | 257s | 35 (+0 refused) |
| 3 | 82% | 75% | 0.78 | 2 | 181s | 35 (+0 refused) |

## How often each planted mistake was caught

| Mistake | Type | Caught | Why missed (per run) | Description |
|---|---|---|---|---|
| A1 | attribute | 3/3 (always) | ✓, ✓, ✓ | Ines's eyes: grey (ch1) vs green (ch4). Uses a different name, 'Keeper Calloway'. |
| A2 | attribute | 3/3 (always) | ✓, ✓, ✓ | Tobias is Ines's older brother (ch1) but her younger brother (ch5). |
| A3 | attribute | 3/3 (always) | ✓, ✓, ✓ | The Merrow is red-painted (ch2) but has a blue hull (ch5). |
| A4 | attribute | 1/3 (sometimes) | ✓, checker, checker | Rudd has a long white beard (ch2) but a clean-shaven chin (ch6). Uses 'Harbourmaster Rudd'. |
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

# StoryForge evaluation — lighthouse — 2026-10-05 10:03

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3-ultra-550b-a55b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 217s · AI requests per run: 35 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: 0.2 · Reading passage size: whole chapter characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 0 |
| linking names | 54 |
| preparing search | 6 |
| story clock | 0 |
| checking for mistakes | 56 |
| safety-net check | 59 |
| double-checking | 79 |
| saving | 8 |

*Checking, story clock and safety net run at the same time, so their times overlap: the rows add up to more than the total time.*

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 82% | 75% | 0.78 | 9 / 12 | 2 | 2 | 100% |

| Type | Planted | Caught | Recall |
|---|---|---|---|
| attribute | 5 | 4 | 80% |
| status | 4 | 4 | 100% |
| timeline | 3 | 1 | 33% |

## Missed mistakes

- **A4** (ch6): Rudd has a long white beard (ch2) but a clean-shaven chin (ch6). Uses 'Harbourmaster Rudd'.
- **T2** (ch6): The storm broke on Tuesday (ch4) but was 'on Friday' (ch6).
- **T3** (ch5): Tobias arrived three days before the storm (ch2) but the morning after it (ch5).

## Why each mistake was missed

Causes: *not read* = the Reader didn't record the detail; *split* = the details were filed under different entries (a name-linking problem); *checker* = both were on the same entry but weren't flagged.

- **A4** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch2: [Silas Rudd] Silas Rudd | physical_description | a broad man with a white beard that reached the second button of his coat
    - ch6: [Silas Rudd] Harbourmaster Rudd | habit | rubbing his clean-shaven chin when he is thinking
    - ch6: [Ines Calloway] Ines | opinion of habit | found oddly comforting
- **T2** → **not read (later)**: No fact from ch6 mentions this detail.
    - ch4: [storm] storm | day | Tuesday night
- **T3** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch2: [storm] storm | time_reference | Three days before the storm
    - ch3: [storm] week before the storm | description | quiet and sad in its own way
    - ch5: [Reporter's Thursday visit] event | time of Tobias's arrival | the morning after the storm

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| false alarm | - | ch2 | Gullstone Light | attribute | In chapter 1, Gullstone Light is established as a lighthouse standing on a rock two miles offshore. In chapter 2, 'the Gullstone' is described as a harbour launch (a small boat). These are fundamentally different entities — a fixed lighthouse vs. a movable boat — and cannot both be true for the same entity name without explanation. |
| false alarm | - | ch2 | Tobias Calloway | status | Chapter 1 establishes Tobias is on the mainland writing letters twice a year. Chapter 2 (which continues the story) shows Tobias sitting at the kitchen table on the rock/island that evening. This is a status contradiction: he cannot be both on the mainland and physically present at the kitchen table simultaneously with no explanation of travel. |
| correct | A1 | ch4 | Ines Calloway | attribute | Chapter 1 establishes Ines Calloway has grey eyes ('grey eyes that the fishermen said could spot a sail through fog'), but Chapter 4 describes Keeper Calloway (same person) as having green eyes. Eye color is a permanent physical attribute that cannot change without explanation. |
| correct | S2 | ch4 | Tobias Calloway | status | Chapter 2 establishes Tobias Calloway lost his left hand in a winch accident and keeps the empty sleeve pinned to his coat. Chapter 4 describes him using 'both hands' to clap over a broken latch, which is impossible with only one hand. |
| correct | S1 | ch5 | Bramble | status | Bramble was buried in chapter 3, but in chapter 5 (a few weeks later) he is barking at gulls from the rocks. A dead, buried dog cannot bark; this is a status contradiction with no in-story explanation for resurrection. |
| correct | S4 | ch5 | storm | status | Chapter 5 states Silas Rudd rowed out to the Gullstone on the night of the storm and sat with Ines in the lamp room until dawn. Chapter 4 explicitly states Silas Rudd spent the whole night of the storm in the harbour office. He cannot be in two places at once. This is a direct status contradiction regarding Silas Rudd's location during the storm. |
| correct | T1 | ch5 | Ines Calloway | attribute | In chapter 1, Ines is stated to have kept the light burning for twenty years. In chapter 5 (a few weeks later), she says she has been keeper for eight years. This is a direct contradiction in the duration of her role that cannot be explained by the passage of a few weeks. |
| correct | A3 | ch5 | Merrow | attribute | In chapter 2, the Merrow is explicitly described as a 'red-painted launch'. In chapter 5, it is described as having a 'blue hull freshly scrubbed'. The color of the boat's hull is a fixed physical attribute that cannot change without explanation (e.g., repainting), and none is provided. |
| duplicate | S4 | ch5 | Silas Rudd | status | Chapter 4 states Silas Rudd spent the entire night of the storm in the harbour office sending telegrams and did not leave until dawn. Chapter 5 claims he rowed out to the Gullstone and sat with Ines in the lamp room until dawn. He cannot be in two places at once during the same event. |
| correct | A2 | ch5 | Ines Calloway | attribute | In chapter 1, Tobias is explicitly described as Ines's 'older brother'. In chapter 5, Ines refers to him as 'my younger brother'. This is a direct contradiction in their sibling age order, which is a fixed biographical fact. |
| duplicate | A2 | ch5 | Tobias Calloway | attribute | Chapter 1 establishes Tobias as Ines's older brother. Chapter 5 has Ines call him her younger brother. This contradicts the established birth order, which cannot change over time. |
| correct | S3 | ch6 | brass key | status | The brass key was thrown into the sea by Tobias in chapter 3, making it unavailable for Ines to use in chapter 6. The new chapter shows Ines using the key to unlock the lamp room, but the key was permanently disposed of with no explanation of recovery or replacement. |
| correct | A5 | ch6 | Pip Aldane | attribute | Pip was established as ten years old in chapter 3. Chapter 5 indicates only 'a few weeks' have passed since the storm (which occurred after chapter 3). A two-year age jump in a few weeks is impossible without explanation. |

Decoys wrongly flagged: none



## What the double-check removed

9 warnings dismissed: 8 were false alarms; real mistakes wrongly removed: none.

- ch3 · Bramble: Set aside: the story moving forward (something that existed earlier has 'buried' later). Only the reverse would be a mistake.
- ch3 · Bramble: Set aside: the story moving forward (something that existed earlier has 'buried' later). Only the reverse would be a mistake.
- ch3 · Bramble: Set aside: the story moving forward (something that existed earlier has 'buried' later). Only the reverse would be a mistake.
- ch3 · Silas Rudd: Set aside: the story moving forward (something that existed earlier has 'thrown' later). Only the reverse would be a mistake.
- ch3 · Tobias Calloway: Double-check: The earlier quote only states Tobias lost his left hand years ago; it does not say he cannot use his right hand to find a key on a nail and throw it. One-handed people routinely perform such actions, so this is not a contradiction, only an unstated detail.
- ch3 · Ines Calloway: Double-check: The earlier quote is Ines Calloway saying 'I've got myself a lot of questions'; the newer quote is about Pip Aldane not asking questions during a burial. They are different characters in different situations, so no attribute contradiction exists.
- ch5 · Silas Rudd: Double-check: The warning conflates Silas Rudd with the boat Merrow. Chapter 4 places Silas in the harbour office; chapter 5 describes the Merrow moored with a blue hull. The boat's location does not contradict Silas's location, and the colour discrepancy is covered by warning 4.
- ch5 · Ines Calloway: Double-check: Chapter 4 shows an improvised dish-towel wrap immediately after the injury; chapter 5 (weeks later) shows a clean medical bandage. This is normal wound-care progression, not a contradiction.
- ch6 · Tobias Calloway: Double-check: The warning claims a contradiction between chapter 1 (Tobias as older brother) and chapter 5 (Tobias as younger brother), but the NEW quote in chapter 6 ('Tobias read the letter twice...') does not mention sibling age at all. The conflict is between chapters 1 and 5, not involving chapter 6. Per rul

## Name linking

6 of 6 testable checks passed.

- same: Ines Calloway, Keeper Calloway, Ines → pass
- same: Silas Rudd, Harbourmaster Rudd → pass
- same: Tobias Calloway, Tobias → pass
- different: Mara Calloway, Ines Calloway → pass
- different: Mara Calloway, Tobias Calloway → pass
- different: Tobias Calloway, Ines Calloway → pass

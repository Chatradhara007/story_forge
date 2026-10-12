# Consistency over 3 runs

Average precision 55% · average recall 83% · average F1 0.66 · average false alarms 8.3 · average time 487s

| Run | Precision | Recall | F1 | False alarms | Time | AI requests |
|---|---|---|---|---|---|---|
| 1 | 53% | 83% | 0.65 | 9 | 905s | 57 (+0 refused) |
| 2 | 62% | 83% | 0.71 | 6 | 267s | 36 (+0 refused) |
| 3 | 50% | 83% | 0.62 | 10 | 289s | 36 (+0 refused) |

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

- D1: flagged in 3/3 runs: Ines moves into the village for winter: a normal change of location over time.

---

# Details of the last run

# StoryForge evaluation — lighthouse — 2026-10-04 23:27

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3-ultra-550b-a55b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 487s · AI requests per run: 43 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: 0.2 · Reading passage size: whole chapter characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 198 |
| linking names | 52 |
| preparing search | 14 |
| story clock | 0 |
| checking for mistakes | 109 |
| safety-net check | 104 |
| double-checking | 83 |
| saving | 8 |

*Checking, story clock and safety net run at the same time, so their times overlap: the rows add up to more than the total time.*

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 50% | 83% | 0.62 | 10 / 12 | 10 | 3 | 100% |

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
    - ch5: [Thursday visit] event | time of Tobias's arrival | the morning after the storm

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| false alarm | - | ch2 | Gullstone Light | attribute | In chapter 1, Gullstone Light is established as a lighthouse standing on a rock two miles offshore. In chapter 2, 'the Gullstone' is described as a harbour launch (a small boat). These are fundamentally different entities — a fixed lighthouse vs. a movable boat — and cannot both be true for the same named entity. |
| false alarm | - | ch2 | Tobias Calloway | status | Chapter 1 establishes Tobias lives on the mainland and writes letters from there. Chapter 2 shows him physically present at the kitchen table on the rock/island with no explanation of travel or arrival, contradicting his established location. |
| false alarm | - | ch3 | Bramble | status | Chapter 1 establishes Bramble is alive and sleeping by the stove in the keeper's cottage. Chapter 3 states Ines buried Bramble behind the cottage under thrift flowers. Since chapters 1-3 are in chronological order (each 'continues' the previous), Bramble cannot be both alive in chapter 1 and buried in chapter 3 without a death event occurring between them, which is not described. This is a status contradiction: alive vs. dead/buried. |
| false alarm | - | ch3 | Bramble | status | Same entities as pair 3. Chapter 1 shows Bramble alive at the stove; chapter 3 describes his burial. The chronological order makes this a status contradiction (alive vs. buried) with no intervening death narrated. |
| false alarm | - | ch3 | Bramble | status | Same entities as pair 3. The cross location (behind cottage, under thrift flowers) is explicitly the burial site from pair 3. Chapter 1 has Bramble alive at the stove; chapter 3 places a cross at his burial site. Contradiction: Bramble cannot be both alive in chapter 1 and buried with a cross in chapter 3. |
| false alarm | - | ch3 | Ines Calloway | attribute | Pip (chapter 3) and Pip Aldane (chapter 1) are the same character (harbourmaster sent him to learn from Ines; chapter 3 continues the story). Chapter 1: 'Pip was small and freckled and asked a great many questions.' Chapter 3: 'and did not ask any questions at all.' This is an attribute contradiction: a defining trait (asking many questions) is directly negated without explanation (no injury, trauma, or time-skip justification). The confidence is slightly reduced because 'did not ask any questions at all' could refer to a specific scene, but the phrasing suggests a general behavior change. |
| false alarm | - | ch4 | Ines Calloway | status | Ines Calloway is buried Bramble behind the cottage under thrift flowers in chapter 3, but in chapter 4 activity: feeding the flame and winding the clockwork every hour. No flashback is recorded in between. |
| correct | A1 | ch4 | Ines Calloway | attribute | Ines Calloway's eye color is established as grey in chapter 1 ('grey eyes that the fishermen said could spot a sail through fog'), but chapter 4 describes Keeper Calloway (Ines) as having 'green eyes'. This is a direct attribute contradiction with no in-story explanation for the change. |
| correct | S2 | ch4 | Tobias Calloway | status | Tobias Calloway is established as having lost his left hand in a winch accident years ago (chapter 2), keeping the empty sleeve pinned to his coat. Chapter 4 describes him using 'both hands' to hold a broken shutter latch, which is physically impossible given his established condition with no explanation of a prosthesis or regeneration. |
| correct | S1 | ch5 | Bramble | status | Bramble was buried in chapter 3, but in chapter 5 (a few weeks later) he is barking at gulls from the rocks, with no explanation of resurrection or survival. |
| correct | A2 | ch5 | Ines Calloway | attribute | Chapter 1 explicitly states Tobias is Ines's 'older brother'. Chapter 5 has Ines refer to him as 'my younger brother'. This is a direct contradiction in their sibling age order, which is a fixed attribute. |
| duplicate | A2 | ch5 | Tobias Calloway | attribute | Chapter 1 establishes Tobias as Ines's 'older brother'. Chapter 5 describes him as 'younger brother'. This contradicts the established sibling age relationship. |
| correct | S4 | ch5 | Silas Rudd | status | Chapter 4 explicitly states Silas Rudd spent the entire storm night in the harbour office sending telegrams and did not leave until dawn. Chapter 5 claims he rowed out to the Gullstone and sat in the lamp room with Ines until dawn. He cannot be in two places at once during the same night. |
| correct | T1 | ch5 | Ines Calloway | attribute | Chapter 1 (earlier in story) establishes Ines has been keeper for 20 years. Chapter 5 (a few weeks later) states she has been keeper for 8 years. This is a direct contradiction in the duration of her role that cannot be explained by the passage of a few weeks. |
| correct | A3 | ch5 | Merrow | attribute | Chapter 2 describes the Merrow as a 'red-painted launch'. Chapter 5 describes it as having a 'blue hull freshly scrubbed'. The color of the boat contradicts between chapters. |
| duplicate | S4 | ch5 | storm | status | Ines states Silas rowed out to the Gullstone on the night of the storm and sat with her until dawn, but chapter 4 says Silas spent the whole night of the storm in the harbour office. He cannot be in two places at once. |
| duplicate | A3 | ch5 | Merrow | attribute | Chapter 2 states Silas Rudd came to the Gullstone in the Merrow (the red-painted launch). Chapter 5 implies Silas Rudd rowed out to the Gullstone (suggesting a rowboat, not the launch). The vessel type contradicts. |
| false alarm | D1 | ch6 | Ines Calloway | status | Ines Calloway is buried Bramble behind the cottage under thrift flowers in chapter 3, but in chapter 6 action: moved into the village for the winter. No flashback is recorded in between. |
| correct | S3 | ch6 | brass key | status | The brass key was thrown into the sea by Tobias in chapter 3, yet chapter 6 shows Ines using it to unlock the lamp room. No explanation is given for its recovery or replacement. |
| correct | A4 | ch6 | Silas Rudd | attribute | The new fact describes Silas Rudd as clean-shaven, while the existing fact from chapter 2 describes him as having a white beard reaching the second button of his coat. This is a direct physical attribute contradiction with no in-story explanation for the change (e.g., shaving off a long beard). |
| correct | A5 | ch6 | Pip Aldane | attribute | Pip's age is stated as twelve in chapter 6 but was ten in chapter 3. Chapter 5 indicates only 'a few weeks' have passed since chapter 3, which is insufficient time for a two-year age increase. |
| false alarm | - | ch6 | Tobias Calloway | status | The existing fact from chapter 4 shows Tobias using both hands to hold a broken shutter latch during the storm, which is impossible given he lost his left hand in a winch accident (established in chapter 2). The new fact from chapter 6 shows him using two hands to read a letter and put it in his pocket, which is consistent with the missing hand, but the chapter 4 action contradicts his established physical limitation. |
| false alarm (check by hand: maybe S3) | - | ch6 | Gullstone Light | status | The lamp room door was wedged shut with a chair in chapter 3, but chapter 6 describes Ines unlocking it with a key each evening. No explanation is given for how the door was un-wedged or if the chair was removed. |

Decoys wrongly flagged: D1

**Check by hand:** S3. A warning counted as a false alarm has the right chapter, entity and new detail for these items; only its earlier side is worded differently from the answer key. If it is right, the item was caught.

## What the double-check removed

2 warnings dismissed: 2 were false alarms; real mistakes wrongly removed: none.

- ch3 · Silas Rudd: Double-check: The warning compares two different entities: a brass key (thrown into the sea in chapter 3) and Silas Rudd arriving in the Merrow launch (chapter 2). The key and Silas Rudd are not the same object or character. Chapter 2 shows the Merrow operating normally before the key is thrown in chapter 3 — thi
- ch5 · Ines Calloway: Double-check: Chapter 4 shows Ines wrapping a fresh cut in a dish towel (immediate first aid). Chapter 5, weeks later, shows a clean white bandage (healed/treated wound). This is normal wound-care progression over time, not a contradiction.

## Name linking

6 of 6 testable checks passed.

- same: Ines Calloway, Keeper Calloway, Ines → pass
- same: Silas Rudd, Harbourmaster Rudd → pass
- same: Tobias Calloway, Tobias → pass
- different: Mara Calloway, Ines Calloway → pass
- different: Mara Calloway, Tobias Calloway → pass
- different: Tobias Calloway, Ines Calloway → pass

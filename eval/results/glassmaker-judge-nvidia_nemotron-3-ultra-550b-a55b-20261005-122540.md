# Consistency over 3 runs

Average precision 66% · average recall 62% · average F1 0.63 · average false alarms 4.3 · average time 285s

| Run | Precision | Recall | F1 | False alarms | Time | AI requests |
|---|---|---|---|---|---|---|
| 1 | 57% | 62% | 0.59 | 6 | 316s | 26 (+0 refused) |
| 2 | 67% | 62% | 0.64 | 4 | 365s | 26 (+0 refused) |
| 3 | 73% | 62% | 0.67 | 3 | 174s | 26 (+0 refused) |

## How often each planted mistake was caught

| Mistake | Type | Caught | Why missed (per run) | Description |
|---|---|---|---|---|
| A1 | attribute | 3/3 (always) | ✓, ✓, ✓ | Orla's scar is on her right palm (ch1, ch3) but her left palm (ch2). |
| A2 | attribute | 3/3 (always) | ✓, ✓, ✓ | The workshop has a single furnace (ch1) but all three furnaces are roaring (ch2). |
| A3 | attribute | 3/3 (always) | ✓, ✓, ✓ | Orla is left-handed (ch1) but signs with her right hand 'as she always had' (ch4). |
| A4 | attribute | 3/3 (always) | ✓, ✓, ✓ | Rose is Orla's younger sister (ch1) but her cousin (ch4). |
| A5 | attribute | 3/3 (always) | ✓, ✓, ✓ | Captain Crane is tall and stooping (ch1, ch3) but 'the short captain' who stands on his toes (ch5). |
| S1 | status | 0/3 (never) | not read (later), not read (later), not read (later) | Tom Fenner drowned in the fire (ch2) but poles his ferry past, whistling (ch4). |
| S2 | status | 3/3 (always) | ✓, ✓, ✓ | The green ledger burned to ash (ch2) but Crane reads its old entries (ch5). |
| S3 | status | 0/3 (never) | not read (later), not read (later), not read (later) | Rook lost two fingers (ch1) but Edwin Marsh spreads all ten fingers (ch5). Needs the secret identity linked. |
| S4 | status | 3/3 (always) | ✓, ✓, ✓ | The lens was mended seamlessly by magic (ch4) but is 'still cracked, just as it had been since the fire' (ch5). |
| T1 | timeline | 3/3 (always) | ✓, ✓, ✓ | Orla was born in Varrow and never left (ch1) but came to Varrow at nineteen (ch3). The mistake is inside the flashback. |
| T2 | timeline | 0/3 (never) | checker, checker, checker | Rook is sixteen (ch1); three years later he should be nineteen, not twenty-two (ch4). |
| T3 | timeline | 0/3 (never) | not read (later), not read (later), not read (later) | The fire began just after midnight (ch2) but started at dusk (ch4). |
| T4 | timeline | 0/3 (never) | split, split, split | The fire was on the eve of the autumn Lantern Festival (ch1-2) but is called 'the midsummer fire' (ch5). |

## Traps wrongly flagged

- D3: flagged in 1/3 runs: FLASHBACK: Orla is 22 in ch3 and 34 in ch1: exactly 12 years apart.
- D6: flagged in 3/3 runs: TWO TOMS: 'Tom' in ch5 is Tom Brisk the clerk, not the drowned ferryman Tom Fenner.

---

# Details of the last run

# StoryForge evaluation — glassmaker — 2026-10-05 12:25

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3-ultra-550b-a55b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 285s · AI requests per run: 26 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: reader 0.0, judge 0.0 · Reading passage size: 700 characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 0 |
| linking names | 128 |
| preparing search | 5 |
| story clock | 0 |
| checking for mistakes | 63 |
| safety-net check | 81 |
| double-checking | 58 |
| saving | 7 |

*Checking, story clock and safety net run at the same time, so their times overlap: the rows add up to more than the total time.*

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 73% | 62% | 0.67 | 8 / 13 | 3 | 1 | 100% |

| Type | Planted | Caught | Recall |
|---|---|---|---|
| attribute | 5 | 5 | 100% |
| status | 4 | 2 | 50% |
| timeline | 4 | 1 | 25% |

## Missed mistakes

- **S1** (ch4): Tom Fenner drowned in the fire (ch2) but poles his ferry past, whistling (ch4).
- **S3** (ch5): Rook lost two fingers (ch1) but Edwin Marsh spreads all ten fingers (ch5). Needs the secret identity linked.
- **T2** (ch4): Rook is sixteen (ch1); three years later he should be nineteen, not twenty-two (ch4).
- **T3** (ch4): The fire began just after midnight (ch2) but started at dusk (ch4).
- **T4** (ch5): The fire was on the eve of the autumn Lantern Festival (ch1-2) but is called 'the midsummer fire' (ch5).

## Why each mistake was missed

Causes: *not read* = the Reader didn't record the detail; *split* = the details were filed under different entries (a name-linking problem); *checker* = both were on the same entry but weren't flagged.

- **S1** → **not read (later)**: No fact from ch4 mentions this detail.
    - ch2: [Tom Fenner] Tom Fenner | status | drowned
    - ch2: [Tom Fenner] Tom Fenner | event | boat capsized when the roof beams fell into the water
    - ch2: [Tom Fenner] Tom Fenner | event | drowned before anyone could reach him
- **S3** → **not read (later)**: No fact from ch5 mentions this detail.
    - ch1: [Edwin Marsh] Rook | physical_description | thin, red-haired, lost two fingers of his left hand
    - ch1: [furnace] furnace | damage | lost two fingers of Rook's left hand
- **T2** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch1: [Orla Venn] Orla Venn | social tie | mentor of Rook
    - ch1: [Edwin Marsh] Rook | social tie | student of Orla Venn
    - ch1: [Edwin Marsh] Rook | age | sixteen
    - ch1: [Edwin Marsh] Rook | physical_description | thin, red-haired, lost two fingers of his left hand
    - ch4: [Edwin Marsh] Edwin | age | twenty-two
- **T3** → **not read (later)**: No fact from ch4 mentions this detail.
    - ch2: [The workshop fire] fire | time | just after midnight
    - ch2: [The workshop fire] fire | location | workshop
- **T4** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch1: [Lantern Festival] Lantern Festival | occurrence | eve of the autumn Lantern Festival
    - ch5: [Edwin Marsh's family] debt the Marsh family owed | owed the workshop since before the midsummer fire | owed the workshop since before the midsummer fire
    - ch5: [Edwin Marsh's family] Marsh family | owed debt to workshop | owed the workshop since before the midsummer fire

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| correct | A1 | ch2 | Orla Venn | attribute | The new fact states Orla has an old scar on her left palm, while the existing fact from chapter 1 clearly states she has a pale scar across her right palm from a blowpipe accident. This is a direct contradiction of a physical attribute that cannot change sides without explanation. |
| correct | A2 | ch2 | Orla Venn's workshop on Tallow Street | attribute | Chapter 1 establishes the workshop has a single furnace that has been continuously burning for eleven years. Chapter 2 (three years later) describes three furnaces roaring simultaneously. The number of furnaces has changed from one to three without explanation, which is an attribute contradiction. |
| correct | T1 | ch3 | Orla Venn | attribute | New fact states Orla came to Varrow as a girl of nineteen, three years before the flashback (i.e., 15 years before the fire), implying she was not born there. Existing fact (chapter 1) states she was born in Varrow and never left it. These are mutually exclusive. |
| duplicate | T1 | ch3 | Orla Venn | timeline | Chapter 3 states Orla came to Varrow at 19, 'three years before' the flashback (which is 12 years before the fire), so she arrived 15 years before the fire. Chapter 1 states she is 34 and 'had never once left' Varrow, implying she was born there. These directly contradict: either she was born in Varrow (Ch1) or arrived at 19 (Ch3). |
| false alarm | - | ch3 | Orla Venn | attribute | Chapter 3 states Ysolde hummed over Orla's wound (from a blowpipe slip) and 'the scar stayed' on Orla's right palm (implied by Ch1: 'pale scar ran across her right palm'). Chapter 2 states Orla presses her *left* palm, 'where the old scar ran,' against her mouth. The scar has moved from right palm (Ch1, Ch3) to left palm (Ch2) with no explanation. |
| false alarm | - | ch3 | Orla Venn | attribute | Chapter 3 states 'the scar stayed' on Orla (right palm, per Ch1). Chapter 2 describes Orla pressing her *left* palm where 'the old scar ran.' The scar's location contradicts between right (Ch1, Ch3) and left (Ch2) with no in-story explanation. |
| correct | A4 | ch4 | Rose Halloway | attribute | Chapter 4 states Rose is Orla's cousin, while Chapter 1 establishes she is Orla's younger sister. These are mutually exclusive familial relationships. |
| correct | A3 | ch4 | Orla Venn | attribute | Chapter 4 states Orla signs with her right hand 'as she always had', but Chapter 1 explicitly states she is left-handed. This is a direct contradiction of an established permanent trait. |
| false alarm | D6 | ch5 | Tom Fenner | status | Tom Fenner is established as having drowned in chapter 2 (three years after the fire). Chapter 5 is set three years after the fire (same timeframe as chapter 2), yet Tom is alive and acting as the captain's clerk. A dead person cannot hand a warrant to a captain. |
| correct | S2 | ch5 | ledger | status | The green ledger is established as having 'burned to ash on the counter' in chapter 2 (during the fire). Chapter 5 (three years after the fire) shows the ledger intact and on the counter, being opened by Captain Crane. A destroyed object cannot be used later without explanation of restoration or replacement. |
| correct | S4 | ch5 | Sunstone lens | attribute | Chapter 4 explicitly states the Sunstone lens was magically reassembled and sealed until it was 'whole and seamless again, without a line to show where it had broken.' Chapter 5 (set at the same time as Chapter 4, both 'three years after the fire') describes it as 'still cracked down the middle, just as it had been since the fire.' These are mutually exclusive physical states for the same object at the same narrative time. |
| correct | A5 | ch5 | Captain Aldous Crane | attribute | Captain Crane is described as 'short' in chapter 5, but chapter 1 establishes him as 'tall, stooping man who seemed to apologise to every ceiling.' Chapter 3 (flashback) confirms he was 'already tall and already stooping' twelve years before the fire. Height is a permanent physical attribute that cannot change without explanation. |

Decoys wrongly flagged: D6



## What the double-check removed

7 warnings dismissed: 7 were false alarms; real mistakes wrongly removed: none.

- ch2 · sand: Set aside: the story moving forward (something that existed earlier in story time has 'drowned' later). Only the reverse would be a mistake.
- ch2 · Orla Venn: Double-check: The new quote ('The fire began just after midnight') does not mention the number of furnaces or identify the workshop as Orla's. The warning relies on the furnace count from warning 1, but that detail is not in this quote. Without that link, there is no direct contradiction here.
- ch3 · Orla Venn: Set aside: the warning's own explanation says the two facts are consistent.
- ch3 · Orla Venn: Double-check: The age timeline is consistent: Orla is 22 in chapter 3 (12 years before the fire) and 34 in chapter 1 (before the fire), a 12-year gap. The warning itself acknowledges the math works. No contradiction exists.
- ch4 · Sunstone lens: Set aside: the warning's own explanation says the two facts are consistent.
- ch4 · Edwin Marsh: Double-check: Chapter 2 (three years after Rook went into hiding) calls Edwin Marsh a 'runaway son'—a description that can fit a 19-year-old. Chapter 4 (three years after the fire, same timeline) says he is now 22. The age progression is consistent, and the 'runaway son' label does not require him to have been a 
- ch5 · Orla Venn: Set aside: the warning's own explanation says the two facts are consistent.

## Name linking

7 of 7 testable checks passed.

- same: Rook, Edwin Marsh, Edwin → pass
- same: Aldous Crane, Captain Aldous Crane, Captain Crane → pass
- same: Orla Venn, Orla → pass
- same: Rose Halloway, Rose → pass
- different: Tom Fenner, Tom Brisk → pass
- different: Rose Halloway, Orla Venn → pass
- different: Ysolde, Orla Venn → pass

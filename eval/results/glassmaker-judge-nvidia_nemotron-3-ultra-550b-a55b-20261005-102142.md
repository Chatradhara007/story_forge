# Consistency over 3 runs

Average precision 51% · average recall 62% · average F1 0.55 · average false alarms 8.0 · average time 326s

| Run | Precision | Recall | F1 | False alarms | Time | AI requests |
|---|---|---|---|---|---|---|
| 1 | 44% | 62% | 0.52 | 10 | 657s | 44 (+0 refused) |
| 2 | 57% | 62% | 0.59 | 6 | 152s | 26 (+0 refused) |
| 3 | 50% | 62% | 0.55 | 8 | 168s | 25 (+0 refused) |

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
| T2 | timeline | 0/3 (never) | split, split, split | Rook is sixteen (ch1); three years later he should be nineteen, not twenty-two (ch4). |
| T3 | timeline | 0/3 (never) | not read (later), not read (later), not read (later) | The fire began just after midnight (ch2) but started at dusk (ch4). |
| T4 | timeline | 0/3 (never) | split, split, split | The fire was on the eve of the autumn Lantern Festival (ch1-2) but is called 'the midsummer fire' (ch5). |

## Traps wrongly flagged

- D2: flagged in 1/3 runs: FLASHBACK: Orla's palms are unmarked in ch3 because she hasn't been cut yet; she gets the scar at the end of the chapter.
- D3: flagged in 3/3 runs: FLASHBACK: Orla is 22 in ch3 and 34 in ch1: exactly 12 years apart.
- D6: flagged in 3/3 runs: TWO TOMS: 'Tom' in ch5 is Tom Brisk the clerk, not the drowned ferryman Tom Fenner.

---

# Details of the last run

# StoryForge evaluation — glassmaker — 2026-10-05 10:21

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3-ultra-550b-a55b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 326s · AI requests per run: 32 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: 0.2 · Reading passage size: whole chapter characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 158 |
| linking names | 39 |
| preparing search | 6 |
| story clock | 1 |
| checking for mistakes | 45 |
| safety-net check | 62 |
| double-checking | 40 |
| saving | 7 |

*Checking, story clock and safety net run at the same time, so their times overlap: the rows add up to more than the total time.*

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 50% | 62% | 0.55 | 8 / 13 | 8 | 1 | 100% |

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
    - ch1: [Rook] Rook | physical_description | thin, red-haired, lost two fingers of his left hand
    - ch1: [furnace] furnace | damage | lost two fingers of Rook's left hand
- **T2** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch1: [Orla Venn] Orla Venn | social tie | mentor of Rook
    - ch1: [Rook] Rook | social tie | student of Orla Venn
    - ch1: [Rook] Rook | age | sixteen
    - ch1: [Rook] Rook | physical_description | thin, red-haired, lost two fingers of his left hand
    - ch4: [Edwin Marsh] Edwin | age | twenty-two
- **T3** → **not read (later)**: No fact from ch4 mentions this detail.
    - ch2: [the workshop fire] fire | time | just after midnight
    - ch2: [the workshop fire] fire | location | workshop
- **T4** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch1: [Lantern Festival] Lantern Festival | occurrence | eve of the autumn Lantern Festival
    - ch5: [Edwin Marsh's family] debt the Marsh family owed | owed the workshop since before the midsummer fire | owed the workshop since before the midsummer fire
    - ch5: [Edwin Marsh's family] Marsh family | owed debt to workshop | owed the workshop since before the midsummer fire

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| correct | A1 | ch2 | Orla Venn | attribute | Chapter 1 establishes Orla has a pale scar across her right palm from a blowpipe accident. Chapter 2 states she has an old scar on her left palm. This is a direct contradiction of a physical attribute (which hand is scarred) without any in-story explanation for the change. |
| correct | A2 | ch2 | Orla Venn's workshop | attribute | Chapter 1 establishes the workshop has a single furnace that has been continuously burning for eleven years. Chapter 2 (three years later) describes three furnaces roaring. The number of furnaces is a fixed attribute of the workshop's construction; adding two more furnaces would be a major structural change not mentioned or explained in the three-year gap. |
| false alarm | - | ch2 | Orla Venn | attribute | Same contradiction as pair 1: Chapter 1 states Orla's workshop has a single furnace; Chapter 2 describes a fire in a workshop with three furnaces. The fire location is Orla's workshop (confirmed by pair 13), so the furnace count contradicts. |
| correct | T1 | ch3 | Orla Venn | attribute | New fact states Orla came to Varrow as a girl of nineteen, three years before the flashback (i.e., at age 19), implying she was not born there. Existing fact (chapter 1) states she was born in Varrow and never left it. These are mutually exclusive claims about her birthplace and lifelong residence. |
| false alarm | D3 | ch3 | Orla Venn | timeline | Chapter 3 (flashback set 12 years before the fire) states Orla Venn was 22 at that time. Chapter 1 (set after the fire) states Orla is 34 and was born in Varrow and never left. If the fire occurred recently before Chapter 1, Orla would be ~34 at the time of the fire, making her 22 exactly 12 years prior — this is mathematically consistent. However, Chapter 1 also states her furnace 'had not gone cold in eleven years,' implying she has been working continuously for 11 years up to Chapter 1. But Chapter 3 says she 'had never made anything worth selling' 12 years before the fire (i.e., at age 22), and only came to Varrow at 19 (3 years before that). This suggests she started working in Varrow at 19, but the furnace not going cold for 11 years would mean she started at age 23 (34-11), creating a 4-year gap between her arrival (19) and the furnace being continuously lit (from 23). This is a timeline contradiction about when her continuous work began. |
| false alarm | - | ch3 | Orla Venn | attribute | New fact describes the injury as caused by a hot iron laying open the right palm from thumb to little finger. Existing fact describes the scar as from a blowpipe that slipped. The cause and mechanism of the injury are different, and both are presented as the origin of the scar on the right palm. |
| duplicate | T1 | ch3 | Orla Venn | timeline | Chapter 3 states Orla came to Varrow at age 19, 'three years before' the flashback (which is 12 years before the fire). So she arrived 15 years before the fire. Chapter 1 states she is 34 and 'had been born in Varrow and had never once left it.' This directly contradicts Chapter 3's claim that she came to Varrow as a girl of 19 from elsewhere. If she was born in Varrow and never left, she could not have 'come to Varrow' at 19. This is a fundamental timeline and origin contradiction. |
| false alarm | D2 | ch3 | Orla Venn | attribute | New fact (flashback, 12 years before fire) states Orla's palms were unmarked by any burn or cut. Existing fact (chapter 2, 3 years after hiding began, which is after chapter 1) states she has an old scar on her left palm. Since the flashback is earlier, the scar must have been acquired after this flashback. However, the existing fact in chapter 1 says the scar is on the right palm from a blowpipe slip. The new fact says no marks on either palm at age 22. The chapter 2 fact says left palm has old scar. This suggests either the scar moved from right to left, or there are two scars, or the new fact is wrong. But the new fact explicitly says 'palms unmarked by any burn or cut' — plural — so both palms were unmarked. The chapter 1 fact says right palm has scar from blowpipe. The chapter 2 fact says left palm has old scar. This is a contradiction in location and existence of scar at that time. |
| false alarm | - | ch3 | Orla Venn | attribute | Chapter 3 states Ysolde hummed over Orla's wound (from a blowpipe slip) and 'the scar stayed' — implying the scar is on Orla's right palm (since Chapter 1 says 'a pale scar ran across her right palm, the mark of a blowpipe that had slipped long ago'). But Chapter 2 states Orla 'pressed her left palm, where the old scar ran, against her mouth and nose.' This is a direct contradiction: the scar is on the right palm in Chapter 1 (confirmed as from a blowpipe slip) but on the left palm in Chapter 2. Since both describe the same old scar, this is an attribute contradiction. |
| correct | A4 | ch4 | Rose Halloway | attribute | New fact states Rose is Orla's cousin, but existing fact from chapter 1 establishes Rose as Orla's younger sister. This is a direct contradiction in their familial relationship. |
| correct | A3 | ch4 | Orla Venn | attribute | New fact states Orla signed with her right hand 'as she always had', but existing fact from chapter 1 establishes she is left-handed. This contradicts her established handedness. |
| false alarm | - | ch4 | Sunstone lens | attribute | Chapter 1 states the Sunstone lens was whole and 'on the bench, wrapped in felt', while Chapter 4 says Rose unwrapped 'the pieces of the Sunstone lens, which she had kept in a box for three years'. Chapter 2 confirms the lens 'shattered on the stone floor into a hundred golden pieces' during the fire. The new chapter describes the lens as already in pieces and kept in a box for three years, contradicting the earlier description of it being whole and on the bench in Chapter 1 (which is set before the fire). This is an attribute contradiction about the physical state of the lens. |
| false alarm (check by hand: maybe T2) | - | ch4 | Edwin Marsh | attribute | New fact says Edwin is now 22. Existing fact from chapter 2 says Rook's real name is Edwin Marsh, and Rook had been hiding in Orla's workshop for 3 years (chapter 2). Chapter 4 is 3 years after the fire. If Edwin/Rook was hiding for 3 years before chapter 2, and chapter 4 is 3 years after the fire (which likely happened around chapter 2), then Edwin would be older than 22 unless he was very young when he started hiding. But chapter 2 calls him 'the runaway son' suggesting he was at least a teenager. This needs more context but could be a timeline contradiction. |
| false alarm | D6 | ch5 | Tom Fenner | status | Tom Fenner is established as having drowned in chapter 2 (three years after fire). Chapter 5 is set three years after the fire (same timeframe as chapter 2), yet Tom is alive and acting as the captain's clerk. A dead character cannot perform actions. |
| correct | S2 | ch5 | ledger | status | The green ledger is explicitly stated to have 'burned to ash on the counter' in chapter 2 (during the fire). Chapter 5 (three years after the fire) shows the ledger intact and on the counter. A destroyed object cannot reappear without explanation. |
| correct | S4 | ch5 | Sunstone lens | attribute | Chapter 4 explicitly states the Sunstone lens was magically repaired and became 'whole and seamless again, without a line to show where it had broken.' Chapter 5 (three years later) describes it as 'still cracked down the middle, just as it had been since the fire,' directly contradicting the established repair. |
| correct | A5 | ch5 | Captain Aldous Crane | attribute | Captain Crane is described as 'short' in chapter 5, but chapter 1 establishes him as 'tall, stooping man who seemed to apologise to every ceiling.' Chapter 3 (flashback 12 years before fire) confirms he was 'already tall and already stooping.' Height is a permanent physical attribute that cannot change without explanation. |

Decoys wrongly flagged: D2, D3, D6

**Check by hand:** T2. A warning counted as a false alarm has the right chapter, entity and new detail for these items; only its earlier side is worded differently from the answer key. If it is right, the item was caught.

## What the double-check removed

3 warnings dismissed: 3 were false alarms; real mistakes wrongly removed: none.

- ch2 · sand: Set aside: the story moving forward (something that existed earlier has 'drowned' later). Only the reverse would be a mistake.
- ch4 · Orla Venn: Double-check: Chapter 1 gives Orla's age as 34 before the fire. Chapter 4 is explicitly 'three years after the fire', making her 37. The progression is consistent with the stated time skip; no contradiction exists.
- ch5 · Rook: Double-check: The warning claims a contradiction about Rook/Edwin Marsh's hiding status, but the chapter 5 quote provided ('I'll testify') does not contain the name 'Edwin Marsh' or show him acting openly under that name. The quote only shows someone saying 'I'll testify'—this could be Rook using his alias, or a 

## Name linking

6 of 7 testable checks passed.

- same: Rook, Edwin Marsh, Edwin → FAIL
- same: Aldous Crane, Captain Aldous Crane, Captain Crane → pass
- same: Orla Venn, Orla → pass
- same: Rose Halloway, Rose → pass
- different: Tom Fenner, Tom Brisk → pass
- different: Rose Halloway, Orla Venn → pass
- different: Ysolde, Orla Venn → pass

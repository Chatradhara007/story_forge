# Consistency over 3 runs

Average precision 68% · average recall 72% · average F1 0.69 · average false alarms 4.3 · average time 270s

| Run | Precision | Recall | F1 | False alarms | Time | AI requests |
|---|---|---|---|---|---|---|
| 1 | 71% | 83% | 0.77 | 4 | 308s | 35 (+0 refused) |
| 2 | 75% | 50% | 0.60 | 2 | 218s | 36 (+0 refused) |
| 3 | 59% | 83% | 0.69 | 7 | 283s | 35 (+0 refused) |

## How often each planted mistake was caught

| Mistake | Type | Caught | Why missed (per run) | Description |
|---|---|---|---|---|
| A1 | attribute | 3/3 (always) | ✓, ✓, ✓ | Ines's eyes: grey (ch1) vs green (ch4). Uses a different name, 'Keeper Calloway'. |
| A2 | attribute | 2/3 (sometimes) | ✓, checker, ✓ | Tobias is Ines's older brother (ch1) but her younger brother (ch5). |
| A3 | attribute | 2/3 (sometimes) | ✓, checker, ✓ | The Merrow is red-painted (ch2) but has a blue hull (ch5). |
| A4 | attribute | 3/3 (always) | ✓, ✓, ✓ | Rudd has a long white beard (ch2) but a clean-shaven chin (ch6). Uses 'Harbourmaster Rudd'. |
| A5 | attribute | 3/3 (always) | ✓, ✓, ✓ | Pip is ten (ch3) but twelve (ch6), within one autumn. |
| S1 | status | 3/3 (always) | ✓, ✓, ✓ | Bramble dies (ch3) but barks at gulls (ch5). |
| S2 | status | 2/3 (sometimes) | ✓, checker, ✓ | Tobias lost his left hand (ch2) but claps both hands over a latch (ch4). |
| S3 | status | 3/3 (always) | ✓, ✓, ✓ | The brass key is thrown into the sea (ch3) but used to unlock the lamp room (ch6). |
| S4 | status | 3/3 (always) | ✓, ✓, ✓ | Rudd spent the whole storm night in the harbour office (ch4) but rowed out to the Gullstone that night (ch5). |
| T1 | timeline | 2/3 (sometimes) | ✓, checker, ✓ | Ines has kept the light twenty years (ch1) but eight years (ch5). |
| T2 | timeline | 0/3 (never) | not read (later), not read (later), not read (later) | The storm broke on Tuesday (ch4) but was 'on Friday' (ch6). |
| T3 | timeline | 0/3 (never) | split, split, split | Tobias arrived three days before the storm (ch2) but the morning after it (ch5). |

## Traps wrongly flagged

None, in any run.

---

# Details of the last run

# StoryForge evaluation — lighthouse — 2026-10-05 00:26

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3-ultra-550b-a55b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 270s · AI requests per run: 35 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: 0.2 · Reading passage size: whole chapter characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 0 |
| linking names | 63 |
| preparing search | 6 |
| story clock | 1 |
| checking for mistakes | 74 |
| safety-net check | 123 |
| double-checking | 49 |
| saving | 9 |

*Checking, story clock and safety net run at the same time, so their times overlap: the rows add up to more than the total time.*

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 59% | 83% | 0.69 | 10 / 12 | 7 | 2 | 100% |

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
    - ch5: [Reporter's Thursday visit] event | time of Tobias's arrival | the morning after the storm

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| false alarm | - | ch2 | Gullstone Light | attribute | The new fact describes Gullstone as a red-painted launch (a boat), while the existing fact describes Gullstone Light as a lighthouse standing on a rock two miles offshore. These are fundamentally different physical entities with incompatible attributes. |
| false alarm | - | ch2 | Pip Aldane | attribute | Pair 0 compares Silas Rudd (harbourmaster in chapter 2) with Pip Aldane (described as a boy sent by the harbourmaster in chapter 1). The quotes show Silas Rudd IS the harbourmaster of Port Wick, while Pip Aldane is a boy the harbourmaster sent out. They cannot be the same person — one is the adult harbourmaster, the other a boy apprentice. This is an attribute contradiction: the new chapter names the harbourmaster as Silas Rudd, while the earlier chapter implies the harbourmaster is someone else (who sent Pip). |
| false alarm | - | ch2 | Pip Aldane | attribute | Pair 2 compares Silas Rudd (broad man with white beard, harbourmaster in chapter 2) with Pip Aldane (boy sent by harbourmaster in chapter 1). Same as pair 0: Silas Rudd is the harbourmaster, Pip is a boy the harbourmaster sent. They are different people. The physical description of Silas (broad, white beard) contradicts Pip being a small, freckled boy — but more fundamentally, the role 'harbourmaster' is assigned to Silas in ch2, while ch1 shows the harbourmaster sending Pip, implying the harbourmaster is not Pip. This is an attribute contradiction on identity/role. |
| false alarm | - | ch2 | Tobias Calloway | status | Chapter 1 establishes Tobias lives on the mainland and writes letters from there. Chapter 2 shows him physically present at the kitchen table on the rock/island. Since the chapters are sequential with no time skip mentioned, this is a status contradiction - he cannot be both living on the mainland and sitting at the kitchen table on the rock simultaneously without explanation of travel/arrival. |
| false alarm | - | ch2 | Pip Aldane | attribute | Pair 5 compares Silas Rudd coming out to the Gullstone in the Merrow (ch2) with Pip Aldane being a boy sent by the harbourmaster (ch1). The action implies Silas is the harbourmaster acting officially, while Pip is the apprentice sent out. If they were the same entity, a boy would not be commanding the harbour launch. The roles contradict: harbourmaster vs apprentice. Attribute contradiction on role/status. |
| false alarm | - | ch3 | Bramble | timeline | Pair 12: Chapter 3 says Ines buried Bramble 'and did not speak for the rest of the day'. Chapter 1 establishes Bramble 'lived Ines's old sheepdog, Bramble, who was nearly deaf and slept by the stove' - implying Bramble was alive and living at the cottage. Chapter 2 shows Ines active at the landing. The timeline contradiction: if Bramble was alive in chapter 1 (earlier) and buried in chapter 3 (later), that's consistent. But chapter 2 (between them) shows Ines active at the landing with no mention of a recent burial or grief. The 'rest of the day' silence in chapter 3 suggests the burial just happened, but chapter 2 shows her functioning normally afterward. This creates a timeline inconsistency about when the burial occurred relative to chapter 2 events. |
| correct | A1 | ch4 | Ines Calloway | attribute | Chapter 1 establishes Ines Calloway has 'grey eyes' (existing fact 2). Chapter 4 describes Keeper Calloway (same person) with 'green eyes' (new fact 0). Eye color is a permanent physical attribute that cannot change without explanation (magic, injury, disguise), and none is provided. The chapters are in chronological order (1 then 4), so this is a contradiction. |
| correct | S2 | ch4 | Tobias Calloway | status | Chapter 2 establishes Tobias Calloway lost his left hand in a winch accident 'many years ago' and 'kept the empty sleeve pinned neatly to his coat' (existing facts 7-8). Chapter 4 describes him clapping 'both hands over the broken latch' (new fact 1), which requires two functioning hands. This is a status contradiction: a character with one hand cannot use both hands without explanation (prosthetic, regeneration, etc.), and none is provided. The chapters are in chronological order (2 then 4), so the disability should persist. |
| correct | A2 | ch5 | Tobias Calloway | attribute | New fact from chapter 5 describes Tobias as Ines's 'younger brother', but chapter 1 explicitly states he is her 'older brother'. This is a direct contradiction in sibling birth order, which cannot change over time. |
| correct | A3 | ch5 | Merrow | attribute | Chapter 2 describes the Merrow as a 'red-painted launch'. Chapter 5 describes it as having a 'blue hull freshly scrubbed'. A hull color change from red to blue in a few weeks without explanation (e.g., repainting) is a contradiction in a permanent physical attribute. |
| correct | S4 | ch5 | Silas Rudd | status | Chapter 4 states Silas Rudd spent the entire storm night in the harbour office sending telegrams and did not leave until dawn. Chapter 5 claims he rowed out to the Gullstone and stayed in the lamp room with Ines until dawn. He cannot be in two places at once during the same night. |
| correct | S1 | ch5 | Bramble | status | Bramble was buried in chapter 3, but in chapter 5 (a few weeks later) he is barking at gulls from the rocks, with no explanation of resurrection or survival. |
| correct | T1 | ch5 | Ines Calloway | attribute | New fact states Ines has been keeper for eight years, but existing fact from chapter 1 says she had kept the light burning for twenty years. A time skip of 'a few weeks' cannot account for a 12-year reduction in tenure. |
| duplicate | S4 | ch5 | storm | status | Chapter 5 states that on the night of the storm, Silas Rudd rowed out to the Gullstone and sat with Ines in the lamp room until dawn. Chapter 4 states Silas Rudd spent the whole night of the storm in the harbour office. These are mutually exclusive locations for the same person at the same time. This is a direct status contradiction: Silas cannot be both at the Gullstone lamp room and in the harbour office for the entire night. |
| duplicate | S4 | ch5 | Silas Rudd | status | The Merrow is described in chapter 5 as moored at the landing with its blue hull freshly scrubbed, and the reporter's question implies Silas Rudd rowed it out to the Gullstone on the night of the storm. However, chapter 4 explicitly states Silas Rudd spent the whole night of the storm in the harbour office. If Silas was in the harbour office all night, he could not have rowed the Merrow to the Gullstone. The Merrow cannot be both moored at the landing (implying it wasn't used that night) and have been rowed out by Silas (who was elsewhere). This is a status contradiction about the boat's use and Silas's location. |
| correct | A5 | ch6 | Pip Aldane | attribute | Pip's age jumps from 10 (chapter 3) to 12 (chapter 6). Chapter 5 mentions 'a few weeks after the storm' and chapter 6 also says 'a few weeks after the storm', meaning only weeks have passed. A two-year age increase in weeks is impossible. |
| correct | S3 | ch6 | brass key | status | Chapter 3 explicitly states Tobias threw the brass key into the sea. Chapter 6 shows Ines using that same key to unlock the lamp room. A key thrown into the sea cannot be used unless retrieved or replaced, neither of which is mentioned. |
| correct | A4 | ch6 | Silas Rudd | attribute | New fact describes Silas Rudd as clean-shaven, while existing fact from chapter 2 describes him with a white beard reaching his coat button. No in-story explanation (shaving, disguise, time passage) is provided for this change in physical appearance. |
| false alarm | - | ch6 | Tobias Calloway | status | Tobias lost his left hand in a winch accident many years ago (existing fact 7) and keeps the empty sleeve pinned to his coat (existing fact 8). In chapter 4, he 'clapped both hands over the broken latch,' which is already a contradiction with his missing hand. The new fact in chapter 6 describes him reading a letter and putting it in his pocket — a two-handed action — without any explanation of how he manages this with only one hand. This contradicts his established physical status as a one-handed man. |

Decoys wrongly flagged: none



## What the double-check removed

9 warnings dismissed: 9 were false alarms; real mistakes wrongly removed: none.

- ch3 · Ines Calloway: Set aside: the story moving forward (something that existed earlier has 'buried' later). Only the reverse would be a mistake.
- ch3 · Ines Calloway: Double-check: The warning misreads the quotes. The earlier quote is Ines saying *she* has a lot of questions; the new quote says *Pip* did not ask any questions. They describe different people. No contradiction.
- ch3 · Bramble: Set aside: the story moving forward (something that existed earlier has 'buried' later). Only the reverse would be a mistake.
- ch3 · Silas Rudd: Set aside: the story moving forward (something that existed earlier has 'thrown' later). Only the reverse would be a mistake.
- ch3 · Pip Aldane: Double-check: Being sent to learn lighthouse work does not guarantee the boy has already experienced a real storm at sea. The new quote says he *had never seen* one (up to that point), which is plausible for a novice. No contradiction.
- ch3 · empty sleeve: Double-check: The two quotes describe completely different objects (an empty sleeve vs. a lamp-room key) in different locations. The warning itself acknowledges they are distinct entities. No contradiction.
- ch5 · Ines Calloway: Double-check: Normal progression: a dish towel is an improvised first-aid wrap; a clean white bandage weeks later is exactly what one would expect after proper care. No contradiction.
- ch6 · Ines Calloway: Double-check: This is a normal story progression: Ines moves to the village for winter and leaves Pip in charge on alternate days. The timing notes show a time skip of weeks between chapters 4 and 6, allowing this change in routine. No contradiction.
- ch6 · lamp room: Double-check: A door wedged shut with a chair (chapter 3) can be un-wedged and then locked/unlocked with a key later (chapter 6). This is a normal change in security routine over weeks, not a contradiction.

## Name linking

6 of 6 testable checks passed.

- same: Ines Calloway, Keeper Calloway, Ines → pass
- same: Silas Rudd, Harbourmaster Rudd → pass
- same: Tobias Calloway, Tobias → pass
- different: Mara Calloway, Ines Calloway → pass
- different: Mara Calloway, Tobias Calloway → pass
- different: Tobias Calloway, Ines Calloway → pass

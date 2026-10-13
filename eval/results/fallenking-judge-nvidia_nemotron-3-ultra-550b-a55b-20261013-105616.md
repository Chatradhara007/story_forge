# Consistency over 2 runs

Average precision 22% · average recall 23% · average F1 0.22 · average false alarms 9.0 · average time 686s

| Run | Precision | Recall | F1 | False alarms | Time | AI requests |
|---|---|---|---|---|---|---|
| 1 | 21% | 27% | 0.24 | 11 | 707s | 84 (+0 refused) |
| 2 | 22% | 18% | 0.20 | 7 | 666s | 81 (+1 refused) |

## How often each planted mistake was caught

| Mistake | Type | Caught | Why missed (per run) | Description |
|---|---|---|---|---|
| A1 | attribute | 2/2 (always) | ✓, ✓ | Ember is a grey stallion (ch1, ch6) but 'the black stallion' (ch5). |
| A2 | attribute | 1/2 (sometimes) | ✓, checker | Aurel's Greywater scar is on his left hand (ch1) but his right hand (ch7). |
| A3 | attribute | 0/2 (never) | checker, checker | Thessaly's eyes are grey-green (ch1) but dark brown (ch8). |
| A4 | attribute | 0/2 (never) | checker, checker | Mira is four years younger than Aurel (ch5) but his elder sister (ch7). |
| A5 | attribute | 0/2 (never) | split, split | Sixty of the 940 ships came home (ch2) but every last one went down (ch4). |
| S1 | status | 0/2 (never) | checker, checker | Aurel gave the signet ring to Corvin (ch3) but turns it on his own finger as a ferryman (ch4). |
| S2 | status | 0/2 (never) | checker, checker | Ember had to be left behind in Vessa (ch3) but Pell rubs him down at the ferry hut (ch4). |
| S3 | status | 0/2 (never) | checker, checker | Queen Liesl is nearly blind (ch5) but writes in her own careful hand and reads his letters (ch7). |
| T1 | timeline | 0/2 (never) | split, split | Aurel is 35 (ch4); four months later he turns thirty-eight (ch7). |
| T2 | timeline | 0/2 (never) | split, split | The fleet sank in the autumn storms (ch2) but 'the spring storm at the Kettle Rocks' (ch8). |
| T3 | timeline | 2/2 (always) | ✓, ✓ | Bram is 64 at Greywater (ch1) and 66 at the fall (ch3), but 'sixty-two now' years later (ch7). |

## Traps wrongly flagged

- D3: flagged in 1/2 runs: Aurel now works as a ferryman called Rell: a normal change after his fall, not a contradiction with being king.

---

# Details of the last run

# StoryForge evaluation — fallenking — 2026-10-13 11:19

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3-ultra-550b-a55b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 686s · AI requests per run: 82 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: reader 0.0, judge 0.0 · Reading passage size: 700 characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 1 |
| linking names | 149 |
| preparing search | 158 |
| safety-net check | 191 |
| checking for mistakes | 263 |
| story clock | 0 |
| double-checking | 71 |
| saving | 9 |

*Checking, story clock and safety net run one after another per chapter; reading and timing run together.*

## Time per chapter

| Chapter | Words | Facts | Reading (s) | Judging (s) |
|---|---|---|---|---|
| ch1 | 906 | 81 | saved | 43.5 |
| ch2 | 795 | 63 | saved | 56.4 |
| ch3 | 823 | 87 | saved | 77.2 |
| ch4 | 828 | 84 | saved | 60.8 |
| ch5 | 922 | 92 | saved | 60.6 |
| ch6 | 726 | 74 | saved | 48.8 |
| ch7 | 985 | 91 | saved | 109.6 |
| ch8 | 1,078 | 76 | saved | 208.6 |

**Judging:** 89 s per chapter on average (chapters after the first; the first has nothing earlier to compare). 7,063 words in 8 chapters.

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 22% | 18% | 0.20 | 2 / 11 | 7 | 0 | 100% |

| Type | Planted | Caught | Recall |
|---|---|---|---|
| attribute | 5 | 1 | 20% |
| status | 3 | 0 | 0% |
| timeline | 3 | 1 | 33% |

## Missed mistakes

- **A2** (ch7): Aurel's Greywater scar is on his left hand (ch1) but his right hand (ch7).
- **A3** (ch8): Thessaly's eyes are grey-green (ch1) but dark brown (ch8).
- **A4** (ch7): Mira is four years younger than Aurel (ch5) but his elder sister (ch7).
- **A5** (ch4): Sixty of the 940 ships came home (ch2) but every last one went down (ch4).
- **S1** (ch4): Aurel gave the signet ring to Corvin (ch3) but turns it on his own finger as a ferryman (ch4).
- **S2** (ch4): Ember had to be left behind in Vessa (ch3) but Pell rubs him down at the ferry hut (ch4).
- **S3** (ch7): Queen Liesl is nearly blind (ch5) but writes in her own careful hand and reads his letters (ch7).
- **T1** (ch7): Aurel is 35 (ch4); four months later he turns thirty-eight (ch7).
- **T2** (ch8): The fleet sank in the autumn storms (ch2) but 'the spring storm at the Kettle Rocks' (ch8).

## Why each mistake was missed

Causes: *not read* = the Reader didn't record the detail; *split* = the details were filed under different entries (a name-linking problem); *checker* = both were on the same entry but weren't flagged.

- **A2** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch1: [King Aurel] King Aurel | physical description | scar across the back of his left hand, a pale line where a Venn boarding hook had opened him to the bone
    - ch1: [King Aurel] King Aurel | gesture | held up his left hand with the cup in it
    - ch1: [cup] cup | location | in King Aurel's left hand
    - ch2: [Aurel] Aurel | has a scar on the back of his left hand | The scar on the back of his left hand ached in the cold the way it always did now
    - ch7: [Aurel] Aurel | physical_description | forehead healed into a second scar to match the one on his right hand
    - ch7: [Aurel] Aurel | injury | forehead scar
- **A3** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch1: [Venn fleet] Venn fleet | status | fleet lay broken on the shoals of Greywater bay
    - ch1: [King Aurel] King Aurel | relationship | married to Queen Thessaly
    - ch1: [Queen Thessaly] Queen Thessaly | relationship | married to King Aurel
    - ch1: [Queen Thessaly] Queen Thessaly | physical description | grey-green eyes
    - ch8: [Queen Thessaly] Thessaly | emotion | laughed then ran to Aurel
- **A4** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch1: [King Aurel] King Aurel | relationship | parent of Tam
    - ch1: [Tam] Tam | relationship | child of King Aurel
    - ch1: [Queen Thessaly] Queen Thessaly | relationship | parent of Tam
    - ch1: [Tam] Tam | relationship | child of Queen Thessaly
    - ch7: [Aurel] Aurel | relationship | sibling of elder sister of Aurel
    - ch7: [Mira] elder sister of Aurel | relationship | sibling of Aurel
    - ch7: [Aurel] Aurel | purpose | here with wheat, and with my elder sister who is a healer, and with a boy named Pell who keeps better accounts than my old treasurer
    - ch7: [Mira] elder sister of Aurel | role | healer
- **A5** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch1: [Bram Holloway] Bram Holloway | age | sixty-four years old
    - ch1: [Bram Holloway] Bram Holloway | role | swordmaster who had taught Aurel to hold a blade when he was seven
    - ch2: [Venn fleet] Venn fleet | ships lost | of nine hundred and forty ships, sixty came home
    - ch3: [Venn fleet] sixty battered hulls | remain | sixty battered hulls
    - ch4: [Admiral Saska Venn] Saska Venn | quote about watching ships sink | watching all nine hundred and forty ships go down, every last one of them
- **S1** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch1: [King Aurel's left hand] King Aurel's left hand | current location | on the high table of his own hall
    - ch1: [Duke Corvin] Duke Corvin | relationship | related to Aurel
    - ch1: [King Aurel] Aurel | relationship | related to Duke Corvin
    - ch1: [Duke Corvin] Duke Corvin | relation | Aurel's cousin
    - ch4: [King Oren] his father | relationship | parent of Aurel
    - ch4: [Aurel] Aurel | relationship | child of his father
    - ch4: [Aurel] Aurel | object_manipulation | turned his father's signet ring
- **S2** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch1: [King Aurel] King Aurel | physical description | scar across the back of his left hand, a pale line where a Venn boarding hook had opened him to the bone
    - ch1: [King Aurel] King Aurel | gesture | held up his left hand with the cup in it
    - ch1: [cup] cup | location | in King Aurel's left hand
    - ch1: [Duke Corvin] Duke Corvin | military_experience | commanded the left wing at Greywater and held it when the Venn galleys broke through
    - ch4: [Pell] Pell | action | rubbed down Ember behind the ferry hut
    - ch4: [Ember] Ember | location | behind the ferry hut
- **S3** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch5: [Queen Liesl] Queen Liesl | health | nearly blind
    - ch5: [Aurel] Aurel | relationship | parent of Oren
    - ch5: [King Oren] Oren | relationship | child of Aurel
    - ch7: [Queen Liesl] Queen Liesl | relationship | parent of Aurel
    - ch7: [Aurel] Aurel | relationship | child of Queen Liesl
    - ch7: [Bram Holloway] Bram Holloway | brought | a letter from Queen Liesl
    - ch7: [Queen Liesl] Queen Liesl | wrote_letter | she had read every one of her son's letters twice by candlelight
- **T1** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch4: [Rell] Rell | age | thirty-five
    - ch7: [Aurel] Aurel | age | thirty-eight
    - ch7: [Aurel] Aurel | location | hayloft above a mill
    - ch7: [Aurel] Aurel | age_at_event | turned thirty-eight that winter
    - ch7: [Winter] winter | time_reference | winter
- **T2** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch2: [King Aurel] King Aurel | decision | ordered the fleet to sail for the Venn isles
    - ch2: [autumn storms] autumn storms | time reference | second week of the autumn storms
    - ch8: [spring] spring equinox | time of council meeting | spring equinox
    - ch8: [people of the Dun valley] people from Dun valley | group composition | widows of the spring storm at the Kettle Rocks that took the fleet, on carts and on foot and on Saska Venn's two barges, which had sailed brazenly into the royal harbour under the flag of the Venn isles: millers and farmers, mothers and grandfathers, the old woman who had spat at Aurel's feet twice, and every village between Hollin and Dun Crossing
    - ch8: [great square of Vessa] great square of Vessa | description | they laid them down in the great square of Vessa in a grey heap taller than a man
    - ch8: [Pell] Pell | action | led an old grey stallion out of the royal stables into the spring dusk

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| false alarm | - | ch2 | Vessmark fleet | status | Chapter 1 establishes the Venn fleet was destroyed ('lay broken on the shoals') at Greywater Bay. Chapter 2 (set three years later) describes a fleet of 940 ships at anchor, implying the fleet exists and is operational. Unless the fleet was rebuilt in the interim, this is a status contradiction: a destroyed fleet cannot be intact three years later without explanation. |
| false alarm | - | ch2 | King Aurel | timeline | Chapter 1 describes the scar as 'still fresh' (recent injury), while Chapter 2 (set three years later) says it 'ached in the cold the way it always did now', implying a long-standing condition. The phrasing 'always did now' suggests the ache has been present for a significant time, which contradicts the 'fresh' description from three years earlier unless the scar became chronic immediately — but 'fresh' and long-term chronic pain are inconsistent without explanation. |
| false alarm | - | ch3 | Vessmark fleet | status | The new fact states all nine hundred ships are at the bottom of the sea, but the existing fact from chapter 2 explicitly states that of 940 ships, 60 came home (survived). This is a direct contradiction about the fate of the fleet. |
| false alarm | - | ch3 | Crowned salt-hawk | status | In chapter 3, Aurel gives away his signet ring (the crowned salt-hawk of the house of Oren) by pushing it across the table to his cousin Duke Corvin, who then puts it on his own finger. In chapter 2 (which takes place three years earlier), Aurel is still wearing and turning the same signet ring on his finger. Since chapter 3 occurs the day after chapter 2's events (per timing notes: chapter 2 is 'three years after the fire', chapter 3 'continues: the next day'), Aurel cannot both have given away the ring in chapter 3 and still be wearing it in chapter 2 unless chapter 3 is a flashback — but the timing notes indicate chapter 3 continues forward. This is a status contradiction: the ring's possession changes from Aurel to Corvin in chapter 3, yet chapter 2 (earlier in story time) shows Aurel still having it. |
| false alarm | - | ch3 | Crowned salt-hawk | status | Duke Corvin puts the signet ring on his own finger in chapter 3, and it's noted as 'a little too big for him. He wore it anyway.' In chapter 2 (three years earlier in story time), Aurel is still wearing the same signet ring on his finger. Since chapter 3 takes place the day after chapter 2's events, the ring cannot be on Corvin's finger in chapter 3 and still on Aurel's in chapter 2 unless chapter 3 is earlier — but the timing notes show chapter 3 continues forward. This is a status contradiction: the ring's location and ownership change in chapter 3, yet chapter 2 shows it still with Aurel at an earlier story time. |
| false alarm | - | ch3 | Crowned salt-hawk | status | The signet ring is described as being on Duke Corvin's finger in chapter 3 ('He wore it anyway'), but in chapter 2 (set three years earlier), the same ring is on Aurel's finger ('turned the signet ring on his finger'). Given the chapter timing — chapter 2 is 'three years after the fire', chapter 3 'continues: the next day' — chapter 3 occurs after chapter 2 in story chronology. The ring cannot be on Corvin in chapter 3 and still on Aurel in chapter 2 unless the ring was duplicated or returned, which is not indicated. This is a status contradiction: the ring's possession is mutually exclusive at these two points in the timeline. |
| false alarm | - | ch5 | Aurel | status | Chapter 2 states Aurel's 'legs would no longer hold him' (paralysis/weakness). Chapter 5 states 'It took Aurel and Pell three weeks on foot to reach the convent', implying Aurel walked for three weeks. This contradicts the established physical limitation unless recovery occurred off-screen. |
| correct | A1 | ch5 | Ember | attribute | Chapter 5 describes Ember as a 'black stallion' while chapter 1 explicitly calls him a 'grey stallion'. This is a direct attribute contradiction about the same horse (same name, same owner Aurel). Horse color doesn't change naturally without explanation (aging grey horses get lighter, not darker to black). |
| correct | T3 | ch7 | Bram Holloway | timeline | Bram Holloway is 66 in chapter 3 and the chapter timing notes say about 2.39103 years pass in between, so Bram Holloway should be about 68.391 in chapter 7, but the text says 62. |

Decoys wrongly flagged: none

## What the double-check removed

13 warnings dismissed: 12 were false alarms; real mistakes wrongly removed: A2.

- ch3 · Grain: Set aside: the story moving forward (something that existed earlier in story time has 'sold' later). Only the reverse would be a mistake.
- ch3 · Vessmark fleet: Set aside: the warning's own explanation says the two facts are consistent.
- ch3 · Tam: Set aside: ages are compared by the story clock, which does the arithmetic with the chapter timing; here one side isn't this character's age now (someone else's age, a past or future age, a relative age, or a length of time).
- ch4 · Pell: Double-check: This is normal character development over a two-year time skip (chapter 2: age 15, chapter 4: age 17). 'All elbows' describes a gangly adolescent; 'broad in the shoulders from hauling the ferry chain' describes a young adult who has done heavy physical labor for two years. The change is explained by
- ch4 · Tam: Set aside: ages are compared by the story clock, which does the arithmetic with the chapter timing; here one side isn't this character's age now (someone else's age, a past or future age, a relative age, or a length of time).
- ch5 · Aurel: Set aside: being alive only conflicts with a death, and the other fact doesn't mention one.
- ch5 · Aurel: Set aside: the story moving forward (something that existed earlier in story time has 'scarred' later). Only the reverse would be a mistake.
- ch5 · Queen Thessaly: Double-check: Chapter 4 says Prince Tam was moved 'away from his mother' (Queen Thessaly), indicating separation. Chapter 5 says 'the queen is well', which refers only to health, not location or proximity to her son. A queen can be 'well' while living apart from her child. No contradiction.
- ch6 · Aurel: Set aside: ages are compared by the story clock, which does the arithmetic with the chapter timing; here one side isn't this character's age now (someone else's age, a past or future age, a relative age, or a length of time).
- ch6 · Ember: Set aside: a young animal grown up (or seen young in a flashback), not a different animal.
- ch7 · Aurel: Double-check: The earlier quote (ch6) only states Aurel had no scar on his LEFT hand 14 years before the fall. The new quote (ch7) describes a forehead scar matching a scar on his RIGHT hand, which was established in ch4 as coming from Greywater (after the fall). These are different hands and different time perio
- ch8 · the roar from the lower city: Double-check: The two quotes describe different sounds heard at different times. Chapter 2 describes a roar Aurel had 'never heard before' (three years after the fire). Chapter 8 describes a different sound ('This was a different sound') that Aurel contrasts with 'the roar of a riot he had heard once'—which could
- ch8 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.

## Name linking

7 of 8 testable checks passed.

- same: Aurel, King Aurel, Rell → FAIL
- same: Corvin, Duke Corvin → pass
- same: Bram Holloway, Bram → pass
- same: Saska Venn, Saska → pass
- different: Aurel, Corvin → pass
- different: Mira, Thessaly → pass
- different: Oren, Aurel → pass
- different: Liesl, Mira → pass

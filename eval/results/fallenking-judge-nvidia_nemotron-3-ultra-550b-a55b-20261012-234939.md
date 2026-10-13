# StoryForge evaluation — fallenking — 2026-10-12 23:58

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3-ultra-550b-a55b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 545s · AI requests per run: 76 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: reader 0.0, judge 0.0 · Reading passage size: 700 characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 0 |
| linking names | 141 |
| preparing search | 39 |
| safety-net check | 160 |
| checking for mistakes | 251 |
| story clock | 0 |
| double-checking | 96 |
| saving | 6 |

*Checking, story clock and safety net run one after another per chapter; reading and timing run together.*

## Time per chapter

| Chapter | Words | Facts | Reading (s) | Judging (s) |
|---|---|---|---|---|
| ch1 | 906 | 81 | saved | 28.2 |
| ch2 | 795 | 63 | saved | 45.1 |
| ch3 | 823 | 87 | saved | 49.4 |
| ch4 | 828 | 84 | saved | 52.5 |
| ch5 | 922 | 92 | saved | 133.6 |
| ch6 | 726 | 74 | saved | 58.3 |
| ch7 | 985 | 91 | saved | 90.3 |
| ch8 | 1,078 | 76 | saved | 87.2 |

**Judging:** 74 s per chapter on average (chapters after the first; the first has nothing earlier to compare). 7,063 words in 8 chapters.

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 22% | 36% | 0.28 | 4 / 11 | 14 | 0 | 100% |

| Type | Planted | Caught | Recall |
|---|---|---|---|
| attribute | 5 | 2 | 40% |
| status | 3 | 1 | 33% |
| timeline | 3 | 1 | 33% |

## Missed mistakes

- **A3** (ch8): Thessaly's eyes are grey-green (ch1) but dark brown (ch8).
- **A4** (ch7): Mira is four years younger than Aurel (ch5) but his elder sister (ch7).
- **A5** (ch4): Sixty of the 940 ships came home (ch2) but every last one went down (ch4).
- **S2** (ch4): Ember had to be left behind in Vessa (ch3) but Pell rubs him down at the ferry hut (ch4).
- **S3** (ch7): Queen Liesl is nearly blind (ch5) but writes in her own careful hand and reads his letters (ch7).
- **T1** (ch7): Aurel is 35 (ch4); four months later he turns thirty-eight (ch7).
- **T2** (ch8): The fleet sank in the autumn storms (ch2) but 'the spring storm at the Kettle Rocks' (ch8).

## Why each mistake was missed

Causes: *not read* = the Reader didn't record the detail; *split* = the details were filed under different entries (a name-linking problem); *checker* = both were on the same entry but weren't flagged.

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
    - ch7: [King Aurel] Aurel | relationship | sibling of elder sister of Aurel
    - ch7: [Mira] elder sister of Aurel | relationship | sibling of Aurel
    - ch7: [King Aurel] Aurel | purpose | here with wheat, and with my elder sister who is a healer, and with a boy named Pell who keeps better accounts than my old treasurer
    - ch7: [Mira] elder sister of Aurel | role | healer
- **A5** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch1: [Bram Holloway] Bram Holloway | age | sixty-four years old
    - ch1: [Bram Holloway] Bram Holloway | role | swordmaster who had taught Aurel to hold a blade when he was seven
    - ch2: [Venn fleet] Venn fleet | ships lost | of nine hundred and forty ships, sixty came home
    - ch3: [Vessmark fleet] sixty battered hulls | remain | sixty battered hulls
    - ch4: [Admiral Saska Venn] Saska Venn | quote about watching ships sink | watching all nine hundred and forty ships go down, every last one of them
- **S2** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch1: [King Aurel] King Aurel | physical description | scar across the back of his left hand, a pale line where a Venn boarding hook had opened him to the bone
    - ch1: [King Aurel] King Aurel | gesture | held up his left hand with the cup in it
    - ch1: [cup] cup | location | in King Aurel's left hand
    - ch1: [Duke Corvin] Duke Corvin | military_experience | commanded the left wing at Greywater and held it when the Venn galleys broke through
    - ch4: [Pell] Pell | action | rubbed down Ember behind the ferry hut
    - ch4: [Ember] Ember | location | behind the ferry hut
- **S3** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch5: [Queen Liesl] Queen Liesl | health | nearly blind
    - ch5: [King Aurel] Aurel | relationship | parent of Oren
    - ch5: [King Oren] Oren | relationship | child of Aurel
    - ch7: [Queen Liesl] Queen Liesl | relationship | parent of Aurel
    - ch7: [King Aurel] Aurel | relationship | child of Queen Liesl
    - ch7: [Bram Holloway] Bram Holloway | brought | a letter from Queen Liesl
    - ch7: [Queen Liesl] Queen Liesl | wrote_letter | she had read every one of her son's letters twice by candlelight
- **T1** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch4: [Rell] Rell | age | thirty-five
    - ch7: [King Aurel] Aurel | age | thirty-eight
    - ch7: [King Aurel] Aurel | location | hayloft above a mill
    - ch7: [King Aurel] Aurel | age_at_event | turned thirty-eight that winter
    - ch7: [winter] winter | time_reference | winter
- **T2** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch2: [King Aurel] King Aurel | decision | ordered the fleet to sail for the Venn isles
    - ch2: [autumn storms] autumn storms | time reference | second week of the autumn storms
    - ch8: [spring] spring equinox | time of council meeting | spring equinox
    - ch8: [Dun valley] people from Dun valley | group composition | widows of the spring storm at the Kettle Rocks that took the fleet, on carts and on foot and on Saska Venn's two barges, which had sailed brazenly into the royal harbour under the flag of the Venn isles: millers and farmers, mothers and grandfathers, the old woman who had spat at Aurel's feet twice, and every village between Hollin and Dun Crossing
    - ch8: [great square of Vessa] great square of Vessa | description | they laid them down in the great square of Vessa in a grey heap taller than a man
    - ch8: [Pell] Pell | action | led an old grey stallion out of the royal stables into the spring dusk

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| correct | S1 | ch4 | King Aurel | status | In chapter 3, Aurel removes his father's signet ring and gives it to Corvin. In chapter 4 (two years later), he is still wearing and turning the same ring on his finger, with no explanation of how he got it back. |
| false alarm | - | ch4 | Tam | timeline | Chapter 1 (three days after Greywater) states Tam is four years old. Chapter 4 (two years after chapter 3, which is three years after the fire) states Tam is eight. The total elapsed time from chapter 1 to chapter 4 is roughly five years (three days + three years + one day + two years), so Tam should be about nine, not eight. An eight-year-old Tam in chapter 4 contradicts the established timeline. |
| false alarm | - | ch5 | King Aurel | timeline | In chapter 1 (three days after Greywater), King Aurel is 31 and his son Tam is 4. Chapter 5 is set three weeks after the convent gate, which occurs after chapter 4's two-year time skip from chapter 3. Chapter 3 shows Tam as 6. Even with maximum plausible time passage (~2 years 3 weeks since chapter 1), Tam would be at most ~6.5, not 8. Aurel's statement that his son is 8 contradicts the established timeline. |
| false alarm | - | ch5 | King Aurel | attribute | Chapter 1 establishes Aurel is married to Queen Thessaly, mother of his son Tam. Chapter 5 has Aurel refer to 'my son is eight years old and being raised by the man who took my crown' and 'We gave you a father who never lost... She patted his head' addressing someone as 'Mother' (Liesl). This suggests a different mother for his son, contradicting Thessaly as queen and mother of Tam unless Liesl is a different role (wet nurse/governess), but 'my son... being raised by the man who took my crown' implies Liesl is the biological mother. |
| false alarm | - | ch5 | King Aurel | status | Chapter 1 shows Aurel as reigning king at the height of his power. Chapter 5 has him say 'I was the king who never lost. And I threw it into the sea, all of it, and now I pole a ferry.' This indicates he abdicated/lost the crown and is now a ferryman. While a status change is possible, the phrasing 'threw it into the sea' suggests voluntary abdication, yet chapter 3 shows him deciding to stay in the castle ('Then I'll stay') and chapter 4 shows him still involved in royal affairs (signet ring, broadsheets). No prior chapter explains this transition to ferryman. |
| false alarm | - | ch5 | Duke Corvin | attribute | Chapter 1 establishes Corvin is two years younger than Aurel (who is 31 in chapter 1, so Corvin is 29). Chapter 5 states 'He was a good letter writer at seventeen' referring to Corvin. This could mean Corvin was 17 at some past time, but the present tense context ('He has always been a good letter writer, your cousin') and the fact that Liesl says this while discussing current correspondence suggests she might think Corvin is currently 17, which contradicts him being ~31-33 (Aurel's age in chapter 2 is 33, so Corvin would be 31). |
| correct | A1 | ch5 | Ember | attribute | Chapter 5 describes Ember as a 'black stallion' while chapter 1 explicitly calls him a 'grey stallion'. This is a direct attribute contradiction about the same horse (same name, same owner Aurel). Horse coat color doesn't change from grey to black without explanation. |
| false alarm | - | ch5 | Tam | timeline | Chapter 5 states 'It took him six years to earn back what he had lost in an afternoon.' Chapter 2 shows Tam is 'six years old now' and the time skips indicate: chapter 1 is 3 days after Greywater, chapter 2 is 3 years after the fire, chapter 4 is 2 years later (total ~5 years), chapter 5 is 3 weeks after chapter 4 (~5 years + 3 weeks). Six years cannot have passed when only ~5 years have elapsed in the timeline. |
| false alarm | - | ch6 | Duke Corvin | timeline | New fact states Corvin was 20 when he swore on Vessa's battlements. Existing fact states Corvin is 2 years younger than Aurel. If Corvin was 17 in the flashback (14 years before fall) and 20 when he swore (presumably a few years later), then Aurel would be 19-22 at that time. But chapter 1 (3 days after Greywater) shows Aurel as king with a 4-year-old son, implying Aurel is at least in his 20s. The timeline compression between Corvin's ages (17 to 20) and Aurel's implied age creates a likely contradiction. |
| false alarm | - | ch6 | Ember | attribute | Pair 2 compares Aurel's new horse in chapter 6 (a grey colt from the royal stud, just given to him) with Ember, described in chapter 1 as Aurel's grey stallion. Chapter 6 is a flashback set 14 years before the fall, while chapter 1 occurs three days after Greywater (which is after the fall). A colt is a young male horse, typically under four years old, while a stallion is an adult male. Given the 14+ year gap, the colt could mature into a stallion, but the text says Aurel had 'just been given' the colt in the flashback, implying this is the acquisition of the horse. If Ember is the same horse, it would be a colt at acquisition and a stallion years later — which is plausible. However, the phrasing 'Aurel's grey stallion Ember' in chapter 1 suggests Ember is already an established, named stallion at that point, while the flashback presents the colt as a new gift without a name. The contradiction arises if the colt is meant to be Ember but is called a colt (young) vs stallion (adult) at different times without a |
| correct | A2 | ch7 | King Aurel | attribute | Chapter 1 establishes a scar on the back of the LEFT hand from a Venn boarding hook. Chapter 7 describes a forehead scar matching one on the RIGHT hand. This contradicts the established location (left vs right hand) and introduces a new forehead scar without explanation. The hand scar's location has changed from left to right. |
| false alarm | - | ch7 | King Oren | attribute | New fact 0 states King Oren is the parent of Aurel, while existing fact 11 states Oren is the child of Aurel. These are mutually exclusive relationships. Given the overwhelming evidence from other facts (existing facts 1, 2, 5, 7, 10, 20, 23) that King Oren is Aurel's father, existing fact 11 appears to be an error in the original data extraction or recording. |
| false alarm | - | ch7 | King Aurel | timeline | King Aurel is 33 in chapter 2 and the chapter timing notes say about 2.39103 years pass in between, so King Aurel should be about 35.391 in chapter 7, but the text says 38. |
| correct | T3 | ch7 | Bram Holloway | timeline | Bram Holloway is 66 in chapter 3 and the chapter timing notes say about 2.39103 years pass in between, so Bram Holloway should be about 68.391 in chapter 7, but the text says 62. |
| false alarm | - | ch7 | grain | attribute | Chapter 3 states 'The grain reserve, sold' (past tense, completed action), while chapter 7 says 'The regent has stopped buying Venn grain' and 'He's selling it off a sack at a time', implying the grain reserve still exists and is being sold gradually. If the reserve was already sold in chapter 3, it cannot be sold again in chapter 7. The regent's actions in chapter 7 contradict the established fact that the grain reserve was already sold. |
| false alarm | - | ch8 | Duke Corvin | timeline | In chapter 6 (flashback: fourteen years before the fall), Corvin is explicitly stated to be seventeen years old. In chapter 8 (present day), Corvin is still referred to as Aurel's cousin with no indication of aging, but the timeline spans at least 14 years plus additional time skips (3 days, 3 years, 2 years, 3 weeks, 4 months). Corvin should be in his 30s, not still seventeen. The new fact doesn't state his age, but the relationship fact in context implies no aging has occurred, contradicting the established timeline. |
| false alarm | - | ch8 | Tam | attribute | New fact describes Tam as a growing child ('all knees and elbows') while existing fact from chapter 7 states Tam is 25 years old. Chapter 8 continues from chapter 7 (next day), so Tam cannot be both a child and 25 simultaneously. |
| false alarm | D4 | ch8 | Ember | attribute | New fact describes Ember as a grey stallion with white around the muzzle (consistent with aging grey), while existing fact from chapter 5 explicitly calls Ember 'the black stallion'. A horse cannot be both grey and black simultaneously. |

Decoys wrongly flagged: D4

**Check by hand:** T1. A warning counted as a false alarm has the right chapter, entity and new detail for these items; only its earlier side is worded differently from the answer key. If it is right, the item was caught.

## What the double-check removed

14 warnings dismissed: 14 were false alarms; real mistakes wrongly removed: none.

- ch2 · King Aurel: Double-check: The quotes are about different subjects: Chapter 1 describes King Aurel's plan to build a Vessmark fleet of 1,000 ships over two summers, while Chapter 2 describes the actual Vessmark fleet of 940 ships that was built and sailed. The 60-ship difference is a plan vs. reality discrepancy, not a contin
- ch2 · Venn fleet: Double-check: The quotes describe different fleets at different times and places. Chapter 1 states the Venn fleet was destroyed at Greywater Bay (three days before Chapter 1). Chapter 2 describes a Venn fleet of 940 ships caught in a storm at Kettle Rocks three years later. A nation can build a new fleet in three
- ch2 · Vessmark fleet: Double-check: The quotes describe different fleets. Chapter 1 says the Venn fleet was broken at Greywater Bay. Chapter 2 describes a Vessmark fleet of 940 ships (Aurel's fleet, not the Venn fleet) riding at anchor. There is no contradiction because they are different fleets belonging to different nations.
- ch3 · King Aurel: Double-check: The Chapter 3 quote does not mention a scar or a scarred hand at all; it is a line of dialogue about identity and return. The warning misreads the quote. Even if 'scarred hand' were implied elsewhere, a general reference does not contradict the specific left-hand detail from Chapter 1.
- ch3 · grain: Set aside: the story moving forward (something that existed earlier in story time has 'sold' later). Only the reverse would be a mistake.
- ch3 · Vessmark fleet: Set aside: the warning's own explanation says the two facts are consistent.
- ch3 · crowned salt-hawk: Set aside: the warning's own explanation says the two facts are consistent.
- ch5 · King Aurel: Double-check: Not a contradiction. Chapter 1 states Aurel was taught to hold a blade at age 7 by his father Oren. Chapter 5 says 'When you were two years old, Oren marched on the salt coast...' These are different events at different ages (a military campaign when Aurel was 2 vs. his own training at 7). The phras
- ch5 · Duke Corvin: Double-check: Not a contradiction. Chapter 3 emphasizes Corvin wearing Aurel's signet ring. Chapter 5 says 'That one Corvin has, I expect, along with the ring' referring to a court sword. This means Corvin has both the sword and the ring; the ring is mentioned as an additional item, not replaced. The phrasing dif
- ch6 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch7 · Dun valley: Double-check: Chapter 4 states the Dun valley people 'are eating bark again' at that time. Chapter 7, set four months later, says they 'had stopped eating bark.' This is a normal progression of time — a situation changing over months is expected storytelling, not a contradiction. The new chapter does not reverse 
- ch8 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch8 · Tam: Double-check: Chapter 7 says Corvin *told* Tam that Aurel is dead. Chapter 8 shows Aurel alive and saying 'I told them you weren't dead.' This is not a contradiction: Corvin lied or was mistaken, and Aurel is now correcting that falsehood. The narrative state allows both — a character can be falsely reported dead
- ch8 · riot in the lower city: Double-check: The two quotes describe different sounds at different times. Chapter 2: a 'low, steady roar, like the sea in a cave' from a riot, which Aurel had never heard before. Chapter 8: 'thousands of feet, walking, and under it, very faintly, singing,' explicitly contrasted with 'the roar of a riot' that Aur

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

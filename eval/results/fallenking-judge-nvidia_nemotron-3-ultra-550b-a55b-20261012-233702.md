# StoryForge evaluation — fallenking — 2026-10-12 23:49

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3-ultra-550b-a55b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 721s · AI requests per run: 82 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: reader 0.0, judge 0.0 · Reading passage size: 700 characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 2 |
| linking names | 197 |
| preparing search | 52 |
| safety-net check | 150 |
| checking for mistakes | 317 |
| story clock | 0 |
| double-checking | 148 |
| saving | 4 |

*Checking, story clock and safety net run one after another per chapter; reading and timing run together.*

## Time per chapter

| Chapter | Words | Facts | Reading (s) | Judging (s) |
|---|---|---|---|---|
| ch1 | 906 | 81 | saved | 23.0 |
| ch2 | 795 | 63 | saved | 94.0 |
| ch3 | 823 | 87 | saved | 105.7 |
| ch4 | 828 | 84 | saved | 96.7 |
| ch5 | 922 | 92 | saved | 121.7 |
| ch6 | 726 | 74 | saved | 87.1 |
| ch7 | 985 | 91 | saved | 80.6 |
| ch8 | 1,078 | 76 | saved | 112.1 |

**Judging:** 100 s per chapter on average (chapters after the first; the first has nothing earlier to compare). 7,063 words in 8 chapters.

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 15% | 27% | 0.19 | 3 / 11 | 17 | 0 | 100% |

| Type | Planted | Caught | Recall |
|---|---|---|---|
| attribute | 5 | 2 | 40% |
| status | 3 | 0 | 0% |
| timeline | 3 | 1 | 33% |

## Missed mistakes

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
    - ch3: [Venn fleet] sixty battered hulls | remain | sixty battered hulls
    - ch4: [Admiral Saska Venn] Saska Venn | quote about watching ships sink | watching all nine hundred and forty ships go down, every last one of them
- **S1** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch1: [King Aurel's left hand] King Aurel's left hand | current location | on the high table of his own hall
    - ch1: [Duke Corvin] Duke Corvin | relationship | related to Aurel
    - ch1: [King Aurel] Aurel | relationship | related to Duke Corvin
    - ch1: [Duke Corvin] Duke Corvin | relation | Aurel's cousin
    - ch4: [King Oren] his father | relationship | parent of Aurel
    - ch4: [King Aurel] Aurel | relationship | child of his father
    - ch4: [King Aurel] Aurel | object_manipulation | turned his father's signet ring
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
| false alarm | - | ch2 | Vessmark fleet | status | Chapter 1 (set three days after Greywater) establishes the Venn fleet is destroyed ('lay broken on the shoals'). Chapter 2 (set three years after the fire) describes a fleet of 940 ships riding at anchor, which directly contradicts the established destruction of the fleet. The fleet cannot be both destroyed and intact three years later without explanation of rebuilding. |
| false alarm | - | ch3 | King Aurel | status | New fact 22 states 'Aurel had won a war' (past tense, completed), while existing fact 13 (Chapter 1) shows Aurel declaring 'I will finish it... end the war for a hundred years' — indicating the war was ongoing and not yet won. Chapter 2 (fact 25) says he 'ordered the fleet to sail for the Venn isles', and fact 44 notes 'Nine hundred and forty ships... not quite the thousand Aurel had promised', implying the campaign was underway but not concluded. The new chapter (3) is the next day after Chapter 2, so the war cannot have been won already. Claiming he 'had won a war' contradicts the established timeline where the war effort is still in progress. |
| false alarm | - | ch3 | crowned salt-hawk | status | In chapter 3, Aurel takes off his father's signet ring and pushes it across the table to Duke Corvin, who then slides it onto his own finger (pairs 7 and 8). This means Aurel no longer has the ring on his finger. However, the earlier fact from chapter 2 states the signet ring is 'on his finger' (Aurel's). Since chapter 3 takes place the next day after chapter 2, the ring cannot be on Aurel's finger in chapter 2 and also be transferred to Corvin in chapter 3 unless the chapter 2 observation occurs before the transfer. But the chapter 2 quote describes Aurel sitting and turning the ring on his finger as a current state, and chapter 3 shows the transfer happening afterward. This is a status contradiction: the ring is simultaneously on Aurel's finger (chapter 2) and transferred to Corvin (chapter 3) with no explanation of it being returned or duplicated. |
| false alarm | - | ch3 | crowned salt-hawk | status | Duke Corvin slides the signet ring onto his own finger in chapter 3, and it's noted as 'a little too big for him. He wore it anyway.' This directly conflicts with the chapter 2 fact that the signet ring is 'on his finger' (Aurel's). The ring cannot be on both Aurel's and Corvin's fingers at the same time. Since chapter 3 occurs the day after chapter 2, and the transfer happens in chapter 3, the chapter 2 state (ring on Aurel) should precede the transfer. But the chapter 2 description presents it as a current, ongoing state, not a past one. This is a status contradiction: an object used by one character in the new chapter while established as being with another in the immediate prior chapter. |
| false alarm | - | ch3 | crowned salt-hawk | status | The signet ring is described in chapter 3 as being worn by Duke Corvin ('It was a little too big for him. He wore it anyway.'), but in chapter 2 it is explicitly stated to be 'on his finger' — Aurel's finger. The ring cannot be on both men's fingers simultaneously. Chapter 3 occurs the next day after chapter 2, and the transfer is depicted in chapter 3 (pair 5), so the chapter 2 state should be before the transfer. However, the chapter 2 quote presents the ring on Aurel's finger as a current observation, not a memory. This creates a status contradiction: the ring is in two places at once across consecutive chapters with no explanation. |
| false alarm | - | ch4 | King Aurel | attribute | The new fact states the hook injury occurred while Aurel was trying to pull someone off the rail of the Salt Hawk at Greywater, implying the hook was *his* and he was the one pulling. The existing fact from Chapter 1 describes the scar as from a 'Venn boarding hook' that 'opened him to the bone' — suggesting he was the victim of an enemy boarding action, not the one wielding the hook. The accounts differ on who was hooking whom and the context of the injury. |
| false alarm | - | ch4 | Tam | timeline | Chapter 1 (three days after Greywater) states Tam is four years old. Chapter 4 (two years after chapter 3, which is three years after the fire) states Tam is eight. The total elapsed time from chapter 1 to chapter 4 is roughly five years (three days + three years + one day + two years), so Tam aging from four to eight is a four-year jump — one year more than the plausible passage of time. |
| false alarm | - | ch5 | King Aurel | attribute | New fact 16 states Aurel's son is eight years old, while existing fact 1 states Aurel himself is thirty-one years old in chapter 1. Given the timeline (chapter 1 to chapter 5 spans roughly 5 years and 3 weeks), Aurel would be ~36, making it impossible for him to have an 8-year-old son if he was 31 in chapter 1 (son would be at most ~5). This contradicts the established age progression. |
| false alarm | - | ch5 | King Aurel | attribute | New fact 13 refers to 'my son is eight years old and being raised by the man who took my crown' and 'child of Liesl', implying Liesl is the mother. Existing fact 4 establishes Queen Thessaly as Aurel's wife and mother of Tam in chapter 1. No explanation is given for a change in queen/mother of the child. |
| false alarm | - | ch5 | King Aurel | status | New fact 15 states Aurel now poles a ferry (implying he abdicated/lost kingship), while existing fact 12 (chapter 1) and fact 24 (chapter 2) show him as active King. Chapter 3 shows him giving up the signet ring to Corvin, but chapter 4 shows him as a ferryman. The transition from King to ferryman between chapters 3 and 5 (2 years + 3 weeks) is a major status change without clear in-story explanation in the provided facts. |
| false alarm | - | ch5 | King Aurel | attribute | New fact 21 states Aurel was two years old when Oren marched on the salt coast. Existing fact 10 states Aurel was taught to hold a blade at seven by his father Oren. If Oren marched when Aurel was two, and was defeated (existing facts 4-6, entity 2), it's unlikely he taught Aurel at seven unless he recovered. But existing fact 5 (entity 2) says Oren 'never fully shook' the fever. This creates a timeline contradiction about Oren's capacity to teach at seven after being broken at Aurel's age two. |
| correct | A1 | ch5 | Ember | attribute | Ember is described as a 'black stallion' in chapter 5 but as a 'grey stallion' in chapter 1. This is a direct attribute contradiction (coat color) with no in-story explanation for the change. |
| false alarm | - | ch5 | Tam | timeline | Chapter 5 states 'It took him six years to earn back what he had lost in an afternoon.' Chapter 2 (set three years after the fire) mentions Tam is 'six years old now.' If the loss occurred at the fire (three years before chapter 2), then only three years have passed by chapter 2, not six. Chapter 5 is only three weeks after chapter 4 (which is two years after chapter 3), making the total timeline approximately 5 years and 3 weeks since the fire — still not six years. The six-year claim contradicts the established timeline. |
| false alarm | - | ch6 | King Aurel | timeline | New fact states Aurel was crowned at age nineteen, while existing fact from chapter 1 states King Aurel is thirty-one years old. Given the chapter timing (chapter 6 is a flashback 14 years before the fall, chapter 1 is 3 days after Greywater), if the fall is the present timeline, then 14 years have passed since coronation. 19 + 14 = 33, but chapter 1 says 31. This is a 2-year discrepancy that exceeds plausible rounding. |
| false alarm | - | ch6 | King Aurel | status | New fact states Aurel had never been in a battle at the time of his coronation, while existing fact from chapter 3 states Aurel had won a war. Since chapter 3 is after the fall (continues next day after chapter 2), and the war was presumably won before or during the fall, this could be consistent if the war was won after coronation. However, 'won a war' suggests direct participation, while 'never been in a battle' suggests no combat experience. This may be a contradiction if the war required battle participation. |
| correct | A2 | ch7 | King Aurel | attribute | Chapter 1 and Chapter 4 establish Aurel's scar is on the back of his LEFT hand from a Venn boarding hook at Greywater. Chapter 7 says he has a scar on his RIGHT hand and a matching one on his forehead. This contradicts the established location (left vs right hand) and origin of the scar. |
| false alarm | - | ch7 | King Aurel | timeline | King Aurel is 33 in chapter 2 and the chapter timing notes say about 2.39103 years pass in between, so King Aurel should be about 35.391 in chapter 7, but the text says 38. |
| correct | T3 | ch7 | Bram Holloway | timeline | Bram Holloway is 66 in chapter 3 and the chapter timing notes say about 2.39103 years pass in between, so Bram Holloway should be about 68.391 in chapter 7, but the text says 62. |
| false alarm | - | ch8 | Tam | attribute | New fact describes Tam as a growing child ('all knees and elbows') while existing fact from chapter 7 states Tam is 25 years old. Chapter 8 continues from chapter 7 (next day), so Tam cannot be both a young child and 25 simultaneously. |
| false alarm | - | ch8 | the roar from the lower city | attribute | Both facts describe the sound Aurel hears from the lower city through a window. In chapter 2 (three years after the fire), the sound is a 'low, steady roar, like the sea in a cave' that Aurel had never heard before. In chapter 8 (next day after chapter 7), the sound is 'thousands of feet, walking, and under it, very faintly, singing' and Aurel explicitly contrasts it with 'the roar of a riot' which he had heard once and would never forget. The two descriptions of the same auditory event are mutually exclusive: a continuous low roar vs. rhythmic footsteps with singing. Since chapter 8 comes later in reading order but may refer to the same past event, and Aurel's memory of the 'roar' contradicts the earlier 'never heard before' claim, this is an attribute contradiction about the nature of the sound. |

Decoys wrongly flagged: none

**Check by hand:** T1. A warning counted as a false alarm has the right chapter, entity and new detail for these items; only its earlier side is worded differently from the answer key. If it is right, the item was caught.

## What the double-check removed

18 warnings dismissed: 18 were false alarms; real mistakes wrongly removed: none.

- ch2 · King Aurel: Double-check: The timeline is consistent. Chapter 1 (three days after Greywater) records King Aurel's plan to build a thousand ships over two summers and then sail. Chapter 2 (three years after the fire) shows the fleet sailing in autumn storms, numbering 940 ships — 'not quite the thousand Aurel had promised.' T
- ch3 · King Aurel: Double-check: The new quote does not mention a scar or a scarred hand at all. The warning misreads the quote; there is no new fact about Aurel's hand to contradict the specific detail from chapter 1.
- ch3 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch3 · grain: Set aside: the story moving forward (something that existed earlier in story time has 'sold' later). Only the reverse would be a mistake.
- ch3 · Vessmark fleet: Set aside: the warning's own explanation says the two facts are consistent.
- ch4 · King Aurel: Double-check: The warning itself acknowledges that Chapter 4 does not state Aurel's age, only his emotional state. Since the new quote contains no age value, there is no direct attribute contradiction to flag.
- ch5 · King Aurel: Double-check: Pell's sudden appearance as a named companion for a three-week journey in chapter 5, unmentioned in chapters 1-4, is a continuity gap but not a contradiction. The warning acknowledges this: 'not a direct contradiction.' New characters can be introduced; this doesn't violate the 'both quotes cannot b
- ch5 · Pell: Double-check: Chapter 4: Pell is 17. Chapter 5 is three weeks later; Pell is still ~17. The burn from a cooking fire in a convent kitchen doesn't conflict with being a ferry worker (hauling chains) — people can have burns in domestic settings. No explicit age or role contradiction exists in the quotes.
- ch6 · King Oren: Double-check: No contradiction. Chapter 5 says Oren came home with a fever he never fully shook (lingering illness). Chapter 6 says he died of that same fever. A lingering fever that eventually kills is consistent; the quotes describe the same illness at different stages.
- ch6 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch6 · Ember: Double-check: Normal passage of time. Chapter 6 (14 years before the fall) shows Aurel receiving a young, untrained colt. Chapter 1 (years after the fall) refers to a mature, named stallion Ember. A colt growing into a stallion, being trained, and receiving a name over 14+ years is expected character/horse develo
- ch7 · King Aurel: Set aside: the story moving forward (something that existed earlier in story time has 'sank' later). Only the reverse would be a mistake.
- ch7 · King Aurel: Set aside: the story moving forward (something that existed earlier in story time has 'sold' later). Only the reverse would be a mistake.
- ch7 · King Oren: Double-check: The Chapter 5 quote ('Her blind eyes looked somewhere past him') does not state or imply that Aurel is Oren's parent; it only describes a blind woman looking past someone. The claimed 'existing fact 21' is not supported by the provided quote. The Chapter 7 quote ('Your father's army...') clearly ind
- ch7 · Quiet: Double-check: The two quotes refer to completely different entities that happen to share the name 'Quiet': Chapter 5 describes a female character (Mira) nicknamed 'the quiet one,' while Chapter 7 describes a sword named 'Quiet' that a male character buckles on. This is not a continuity error—it's two distinct thi
- ch7 · Dun valley: Double-check: Chapter 4 states the people 'are eating bark again' (present tense, at that time). Chapter 7, set four months later, states they 'had stopped eating bark' (past perfect, completed before that later time). This is a normal chronological progression: they were eating bark at the earlier point, and by 
- ch8 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch8 · Ember: Double-check: A black horse developing white hairs around the muzzle with age is a normal, real-world occurrence (greying). The chapter 8 quote explicitly says Ember 'had grown white around the muzzle since Aurel had last seen him, and he was too old now,' which is consistent with an aging black stallion. No cont

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

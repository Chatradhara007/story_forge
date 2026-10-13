# StoryForge evaluation — fallenking — 2026-10-13 13:27

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3-ultra-550b-a55b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 1572s · AI requests per run: 92 accepted, 16 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: reader 0.0, judge 0.0 · Reading passage size: 700 characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 0 |
| linking names | 323 |
| preparing search | 278 |
| safety-net check | 726 |
| checking for mistakes | 699 |
| story clock | 0 |
| double-checking | 147 |
| saving | 4 |

*Checking, story clock and safety net run one after another per chapter; reading and timing run together.*

## Time per chapter

| Chapter | Words | Facts | Reading (s) | Judging (s) |
|---|---|---|---|---|
| ch1 | 906 | 81 | saved | 80.5 |
| ch2 | 795 | 63 | saved | 209.2 |
| ch3 | 823 | 87 | saved | 259.4 |
| ch4 | 828 | 84 | saved | 194.7 |
| ch5 | 922 | 92 | saved | 180.6 |
| ch6 | 726 | 74 | saved | 152.1 |
| ch7 | 985 | 91 | saved | 266.5 |
| ch8 | 1,078 | 76 | saved | 228.8 |

**Judging:** 213 s per chapter on average (chapters after the first; the first has nothing earlier to compare). 7,063 words in 8 chapters.

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 38% | 27% | 0.32 | 3 / 11 | 5 | 0 | 100% |

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
    - ch4: [King Aurel's father] his father | relationship | parent of Aurel
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
    - ch7: [winter] winter | time_reference | winter
- **T2** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch2: [King Aurel] King Aurel | decision | ordered the fleet to sail for the Venn isles
    - ch2: [autumn storms] autumn storms | time reference | second week of the autumn storms
    - ch8: [spring] spring equinox | time of council meeting | spring equinox
    - ch8: [Dun valley] people from Dun valley | group composition | widows of the spring storm at the Kettle Rocks that took the fleet, on carts and on foot and on Saska Venn's two barges, which had sailed brazenly into the royal harbour under the flag of the Venn isles: millers and farmers, mothers and grandfathers, the old woman who had spat at Aurel's feet twice, and every village between Hollin and Dun Crossing
    - ch8: [great square of Vessa] great square of Vessa | description | they laid them down in the great square of Vessa in a grey heap taller than a man
    - ch8: [Pell] Pell | action | led an old grey stallion out of the royal stables into the spring dusk

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| false alarm | - | ch3 | Vessmark fleet | status | New fact states all nine hundred ships are at the bottom of the sea, but existing fact from chapter 2 states that of 940 ships, 60 came home (survived). These cannot both be true simultaneously - either 60 ships survived or all were lost. |
| false alarm | - | ch5 | Queen Thessaly | status | Chapter 5 states 'the boy is well and the queen is well' (referring to Prince Tam and Queen Thessaly). However, Chapter 4 established that Tam was moved out of the castle away from his mother by Corvin, suggesting separation and potential danger. The new fact implies both are 'well' and presumably together or at least safe, which conflicts with the established forced separation without any explanation of reconciliation or resolution in the intervening three weeks. |
| correct | A1 | ch5 | Ember | attribute | Chapter 5 describes Ember as a 'black stallion' while Chapter 1 explicitly calls him a 'grey stallion'. This is a direct attribute contradiction about the same horse (same name, same owner Aurel) with no in-story explanation for a color change. |
| correct | A2 | ch7 | Aurel | attribute | Chapter 7 states Aurel has a scar on his right hand ('match the one on his right hand') and a new forehead scar matching it. Chapter 2 states the scar is on the back of his left hand. Chapter 4 (existing fact 25) says the hook went in while trying to pull someone off the rail of the Salt Hawk at Greywater, and 'you cut the rope with your other hand' — implying the hook injured one hand and the knife the other. But Chapter 2 explicitly says left hand, Chapter 7 says right hand. This is a direct attribute contradiction about which hand bears the original scar. |
| false alarm | - | ch7 | Dun valley | status | Chapter 4 (two years after the fire) states the people of the Dun valley 'are eating bark again,' implying they had resumed the practice. Chapter 7 (four months after chapter 5) states they 'had stopped eating bark.' Since chapter 7 is later in the timeline, the new fact contradicts the established status from chapter 4 without any in-story explanation for the change. |
| correct | T3 | ch7 | Bram Holloway | timeline | Bram Holloway is 66 in chapter 3 and the chapter timing notes say about 2.39103 years pass in between, so Bram Holloway should be about 68.391 in chapter 7, but the text says 62. |
| false alarm | - | ch8 | Aurel | attribute | Chapter 2 explicitly states Aurel had NEVER heard this roar before ('a noise Aurel had never heard before'). Chapter 8 says 'Aurel had heard that roar once, and he would never forget it.' This is a direct contradiction about whether this is his first time hearing the roar. |
| false alarm | - | ch8 | the roar from the lower city | attribute | Both facts describe Aurel hearing a noise from the lower city through a window. In chapter 2, the noise is described as 'a low, steady roar, like the sea in a cave' and Aurel had never heard it before. In chapter 8, Aurel compares the current sound to 'the roar of a riot' which he 'had heard once, and he would never forget it', describing the new sound as 'thousands of feet, walking, and under it, very faintly, singing'. These are contradictory descriptions of the same auditory experience - the chapter 2 roar is explicitly something Aurel had never heard before, while chapter 8 describes him recognizing a riot roar from past experience. The sounds themselves are also fundamentally different (steady roar vs. walking feet with singing). |

Decoys wrongly flagged: none

## What the double-check removed

21 warnings dismissed: 21 were false alarms; real mistakes wrongly removed: none.

- ch2 · Venn fleet: Double-check: The two quotes describe different fleets at different locations and events. Chapter 1 refers to the 'Venn fleet' destroyed at Greywater Bay. Chapter 2 describes a storm catching the 'Vessmark fleet' at Kettle Rocks. These are distinct fleets (Venn vs. Vessmark) and distinct battles/locations, so the
- ch2 · Bram Holloway: Set aside: ages are compared by the story clock, which does the arithmetic with the chapter timing; here one side isn't this character's age now (someone else's age, a past or future age, a relative age, or a length of time).
- ch2 · Vessmark fleet: Double-check: Chapter 1 states the 'Venn fleet' was broken at Greywater Bay. Chapter 2 describes a fleet of 940 ships at anchor, but the quote does not identify it as the Venn fleet; given the previous warning, it is likely the Vessmark or another fleet. Even if it were the same fleet, a three-year time skip allo
- ch2 · King Aurel: Double-check: Both quotes refer to King Aurel's scar on the back of his left hand. Chapter 1 (three days after Greywater) calls it 'still fresh.' Chapter 2 (three years later) says it 'ached in the cold the way it always did now,' indicating a healed, chronic ache. This is a natural progression of a wound healing
- ch3 · Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch3 · Tam: Set aside: ages are compared by the story clock, which does the arithmetic with the chapter timing; here one side isn't this character's age now (someone else's age, a past or future age, a relative age, or a length of time).
- ch3 · Crowned salt-hawk: Double-check: Chapter 3 explicitly shows the transfer: Aurel pushes the ring across the table and Corvin slides it onto his own finger. This is a normal story progression (possession change) between consecutive days, not a contradiction.
- ch3 · Crowned salt-hawk: Double-check: Same as warning 1: chapter 3 narrates the ring passing from Aurel to Corvin. The 'too big' line refers to Corvin wearing it after the transfer, which is consistent with the story moving forward one day.
- ch4 · Tam: Set aside: ages are compared by the story clock, which does the arithmetic with the chapter timing; here one side isn't this character's age now (someone else's age, a past or future age, a relative age, or a length of time).
- ch5 · Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch5 · Rell: Double-check: The two quotes are about completely different subjects. The earlier quote describes Rell's left hand with rope burns, while the new quote describes a sword's leather grip worn by someone else's hand. They do not refer to the same character, place, object, or event, so this is not a valid continuity 
- ch6 · King Oren: Double-check: The earlier quote says King Oren came home with a fever he 'never fully shook,' which strongly implies the fever persisted and contributed to his death. The new quote explicitly states he 'died of the fever he had carried home from the river Kell.' This is a natural elaboration of the same fact, not
- ch6 · Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch6 · Aurel: Set aside: ages are compared by the story clock, which does the arithmetic with the chapter timing; here one side isn't this character's age now (someone else's age, a past or future age, a relative age, or a length of time).
- ch6 · Duke Corvin: Set aside: ages are compared by the story clock, which does the arithmetic with the chapter timing; here one side isn't this character's age now (someone else's age, a past or future age, a relative age, or a length of time).
- ch6 · Ember: Set aside: a young animal grown up (or seen young in a flashback), not a different animal.
- ch7 · Aurel: Double-check: The timeline is consistent. Chapter 6's flashback (14 years before the fall) shows Aurel crowned at 19. The fall occurs 14 years later when he is ~33. Chapter 5 is 3 years after the fire (which coincides with the fall), making Aurel ~36 and his son 8 (conceived around the fall). Chapter 7 is 4 month
- ch8 · Duke Corvin: Set aside: ages are compared by the story clock, which does the arithmetic with the chapter timing; here one side isn't this character's age now (someone else's age, a past or future age, a relative age, or a length of time).
- ch8 · Bram Holloway: Set aside: ages are compared by the story clock, which does the arithmetic with the chapter timing; here one side isn't this character's age now (someone else's age, a past or future age, a relative age, or a length of time).
- ch8 · Aurel: Double-check: Chapter 7 explicitly states Aurel has two scars: one on his right hand and a matching one on his forehead. Chapter 8 says Thessaly sees 'his two scars'—this is consistent with the two scars just established. The left-hand scar from Greywater (chapters 2 and 4) is not mentioned in chapter 7 or 8; its
- ch8 · King Aurel: Double-check: The timeline spans roughly five years (three years + two years + three weeks + four months + one day). A child carried on shoulders in chapter 1 would be a gangly adolescent in chapter 8. 'Taller than Aurel remembered' is a natural reaction to seeing a child after years; it does not imply a recent m

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

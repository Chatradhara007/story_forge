# StoryForge evaluation — fallenking — 2026-10-12 23:28

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3.5-lightning-30b-a3b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 571s · AI requests per run: 85 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: reader 0.0, judge 0.0 · Reading passage size: 700 characters

> **Models switched during the run:** 'nvidia/nemotron-3-ultra-550b-a55b' keeps failing (AI call 'report_contradictions' (nvidia/nemotron-3-ultra-550b-a55b) failed after 2 tries: Error code: 500 - {'error': {'); using the next model for 10 minutes.

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 3 |
| linking names | 114 |
| preparing search | 43 |
| safety-net check | 247 |
| checking for mistakes | 263 |
| story clock | 0 |
| double-checking | 72 |
| saving | 4 |

*Checking, story clock and safety net run one after another per chapter; reading and timing run together.*

## Time per chapter

| Chapter | Words | Facts | Reading (s) | Judging (s) |
|---|---|---|---|---|
| ch1 | 906 | 81 | saved | 38.0 |
| ch2 | 795 | 63 | saved | 114.6 |
| ch3 | 823 | 87 | saved | 80.6 |
| ch4 | 828 | 84 | saved | 53.5 |
| ch5 | 922 | 92 | saved | 91.5 |
| ch6 | 726 | 74 | saved | 56.0 |
| ch7 | 985 | 91 | saved | 71.3 |
| ch8 | 1,078 | 76 | saved | 65.3 |

**Judging:** 76 s per chapter on average (chapters after the first; the first has nothing earlier to compare). 7,063 words in 8 chapters.

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 9% | 18% | 0.12 | 2 / 11 | 21 | 0 | 100% |

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
    - ch2: [King Aurel] Aurel | has a scar on the back of his left hand | The scar on the back of his left hand ached in the cold the way it always did now
    - ch7: [King Aurel] Aurel | physical_description | forehead healed into a second scar to match the one on his right hand
    - ch7: [King Aurel] Aurel | injury | forehead scar
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
    - ch7: [his mother] elder sister of Aurel | relationship | sibling of Aurel
    - ch7: [King Aurel] Aurel | purpose | here with wheat, and with my elder sister who is a healer, and with a boy named Pell who keeps better accounts than my old treasurer
    - ch7: [his mother] elder sister of Aurel | role | healer
- **A5** → **split**: Both details were recorded, but under different entries, so they were never compared.
    - ch1: [Bram Holloway] Bram Holloway | age | sixty-four years old
    - ch1: [Bram Holloway] Bram Holloway | role | swordmaster who had taught Aurel to hold a blade when he was seven
    - ch2: [Venn fleet] Venn fleet | ships lost | of nine hundred and forty ships, sixty came home
    - ch3: [Vessmark fleet] sixty battered hulls | remain | sixty battered hulls
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
    - ch7: [harvest] winter | time_reference | winter
- **T2** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch2: [King Aurel] King Aurel | decision | ordered the fleet to sail for the Venn isles
    - ch2: [autumn storms] autumn storms | time reference | second week of the autumn storms
    - ch8: [autumn storms] spring equinox | time of council meeting | spring equinox
    - ch8: [valley full of people eating bark] people from Dun valley | group composition | widows of the spring storm at the Kettle Rocks that took the fleet, on carts and on foot and on Saska Venn's two barges, which had sailed brazenly into the royal harbour under the flag of the Venn isles: millers and farmers, mothers and grandfathers, the old woman who had spat at Aurel's feet twice, and every village between Hollin and Dun Crossing
    - ch8: [Vessa] great square of Vessa | description | they laid them down in the great square of Vessa in a grey heap taller than a man
    - ch8: [Pell] Pell | action | led an old grey stallion out of the royal stables into the spring dusk

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| false alarm | - | ch3 | King Aurel | attribute | New fact 18 states Aurel 'has a scarred hand' (singular, generic) while existing fact 2 specifies the scar is 'across the back of his left hand' from a 'Venn boarding hook'. The new fact's vagueness ('a scarred hand') could imply a different hand or a different scar, contradicting the established specific location and cause. Since the scar is a permanent, defining attribute established in chapter 1 and referenced again in chapter 2 (fact 29), a generic description in chapter 3 that doesn't match the established detail is a contradiction. |
| false alarm | - | ch3 | Castle of Harrowmere | attribute | Chapter 3 states the king will retire to 'the castle you gave me' (Harrowmere), implying Corvin gave Aurel the castle. Chapter 1 [CANON] states 'Aurel had already given him the castle of Harrowmere as a reward' — Aurel gave it to Corvin. The giver/receiver is reversed, a permanent attribute of the castle's ownership history that cannot change without explanation. |
| false alarm | - | ch3 | King Aurel | attribute | Chapter 3 has the king tell Corvin 'You will retire to Harrowmere, to the castle you gave me' — Corvin gave the castle to Aurel. Chapter 1 [CANON] states 'Aurel had already given him the castle of Harrowmere as a reward' — Aurel gave it to Corvin. Direct contradiction in the established chain of ownership. |
| false alarm | - | ch3 | crowned salt-hawk | status | In chapter 2, Aurel is wearing the signet ring ('turned the signet ring on his finger'). In chapter 3 (the next day), Duke Corvin slides the same signet ring onto his own finger. The ring cannot be on both men's fingers simultaneously without explanation (e.g., transfer, theft, duplication). This is a status contradiction: the ring's location/possession changes impossibly between consecutive days. |
| false alarm | - | ch3 | crowned salt-hawk | status | Same signet ring as pair 0. Chapter 2 establishes it is on Aurel's finger. Chapter 3 has Duke Corvin put it on his own finger, noting it's 'a little too big for him.' The ring cannot be worn by both at the same time. The size detail (too big for Corvin) further suggests it was fitted for Aurel, making the transfer implausible without explanation. |
| false alarm | - | ch4 | Venn | timeline | Saska Venn's location in the new chapter is the Lamb and Anchor in Dunmouth for a week. The earlier fact places her at the cliffs of Venn in chapter 2. These are about the same entity (Saska Venn), and there is a contradiction in location: she cannot be at the Lamb and Anchor in Dunmouth and at the cliffs of Venn at the same time, unless there is an off-screen move. The chapter timing shows chapter 2 is earlier, so this is a genuine contradiction. |
| false alarm | - | ch4 | Venn | timeline | Saska Venn's duration a week at the Lamb and Anchor in Dunmouth contradicts the earlier fact of her watching from the cliffs of Venn for two years (chapter 2). The new chapter says she will be there for a week, implying a short stay, while the earlier fact establishes she spent two years being hated. This is a contradiction in duration/status. |
| false alarm | - | ch5 | King Aurel | attribute | The new fact states Aurel's son is eight years old and raised by the man who took his crown. The existing fact from chapter 1 identifies the son as a child of King Oren (Aurel's father). This creates a conflict: the son's caretaker and age differ from the established parentage. |
| false alarm | - | ch5 | his mother | status | The new fact states Mira is Aurel's sibling. The existing fact from chapter 4 states 'his mother / relationship / child of Aurel', which implies Mira is Aurel's child, not sibling. This is a direct contradiction: Mira cannot be both sibling and child of Aurel. |
| false alarm | - | ch5 | King Aurel | attribute | The sword description in pair 30 states the leather grip is worn smooth and dark by a hand that was not Aurel's, while pair 29 states the scar on the back of Aurel's left hand ached in the cold. These are contradictory attributes of the sword's grip and Aurel's hand; the description implies the sword was not handled by Aurel, yet the scar belongs to Aurel. |
| false alarm | - | ch5 | King Aurel | timeline | Pair 33 places the sword inside the long chest under the narrow bed, while pair 33 (duplicate index) places the sword with the old swordmaster on a bench. The sword's location contradicts itself: it cannot be both inside the chest and on a bench at the same time without an in-story explanation. |
| false alarm | - | ch5 | Bram Holloway | timeline | Pair 25 describes the famine as the famine of 'his twelfth year', while pair 25 (duplicate index) references Bram Holloway's statement about the twelfth year. The famine's association with Aurel's twelfth year conflicts with the later chapter's timeline if the time elapsed does not match. |
| correct | A1 | ch5 | Ember | attribute | Pair 1 states Ember is a grey stallion, while the new chapter (pair 0) refers to Ember as the black stallion. The color of the horse changed without in-story explanation, which is an attribute contradiction. |
| false alarm | - | ch5 | King Aurel | attribute | The new chapter states Quiet is a plain, old sword with a leather grip worn smooth and dark by a hand that was not Aurel's, and that the name Quiet was given after the Kell river event because it never had anything to boast about. The earlier fact attributes a scar on the back of Aurel's left hand and says the scar ached in the cold 'the way it always did now'. The sword's grip being worn by a hand that is not Aurel's contradicts the established fact that Aurel has a scarred left hand and is the one who carried Quiet. This is an attribute contradiction without in-story explanation. |
| false alarm | - | ch7 | Pell | attribute | NEW: Pell is described as 'keeps better accounts than my old treasurer' implying he is a quartermaster/accountant. EXISTING: Pell was established in chapter 1 as 'the stable boy, thirteen years old'. The role of quartermaster/accountant conflicts with the established role of stable boy. This is a genuine contradiction in Pell's role/identity. |
| false alarm | - | ch7 | Quiet | timeline | Quiet/Mira is described as the quiet one who read in the window seat (chapter 5 personality description), but the new fact describes Quiet being buckled on for the first time at his hip, suggesting sword training/swordplay involvement. This conflicts with the established personality description of someone who reads in window seats, unless there's a significant time gap or character development not accounted for. |
| false alarm | - | ch7 | King Aurel | timeline | King Aurel is 33 in chapter 2 and the chapter timing notes say about 2.39103 years pass in between, so King Aurel should be about 35.391 in chapter 7, but the text says 38. |
| correct | T3 | ch7 | Bram Holloway | timeline | Bram Holloway is 66 in chapter 3 and the chapter timing notes say about 2.39103 years pass in between, so Bram Holloway should be about 68.391 in chapter 7, but the text says 62. |
| false alarm | - | ch7 | King Oren | status | King Oren is dead from chapter 5 ("the winter King Oren died"), but acts in chapter 7: Burned coastal fields on the way to the river during the Kell war.. |
| false alarm | - | ch7 | grain | attribute | The regent is described as both stopping the purchase of Venn grain (pair 27) and selling it off a sack at a time to guild masters (pairs 29-30). These are contradictory actions regarding the same entity's behavior toward Venn grain, with no in-story explanation for a change from stopping to active selling. |
| false alarm | - | ch7 | guild masters | attribute | The regent is described as selling Venn grain off a sack at a time to guild masters (pair 29) while also having the last of it locked up in cellars at Harrowmere (pair 28). These cannot both be true simultaneously without explanation. |
| false alarm | - | ch8 | sister who opened the gate | attribute | Chapter 7 says Aurel's sister did not recognise him, but chapter 2 (earlier in reading order) shows Aurel kneeling beside Thessaly, implying a close relationship and familiarity. The sister not recognising him is a contradiction unless there is an in-story explanation (e.g. injury, memory loss). |
| false alarm | - | ch8 | Ember | status | Ember is identified as Aurel's grey stallion in chapter 1. In chapter 8, Ember is described as being led out of the royal stables into spring dusk, implying Ember is present at the feast and under Pell's control. This conflicts with Ember being Aurel's stallion in chapter 1, as the new chapter establishes Ember as a royal stable horse under Pell's authority, contradicting the earlier ownership and identity. |

Decoys wrongly flagged: none

**Check by hand:** T1. A warning counted as a false alarm has the right chapter, entity and new detail for these items; only its earlier side is worded differently from the answer key. If it is right, the item was caught.

## What the double-check removed

45 warnings dismissed: 45 were false alarms; real mistakes wrongly removed: none.

- ch2 · King Aurel: Double-check: The timeline is consistent. Chapter 1 (3 days after Greywater) states a plan to build ships over two summers. Chapter 2 (3 years after the fire/Greywater) shows the fleet being ordered to sail. Two summers of building fit within the three-year gap; the departure in autumn of year 3 aligns with the p
- ch2 · Vessmark fleet: Double-check: The quotes refer to different fleets. Chapter 1: 'The Venn fleet lay broken' (enemy fleet destroyed). Chapter 2: 'Nine hundred and forty ships... rode at anchor' (Aurel's own Vessmark fleet, built per the plan). No contradiction.
- ch2 · Venn fleet: Double-check: Same as warning 1. The Venn fleet (enemy) was destroyed; the Vessmark fleet (Aurel's) sails to the Venn Isles. The target is the islands, not a naval fleet. No status contradiction.
- ch2 · Venn fleet: Double-check: Repeats the same misreading. The Vessmark fleet is the attacker; the Venn fleet was the defender destroyed earlier. Admiral Saska Venn watching from the cliffs does not require a Venn fleet at sea. No contradiction.
- ch2 · Venn fleet: Set aside: the warning's own explanation says the two facts are consistent.
- ch2 · Venn fleet: Double-check: Admiral Saska Venn observing from the cliffs of Venn does not imply a functioning Venn fleet. The Venn fleet was destroyed at Greywater Bay; the Admiral can still exist and watch the enemy (Vessmark) fleet founder. No direct contradiction.
- ch3 · King Aurel: Double-check: The two facts are not direct contradictions. Chapter 1 says the highest point was standing on the slipway with his son. Chapter 3 says he never lit a fire. These are separate experiences; one does not logically reverse the other. It is a characterization stretch but not a fact-level contradiction.
- ch3 · Vessmark fleet: Set aside: the story moving forward (something that existed earlier in story time has 'lost' later). Only the reverse would be a mistake.
- ch3 · crowned salt-hawk: Set aside: the warning's own explanation says the two facts are consistent.
- ch3 · keels of the thousand ships: Double-check: The warnings compare chapter 3 with chapter 1, but chapter 2 shows the fleet existed and was intact ('rode at anchor'). The fleet could have been built after chapter 1's keels were laid, survived chapter 2, and then been lost between chapter 2 and 3, or the description in chapter 3 could refer to a 
- ch4 · Duke Corvin: Double-check: The warning misreads the facts. Fact 1 from chapter 4 (Corvin buying Venn grain) and fact 5 from chapter 2 (Aurel saying 'It cannot go on like this, cousin') are separate statements about different contexts. The warning claims a timeline problem, but there is no explicit shared value that contradict
- ch4 · Vessa: Double-check: The warning conflates two different facts about Vessa. Fact 0 from chapter 2 states news reached Vessa on a grey morning; fact 0 from chapter 4 identifies Vessa as the mother of Prince Tam with the quote 'Away from his mother.' These are not the same fact – one is about news arrival, the other about
- ch4 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch4 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch4 · Vessmark fleet: Double-check: The numbers 900 and 990 are close approximations. Both quotes refer to the same event (the loss of ships under Saska Venn). A slight numerical difference does not constitute a genuine contradiction; it could be rounding or an in-universe error. The entity (Saska Venn / the nine hundred ships event) 
- ch5 · riot in the lower city: Double-check: The six-year timeline for earning back a loss and the scar on the ferryman's left hand from a boarding hook are not directly contradictory. The scar fact describes a physical detail, while the six-year fact describes a duration of effort. They can coexist without conflict, so criterion 5 is not met.
- ch5 · river Dun: Double-check: The famine being described as the famine of Aurel's twelfth year and Bram Holloway's statement about the twelfth year are not necessarily contradictory without knowing the exact timeline. The passage of time could align these if the chapters are set at appropriate distances. I am not genuinely unsur
- ch6 · King Oren: Double-check: Both quotes describe the same fever event. Chapter 5 states the king came home with a fever he never fully shook. Chapter 6 adds that the fever came from the river Kell. Adding a source attribution does not contradict the earlier quote; it simply provides more detail. The earlier quote does not say 
- ch6 · keels of the thousand ships: Double-check: Chapter 1 states the first keels of the thousand ships were laid in the yards of Vessa. Chapter 6 mentions a shipwright from the harbour coming to bid for the repair of the royal barge in the spring of that first year. These are not contradictory; the keel-laying is the initial construction event, w
- ch7 · Admiral Saska Venn: Set aside: the warning's own explanation says the two facts are consistent.
- ch7 · his mother: Double-check: The new quote describes the mother's sister as a healer, while the existing fact states the mother's relationship to Aurel. These are different relationships that could both be true; there is no direct contradiction.
- ch7 · flat-boat: Double-check: The earlier quote names a flat-boat type; the new quote describes a cart where Mira stitched a wound. These are different objects/locations and do not directly contradict each other. The comparison is between different entity designations.
- ch7 · Queen Liesl: Double-check: The earlier fact is about Queen Liesl's age (seventy-one), the new fact is about her letter-reading habit. These are unrelated attributes that could both be true; no direct contradiction.
- ch7 · Bram Holloway: Double-check: The earlier fact describes Bram's military allegiance (fought for King Oren), the new fact describes him traveling on a tired horse. These are different attributes that could both be true; no direct contradiction.
- ch7 · Bram Holloway: Double-check: The earlier fact is about Bram being alive, the new fact is about bringing a letter from Queen Liesl. These are different topics that could both be true; no direct contradiction.
- ch7 · Bram Holloway: Double-check: The earlier fact is about a saying regarding harvests in the twelfth year, the new fact is about when the council meets (spring equinox). Different topics; not a direct contradiction.
- ch7 · Duke Corvin: Double-check: The earlier fact mentions seven dead in the market square; the new fact says Corvin told Tam the entity is dead. These could both be true (different people), but timing and context need clarification. Low confidence due to ambiguity.
- ch7 · Queen Thessaly: Set aside: the warning's own explanation says the two facts are consistent.
- ch7 · Tam: Set aside: the story moving forward (something that existed earlier in story time has 'dead' later). Only the reverse would be a mistake.
- ch7 · Tam: Double-check: Tam asks for 'you' every week, but existing fact 7 establishes Tam as six years old in chapter 2. The weekly request could be consistent with character development, but the frequency and context may conflict with the established younger age. However, without clearer conflict, this is not a definitiv
- ch7 · King Aurel: Double-check: The warning conflates different facts: pair 12 concerns King Aurel finding his swordmaster, while pairs 29-30 concern grain selling. There is no direct contradiction between finding a swordmaster and selling grain.
- ch7 · King Aurel: Double-check: The old swordmaster asking for the protagonist every week (pair 34) and the information that Corvin said the protagonist is dead (pair 35) could both be true if the swordmaster is unaware or if there's a time gap. Not a definitive contradiction.
- ch7 · Bram Holloway: Set aside: the story moving forward (something that existed earlier in story time has 'dead' later). Only the reverse would be a mistake.
- ch8 · Duke Corvin: Double-check: The two quotes describe different actions (relationship reference vs. specific council action) that can coexist. No timeline violation is evident; the warning misinterprets the facts as contradictory.
- ch8 · Duke Corvin: Double-check: The quotes refer to different facts: 'seven dead in the market square' vs. 'you're supposed to be dead'. There is no direct link between the two statements, and the warning does not establish that they contradict each other.
- ch8 · Duke Corvin: Double-check: Both quotes can be true at different times (standing in a study vs. sitting in a chair). No explicit timeline conflict is presented, so this is not a continuity error.
- ch8 · Duke Corvin: Double-check: Locking grain away and calling a council are separate actions that can both occur. No contradiction is demonstrated.
- ch8 · Pell: Set aside: the warning's own explanation says the two facts are consistent.
- ch8 · Admiral Saska Venn: Double-check: The new fact about Saska's position 'behind Aurel' does not directly contradict the earlier fact about her losing Greywater and being hated. The warning conflates positioning with established backstory.
- ch8 · castle: Set aside: the warning's own explanation says the two facts are consistent.
- ch8 · harvest: Set aside: the warning's own explanation says the two facts are consistent.
- ch8 · council meeting: Double-check: The council meeting timing can be reconciled: chapter 3 states the council met the next morning, and chapter 8's vote on the cellar can occur after that meeting. No direct contradiction is forced by the chapter timing notes.
- ch8 · King Aurel: Double-check: Tam's height change and Aurel's memory of standing on a slipway with Tam on his shoulders are not directly contradictory. Growth over time is plausible, and the chapters' story order is not clearly violated.
- ch8 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch8 · King Aurel: Double-check: Ember being Aurel's grey stallion in chapter 1 and appearing under Pell's control in chapter 8 does not necessarily contradict each other; the horse could have changed hands or been shared. The warning assumes ownership is exclusive without evidence.

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

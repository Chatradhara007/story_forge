# StoryForge evaluation — fallenking — 2026-10-12 22:58

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3-ultra-550b-a55b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 1234s · AI requests per run: 99 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: reader 0.0, judge 0.0 · Reading passage size: 700 characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 7 |
| linking names | 157 |
| preparing search | 35 |
| checking for mistakes | 350 |
| story clock | 1 |
| safety-net check | 302 |
| double-checking | 371 |
| saving | 10 |

*Checking, story clock and safety net run one after another per chapter; reading and timing run together.*

## Time per chapter

| Chapter | Words | Facts | Reading (s) | Judging (s) |
|---|---|---|---|---|
| ch1 | 906 | 81 | saved | 29.5 |
| ch2 | 795 | 63 | saved | 229.2 |
| ch3 | 823 | 87 | saved | 111.7 |
| ch4 | 828 | 84 | saved | 146.0 |
| ch5 | 922 | 92 | saved | 197.4 |
| ch6 | 726 | 74 | saved | 191.7 |
| ch7 | 985 | 91 | saved | 196.5 |
| ch8 | 1,078 | 76 | saved | 131.7 |

**Judging:** 172 s per chapter on average (chapters after the first; the first has nothing earlier to compare). 7,063 words in 8 chapters.

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 5% | 27% | 0.09 | 3 / 11 | 52 | 0 | 67% |

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
    - ch7: [winter] winter | time_reference | winter
- **T2** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch2: [King Aurel] King Aurel | decision | ordered the fleet to sail for the Venn isles
    - ch2: [autumn storms] autumn storms | time reference | second week of the autumn storms
    - ch8: [spring] spring equinox | time of council meeting | spring equinox
    - ch8: [Dun valley] people from Dun valley | group composition | widows of the spring storm at the Kettle Rocks that took the fleet, on carts and on foot and on Saska Venn's two barges, which had sailed brazenly into the royal harbour under the flag of the Venn isles: millers and farmers, mothers and grandfathers, the old woman who had spat at Aurel's feet twice, and every village between Hollin and Dun Crossing
    - ch8: [Vessa] great square of Vessa | description | they laid them down in the great square of Vessa in a grey heap taller than a man
    - ch8: [Pell] Pell | action | led an old grey stallion out of the royal stables into the spring dusk

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| false alarm | - | ch2 | King Aurel | timeline | Chapter 1 establishes a plan to build ships over 'two summers' then sail to the Venn isles. Chapter 2 (set two years after the fleet's departure) shows the king ordering the fleet to sail for the Venn isles 'in the second week of the autumn storms'. This suggests the fleet was built and departed within two years, which matches the 'two summers' timeline. However, the new fact says 'In the second week of the autumn storms the king ordered them to sail for the Venn isles' - this implies the order to sail is given in chapter 2, but chapter 1 shows the order was signed in the morning after the feast ('In the morning Aurel signed the order'). The fleet departure should have already happened two years ago according to chapter timing. This is a timeline contradiction: the fleet departure is described as happening in chapter 1 (Aurel signs order, stands on slipway with Tam), but chapter 2 shows the king ordering them to sail two years later. |
| false alarm | - | ch2 | Venn fleet | status | Chapter 1 states 'The Venn fleet lay broken on the shoals of Greywater bay,' implying the Venn naval force was destroyed. Chapter 2 has King Aurel ordering his fleet to sail for the Venn isles, and Admiral Saska Venn (who lost Greywater) watches from the cliffs of Venn as the Vessmark fleet is caught in a storm. If the Venn fleet was already broken, the presence of a defending Venn fleet or organized resistance (implied by Saska Venn's command position) contradicts the earlier status of total destruction. |
| false alarm | - | ch2 | Venn fleet | status | Chapter 1 says the Venn fleet was already broken at Greywater Bay. Chapter 2 treats the Venn isles as a target for invasion, implying they are still a viable military objective with defenses. If the Venn fleet was destroyed, the islands should be defenseless or already taken, not a target for a new fleet two years later. |
| false alarm | - | ch2 | Venn fleet | status | Chapter 1 states the Venn fleet lay broken at Greywater Bay. Chapter 2 introduces Admiral Saska Venn as having 'lost Greywater and spent two years being hated for it by her own people,' and she watches from the cliffs of Venn as the Vessmark fleet is caught in a storm. Her presence in command on Venn implies a functioning Venn naval authority, contradicting the total destruction of the Venn fleet. |
| false alarm | - | ch2 | Venn fleet | status | Same as pair 16: The Venn fleet's destruction at Greywater Bay (Chapter 1) contradicts Admiral Saska Venn's active command role on the cliffs of Venn (Chapter 2), which implies an intact Venn naval presence. |
| false alarm | - | ch2 | Venn fleet | status | Chapter 1: Venn fleet broken at Greywater Bay. Chapter 2: Admiral Saska Venn watches from Venn's cliffs as the storm catches the Vessmark fleet at Kettle Rocks. Her position as an observing admiral on Venn implies the Venn still have a fleet or coastal defense, contradicting the earlier claim of total destruction. |
| false alarm | - | ch2 | King Aurel | timeline | Same as pair 1: Tam's age in Chapter 1 is four; in Chapter 2 (12 years later) he is six. This is a timeline contradiction — age should have increased by ~12 years, not 2. |
| false alarm | - | ch3 | Vessmark fleet | attribute | Chapter 3 states 900 ships were lost (at the bottom of the sea), but Chapter 2 establishes that 940 ships departed and 60 returned, meaning 880 were lost. The new figure of 900 lost contradicts the established total of 940 ships and the specific loss count of 880. |
| false alarm | - | ch3 | Pell | timeline | Pell is 15 in chapter 2 and the chapter timing notes say about 2 years pass in between, so Pell should be about 17 in chapter 3, but the text says 15. |
| false alarm | - | ch3 | keels of the thousand ships | attribute | Chapter 3 states 'sixty battered hulls' remain from the fleet, while Chapter 1 states 'the first keels of the thousand ships were laid in the yards of Vessa'. Chapter 2 confirms 940 ships were built and at anchor. The discrepancy between 1000 ships built, 940 afloat, and only 60 remaining hulls in Chapter 3 (same time as Chapter 2) suggests a contradiction in fleet attrition numbers unless explained by a catastrophic event not mentioned in Chapter 2. |
| false alarm | - | ch3 | keels of the thousand ships | attribute | Chapter 3 mentions 'widows in every harbour town from Vessa to Harrowmere' implying massive crew losses, while Chapter 1 describes the keel-laying for 1000 ships and Chapter 2 shows 940 ships intact with crews. The scale of widowhood in Chapter 3 (same time as Chapter 2) contradicts the fleet's intact status in Chapter 2 unless a disaster occurred between chapters - but Chapter 3 is set at the same time as Chapter 2. |
| false alarm | - | ch3 | Tam | attribute | Chapter 3 states Tam is 'six-year-old' while Chapter 1 (12 years earlier) states Tam is 'four years old'. A 2-year age increase over 12 years is impossible. |
| false alarm | - | ch3 | King Aurel | attribute | Chapter 3 states Tam is 'six-year-old' while Chapter 1 (12 years earlier) states Tam is 'four years old'. A 2-year age increase over 12 years is impossible. |
| false alarm | - | ch3 | King Aurel | status | In Chapter 1, Aurel presses his father's signet ring into hot wax, establishing he possesses and uses the ring. In Chapter 3, Duke Corvin puts that same signet ring on his own finger ('It was a little too big for him. He wore it anyway.'). The ring cannot be in Aurel's possession in Chapter 1 and Corvin's possession in Chapter 3 without an explained transfer. The new chapter contradicts the established state of the ring's ownership. |
| false alarm | - | ch3 | crowned salt-hawk | status | Chapter 2 shows Aurel wearing the signet ring ('turned the signet ring on his finger'). Chapter 3 shows Duke Corvin putting on the same ring ('slid the signet ring onto his own finger... It was a little too big for him. He wore it anyway.'). The ring is a unique object; it cannot be worn by both men at once. The new chapter depicts Corvin wearing the ring while the earlier chapter (same time period per timing notes) shows Aurel still wearing it, with no explanation for the transfer. |
| false alarm | - | ch4 | King Aurel | attribute | The new fact states the hook went into Aurel while he was trying to pull someone off the rail of the Salt Hawk at Greywater, implying Aurel was the one hooked. The existing fact describes the scar as being from a Venn boarding hook that opened Aurel to the bone during a boarding action, suggesting Aurel was hooked by an enemy Venn hook, not his own hook while attempting a rescue. These are mutually exclusive accounts of how Aurel received the same scar. |
| false alarm | - | ch4 | King Aurel | attribute | The new fact describes a woman as 'tall and weathered, with a sailor's rolling walk and close-cropped iron-grey hair' who is addressed as 'Your Majesty' and claims to be Aurel's cousin Corvin buying Venn grain. However, existing facts establish King Aurel is a 33-year-old man (chapters 1-3). This appears to describe a different character (possibly Queen Thessaly or another woman) but is indexed under Aurel. If this is meant to be Aurel, it contradicts established gender and age. |
| false alarm | - | ch4 | Pell | timeline | Pell's age is given as 17 in chapter 4, but was 15 in chapters 2 and 3. The chapter timing notes indicate chapters 2, 3, and 4 are all set at the same time ('two years after the fleet's departure / twelve years after Greywater'). Pell cannot be both 15 and 17 at the same time without a time jump that isn't indicated. |
| false alarm | - | ch4 | Tam | timeline | Tam's age is given as 8 in chapter 4, but was 6 in chapters 2 and 3. Since chapters 2, 3, and 4 are all set at the same time point according to the chapter timing notes, Tam cannot be both 6 and 8 simultaneously. This is a clear timeline contradiction. |
| false alarm | - | ch4 | King Aurel | attribute | High confidence Rell and Aurel are the same entity: both have an old pale scar on the back of the left hand (Chapter 4: 'his left hand, with its old pale scar'; Chapter 2: 'The scar on the back of his left hand ached'). However, Chapter 1 describes King Aurel's scar as 'still fresh' and from a 'Venn boarding hook', while Chapter 4 describes Rell's scar as 'old pale scar' and 'rough with rope burns' — different causes (boarding hook vs rope burns) and different ages (fresh vs old). Since Chapters 1, 2, 3, 4 are in reading order but Chapter 1 is earlier in story time (before the 12-year skip), the scar should be older in later chapters, not fresh. But the cause contradiction (boarding hook vs rope burns) is a genuine attribute contradiction if they are the same person. |
| false alarm | - | ch4 | Vessmark fleet | attribute | Saska Venn's quote in chapter 4 says she watched 'nine hundred and ninety and forty ships' (990 + 40 = 1030) go down, while chapter 3 states 'nine hundred ships' (900) were at the bottom of the sea. Both refer to the same event (the fleet's destruction) and the same entity (the ships), but the counts differ by 130 ships with no in-story explanation for the discrepancy. |
| false alarm | - | ch4 | Vessmark fleet | attribute | Saska Venn claims in chapter 4 to have 'two ships' for smuggling wine, while chapter 3 establishes that 'nine hundred ships and their crews' are at the bottom of the sea. If Saska is Admiral Saska Venn (from chapter 2), her fleet was destroyed, so claiming to have two ships now contradicts the established loss of the entire fleet unless she acquired new ships, which is not explained. |
| false alarm | - | ch4 | Venn | status | Chapter 4 has Saska Venn saying she'll be at the Lamb and Anchor in Dunmouth for a week. Chapter 2 places Admiral Saska Venn on the cliffs of Venn, having lost Greywater and been hated for two years. If she is on Venn (the Venn isles), she cannot simultaneously be in Dunmouth (mainland) unless she traveled, but no travel is mentioned and the chapters are set at the same time (two years after fleet departure). |
| false alarm | - | ch5 | King Aurel | timeline | In Chapter 1, King Aurel is stated to be 31 years old. In Chapter 5, Aurel says his son is 8 years old. Given the timeline notes that Chapters 2-5 all take place 'two years after the fleet's departure / twelve years after Greywater', and Chapter 1 is 'continues the story after Chapter One' (presumably shortly before or at the fleet's departure), Aurel would be around 33-43 years old in Chapter 5. Having an 8-year-old son at age 31 is plausible, but the contradiction arises because in Chapter 1, Aurel's son Tam is explicitly stated to be 4 years old ('Their son Tam, four years old'). If only ~2 years have passed (per the chapter timing), Tam should be ~6, not 8. The math doesn't add up: 31 + 2 = 33, son 4 + 2 = 6, but Chapter 5 says son is 8. |
| false alarm | - | ch5 | King Aurel | status | In Chapter 1, Aurel is king and alive. In Chapter 5, he says he 'poles a ferry' and 'threw it into the sea, all of it' (the crown/kingdom). This is a status change (king to ferryman), but the timeline notes indicate Chapters 2-5 are all at the same time point ('two years after the fleet's departure'). In Chapter 3, Aurel is still in the castle, gives up his signet ring to Corvin, and says 'Then I'll stay.' In Chapter 4, he is at a landing, not anyone's majesty, and a woman (possibly Thessaly) comes to be ferried. In Chapter 5, he explicitly says he poles a ferry. This could be a forward progression within the same timeframe, but since all chapters 2-5 are set at the same time, him being king in Chapter 3 and a ferryman in Chapter 5 at the same time is a status contradiction unless it's a flashback/flashforward structure. The chapter timing says they are all 'time skip: two years after the fleet's departure', so they should be concurrent. If Chapter 5 is a flashback to before Chapter 3, then Aurel being a king |
| false alarm | - | ch5 | Duke Corvin | timeline | Duke Corvin is 2 in chapter 1 and the chapter timing notes say about 8 years pass in between, so Duke Corvin should be about 10 in chapter 5, but the text says 17. |
| false alarm | - | ch5 | King Oren | status | King Oren is dead from chapter 1 ("Bram had fought for Aurel's father, King Oren"), but acts in chapter 5: marched on the salt coast with every soldier in Vessmark. |
| correct | A1 | ch5 | Ember | attribute | Chapter 5 describes Ember as a 'black stallion' while Chapter 1 and Chapter 2 both describe Ember as a 'grey stallion'. This is a direct attribute contradiction about the horse's color with no in-story explanation for the change. |
| false alarm | - | ch5 | King Aurel | timeline | Chapter 5 states Mira is 'four years younger than him' (Aurel), and Chapter 1 states Aurel is 'thirty-one years old'. This would make Mira 27. However, Chapter 5 also states 'Mira had followed her there at twenty and taken the healer's grey', implying she was 20 when she joined the convent. Given the timeline notes indicate all chapters 2-5 are set at the same time ('two years after the fleet's departure / twelve years after Greywater'), Mira cannot be both 27 (if Aurel is 31) and have joined at 20 'twelve years after Greywater' unless the timing works out, but the age relationship needs verification against the established timeline. |
| false alarm | - | ch5 | King Aurel | attribute | Liesl says 'my son is eight years old' in chapter 5, but Aurel is 31 in chapter 1 and 33 in chapter 2 (two years later). Chapter 5 is at the same time as chapters 2-4 (two years after fleet departure). Aurel cannot be both 8 and 33. This is a direct attribute contradiction: Aurel's age is established as 31+ in earlier chapters, but Liesl describes her son as 8 in the new chapter. Unless this is a different son, but 'my son' and context suggest Aurel. The man who took her crown is likely Oren (Aurel's father), so the son is Aurel. Contradiction. |
| false alarm | - | ch5 | King Oren | attribute | Chapter 5 says 'Her blind eyes looked somewhere past him' referring to Liesl (queen, mother of the king, nearly blind). The pair says Aurel is parent of Oren. But chapter 1 says 'Aurel's father, King Oren' — so Oren is Aurel's father. Aurel cannot be parent of Oren. This is a relationship contradiction: the new chapter implies Aurel is Oren's parent, but earlier chapters establish Oren as Aurel's father. |
| false alarm | - | ch5 | King Aurel | attribute | Pair says Oren is child of Aurel. Chapter 1 says 'Aurel's father, King Oren' — so Oren is father of Aurel. Contradiction in relationship direction. |
| false alarm | - | ch5 | King Aurel | attribute | Oren and Aurel are the same person (Oren is a nickname/first name for King Aurel). Chapter 3 states 'Aurel had won a war' as an established fact, but Chapter 5 says 'He came home with a third of his army and a fever he never fully shook' — a clear defeat, not a victory. This contradicts the established attribute of the war's outcome without in-story explanation (no mention of a later reversal or propaganda). The chapters share the same timeline (both set two years after fleet departure), so this is not a flashback or time-forward change. |
| false alarm | - | ch5 | Dun valley | status | Aurel promised the Dun valley he would never let them starve again after visiting every village on foot. Chapter 4 (same timeline) states 'The people in the Dun valley are eating bark again,' indicating starvation has returned. This contradicts the established status of his promise being kept, with no explanation for the failure (e.g., new famine, broken supply lines). Since both chapters are set at the same story time, this is a status contradiction: the valley is starving again despite his explicit vow. |
| false alarm | - | ch6 | King Aurel | attribute | Chapter 6 states Aurel was 19 at coronation (14 years before the fall). Chapter 1 states King Aurel is 31 years old. If Chapter 1 is set at or near 'the fall', Aurel should be ~33 (19+14), not 31. A 2-year discrepancy in age for the same timeline point is a contradiction. |
| false alarm | D1 | ch6 | King Aurel | attribute | Chapter 6 explicitly states Aurel had no scar on his left hand at coronation ('then'). Chapter 1 describes a fresh scar from a Venn boarding hook. Since the Greywater battle (where the hook injury occurred) is referenced in Chapter 4 as a past event involving Aurel, and Chapter 6's coronation is 14 years before the fall while Chapter 1 appears to be at the fall, the scar should exist by Chapter 1. The new fact claims no scar at coronation, but doesn't explain the scar's origin later; however, the contradiction is that Chapter 1 says the scar was 'still fresh', implying recent, while Chapter 6 says no scar at coronation 14 years prior. If the scar is from Greywater, and Greywater was 12 years before Chapters 2-5 (which are 2 years after fleet departure), then at coronation (14 years before fall) the scar might not exist yet. But Chapter 1 says 'still fresh' at age 31, which conflicts with a 14-year-old scar. This is a timeline/attribute conflict. |
| false alarm | D2 | ch6 | Bram Holloway | attribute | Chapter 6 states Bram Holloway is 52 at coronation (14 years before fall). Chapter 1 states Bram is 64. If Chapter 1 is at the fall, 14 years later, Bram should be 66, not 64. A 2-year discrepancy (64 vs expected 66) is a contradiction. Chapter 3 also states Bram is 66, consistent with 52+14=66. Chapter 1's 64 contradicts both. |
| false alarm | - | ch6 | Duke Corvin | attribute | New fact (index 1) states Corvin is 17 in chapter 6 (set 14 years before the fall). Existing fact (index 23) from chapter 5 (set 12 years after Greywater) states Corvin was 17 at that time. If chapter 6 is earlier than chapter 5, Corvin cannot be the same age in both unless no time passed between them, which contradicts the established timeline of years passing between chapters. |
| false alarm | - | ch6 | Ember | attribute | Chapter 6 states Aurel was given a grey colt from the royal stud, while Chapter 1 establishes Aurel's horse Ember is a grey stallion. A colt is a young male horse (typically under 4 years old), while a stallion is an adult male horse. This is an attribute contradiction about the same horse (Ember) unless explained by time passage, but Chapter 6 is set 14 years before the fall while Chapter 1 continues after Chapter One, making the timeline unclear. The colt/stallion distinction is a clear attribute change without in-story explanation. |
| false alarm | - | ch7 | King Aurel | timeline | Chapter 1 establishes Aurel as 31 years old. Chapter 7 states he turned 38 'that winter' in a hayloft. Given the timeline (Chapter 6 is 14 years before the fall, Chapter 7 is 4 months later), Aurel would be around 19-20 in Chapter 6 (confirmed by existing facts 46, 54) and 33 in Chapters 2-5 (confirmed by existing fact 15). A jump from 33 to 38 in 4 months is impossible. |
| correct | A2 | ch7 | King Aurel | attribute | Chapter 1 establishes Aurel's scar is on the back of his LEFT hand from a Venn boarding hook. Chapter 7 states he has a scar on his RIGHT hand and a matching one on his forehead. This contradicts the established location (left vs right hand) and origin of the scar. |
| false alarm | - | ch7 | King Aurel | timeline | Chapter 6 establishes Aurel was 19 at coronation (14 years before fall). Chapter 7 is only 4 months after Chapter 6, so he should be ~19, not 38. The 19-year age jump in 4 months is impossible. |
| false alarm | - | ch7 | King Oren | attribute | New fact 0 states King Oren is the parent of Aurel ('Your father's army...'), while existing fact 8 states Oren is the child of Aurel ('Her blind eyes looked somewhere past him' - context shows Oren is the son). This is a direct relationship contradiction: Oren cannot be both father and son of Aurel. |
| correct | T3 | ch7 | Bram Holloway | attribute | Bram's age is stated as 62 in chapter 7, but was 66 in chapter 3. Since chapter 7 takes place only 4 months after chapter 6 (where Bram is 52), and chapter 3 is set 12 years after Greywater (same as chapters 1-5), Bram's age should be around 66-67 in chapter 7, not 62. This is a clear age regression contradiction. |
| false alarm | - | ch7 | Tam | attribute | Tam is 8 in chapter 4 (set 12 years after Greywater). Chapter 7 is only 4 months after chapter 6 (14 years before the fall). Even with maximum timeline spread, Tam cannot age from 8 to 25 in this timeframe. The age jump of 17 years is impossible given the chapter timing. |
| false alarm | - | ch7 | Pell | timeline | Pell is 17 in chapter 4 and the chapter timing notes say about 16 years pass in between, so Pell should be about 33 in chapter 7, but the text says 17. |
| false alarm | - | ch7 | King Aurel | attribute | Chapter 7 refers to Aurel's 'elder sister' who is a healer, while chapter 5 states 'The third was his own sister, Mira' - implying Mira is the third (youngest) sibling, not the elder sister. This is an attribute contradiction about birth order: the same sister cannot be both the elder sister and the third/youngest sibling. |
| false alarm | D5 | ch8 | King Aurel | attribute | Chapter 8 (new) describes Aurel as having 'two scars' and wearing a ring 'back on his finger', implying he has scars on both hands. Chapter 6 (existing) explicitly states 'Aurel had no scar on his left hand then' at his coronation (14 years before the fall). Chapter 1 and 2 establish he received a scar on his left hand from a Venn boarding hook at Greywater. The new fact contradicts the established timeline of when the left-hand scar appeared. |
| false alarm | - | ch8 | Bram Holloway | timeline | Chapter 3 (existing fact 11) states Bram is 66 years old and is set 'two years after the fleet's departure / twelve years after Greywater'. Chapter 8 (new fact 2) says 'for the first time since the night of Greywater' Bram drank, implying he had not drunk since Greywater. However, Chapter 3 occurs 12 years after Greywater, so if he hadn't drunk since Greywater, he would not have been drinking in Chapter 3 either. The new fact in Chapter 8 (set 4 months after Chapter 6, which is 14 years before the fall) claims this is the first time since Greywater, but Chapter 3 is 12 years after Greywater and shows Bram alive and active. The timeline is inconsistent: either Bram drank between Greywater and Chapter 3, or the 'first time since Greywater' claim in Chapter 8 is false. Given the chapter timing notes, Chapter 3 is 12 years after Greywater, Chapter 8 is 14 years before the fall (with Chapter 6 at 14 years before fall, Chapter 7 4 months later, Chapter 8 continuing). The 'fall' is likely the fall of the kingdom or王 |
| false alarm | - | ch8 | paper | status | The paper was established as 'lost' in chapter 6, but in chapter 8 it is physically present 'in front of them, waiting for wax' with no explanation of how it was recovered. This is a status contradiction: an object that was lost cannot be in use unless its recovery is explained. |
| false alarm | - | ch8 | King Aurel | status | King Aurel is dead from chapter 7 ("I am Aurel, who was your king. I sold the grain your fathers stored. I sank the fleet. Your sons drowned at the Kettle Rocks because of me. I am not here to ask for anything. I am here with wheat, and with my elder sister, who is a healer, and with a boy named Pell who keeps better accounts than my old treasurer. Bring your sick to my sister. Bring your hungry to the carts."), but acts in chapter 8: opened the door of the long chamber. |
| false alarm | - | ch8 | riot in the lower city | attribute | Chapter 8 describes the sound from the lower city as 'thousands of feet, walking, and under it, very faintly, singing' and explicitly states it was 'not the roar of a riot' and 'a different sound' from the roar Aurel heard once before. Chapter 2 describes the noise from the lower city as 'a low, steady roar, like the sea in a cave' and says Aurel had never heard it before. These are contradictory descriptions of the same event (the council hearing noise from the lower city during their meeting), with Chapter 8 explicitly contrasting the current sound with a previous 'roar of a riot' while Chapter 2 presents this very noise as a novel 'roar' Aurel never heard before. |
| false alarm | D5 | ch8 | King Aurel | attribute | Chapter 8 states Corvin took the signet ring off his finger and held it out across the table. Chapter 2 states Aurel sat on the edge of the little bed and turned the signet ring on his finger. Since a signet ring is a unique object typically worn by one person (the king/regent), and Chapter 1 shows Aurel pressing his father's signet ring into wax, the ring appears to have moved from Aurel's finger (Chapter 2) to Corvin's finger (Chapter 8) without explanation. This suggests a contradiction in who possesses the signet ring. |
| false alarm | - | ch8 | King Aurel | attribute | Chapter 6 states Aurel was given a 'grey colt' (young male horse) from the royal stud. Chapter 8 describes Pell leading an 'old grey stallion' (adult male horse) from the royal stables. A colt cannot become an old stallion in the few months between chapters 6-8 (chapter 6 is 14 years before the fall, chapter 7 is 4 months later, chapter 8 continues after chapter 7). This is an attribute contradiction: the horse's age and maturity level are fundamentally different without explanation. |
| false alarm | - | ch8 | King Aurel | attribute | Same as pair 21: chapter 6 establishes a 'grey colt' (young horse) given to Aurel, while chapter 8 describes an 'old grey stallion' being led from the royal stables. The timeline (only months between chapters) makes it impossible for a colt to become an old stallion. This contradicts the established attribute of the horse's age. |

Decoys wrongly flagged: D1, D2, D5

**Check by hand:** A4, A5, T1. A warning counted as a false alarm has the right chapter, entity and new detail for these items; only its earlier side is worded differently from the answer key. If it is right, the item was caught.

## What the double-check removed

23 warnings dismissed: 23 were false alarms; real mistakes wrongly removed: none.

- ch2 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch2 · King Aurel: Double-check: The earlier quote describes a fresh hand scar; the new quote describes legs giving out from emotional shock while reading a dispatch, with the scar aching 'the way it always did now.' This is consistent: an old injury aching during a new crisis, not a contradiction.
- ch2 · Venn fleet: Double-check: The earlier quote refers to the Venn fleet destroyed at Greywater. The new quote explicitly says 'the Vessmark fleet' was caught at Kettle Rocks and 'sixty came home.' They describe different fleets in different battles; the warning misattributes the new quote to the Venn fleet.
- ch2 · Tam: Set aside: the warning's own explanation says the two facts are consistent.
- ch2 · Vessmark fleet: Double-check: The earlier quote says the Venn fleet was broken at Greywater. The new quote describes 'Nine hundred and forty ships' riding at anchor — this is Aurel's newly built Vessmark fleet (note: 'not quite the thousand Aurel had promised'), not the old Venn fleet. Different fleets, no contradiction.
- ch3 · Bram Holloway: Double-check: Chapter 1 is set shortly before the fleet's departure; Chapter 3 is set two years after departure. A two-year age increase from 64 to 66 is exactly what the timeline predicts, so this is normal story progression, not a continuity error.
- ch4 · Pell: Double-check: Duplicate of warning 2. Both flag the same age discrepancy for Pell (15 vs 17) across the same chapters. Keeping both would be redundant.
- ch4 · Castle of Harrowmere: Set aside: the warning's own explanation says the two facts are consistent.
- ch4 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch4 · Venn: Double-check: The warning itself notes the two quotes are consistent: chapter 2 calls her 'Admiral Saska Venn,' chapter 4 calls her 'Admiral, once.' No contradiction.
- ch4 · Venn: Double-check: Same as warning 6. The quotes are consistent; 'Admiral, once. Smuggler, now.' aligns with having lost Greywater and being hated for it.
- ch4 · King Aurel: Double-check: The warning states this is 'consistent with Aurel's scar origin.' Chapter 2 mentions the scar aching; chapter 4 gives the origin story (Aurel's own hook during a rescue on the Salt Hawk). No contradiction is claimed or evident.
- ch4 · Vessmark fleet: Set aside: the story moving forward (something that existed earlier in story time has 'sank' later). Only the reverse would be a mistake.
- ch5 · King Aurel: Double-check: Thessaly and Liesl can be the same person (queen's title vs. personal name). The phrasing 'raised by the man who took my crown' fits Corvin (Chapter 3) and is a status change, not a contradiction of identity.
- ch5 · Pell: Double-check: Chapter 3 says Pell is 'a boy without a horse'; Chapter 5 shows him in a convent kitchen with a cooking burn. No direct contradiction—he could have lost the horse and later ended up at the convent. This is a plausible progression, not an impossibility.
- ch5 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch6 · King Aurel: Double-check: Chapter 6 says Aurel had never been in a battle *at coronation* (14 years before fall). Chapter 3 (set 12 years after Greywater / 2 years after fleet departure) says 'Aurel had won a war' in the past tense. The war could have been fought and won in the intervening years. This is a plausible progress
- ch7 · King Oren: Set aside: the story moving forward (something that existed earlier in story time has 'burned' later). Only the reverse would be a mistake.
- ch7 · Dun valley: Double-check: Chapter 4 says the Dun valley people 'are eating bark again' at that time (12 years after Greywater). Chapter 7 says 'Four months later, the people... had stopped eating bark' (14 years before the fall/4 months after Chapter 6). These are different time periods; a situation can change over years. Th
- ch7 · Mother: Double-check: Chapter 5 references 'the winter King Oren died.' Chapter 7 says the grandmother starved 'the winter after the Kell war.' These could be the same winter or closely linked events; the quotes don't prove they are different. Without evidence the Kell war and Oren's death are separated, this is not a cl
- ch7 · council meeting: Double-check: Chapter 3 describes a council meeting 'the next day' (12 years after Greywater). Chapter 7 states 'The council meets at the spring equinox' (14 years before the fall). These are different time periods (likely years apart) and possibly different councils. The quotes don't establish they refer to the 
- ch8 · Duke Corvin: Double-check: The quotes describe different characters and different actions. Chapter 3 shows Duke Corvin sitting in the king's chair; Chapter 8 shows a first-person narrator ('I') locking grain away. The warning misattributes the Chapter 8 quote to Corvin and invents a connection that doesn't exist.
- ch8 · Ember: Set aside: the warning's own explanation says the two facts are consistent.

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

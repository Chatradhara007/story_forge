# StoryForge evaluation — fallenking — 2026-10-05 14:19

Reader: `nvidia/nemotron-3.5-lightning-30b-a3b` · Judge: `nvidia/nemotron-3.5-lightning-30b-a3b` · Embedding model: `nvidia/nemotron-3-embed-1b` · Time: 894s · AI requests per run: 97 accepted, 0 refused
Parallel AI calls: 4 · Thinking (reading): off · Thinking (judging): off · Temperature: reader 0.0, judge 0.0 · Reading passage size: 700 characters

## Where the time went

| Stage | Seconds (all chapters) |
|---|---|
| reading facts | 0 |
| linking names | 154 |
| preparing search | 36 |
| story clock | 2 |
| checking for mistakes | 268 |
| safety-net check | 444 |
| double-checking | 222 |
| saving | 38 |

*Checking, story clock and safety net run at the same time, so their times overlap: the rows add up to more than the total time.*

## Time per chapter

| Chapter | Words | Facts | Reading (s) | Judging (s) |
|---|---|---|---|---|
| ch1 | 906 | 81 | saved | 56.1 |
| ch2 | 795 | 63 | saved | 103.6 |
| ch3 | 823 | 87 | saved | 93.5 |
| ch4 | 828 | 84 | saved | 84.3 |
| ch5 | 922 | 92 | saved | 151.5 |
| ch6 | 726 | 74 | saved | 105.0 |
| ch7 | 985 | 91 | saved | 124.2 |
| ch8 | 1,078 | 76 | saved | 175.2 |

**Judging:** 120 s per chapter on average (chapters after the first; the first has nothing earlier to compare). 7,063 words in 8 chapters.

## Contradiction detection

| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |
|---|---|---|---|---|---|---|
| 6% | 36% | 0.11 | 4 / 11 | 60 | 0 | 100% |

| Type | Planted | Caught | Recall |
|---|---|---|---|
| attribute | 5 | 4 | 80% |
| status | 3 | 0 | 0% |
| timeline | 3 | 0 | 0% |

## Missed mistakes

- **A4** (ch7): Mira is four years younger than Aurel (ch5) but his elder sister (ch7).
- **S1** (ch4): Aurel gave the signet ring to Corvin (ch3) but turns it on his own finger as a ferryman (ch4).
- **S2** (ch4): Ember had to be left behind in Vessa (ch3) but Pell rubs him down at the ferry hut (ch4).
- **S3** (ch7): Queen Liesl is nearly blind (ch5) but writes in her own careful hand and reads his letters (ch7).
- **T1** (ch7): Aurel is 35 (ch4); four months later he turns thirty-eight (ch7).
- **T2** (ch8): The fleet sank in the autumn storms (ch2) but 'the spring storm at the Kettle Rocks' (ch8).
- **T3** (ch7): Bram is 64 at Greywater (ch1) and 66 at the fall (ch3), but 'sixty-two now' years later (ch7).

## Why each mistake was missed

Causes: *not read* = the Reader didn't record the detail; *split* = the details were filed under different entries (a name-linking problem); *checker* = both were on the same entry but weren't flagged.

- **A4** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch1: [King Aurel] King Aurel | relationship | parent of Tam
    - ch1: [Prince Tam] Tam | relationship | child of King Aurel
    - ch1: [Queen Thessaly] Queen Thessaly | relationship | parent of Tam
    - ch1: [Prince Tam] Tam | relationship | child of Queen Thessaly
    - ch7: [King Aurel] Aurel | relationship | sibling of elder sister of Aurel
    - ch7: [Mira] elder sister of Aurel | relationship | sibling of Aurel
    - ch7: [King Aurel] Aurel | purpose | here with wheat, and with my elder sister who is a healer, and with a boy named Pell who keeps better accounts than my old treasurer
    - ch7: [Mira] elder sister of Aurel | role | healer
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
- **T3** → **checker**: Both details were on the same entry, but the checker didn't flag them.
    - ch1: [Bram Holloway] Bram Holloway | age | sixty-four years old
    - ch1: [Bram Holloway] Bram Holloway | role | swordmaster who had taught Aurel to hold a blade when he was seven
    - ch3: [Bram Holloway] Bram Holloway | age | sixty-six years old
    - ch7: [Bram Holloway] Bram Holloway | age | sixty-two

## Every warning raised

| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |
|---|---|---|---|---|---|
| false alarm | - | ch2 | King Aurel | timeline | King Aurel is 7 in chapter 1 and the chapter timing notes say about 2 years pass in between, so King Aurel should be about 9 in chapter 2, but the text says 33. |
| false alarm | - | ch3 | Bram Holloway | timeline | Bram Holloway is 64 in chapter 1 and the chapter timing notes say about 4 years pass in between, so Bram Holloway should be about 68 in chapter 3, but the text says 66. |
| false alarm | - | ch3 | Pell | timeline | Pell is 15 in chapter 2 and the chapter timing notes say about 2 years pass in between, so Pell should be about 17 in chapter 3, but the text says 15. |
| false alarm | - | ch3 | King Oren | status | King Oren is deceased (implied - fought for by Bram after him) in chapter 1, but in chapter 3 action: will retire to Harrowmere. No flashback is recorded in between. |
| false alarm | - | ch3 | Duke Corvin | status | Duke Corvin is seven dead in the market square in chapter 2, but in chapter 3 action: looked at Aurel directly. No flashback is recorded in between. |
| false alarm | - | ch3 | Castle of Harrowmere | attribute | In chapter 1, Aurel gave the castle of Harrowmere to Duke Corvin as a reward. In chapter 3, someone is told they will retire to 'the castle you gave me,' implying Aurel gave it to them instead. This is a direct contradiction about who received the castle from Aurel. |
| false alarm | - | ch3 | Harrowmere | attribute | Chapter 1 establishes that Aurel gave the castle of Harrowmere to Duke Corvin. Chapter 3 has someone being told to retire to Harrowmere, 'to the castle you gave me,' implying Aurel gave it to the listener. This contradicts the established recipient of the castle. |
| false alarm | - | ch3 | Prince Tam | attribute | In chapter 2 (two years after the fleet disaster), Prince Tam is explicitly stated to be six years old. In chapter 3 (two years after the council/abdication), he is described as 'coming of age,' which typically means reaching legal adulthood (usually 16-21). Even with a two-year time skip, he would only be eight, making 'comes of age' a contradiction unless the age of majority is implausibly low or the time skip is much longer than stated. |
| false alarm | - | ch3 | Venn fleet | status | Chapter 1 establishes the Venn fleet was broken on the shoals of Greywater Bay (implying wrecked in shallow coastal waters). Chapter 3 states nine hundred ships are at the bottom of the sea (implying deep water sinking). These are mutually exclusive locations for the same fleet disaster. |
| false alarm | - | ch3 | Prince Tam | attribute | Chapter 1 states Tam is four years old. Chapter 3 (set two years after chapter 2, which itself is two years after chapter 1) describes Tam as a six-year-old. With a four-year time skip, Tam should be eight, not six. This is an age contradiction. |
| false alarm | - | ch3 | King Aurel | attribute | Chapter 1 states Tam is four years old. Chapter 3 (set four years after chapter 1) describes Tam as a six-year-old. With a four-year time skip, Tam should be eight, not six. This is an age contradiction. |
| false alarm | - | ch3 | Prince Tam | attribute | Chapter 1 states Tam is four years old. Chapter 3 (set four years after chapter 1) describes Tam as a six-year-old. With a four-year time skip, Tam should be eight, not six. This is an age contradiction. |
| false alarm | - | ch3 | Queen Thessaly | attribute | Chapter 1 states Tam is four years old. Chapter 3 (set four years after chapter 1) describes Tam as a six-year-old. With a four-year time skip, Tam should be eight, not six. This is an age contradiction. |
| false alarm | - | ch3 | crowned salt-hawk | status | In chapter 2, Aurel is still wearing/turning the signet ring on his finger, indicating he possesses it. In chapter 3, Duke Corvin takes the same signet ring and puts it on his own finger ('slid the signet ring onto his own finger'), implying a transfer of possession without explanation. Since the signet ring is a unique object symbolizing authority, and Aurel was using it in the immediately preceding chapter (chronologically), Corvin taking it constitutes a status contradiction — the ring cannot be on both men's fingers simultaneously without a transfer being shown or explained. |
| false alarm | - | ch3 | Duke Corvin | timeline | Chapter 3 lists 'Seven dead in the market square' as a current, ongoing crisis ('The riots in the lower city. Seven dead in the market square. The southern merchants refusing credit. The guild masters threatening to close the city gates...'). But Chapter 2 (two years earlier) describes this as a past event: 'Corvin came back at dusk with blood on his sleeve and seven dead in the market square.' The same specific event (seven dead in the market square) cannot be both a completed past event and a current ongoing situation two years later. |
| false alarm | - | ch3 | crowned salt-hawk | status | Chapter 2 states Aurel is turning the signet ring on his finger, confirming it fits him (or at least he wears it). Chapter 3 says the same signet ring is 'a little too big for him [Corvin]. He wore it anyway.' This implies the ring was sized for Aurel (or a larger finger), but Corvin now wears it. While not a direct logical impossibility, the ring's fit changing between wearers without explanation — especially when Aurel was just using it — suggests an inconsistency in the physical continuity of the object. Combined with pairs 11 and 12, this reinforces a status contradiction: the ring has moved from Aurel to Corvin without narrative justification. |
| false alarm | - | ch4 | Prince Tam | timeline | Prince Tam is 6 in chapter 2 and the chapter timing notes say about 4 years pass in between, so Prince Tam should be about 10 in chapter 4, but the text says 8. |
| false alarm | - | ch4 | Duke Corvin | status | Duke Corvin is seven dead in the market square in chapter 2, but in chapter 4 action: moved Prince Tam out of the castle. No flashback is recorded in between. |
| false alarm | - | ch4 | Pell | attribute | Pell's age is stated as seventeen in chapter 4, but chapter 3 (which is set at the same time as chapter 4, both 'two years after the council / after the abdication') states Pell is fifteen. Since both chapters are set at the same point in the timeline, Pell cannot be both fifteen and seventeen simultaneously. This is a direct age contradiction. |
| correct | A5 | ch4 | Admiral Saska Venn | attribute | New fact claims Saska Venn watched all 990 ships go down (implying total loss), but existing fact states 60 ships survived and came home. These are mutually exclusive accounts of the same event (the fleet disaster at Kettle Rocks). |
| false alarm | - | ch4 | Pell | attribute | Rell is stated to be 35 years old in chapter 4, while Pell is stated to be 15 in chapter 3. The narrative strongly implies Rell and Pell are the same person (the ferryman's backstory matches Pell's history: 'thirty-three years of everyone looking at him' aligns with Pell's royal upbringing, and the scar on the left hand matches Pell's injury from chapter 2). A 20-year age difference for the same character at the same story time (both chapters set two years after the council) is a direct attribute contradiction. |
| false alarm | - | ch4 | King Aurel | attribute | Rell's left hand has an 'old pale scar' that is 'rough with rope burns' in chapter 4. King Aurel's left hand has a 'pale line where a Venn boarding hook had opened him to the bone' in chapter 1, still fresh. The scar origin (boarding hook vs. rope burns) and description (fresh wound vs. old, rope-roughened scar) contradict for the same hand of the same character (Rell = Aurel). |
| false alarm | - | ch4 | Prince Tam | timeline | Prince Tam is 8 in chapter 4 (received into Lord Regent's household), but was 4 in chapter 1. Chapter 4 is set two years after the council/abdication; chapter 1 is immediately before. Even with a two-year gap, Tam ages 4 years in ~2 years, a timeline contradiction. |
| false alarm | - | ch4 | Venn fleet | attribute | Saska Venn claims to have two ships in Chapter 4, but Chapter 3 states nine hundred ships and their crews are at the bottom of the sea. Given the context of the fleet disaster and Saska's role as admiral who lost Greywater, this is a direct contradiction in the number of ships she commands, with no in-story explanation for how she acquired two ships after the entire fleet was destroyed. |
| false alarm | - | ch4 | Pell | attribute | Chapter 4 describes Pell as 'broad in the shoulders from hauling the ferry chain' while chapter 3 (same timeline) describes him as 'tall and all elbows'. These are contradictory physical descriptions for the same character at the same time. 'Broad in the shoulders' suggests a stocky, muscular build from labor, while 'tall and all elbows' suggests a lanky, awkward adolescent frame. Both cannot be true simultaneously without explanation. |
| false alarm | - | ch4 | Queen Thessaly | attribute | Chapter 3 identifies Thessaly as Tam's parent ('Thessaly was there...'). Chapter 4 identifies Vessa as Tam's mother ('Away from his mother'). Unless Vessa and Thessaly are the same person (not established), this contradicts Tam's maternity. |
| false alarm | - | ch4 | Venn | status | Saska Venn says she'll be at the Lamb and Anchor in Dunmouth for a week in Chapter 4, but Chapter 2 places her on the cliffs of Venn, having spent two years there being hated by her people after losing Greywater. The chapters are set at the same time (both 'two years after the council/abdication'), so she cannot be in two places simultaneously without explanation. |
| false alarm | - | ch4 | Venn | timeline | Saska Venn's statement about staying a week at the Lamb and Anchor in Chapter 4 contradicts Chapter 2's description of her spending two years on the cliffs of Venn. Both chapters are set at the same time point ('two years after the council/abdication'), making it impossible for her to have both just arrived for a week and have been there for two years. |
| false alarm | - | ch5 | Duke Corvin | timeline | Duke Corvin is 2 in chapter 1 and the chapter timing notes say about 8 years pass in between, so Duke Corvin should be about 10 in chapter 5, but the text says 17. |
| false alarm | - | ch5 | King Aurel | timeline | King Aurel is 33 in chapter 2 and the chapter timing notes say about 6 years pass in between, so King Aurel should be about 39 in chapter 5, but the text says 8. |
| false alarm | - | ch5 | King Oren | status | King Oren is deceased (implied - fought for by Bram after him) in chapter 1, but in chapter 5 action: marched on the salt coast with every soldier in Vessmark. No flashback is recorded in between. |
| false alarm | - | ch5 | Duke Corvin | status | Duke Corvin is seven dead in the market square in chapter 2, but in chapter 5 comes later; if Aurel goes to Corvin first, he's just a man who wants his chair back: comes later. If I go to Corvin first, I'm just a man who wants his chair back.. No flashback is recorded in between. |
| false alarm | - | ch5 | Queen Liesl | attribute | New fact states Queen Liesl is the mother of the king, but existing facts establish King Aurel is married to Queen Thessaly and they have a son Tam. This suggests Queen Thessaly is the queen consort and mother of the heir, making Queen Liesl's relationship as 'mother of the king' contradictory unless she is a former queen or queen mother, which is not established. |
| correct | A1 | ch5 | Ember | attribute | Chapter 5 describes Ember as a 'black stallion' while Chapter 1 and Chapter 2 both describe Ember as a 'grey stallion'. This is a direct attribute contradiction (coat color) with no in-story explanation for the change. |
| false alarm | - | ch5 | King Aurel | attribute | In chapter 5, Liesl says 'my son is eight years old and being raised by the man who took my crown.' In chapter 4, Aurel has 'his father's signet ring' and is clearly an adult king. Aurel cannot be both an 8-year-old child and an adult king who wears his father's signet ring. This is an attribute contradiction: age and role are incompatible. |
| false alarm | - | ch5 | Queen Thessaly | attribute | In chapter 5, Liesl says 'my son is eight years old and being raised by the man who took my crown.' In chapter 4, Aurel says 'I need to see my mother.' If Aurel is Liesl's son and is 8, he cannot be the adult king speaking in chapter 4. Contradiction in age and identity. |
| false alarm | - | ch5 | Queen Thessaly | attribute | In chapter 5, Oren says 'my son' (referring to an 8-year-old). In chapter 4, Aurel says 'I need to see my mother.' If Oren is Aurel's father, then Aurel is Oren's son. But Liesl (chapter 5) says her son is 8 and raised by the man who took her crown. Oren is the king who died (chapter 1). If Oren is the father of an 8-year-old, that child cannot be Aurel (31+). Contradiction in parentage and age. |
| false alarm | - | ch5 | King Oren | attribute | In chapter 5, 'Her blind eyes looked somewhere past him' refers to Liesl (nearly blind, 71). The text says 'Her blind eyes looked somewhere past him' in context of 'my son is eight...' implying Liesl is looking at her son. But in chapter 1, 'Aurel's father, King Oren' establishes Oren as Aurel's father. If Liesl is Aurel's mother, then Oren is her husband. But then 'Her blind eyes looked somewhere past him' would be Liesl looking at Aurel (her son). But Aurel is 31, not 8. Contradiction in age. |
| false alarm | - | ch5 | King Aurel | attribute | In chapter 5, Oren is described as the child of Aurel ('Her blind eyes looked somewhere past him' — Liesl looking at Oren? But Oren is dead). Chapter 1 says 'Aurel's father, King Oren'. So Oren is Aurel's father, not child. This is a direct relationship reversal: chapter 5 implies Oren is Aurel's son (Liesl's son, 8 years old), but chapter 1 says Oren is Aurel's father. Contradiction in parentage. |
| false alarm | - | ch5 | Queen Liesl | timeline | Chapter 5 states Queen Liesl is 71 years old. Chapter 3 (two years earlier) refers to 'the queen and the prince' under protection. If this queen is Liesl, she would have been 69 in Chapter 3. However, Chapter 1 shows Queen Thessaly as queen with a 4-year-old son Tam. A 69-year-old queen having a 4-year-old son is biologically implausible, suggesting 'the queen' in Chapter 3 is Thessaly, not Liesl — but then Liesl's age and role remain unexplained and potentially contradictory. |
| false alarm | - | ch6 | King Aurel | timeline | King Aurel is 2 in chapter 5 and the chapter timing notes say about 14 years pass in between, so King Aurel should be about 16 in chapter 6, but the text says 19. |
| false alarm | D2 | ch6 | Bram Holloway | timeline | Bram Holloway is 66 in chapter 3 and the chapter timing notes say about 18 years pass in between, so Bram Holloway should be about 84 in chapter 6, but the text says 52. |
| false alarm | - | ch6 | Duke Corvin | timeline | Duke Corvin is 17 in chapter 5 and the chapter timing notes say about 14 years pass in between, so Duke Corvin should be about 31 in chapter 6, but the text says 17. |
| false alarm | - | ch6 | King Oren | status | King Oren is deceased (implied - fought for by Bram after him) in chapter 1, but in chapter 6 cause of death: fever. No flashback is recorded in between. |
| false alarm | - | ch6 | Duke Corvin | status | Duke Corvin is seven dead in the market square in chapter 2, but in chapter 6 loyalty statement: I am yours. No flashback is recorded in between. |
| false alarm | D1 | ch6 | King Aurel | attribute | New fact states Aurel had no scar on his left hand at coronation (14 years before fall), but existing fact from chapter 1 (present day) describes a fresh scar from a Venn boarding hook. Chapter 4 reveals the scar originated at Greywater during a battle, which must have occurred after coronation since Aurel had never been in a battle at coronation (new fact 11). However, chapter 1 describes the scar as 'still fresh' when Aurel is 31, implying recent injury, not a 14-year-old scar. This creates a timeline contradiction about when the scar was acquired and its condition in chapter 1. |
| false alarm | - | ch6 | King Aurel | status | New fact states Aurel had never been in a battle at coronation (age 19), but existing fact from chapter 3 says 'Aurel had won a war'. Since chapter 3 occurs after chapter 2 (2 years after council/abdication) and coronation was 14 years before fall, there's time for him to have fought a war. However, chapter 1 shows Aurel as king planning to build ships and sail to Venn isles to 'end the war', suggesting the war is ongoing or not yet won. The contradiction is that 'won a war' (past tense, completed) conflicts with chapter 1's context of preparing for war. |
| false alarm | - | ch6 | Ember | attribute | Chapter 1 and 2 establish Ember as a 'grey stallion' (facts 0 and 1). Chapter 3 also refers to Ember without color contradiction. Chapter 5 (existing fact 3) explicitly calls Ember 'the black stallion'. The new chapter 6 fact 0 simply names him 'Ember' without color, but the existing fact 3 from chapter 5 directly contradicts the established 'grey' color from earlier chapters. Since chapter 5 occurs after chapters 1-4 in reading order (time skip: two years after abdication), and chapter 6 is also 'two years after the council / after the abdication' (same timeframe as chapters 2-5), the color discrepancy between 'grey' (chapters 1,2) and 'black' (chapter 5) is a contradiction in established attributes. |
| false alarm | - | ch6 | King Aurel | attribute | New fact describes Aurel as 'twenty years old and immortal' (at coronation +1 year), but existing fact from chapter 1 states he is 'thirty-one years old' with no mention of immortality. If he were immortal, his age would not progress normally, yet he ages from 19 to 31 over 12 years (14 years before fall to chapter 1). The term 'immortal' contradicts normal aging unless explained by story context (e.g., metaphorical). No such explanation exists in provided facts. |
| false alarm | - | ch6 | riot in the lower city | attribute | Pair 1: New chapter 6 says Aurel asked Thessaly to marry him ('By the end of the summer he had asked her to marry him'), while chapter 2 says 'She knelt beside him' (Thessaly knelt beside Aurel). The kneeling action is traditionally associated with proposing. If Thessaly knelt beside Aurel, she likely proposed to him, contradicting the new claim that Aurel proposed to her. High confidence they refer to the same proposal event. |
| false alarm | - | ch6 | King Oren | timeline | Chapter 6 states King Oren died and Aurel was crowned 'fourteen years before the fall' on 'the coldest morning of the year'. Chapter 5 refers to 'the winter King Oren died' without specifying a year. Chapter 5 is set 'two years after the abdication' (same as Chapters 2-4), while Chapter 6 is set 'fourteen years before the fall / two years after the council / after the abdication'. If 'the fall' is a future event from Chapter 5's perspective, then 'fourteen years before the fall' could align with 'two years after the abdication' only if the fall occurs 16 years after the abdication. But Chapter 5's 'winter King Oren died' suggests the death was recent (within a few years), not 14 years before a future fall. This creates a timeline contradiction about when King Oren died relative to the abdication and the fall. |
| false alarm | - | ch6 | King Oren | timeline | Chapter 6 dates the coronation (and King Oren's death) to 'fourteen years before the fall'. Chapter 1 shows King Aurel already reigning with Queen Thessaly, set 'immediately after Chapter One' (which is before the time skips). Chapter 1 does not mention a recent coronation. If the coronation was 14 years before the fall, and Chapter 1 is set before the fall, then the coronation should be in the past. But Chapter 1 presents King Aurel as established, not newly crowned. The timeline between Chapter 1 and Chapter 6's 'fourteen years before the fall' is unclear, creating a potential timeline contradiction about the coronation date. |
| false alarm | - | ch7 | Pell | timeline | Pell is 17 in chapter 4 and the chapter timing notes say about 16 years pass in between, so Pell should be about 33 in chapter 7, but the text says 17. |
| false alarm (check by hand: maybe T1) | - | ch7 | King Aurel | timeline | King Aurel is 20 in chapter 6 and no time skip is recorded in between, so King Aurel should be about 20 in chapter 7, but the text says 38. |
| false alarm (check by hand: maybe T3) | - | ch7 | Bram Holloway | timeline | Bram Holloway is 52 in chapter 6 and no time skip is recorded in between, so Bram Holloway should be about 52 in chapter 7, but the text says 62. |
| false alarm | - | ch7 | King Oren | status | King Oren is deceased (implied - fought for by Bram after him) in chapter 1, but in chapter 7 action: Burned coastal fields on the way to the river during the Kell war.. No flashback is recorded in between. |
| false alarm (check by hand: maybe A4) | - | ch7 | King Aurel | attribute | Chapter 7 refers to Aurel's 'elder sister' (implying she is older than Aurel). Chapter 5 states 'The third was his own sister, Mira' — listing her as the third child, which would make her younger than at least two siblings, one of whom is presumably Aurel (the heir). If Aurel is the eldest or second-born, Mira cannot be his elder sister. This is an attribute contradiction about birth order. |
| correct | A2 | ch7 | King Aurel | attribute | Chapter 7 describes a scar on Aurel's right hand and a matching forehead scar. Chapter 2 mentions a scar on the back of his left hand. Chapter 4 (existing fact 17) says the hook went into Aurel's hand while trying to pull someone off the Salt Hawk at Greywater, but doesn't specify which hand. Chapter 6 (existing fact 31) explicitly states 'Aurel had no scar on his left hand then' (at coronation, 14 years before fall). The new facts claim a right-hand scar matching the forehead, while earlier chapters reference a left-hand scar. |
| false alarm | - | ch8 | King Aurel | status | King Aurel is I am Aurel, who was your king. I sold the grain your fathers stored. I sank the fleet. Your sons drowned at the Kettle Rocks because of me. I am not here to ask for anything. I am here with wheat, and with my elder sister, who is a healer, and with a boy named Pell who keeps better accounts than my old treasurer. Bring your sick to my sister. Bring your hungry to the carts. in chapter 7, but in chapter 8 heard a sound: thousands of feet walking and faintly singing. No flashback is recorded in between. |
| false alarm | - | ch8 | Duke Corvin | status | Duke Corvin is seven dead in the market square in chapter 2, but in chapter 8 action: rose. No flashback is recorded in between. |
| correct | A3 | ch8 | Queen Thessaly | attribute | Chapter 8 describes Thessaly's eyes as 'dark brown', while Chapter 1 and Chapter 6 consistently describe them as 'grey-green'. Eye color is a fixed physical attribute that cannot change without explanation (e.g., magic, injury, disguise), and no such explanation is provided. |
| false alarm | - | ch8 | Duke Corvin | timeline | New fact 2 states 'It was the first time he had stood for his cousin since the morning he took the chair', implying Corvin had not stood for Aurel since the abdication morning. Existing fact 27 from chapter 6 states 'His cousin Corvin knelt second' during the abdication ceremony, meaning Corvin did stand/kneel for Aurel at that time. This creates a timeline contradiction about whether Corvin stood for Aurel at the abdication. |
| false alarm | - | ch8 | riot in the lower city | status | Chapter 8 states the regent has a cellar full of grain at Harrowmere, but chapter 2 describes a group at the gates of the old granary finding nothing inside. This is a status contradiction: the grain's existence and location conflict between chapters. |
| false alarm | D4 | ch8 | Ember | attribute | Chapter 8 describes Ember as having 'white around the muzzle' and being 'too old now to carry a king into battle', while Chapter 6 describes Ember as a colt that 'threw Aurel eleven times before he would let him stay on'. The physical description of age/white muzzle contradicts the earlier depiction of Ember as a young colt being trained. |

Decoys wrongly flagged: D1, D2, D4

**Check by hand:** A4, T1, T3. A warning counted as a false alarm has the right chapter, entity and new detail for these items; only its earlier side is worded differently from the answer key. If it is right, the item was caught.

## What the double-check removed

29 warnings dismissed: 29 were false alarms; real mistakes wrongly removed: none.

- ch2 · Prince Tam: Set aside: the warning's own explanation says the two facts are consistent.
- ch2 · Pell: Set aside: the warning's own explanation says the two facts are consistent.
- ch2 · King Aurel: Double-check: The warning misreads the quotes. Chapter 1 shows Aurel *planning* to build 1,000 ships over two summers. Chapter 2 (set two years after the fleet disaster) reveals the *actual* fleet numbered 940 ships—'not quite the thousand Aurel had promised.' A plan falling short of its target is not a contradic
- ch2 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch2 · Prince Tam: Set aside: the warning's own explanation says the two facts are consistent.
- ch2 · King Aurel: Double-check: The warning itself notes the relationship is consistent: Tam is Aurel's son in both chapters. No contradiction exists.
- ch2 · Prince Tam: Double-check: The warning itself notes the action is consistent: Aurel kisses his son Tam on the forehead in both chapters. No contradiction exists.
- ch2 · King Aurel: Set aside: the warning's own explanation says the two facts are consistent.
- ch2 · Duke Corvin: Set aside: the warning's own explanation says the two facts are consistent.
- ch3 · King Aurel: Set aside: the story moving forward (something that existed earlier in story time has 'scarred' later). Only the reverse would be a mistake.
- ch3 · Lord Treasurer: Double-check: Chapter 2 says the reserve was sold to southern merchants two years before chapter 2 (i.e., four years before chapter 3). Chapter 3 lists 'southern merchants refusing credit' as a current crisis. A long-standing condition from a past sale can become a new, acute refusal; this is plausible storytelli
- ch5 · King Aurel: Double-check: The two quotes describe different events: Chapter 1 says Oren taught Aurel to hold a blade at age seven; Chapter 5 says Oren marched on the salt coast when Aurel was two. These are not the same campaign, so no contradiction.
- ch5 · Dun valley: Double-check: Chapter 5 describes Aurel making a promise ('never let them starve again') during a past visit. Chapter 4, set two years later, shows the promise was broken — people are eating bark 'again'. This is a narrative consequence, not a contradiction: a promise made and later unfulfilled.
- ch5 · Rell: Set aside: the story moving forward (something that existed earlier in story time has 'lost' later). Only the reverse would be a mistake.
- ch5 · Dun valley: Double-check: Chapter 5's 'valley full of people eating bark' describes the same famine conditions as Chapter 4's 'eating bark again'. The word 'again' in Chapter 4 implies recurrence, which is consistent with Chapter 5 depicting an earlier or ongoing instance. No attribute contradiction — both describe starvatio
- ch6 · King Aurel: Double-check: Chapter 6 clearly establishes King Oren as Aurel's father and predecessor, while Chapters 1-2 reference King Aurel as the current monarch. This is a normal succession (father dies, son becomes king), not a contradiction about the same person having two names or identities. The warning misreads the r
- ch6 · King Oren: Double-check: Chapter 6's 'coldest morning of the year' is a specific day within winter, which is entirely consistent with Chapter 5's general 'the winter King Oren died.' A specific dramatic detail in a later chapter does not contradict a general seasonal reference in an earlier one; this is normal narrative ela
- ch7 · Dun valley: Double-check: This is normal story progression (rule 3). Chapter 4 states the people 'are eating bark again' (ongoing at that time). Chapter 7, set four months later, states they 'had stopped eating bark' (completed action by that later time). A situation changing over four months is not a contradiction; it's the
- ch7 · council meeting: Double-check: The quotes refer to different council meetings. Chapter 3 describes a specific meeting that happened 'the next day' after some prior event. Chapter 7 states a recurring rule: 'The council meets at the spring equinox' (annual schedule). A one-time meeting occurring the day before the equinox would no
- ch7 · King Aurel: Set aside: the story moving forward (something that existed earlier in story time has 'sank' later). Only the reverse would be a mistake.
- ch8 · King Aurel: Double-check: Timeline inconsistency: The son's age (8 at year 2, ~27 in chapter 8) conflicts with the description of Tam as a child and Aurel kneeling to be eye-level. However, the warning misreads the chapter 8 quote – Tam is described as 'taller than Aurel remembered, all knees and elbows', which actually supp
- ch8 · Admiral Saska Venn: Double-check: This is explained by the story moving forward and Aurel's actions: Chapter 7 states Aurel sold the grain his fathers stored. Chapter 8 shows Corvin locking the grain away every night. These are not opposite actions regarding the same grain – Aurel sold the family grain, and Corvin (as regent) is now
- ch8 · King Aurel: Double-check: Timeline inconsistency about Tam's height: Chapter 1 describes Aurel standing on the slipway with Tam on his shoulders. Chapter 8 describes Tam as 'taller than Aurel remembered, all knees and elbows'. However, this is not a continuity error – the chapters span significant time (chapter 1 is early in
- ch8 · Bram Holloway: Double-check: Age inconsistency across chapters: The warning lists multiple chapter ages for Bram (62, 64, 66, 52). However, the warning misreads the chapter 8 quote. Chapter 8 simply shows 'the old swordmaster looked at Aurel's cup for a long moment' – it does not provide a new age for Bram. The warning claims c
- ch8 · grain: Double-check: Harvest failure contradiction: The warning claims chapter 8 mentions harvest failed 'again' conflicts with chapter 7's wheat. However, chapter 7 states 'I am here with wheat' – bringing wheat does not contradict a failed harvest. A character can bring wheat while also acknowledging harvest failures.
- ch8 · council meeting: Double-check: Council meeting timing: The warning claims chapter 8's vote on the cellar contradicts chapter 3's council meeting timing. However, chapter 8 is set much later than chapter 3, and council procedures can change over time. The warning does not account for the story moving forward – new council meetings
- ch8 · King Aurel: Double-check: Grey horse timeline: Chapter 6 states Aurel was given a grey colt from the royal stud. Chapter 8 describes Pell leading an old grey stallion out of the royal stables. These are not necessarily the same horse – a colt grows into a stallion, and time has passed (chapter 6 to chapter 8 spans many years
- ch8 · King Aurel: Double-check: Same as warning 8 – this is a duplicate concern about the grey horse. The colt growing into a stallion and being led out of the royal stables is consistent with normal horse aging and the passage of time between chapters with time skips. Not a continuity error.
- ch8 · scrap of paper: Double-check: Scrap of paper attribute contradiction: The warning claims chapter 8 changes Aurel's quoted phrase from 'a king is a man who keeps the granaries full and the gates open' (chapter 6) to 'A man who knows how much a loaf costs' (chapter 8). However, chapter 8 quote 'A man who knows how much a loaf cost

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

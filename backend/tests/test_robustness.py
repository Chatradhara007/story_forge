"""
Robustness of the checks done in code (traits.py, states.py) on wording that is NOT from the
test stories: written on 18 Oct 2026 to check the rules aren't fitted to three stories. Each
case is a real mistake that must be flagged, or a legitimate change (dye, greying, shaving,
repainting, a new copy, someone else's eyes, a portrait...) that must stay silent.
The second set was written after the first was passing and only measured: 28/30 on first try.
"""
import pytest

from models import Fact
import states
import traits


def F(e, a, v, q="", t="character"):
    return Fact(entity=e, entity_type=t, attribute=a, value=v, source_quote=q or v, confidence=1.0)


def run(earlier, new, ids):
    ids = {k.lower(): v for k, v in ids.items()}
    stored = [{"fact_id": i, "entity_id": ids[e.lower()], "entity": f.entity, "entity_type": f.entity_type,
               "attribute": f.attribute, "value": f.value, "source_quote": f.source_quote,
               "chapter_id": f"ch{n}", "chapter_number": n} for i, (n, e, f) in enumerate(earlier)]
    new_facts = [(ids[e.lower()], e, f, i) for i, (e, f) in enumerate(new)]
    facts_for = lambda eid: [s for s in stored if s["entity_id"] == eid]
    find = lambda name: ids.get(name.lower())
    found = traits.check_traits("ch9", 9, new_facts, facts_for, find)
    objects = [s for s in stored if states.object_mentions(f"{s['value']} {s['source_quote']}")]
    return found + states.check_states("ch9", 9, new_facts, objects, facts_for, find, set())


P = "Mara"
ID = {"Mara": 1, "Dr Mara Quist": 1, "Quist": 1, "Jonah": 2, "the Albatross": 3, "Albatross": 3, "the locket": 4, "Rex": 5}
FIRST = [
 # eyes
 (1, "eyes: blue -> brown, adjective form", [(1, P, F(P, "appearance", "blue-eyed woman of forty"))], [(P, F(P, "appearance", "her brown eyes narrowed"))]),
 (1, "eyes: 'eyes were green' -> grey", [(1, P, F(P, "eye colour", "green"))], [(P, F(P, "description", "pale grey eyes"))]),
 (0, "eyes: hazel vs hazel-green", [(1, P, F(P, "eyes", "hazel"))], [(P, F(P, "eyes", "hazel-green eyes"))]),
 (0, "eyes: someone else's eyes in her fact", [(1, P, F(P, "eyes", "blue"))], [(P, F(P, "action", "stared into Jonah's black eyes", "She stared into Jonah's black eyes"))]),
 (0, "eyes: eyes red from crying", [(1, P, F(P, "eyes", "blue"))], [(P, F(P, "state", "eyes red from crying"))]),
 # sides
 (1, "side: tattoo left wrist -> right wrist", [(1, P, F(P, "body", "a tattoo on her left wrist"))], [(P, F(P, "body", "the tattoo on her right wrist"))]),
 (0, "side: different marks", [(1, P, F(P, "body", "scar on her left knee"))], [(P, F(P, "body", "tattoo on her right arm"))]),
 # handedness
 (1, "hand: right-handed -> writes with left hand", [(1, P, F(P, "trait", "right-handed"))], [(P, F(P, "action", "wrote the note with her left hand"))]),
 (0, "hand: holds cup in left hand (not handedness)", [(1, P, F(P, "trait", "right-handed"))], [(P, F(P, "action", "held the cup in her left hand"))]),
 # height
 (1, "height: 'tall woman' -> 'short woman'", [(1, P, F(P, "physical description", "a tall woman with cropped hair"))], [(P, F(P, "appearance", "the short woman by the door"))]),
 (0, "height: short temper / short-tempered", [(1, P, F(P, "physical description", "tall and thin"))], [(P, F(P, "personality", "short-tempered and loud"))]),
 (0, "height: tall glass / short story", [(1, P, F(P, "description", "tall"))], [(P, F(P, "description", "drank from a short glass"))]),
 (0, "height: child grew", [(1, P, F(P, "physical description", "a short girl of eight"))], [(P, F(P, "physical description", "tall now, nearly a woman"))]),
 # beard
 (1, "beard: thick black beard -> clean-shaven", [(1, "Jonah", F("Jonah", "appearance", "thick black beard"))], [("Jonah", F("Jonah", "appearance", "clean-shaven and pale"))]),
 (0, "beard: grew a beard", [(1, "Jonah", F("Jonah", "appearance", "clean-shaven"))], [("Jonah", F("Jonah", "appearance", "had grown a beard over the winter"))]),
 (0, "beard: stroked his father's beard", [(1, "Jonah", F("Jonah", "appearance", "clean-shaven"))], [("Jonah", F("Jonah", "memory", "tugged at his father's beard as a boy"))]),
 # boat colour
 (1, "boat: 'the Albatross, a green fishing boat' -> 'yellow hull'", [(1, "the Albatross", F("the Albatross", "description", "a green fishing boat", t="item"))], [("Albatross", F("Albatross", "description", "her yellow hull", t="item"))]),
 (0, "boat: repainted", [(1, "the Albatross", F("the Albatross", "description", "a green boat", t="item"))], [("Albatross", F("Albatross", "description", "freshly repainted, a yellow hull now", t="item"))]),
 # animal
 (1, "animal: 'Rex, a brown dog' -> 'black dog'", [(1, "Rex", F("Rex", "type", "brown dog", t="other"))], [("Rex", F("Rex", "description", "a black dog", t="other"))]),
 (0, "animal: muzzle grey with age", [(1, "Rex", F("Rex", "type", "brown dog", t="other"))], [("Rex", F("Rex", "description", "brown dog going grey at the muzzle", t="other"))]),
 # objects
 (1, "object: locket smashed -> she opens the locket", [(1, P, F(P, "action", "smashed the silver locket against the stones"))], [(P, F(P, "action", "opened the silver locket to look at the photograph"))]),
 (0, "object: lost then found", [(1, P, F(P, "action", "lost the silver locket in the river"))], [(P, F(P, "action", "found the silver locket in the mud and opened it"))]),
 (1, "object: gave key to Jonah -> she uses key", [(1, P, F(P, "action", "gave the iron key to Jonah", "Mara gave the iron key to Jonah"))], [(P, F(P, "action", "unlocked the gate with the iron key"))]),
 # abilities
 (1, "ability: blind -> reads newspaper", [(1, P, F(P, "condition", "completely blind since the accident"))], [(P, F(P, "action", "read the newspaper over breakfast"))]),
 (0, "ability: blind, someone reads to her", [(1, P, F(P, "condition", "blind"))], [(P, F(P, "habit", "had Jonah read the newspaper to her"))]),
 # mended
 (1, "mended -> still broken (clock)", [(1, "the locket", F("the locket", "state", "repaired by the jeweller", t="item"))], [("the locket", F("the locket", "state", "still broken, the hinge snapped", t="item"))]),
 # origin
 (1, "origin: born in Lisbon, never left -> moved to Lisbon", [(1, P, F(P, "background", "born in Lisbon", "She was born in Lisbon and never left the city."))], [(P, F(P, "history", "moved to Lisbon at twenty"))]),
 (0, "origin: born in Lisbon -> came to Paris", [(1, P, F(P, "background", "born in Lisbon", "She was born in Lisbon and never left the city."))], [(P, F(P, "history", "came to Paris at twenty"))]),
 # family
 (1, "family: Jonah her brother -> Jonah her cousin", [(1, P, F(P, "relationship", "sibling of Jonah", "her brother Jonah"))], [(P, F(P, "relationship", "cousin of Jonah", "her cousin Jonah"))]),
 (0, "family: brother-in-law vs brother? (different)", [(1, P, F(P, "relationship", "sibling of Jonah", "her brother Jonah"))], [(P, F(P, "relationship", "sibling of Jonah", "Jonah, her twin brother"))]),
 # older/younger
 (1, "order: Jonah her elder brother -> Jonah her little brother", [(1, P, F(P, "relationship", "sibling of Jonah", "her elder brother Jonah"))], [(P, F(P, "relationship", "sibling of Jonah", "Jonah, her little brother"))]),
 # hair (not implemented yet)
 (1, "hair: red-haired -> black hair", [(1, P, F(P, "appearance", "red-haired and freckled"))], [(P, F(P, "appearance", "her black hair tied back"))]),
 (0, "hair: dyed", [(1, P, F(P, "appearance", "red-haired"))], [(P, F(P, "appearance", "had dyed her hair black"))]),
 (0, "hair: greying with age", [(1, P, F(P, "appearance", "dark-haired"))], [(P, F(P, "appearance", "her hair grey now"))]),
]

ID2 = {"Ivo":1,"Ivo Brandt":1,"Captain Brandt":1,"Lena":2,"Lena Brandt":2,"the Heron":3,"Heron":3,"Biscuit":4,"Teo":5}
SECOND = [
 (1, "hair: 'Lena's fair hair' -> 'Lena, dark-haired'", [(1,"Lena",F("Lena","appearance","fair hair falling to her shoulders"))], [("Lena",F("Lena","description","dark-haired and serious"))]),
 (0, "hair: fair -> golden (same)", [(1,"Lena",F("Lena","appearance","fair-haired"))], [("Lena",F("Lena","appearance","her golden curls"))]),
 (0, "hair: brown -> white years later (ageing)", [(1,"Lena",F("Lena","appearance","brown hair"))], [("Lena",F("Lena","appearance","white hair pinned up"))]),
 (0, "hair: black hair under a red scarf", [(1,"Lena",F("Lena","appearance","black hair"))], [("Lena",F("Lena","clothing","a red scarf over her black hair"))]),
 (0, "hair: Teo's red hair in Lena's fact", [(1,"Lena",F("Lena","appearance","black hair"))], [("Lena",F("Lena","action","ruffled Teo's red hair"))]),
 (1, "eyes: 'Ivo had amber eyes' -> 'his blue eyes'", [(1,"Ivo",F("Ivo","appearance","amber eyes"))], [("Ivo",F("Ivo","look","his blue eyes went cold"))]),
 (0, "eyes: black eye (bruise)", [(1,"Ivo",F("Ivo","appearance","grey eyes"))], [("Ivo",F("Ivo","injury","a black eye from the fight"))]),
 (0, "eyes: blue eyes in a painting", [(1,"Ivo",F("Ivo","appearance","grey eyes"))], [("Ivo",F("Ivo","possession","a portrait of a woman with blue eyes"))]),
 (1, "side: limps on left leg -> scar right leg?", [(1,"Ivo",F("Ivo","injury","scar on his left leg"))], [("Ivo",F("Ivo","injury","the old scar on his right leg"))]),
 (0, "side: bandaged right hand (new injury, no mark word)", [(1,"Ivo",F("Ivo","injury","scar on his left hand"))], [("Ivo",F("Ivo","injury","bandaged his right hand"))]),
 (1, "hand: left-handed -> 'right-handed'", [(1,"Ivo",F("Ivo","trait","left-handed"))], [("Ivo",F("Ivo","trait","right-handed fencer"))]),
 (1, "height: 'very tall' -> 'a short, stocky man'", [(1,"Ivo",F("Ivo","physical_description","very tall, with long arms"))], [("Ivo",F("Ivo","physical_description","a short, stocky man"))]),
 (0, "height: 'short of breath'", [(1,"Ivo",F("Ivo","physical_description","tall"))], [("Ivo",F("Ivo","physical_description","short of breath after the stairs"))]),
 (0, "height: tall -> 'shorter than Lena'", [(1,"Ivo",F("Ivo","physical_description","tall"))], [("Ivo",F("Ivo","physical_description","shorter than Lena"))]),
 (1, "beard: 'grey-bearded' -> 'beardless face'", [(1,"Ivo",F("Ivo","appearance","grey-bearded and stooped"))], [("Ivo",F("Ivo","appearance","a beardless face"))]),
 (0, "beard: shaved for the wedding", [(1,"Ivo",F("Ivo","appearance","a long beard"))], [("Ivo",F("Ivo","appearance","clean-shaven for the wedding, he had shaved that morning"))]),
 (1, "boat: 'the Heron, a white skiff' -> 'red-painted hull'", [(1,"the Heron",F("the Heron","description","a white skiff",t="item"))], [("Heron",F("Heron","description","her red-painted hull",t="item"))]),
 (0, "boat: Ivo (a person) rowed a blue boat", [(1,"Ivo",F("Ivo","action","rowed a green boat"))], [("Ivo",F("Ivo","action","rowed a blue boat"))]),
 (1, "animal: 'Biscuit, the ginger cat' -> 'black cat'", [(1,"Biscuit",F("Biscuit","type","ginger cat",t="other"))], [("Biscuit",F("Biscuit","type","black cat",t="other"))]),
 (1, "object: threw the compass into the river -> consulted the compass", [(1,"Ivo",F("Ivo","action","threw the brass compass into the river"))], [("Ivo",F("Ivo","action","consulted the brass compass"))]),
 (0, "object: compass thrown -> bought a new compass", [(1,"Ivo",F("Ivo","action","threw the brass compass into the river"))], [("Ivo",F("Ivo","action","bought a new compass and consulted it"))]),
 (0, "object: remembers the compass", [(1,"Ivo",F("Ivo","action","threw the brass compass into the river"))], [("Ivo",F("Ivo","thought","remembered consulting the brass compass"))]),
 (1, "ability: lost his right hand -> 'with his right hand he drew'", [(1,"Ivo",F("Ivo","injury","lost his right hand at Varna"))], [("Ivo",F("Ivo","action","drew his sword with his right hand"))]),
 (0, "ability: lost right hand -> uses left hand", [(1,"Ivo",F("Ivo","injury","lost his right hand at Varna"))], [("Ivo",F("Ivo","action","drew his sword with his left hand"))]),
 (1, "family: 'Lena, his daughter' -> 'Lena, his sister'", [(1,"Ivo",F("Ivo","relationship","parent of Lena","his daughter Lena"))], [("Ivo",F("Ivo","relationship","sibling of Lena","Lena, his sister"))]),
 (0, "family: daughter -> 'daughter of Ivo' on Lena (same)", [(1,"Ivo",F("Ivo","relationship","parent of Lena","his daughter Lena"))], [("Lena",F("Lena","relationship","daughter of Ivo","Ivo's daughter"))]),
 (1, "order: 'Teo, two years older than Ivo' -> 'Teo, younger than Ivo'", [(1,"Teo",F("Teo","age difference","two years older than Ivo"))], [("Teo",F("Teo","age difference","younger than Ivo"))]),
 (1, "mended: 'the watch, mended' -> 'still broken'", [(1,"the Heron",F("the Heron","state","repaired over the winter",t="item"))], [("Heron",F("Heron","state","still damaged below the waterline",t="item"))]),
 (0, "mended: repaired -> damaged again in the storm", [(1,"the Heron",F("the Heron","state","repaired over the winter",t="item")),(5,"the Heron",F("the Heron","event","smashed against the pier in the storm",t="item"))], [("Heron",F("Heron","state","still damaged below the waterline",t="item"))]),
 (1, "origin: 'born in Kiel and never left' -> arrived in Kiel", [(1,"Ivo",F("Ivo","background","born in Kiel","Ivo was born in Kiel and never left."))], [("Ivo",F("Ivo","history","arrived in Kiel on the night ferry"))]),
]


@pytest.mark.parametrize("expect,description,earlier,new", FIRST, ids=[c[1] for c in FIRST])
def test_first_set(expect, description, earlier, new):
    assert bool(run(earlier, new, ID)) == bool(expect)


@pytest.mark.parametrize("expect,description,earlier,new", SECOND, ids=[c[1] for c in SECOND])
def test_second_set(expect, description, earlier, new):
    assert bool(run(earlier, new, ID2)) == bool(expect)


# --- Third set: general fixes for the held-out failures of 18 Oct 2026 (Night Shift, Kestrel) --
# Those two stories are no longer held out after this; a new story measures the next round.
import entities
import storyclock
import storytime


def test_figures_of_speech_are_not_ages():
    assert storytime.current_age("age", "twelve", "You look twelve") is None
    assert storytime.current_age("age", "a hundred", "She felt about a hundred") is None
    assert storytime.current_age("age", "sixty-two", "He was sixty-two now, and looked tired") == 62


def test_a_beard_shaved_off_in_between_is_not_a_clash():
    ids = {"Bastian": 1, "Bastian Kowal": 1}
    beard = [(1, "Bastian Kowal", F("Bastian Kowal", "appearance", "great black beard"))]
    shaved = beard + [(3, "Bastian", F("Bastian", "action", "shaved it off in the night", "He had shaved it off in the night"))]
    now = [("Bastian", F("Bastian", "appearance", "clean-shaven", "clean-shaven and already in his suit"))]
    assert run(shaved, now, ids) == [] and len(run(beard, now, ids)) == 1


def test_acting_after_death_with_any_verb_or_status_alive():
    acting = lambda a, v, q, n: storyclock.is_acting(F(n, a, v, q), [n])
    assert acting("waved", "hand", "In bed four, Walter Alcott raised a hand and waved at them", "Walter Alcott")
    assert acting("status", "alive", "this is the Tern, said Haruki Mori's voice", "Haruki Mori")
    assert not acting("collected", "glasses", "Walter Alcott's daughter collected his glasses", "Walter Alcott")
    assert not acting("buried", "behind the cottage", "Ines buried Bramble behind the cottage", "Bramble")
    assert not acting("status", "alive", "when Walter was alive, he played cards", "Walter")


def _injury(earlier, new, gap):
    stored = [{"fact_id": i, "entity_id": 1, "entity": f.entity, "entity_type": "character", "attribute": f.attribute,
               "value": f.value, "source_quote": f.source_quote, "chapter_id": f"ch{n}", "chapter_number": n}
              for i, (n, f) in enumerate(earlier)]
    return states.check_states("ch9", 9, [(1, new.entity, new, 0)], [], lambda e: stored, lambda n: 1, set(),
                               lambda a, b: gap)


def test_a_broken_limb_used_hard_within_weeks_but_not_after_healing_or_unknown_time():
    cast = [(2, F("Tom", "treatment", "left forearm in a plaster cast up to the elbow"))]
    lift = F("Tom", "lifted patient", "patient in bed two", "Tom lifted the patient up the bed with both arms")
    assert len(_injury(cast, lift, 1 / 52)) == 1
    assert _injury(cast, lift, 6 / 52) == [] and _injury(cast, lift, None) == []
    assert _injury(cast + [(5, F("Tom", "event", "cast cut off"))], lift, 2 / 52) == []
    leg = [(2, F("Ana", "injury", "broken right leg"))]
    assert len(_injury(leg, F("Ana", "action", "came up the ladder at a run, two rungs at a time"), 1 / 365)) == 1
    assert _injury(leg, F("Ana", "action", "walked with a cane, limping"), 1 / 52) == []
    assert _injury([(2, F("Ana", "history", "broke her arm as a child"))], F("Ana", "action", "lifted the crate with both arms"), 1 / 52) == []


def test_everyday_objects_lost_to_space_or_a_river_then_used():
    ids = {"stores bay": 1, "spare oxygen regulator": 2, "Bastian": 3, "Mara": 5}
    vented = [(2, "stores bay", F("stores bay", "contents", "the station's only spare oxygen regulator",
                                  "Everything went out into the dark: spare suits, and the station's only spare oxygen regulator, tumbling away.", "location"))]
    fitted = [("spare oxygen regulator", F("spare oxygen regulator", "location", "down from the shelf",
                                           "took the spare oxygen regulator down from the shelf and fitted it", "item"))]
    assert len(run(vented, fitted, ids)) == 1
    assert run(vented, [("Bastian", F("Bastian", "action", "installed the new regulator"))], ids) == []
    river = [(1, "Mara", F("Mara", "action", "dropped her phone into the river"))]
    assert len(run(river, [("Mara", F("Mara", "action", "dialled her sister on her phone"))], ids)) == 1
    assert run(river, [("Mara", F("Mara", "action", "dialled her sister on her new phone"))], ids) == []


def test_older_sister_written_as_a_value_or_a_label():
    ids = {"Priya": 1, "Marguerite Doyle": 2, "Marguerite": 2}
    older = [(1, "Priya", F("Priya", "relationship", "older sister Marguerite Doyle"))]
    assert len(run(older, [("Priya", F("Priya", "younger sister", "Marguerite"))], ids)) == 1
    assert run(older, [("Priya", F("Priya", "relationship", "older sister Marguerite"))], ids) == []


def test_titled_and_untitled_full_names_in_one_chapter_are_one_person():
    R = lambda n: entities.Resolution(n, "character", None, n, "new", 1.0)
    res = {n.lower(): R(n) for n in ["Dr Priya Sandoval", "Priya Sandoval", "Priya", "Leo"]}
    entities.join_same_chapter_titled_names(res)
    assert {res[k].canonical_name for k in ("priya", "priya sandoval")} == {"Dr Priya Sandoval"}
    assert res["leo"].canonical_name == "Leo"
    res = {n.lower(): R(n) for n in ["Commander Yusra Adeyemi", "Yusra"]}
    entities.join_same_chapter_titled_names(res)
    assert res["yusra"].canonical_name == "Commander Yusra Adeyemi"
    res = {n.lower(): R(n) for n in ["Dr Ana Reyes", "Ana", "Ana Lopez"]}
    entities.join_same_chapter_titled_names(res)
    assert res["ana"].canonical_name == "Ana"                     # two Anas: unclear, left alone

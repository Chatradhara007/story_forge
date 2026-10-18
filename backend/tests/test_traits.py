"""
Fixed traits compared in code (traits.py): no database, no AI. The wording comes from real
Reader output on the three test stories.
"""
from models import Fact
import traits


def F(entity, attribute, value, quote=""):
    return Fact(entity=entity, entity_type="character", attribute=attribute, value=value,
                source_quote=quote or value, confidence=1.0)


def run(earlier, new, names):
    """
    earlier: [(chapter number, entity name, Fact)], new: [(entity name, Fact)] in chapter 9.
    names: {name: entity id}, so several names can be one entity.
    """
    ids = {n.lower(): i for n, i in names.items()}
    stored = [{"fact_id": i, "entity_id": ids[e.lower()], "entity": f.entity, "attribute": f.attribute,
               "value": f.value, "source_quote": f.source_quote, "chapter_id": f"ch{n}", "chapter_number": n}
              for i, (n, e, f) in enumerate(earlier)]
    new_facts = [(ids[e.lower()], e, f, i) for i, (e, f) in enumerate(new)]
    return traits.check_traits("ch9", 9, new_facts,
                               lambda eid: [s for s in stored if s["entity_id"] == eid],
                               lambda name: ids.get(name.lower()))


def test_eye_colours_that_share_nothing_clash():
    [w] = run([(1, "Thessaly", F("Thessaly", "physical description", "grey-green eyes"))],
              [("Thessaly", F("Thessaly", "emotion", "laughed", "Thessaly's dark brown eyes filled"))],
              {"Thessaly": 1})
    assert w.source == "trait check" and w.contradiction_type == "attribute"
    assert run([(1, "Ines", F("Ines", "eyes", "grey"))], [("Ines", F("Ines", "eye color", "grey-green eyes"))],
               {"Ines": 1}) == []


def test_someone_elses_eyes_in_a_quote_are_ignored():
    assert run([(1, "Aurel", F("Aurel", "eyes", "grey"))],
               [("Aurel", F("Aurel", "action", "looked up", "He looked into Thessaly's brown eyes"))],
               {"Aurel": 1, "Thessaly": 2}) == []


def test_an_animals_colour_is_found_under_its_rider_too():
    [w] = run([(1, "Ember", F("Ember", "type", "grey stallion"))],
              [("Aurel", F("Aurel", "companion", "Ember, the black stallion"))],
              {"Ember": 1, "Aurel": 2})
    assert "black" in w.new_value


def test_a_white_muzzle_is_ageing_not_a_new_colour():
    assert run([(1, "Ember", F("Ember", "type", "grey stallion"))],
               [("Ember", F("Ember", "appearance", "white around the muzzle"))], {"Ember": 1}) == []


def test_a_scar_on_the_other_hand_clashes():
    [w] = run([(1, "Aurel", F("Aurel", "physical description", "scar across the back of his left hand"))],
              [("Aurel", F("Aurel", "physical_description", "forehead healed into a second scar to match the one on his right hand"))],
              {"Aurel": 1})
    assert "right hand" in w.new_value


def test_no_scar_yet_and_other_hands_are_not_clashes():
    earlier = [(1, "Aurel", F("Aurel", "physical description", "scar across the back of his left hand"))]
    assert run(earlier, [("Aurel", F("Aurel", "hand description", "no scar on his right hand"))], {"Aurel": 1}) == []
    assert run(earlier, [("Aurel", F("Aurel", "gesture", "held up his right hand"))], {"Aurel": 1}) == []


def test_handedness_clashes():
    [w] = run([(1, "Orla Venn", F("Orla Venn", "handedness", "left-handed"))],
              [("Orla", F("Orla", "handedness", "right hand", "She signed the new lease with her right hand, as she always had"))],
              {"Orla Venn": 1, "Orla": 1})
    assert w.entity == "Orla"


def test_older_then_younger_brother_clashes():
    earlier = [(1, "Ines Calloway", F("Ines Calloway", "relationship", "sibling of Tobias",
                                      "Her older brother Tobias wrote to her twice a year"))]
    [w] = run(earlier, [("Ines", F("Ines", "relationship", "sibling of Tobias", "Tobias, my younger brother"))],
              {"Ines Calloway": 1, "Ines": 1, "Tobias": 2})
    assert w.source == "trait check"
    same = [("Ines", F("Ines", "relationship", "sibling of Tobias", "my older brother Tobias came home"))]
    assert run(earlier, same, {"Ines Calloway": 1, "Ines": 1, "Tobias": 2}) == []


def test_years_younger_than_and_elder_sister_clash_when_linked():
    earlier = [(5, "Mira", F("Mira", "age_relative_to_Aurel", "four years younger than him"))]
    new = [("Aurel", F("Aurel", "relationship", "sibling of elder sister of Aurel", "with my elder sister"))]
    assert run(earlier, new, {"Mira": 1, "elder sister of Aurel": 1, "Aurel": 2})
    assert run(earlier, new, {"Mira": 1, "elder sister of Aurel": 3, "Aurel": 2}) == []    # not linked: no claim


def test_sister_then_cousin_clashes_using_the_same_chapters_kin_word():
    earlier = [(1, "Rose Halloway", F("Rose Halloway", "relationship", "sibling of Orla Venn",
                                      "Orla's younger sister, Rose Halloway"))]
    new = [("Rose", F("Rose", "relationship", "related to Orla", "Rose came on the first morning")),
           ("Rose", F("Rose", "relation", "cousin", "For luck,"))]
    [w] = run(earlier, new, {"Rose Halloway": 1, "Rose": 1, "Orla Venn": 2, "Orla": 2})
    assert w.new_value == "cousin of Orla"
    vague = [("Rose", F("Rose", "relationship", "related to Orla", "Rose came on the first morning"))]
    assert run(earlier, vague, {"Rose Halloway": 1, "Rose": 1, "Orla Venn": 2, "Orla": 2}) == []


def test_descriptions_are_not_names_for_family_ties():
    earlier = [(1, "his son", F("his son", "relationship", "parent of Aurel", "I will give my son the whole sea"))]
    new = [("Aurel", F("Aurel", "relationship", "parent of his sleeping son", "He kissed his sleeping son"))]
    assert run(earlier, new, {"his son": 1, "his sleeping son": 1, "Aurel": 2}) == []


def test_a_family_tie_needs_a_family_word_in_the_quote():
    """The Reader filed 'Aurel | parent of Oren' from 'Her blind eyes looked somewhere past him'."""
    assert traits.family_tie("relationship", "parent of Oren", "Her blind eyes looked somewhere past him") is None
    assert traits.family_tie("relationship", "parent of Aurel", "Aurel's father, King Oren") is not None


# --- 18 Oct 2026: general checks for misses in Glassmaker and Lighthouse -----------------
def T(entity, attribute, value, quote="", entity_type="item"):
    return Fact(entity=entity, entity_type=entity_type, attribute=attribute, value=value,
                source_quote=quote or value, confidence=1.0)


def test_tall_then_short_is_caught_but_short_hair_is_not_height():
    crane = {"Captain Crane": 1, "Aldous Crane": 1}
    earlier = [(1, "Aldous Crane", F("Aldous Crane", "physical_description", "tall, stooping man who seemed to apologise to every ceiling"))]
    [w] = run(earlier, [("Captain Crane", F("Captain Crane", "physical_description",
                                            "short captain had to stand on his toes to see over the crowd"))], crane)
    assert "height" in w.explanation
    assert run(earlier, [("Captain Crane", F("Captain Crane", "physical_description", "short hair, tall boots"))], crane) == []
    assert run(earlier, [("Captain Crane", F("Captain Crane", "action", "took a short walk"))], crane) == []


def test_a_beard_then_clean_shaven_is_caught_unless_he_shaved():
    rudd = {"Silas Rudd": 1, "Harbourmaster Rudd": 1}
    earlier = [(2, "Silas Rudd", F("Silas Rudd", "physical_description", "a broad man with a white beard that reached the second button of his coat"))]
    [w] = run(earlier, [("Harbourmaster Rudd", F("Harbourmaster Rudd", "habit", "rubbing his clean-shaven chin when he is thinking"))], rudd)
    assert "beard" in w.explanation
    assert run(earlier, [("Silas Rudd", F("Silas Rudd", "change", "had shaved off his beard, clean-shaven now"))], rudd) == []


def test_a_boat_painted_red_then_with_a_blue_hull_is_caught():
    earlier = [(2, "Merrow", T("Merrow", "description", "the harbour", "the harbour's little red-painted launch", "location"))]
    [w] = run(earlier, [("Merrow", T("Merrow", "description", "blue hull freshly scrubbed"))], {"Merrow": 1})
    assert "colour" in w.explanation
    assert run(earlier, [("Merrow", T("Merrow", "description", "repainted blue over the winter, a blue hull"))], {"Merrow": 1}) == []


def test_mended_then_still_cracked_is_caught_but_broken_again_is_not():
    mended = [(4, "Sunstone lens", T("Sunstone lens", "property", "whole and seamless again, without a line to show where it had broken"))]
    still = [("Sunstone lens", T("Sunstone lens", "description", "cracked down the middle",
                                 "It was still cracked down the middle, just as it had been since the fire"))]
    [w] = run(mended, still, {"Sunstone lens": 1})
    assert w.contradiction_type == "status" and "mended" in w.explanation
    dropped = mended + [(5, "Sunstone lens", T("Sunstone lens", "event", "Crane dropped it on the flagstones"))]
    assert run(dropped, still, {"Sunstone lens": 1}) == []


def test_born_somewhere_and_never_left_then_coming_there_is_caught():
    born = [(1, "Orla Venn", F("Orla Venn", "birthplace", "Varrow", "Orla had been born in Varrow and had never once left it."))]
    [w] = run(born, [("Orla Venn", F("Orla Venn", "arrival location", "Varrow", "She had come to Varrow as a girl of nineteen"))],
              {"Orla Venn": 1})
    assert "never left" in w.explanation
    born_only = [(1, "Orla Venn", F("Orla Venn", "birthplace", "Varrow", "Orla had been born in Varrow."))]
    assert run(born_only, [("Orla Venn", F("Orla Venn", "arrival location", "Varrow", "She came back to Varrow"))],
               {"Orla Venn": 1}) == []

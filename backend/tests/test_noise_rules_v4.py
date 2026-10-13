"""
Rules from run B on The Fallen King (13 Oct 2026): 14 false alarms, 4 catches. Twelve of the
false alarms fell into five patterns, each handled by a general rule in set_aside_by_rule.
The planted mistakes these rules must NOT set aside are tested alongside.
"""
from models import Contradiction
from contradictions import set_aside_by_rule


def warning(new_value, old_value, new_attribute="attribute", new_quote="", old_quote="", source="checker",
            kind="attribute"):
    return Contradiction(entity="X", new_chapter_id="c5", new_attribute=new_attribute, new_value=new_value,
                         new_quote=new_quote or new_value, conflicting_chapter_id="c1", conflicting_value=old_value,
                         conflicting_quote=old_quote or old_value, contradiction_type=kind, confidence=0.9,
                         explanation="They differ.", source=source)


def set_aside(c, time_note=None):
    return set_aside_by_rule([c], time_note)[0].status == "dismissed"


def test_ages_that_are_not_this_characters_age_now_are_left_to_the_story_clock():
    assert set_aside(warning("eight years old", "thirty-one years old", "son_age"))
    assert set_aside(warning("taller, all knees and elbows", "twenty-five", "height",
                             old_quote="until Tam is twenty-five"))
    assert set_aside(warning("seventeen", "two years younger than Aurel", "age",
                             new_quote="He was a good letter writer at seventeen"))
    assert set_aside(warning("six years", "six years old now", "day",
                             new_quote="It took him six years to earn back what he had lost"))
    assert set_aside(warning("related to Aurel", "seventeen", "relationship", old_quote="Corvin was seventeen"))


def test_real_mistakes_about_age_and_numbers_are_kept():
    # relative age against relative age (planted: younger sister / elder sister)
    assert not set_aside(warning("elder sister", "four years younger than Aurel", "relationship"))
    # durations are not ages (planted: kept the light twenty years / eight years)
    assert not set_aside(warning("eight years", "twenty years", "years as keeper"))
    # counts are not ages (planted: single furnace / three furnaces)
    assert not set_aside(warning("three furnaces roaring", "a single furnace", "furnaces"))
    # two clean current ages stay (the story clock usually gets there first)
    assert not set_aside(warning("twelve", "ten", "age", new_quote="Pip was twelve", old_quote="Pip, ten,"))


def test_family_ties_that_can_both_be_true_are_set_aside():
    assert set_aside(warning("child of Mother", "married to Queen Thessaly", "relationship"))
    assert set_aside(warning("parent of Aurel", "child of Aurel", "relationship"))


def test_real_family_mistakes_are_kept():
    assert not set_aside(warning("cousin of Orla", "younger sister of Orla", "relationship"))
    assert not set_aside(warning("younger brother of Ines", "older brother of Ines", "relationship"))
    assert not set_aside(warning("married to Mira", "married to Thessaly", "relationship"))


def test_alive_only_conflicts_with_a_death():
    assert set_aside(warning("poles a ferry", "alive", "current_role", kind="status"))
    assert not set_aside(warning("barks at the gulls", "dead", "action", kind="status"))
    assert not set_aside(warning("alive", "drowned in the fire", "status", kind="status"))


def test_growing_up_and_growing_old_are_the_story_moving_on():
    # a colt seen in a flashback, a stallion in the present
    assert set_aside(warning("a grey colt from the royal stud", "grey stallion", "given"),
                     "flashback: fourteen years before the fall")
    # greying with age (decoy D4)
    assert set_aside(warning("white around the muzzle", "Ember, the black stallion", "description"))
    # a colour change is still a mistake (planted A1), and so is a colt AFTER the stallion
    assert not set_aside(warning("Ember, the black stallion", "grey stallion", "companion"))
    assert not set_aside(warning("a grey colt", "grey stallion", "description"))
    # a black colt in a flashback against a grey stallion is a different colour, not growing up
    assert not set_aside(warning("a black colt", "grey stallion", "description"), "flashback: years before")


def test_story_clock_warnings_are_never_set_aside():
    assert not set_aside(warning("thirty-eight", "thirty-three", "age", source="story clock", kind="timeline"))

"""
The story clock's timeline (storytime.py): no database, no AI, plain functions.

Built from what went wrong on The Fallen King (5 Oct 2026): chapters each "two years after the
council" were added up as six years, "fourteen years before the fall" counted as fourteen years
FORWARD, and "taught Aurel when he was seven" was read as Aurel's age. Ten of that run's 60
false alarms came from the old clock, and it caught none of the age mistakes.
"""
from models import Fact
import storytime as st


def chapters(*rows):
    """rows: (time_note, opening text) for chapters 1, 2, 3..."""
    return [{"chapter_id": f"ch{i}", "chapter_number": i, "time_note": note, "opening": opening}
            for i, (note, opening) in enumerate(rows, start=1)]


def span(positions, n):
    p = positions[n]
    return None if p.span is None else (round(p.span.lo, 2), round(p.span.hi, 2))


# ---------------------------------------------------------------- phrases --
def test_time_phrases_are_read_with_their_direction_and_anchor():
    [c] = st.find_clauses("Twelve years before the fire, Orla Venn was twenty-two.")
    assert (c.lo, c.direction, c.anchor) == (12, "before", "fire")
    [c] = st.find_clauses("Two years later, the ferry at Dun Crossing was run by a bearded man.")
    assert (c.lo, c.direction, c.anchor) == (2, "after", "previous")
    [c] = st.find_clauses("The rain began in the spring of the second year after Greywater.")
    assert (c.lo, c.hi, c.anchor) == (1, 2, "greywater")
    [c] = st.find_clauses("four months after Chapter Six")
    assert c.anchor == "chapter:6"
    [c] = st.find_clauses("the morning after the storm on Friday")
    assert c.anchor == "storm" and c.direction == "after"


def test_durations_are_not_time_shifts():
    assert st.find_clauses("It took them three weeks on foot to reach the convent.") == []
    assert st.find_clauses("She had kept it burning for twenty years.") == []


def test_alternatives_in_a_note_share_the_amount():
    clauses = st.note_clauses("two years after the council / after the abdication")
    assert [(c.lo, c.anchor) for c in clauses] == [(2, "council"), (2, "abdication")]


# --------------------------------------------------------------- timeline --
def test_chapters_at_the_same_time_are_not_added_up():
    positions = st.chapter_positions(chapters(
        (None, "The feast lasted all night."),
        ("continues: the next day", "The council met the next morning and voted."),
        ("time skip: two years after the council", "On the road north, Aurel walked."),
        ("time skip: two years after the council", "At the convent, the sisters prayed."),
    ))
    assert span(positions, 3) == span(positions, 4)            # both two years after the council
    assert 1.9 <= positions[4].span.lo and positions[4].span.hi <= 2.4


def test_years_before_an_event_is_a_flashback_not_a_jump_forward():
    positions = st.chapter_positions(chapters(
        (None, "The fire began just after midnight."),
        ("continues", "Orla woke to the smell of smoke."),
        ("time skip: twelve years before the fire", "Twelve years before the fire, Orla was young."),
    ))
    assert positions[3].flashback and span(positions, 3) == (-12.0, -12.0)    # the fire is chapter 1


def test_later_after_a_flashback_continues_the_main_story():
    positions = st.chapter_positions(chapters(
        (None, "The bells rang."),
        (None, "Two years later, the ferry ran again."),
        (None, "Fourteen years before the fall, the old king died."),
        (None, "Four months later, the valley had stopped eating bark."),
    ))
    assert positions[3].flashback and positions[3].span is None      # "the fall" can't be placed
    assert span(positions, 4) == (2.33, 2.33)                         # measured from chapter 2


def test_the_opening_words_beat_a_wrong_timing_note():
    positions = st.chapter_positions(chapters(
        (None, "The council met."),
        ("time skip: two years after the fleet disaster", "The council met the next day, at the hour of the bell."),
    ))
    assert positions[2].source == "opening" and positions[2].span.hi < 0.01


def test_an_unknown_anchor_widens_the_range_instead_of_guessing():
    positions = st.chapter_positions(chapters(
        (None, "Rook was nine."),
        ("time skip: three years after Rook went into hiding", "The workshop was quiet."),
    ))
    assert span(positions, 2) == (0.0, 3.0)


# ------------------------------------------------------------------- ages --
def test_ages_at_another_moment_are_not_current_ages():
    assert st.current_age("age_when_taught", "seven", "taught Aurel to hold a blade when he was seven") is None
    assert st.current_age("age", "seven", "who had taught Aurel to hold a blade when he was seven") is None
    assert st.current_age("age", "twenty-five", "until Tam is twenty-five") is None
    assert st.current_age("age", "seventeen", "He was a good letter writer at seventeen") is None
    assert st.current_age("age_difference", "two years younger than Aurel", "") is None
    assert st.current_age("age", "sixty-four years old",
                          "Bram Holloway, sixty-four years old, the swordmaster who had taught Aurel when he was seven") == 64
    assert st.current_age("age", "Twelve-year-old", "Twelve-year-old Pip was left in charge") == 12


def _check(rows, ages, chapter):
    """ages: {chapter number: [(entity id, age text, quote)]}; checks `chapter` against the ones before."""
    stored = [{"fact_id": i, "chapter_id": f"ch{n}", "chapter_number": n, "attribute": "age", "value": v,
               "source_quote": q, "entity_id": e}
              for i, (n, e, v, q) in enumerate((n, e, v, q) for n, items in ages.items() for e, v, q in items)]
    new = [(e, f"person {e}", Fact(entity=f"person {e}", entity_type="character", attribute="age", value=v,
                                   source_quote=q, confidence=1.0), i)
           for i, (e, v, q) in enumerate(ages[chapter])]
    notes = chapters(*rows)
    return st.check_ages(f"ch{chapter}", chapter, new,
                         lambda eid: [f for f in stored if f["entity_id"] == eid and f["chapter_number"] < chapter],
                         [c for c in notes if c["chapter_number"] < chapter],
                         notes[chapter - 1]["time_note"], notes[chapter - 1]["opening"])


FALLEN = [(None, "The bells of Vessa rang for three days after Greywater."),
          (None, "The rain began in the spring of the second year after Greywater."),
          (None, "The council met at the hour of the morning bell, the next day."),
          (None, "Two years later, the ferry at Dun Crossing was run by a bearded man called Rell."),
          ("time skip: two years after the council", "On the long walk north he listened for hoofbeats."),
          (None, "Fourteen years before the fall, the old king died."),
          (None, "Four months later, the people of the valley had stopped eating bark.")]


def test_an_age_going_down_years_later_is_caught():
    found = _check(FALLEN, {1: [(1, "sixty-four", "Bram, sixty-four years old")],
                            3: [(1, "sixty-six", "I'm sixty-six years old")],
                            7: [(1, "sixty-two", "He was sixty-two now")]}, 7)
    [w] = found
    assert w.source == "story clock" and "62" in w.explanation


def test_too_old_four_months_later_is_caught_and_right_ages_are_not():
    ages = {1: [(1, "thirty-one", "He was thirty-one years old"), (2, "thirteen", "Pell, thirteen years old")],
            2: [(1, "thirty-three", "King Aurel was thirty-three"), (2, "fifteen", "The boy was fifteen now")],
            4: [(2, "seventeen", "Pell, seventeen now")],
            7: [(1, "thirty-eight", "He turned thirty-eight that winter"), (2, "seventeen", "Pell, seventeen")]}
    assert _check(FALLEN, ages, 2) == [] and _check(FALLEN, ages, 4) == []
    [w] = _check(FALLEN, ages, 7)
    assert w.entity == "person 1" and "38" in w.explanation


def test_a_flashback_age_that_fits_is_left_alone():
    rows = [(None, "On the eve of the festival the city glowed."), (None, "The fire began just after midnight."),
            (None, "Twelve years before the fire, Orla Venn was twenty-two."), (None, "Three years after the fire, the workshop opened.")]
    ages = {1: [(1, "thirty-four", "She was thirty-four")], 3: [(1, "twenty-two", "Orla Venn was twenty-two")],
            4: [(1, "thirty-seven", "Orla was thirty-seven now")]}
    assert _check(rows, ages, 3) == [] and _check(rows, ages, 4) == []


def test_ten_then_twelve_a_few_weeks_later_is_caught():
    rows = [(None, "The light stood on black rock."), ("time skip: a few weeks after the storm", "Autumn came in quietly.")]
    [w] = _check(rows, {1: [(1, "ten years old", "Pip was ten years old")],
                        2: [(1, "Twelve-year-old", "Twelve-year-old Pip")]}, 2)
    assert "less than a year" in w.explanation

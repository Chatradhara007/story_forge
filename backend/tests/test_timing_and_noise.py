"""
Fixes from the held-out run on The Fallen King (12 Oct 2026): 52 false alarms, 3 catches.
Chapter timing was misread (so ages "didn't add up"), the safety net compared unrelated names,
and the AI did age arithmetic badly. Each rule is general; none mentions the story.
"""
from conftest import fact, facts_by_marker
from extract import timing_from_opening
import storyclock
from storyclock import parse_age, years_passed, is_death


def test_a_chapter_opening_states_its_own_timing():
    assert timing_from_opening("Chapter Three: Knives\n\nThe council met the next day, at the bell.") == "continues: the next day"
    assert timing_from_opening("Two years later, the ferry was run by Rell.").startswith("time skip: Two years later")
    assert timing_from_opening("Fourteen years before the fall, the old king died.").startswith("flashback: Fourteen years before")
    assert timing_from_opening("Three years after the fire, the shop opened.").startswith("time skip: Three years after")
    assert timing_from_opening("Tobias arrived the morning after the storm.").startswith("continues: the morning after")
    assert timing_from_opening("She walked north for a long time.") is None


def test_the_timing_ai_is_not_asked_when_the_opening_says_it(client, fake_ai):
    client.post("/chapters", json={"chapter_id": "c1", "text": "One."})
    asked = fake_ai.calls.get("record_timing", 0)
    r = client.post("/chapters", json={"chapter_id": "c2", "text": "Two years later, the town was quiet."})
    assert r.json()["time_note"] == "time skip: Two years later"
    assert fake_ai.calls.get("record_timing", 0) == asked


def test_relative_and_past_ages_are_not_ages():
    assert parse_age("age", "seventeen") == 17
    assert parse_age("age", "two years younger than Aurel") is None
    assert parse_age("age at coronation", "nineteen") is None
    assert parse_age("age", "nineteen when he was crowned") is None


def test_flashbacks_do_not_move_the_main_timeline_and_repeated_notes_are_one_moment():
    notes = {1: "continues: start", 2: "time skip: two years after the war", 3: "time skip: two years after the war",
             4: "time skip: fourteen years before the fall", 5: "time skip: four months later"}
    assert storyclock._elapsed(notes, 1, 3) == (2.0, False)            # 2 and 3 are the same moment
    years, flashback_end = storyclock._elapsed(notes, 3, 5)
    assert abs(years - 4 / 12) < 0.01 and not flashback_end             # the flashback (4) is skipped
    assert storyclock.is_flashback(notes[4])                             # "before" = a flashback, whatever the label


def test_age_after_a_flashback_is_compared_on_the_main_timeline(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Bram Holloway", "age", "sixty-six", "Bram was sixty-six")],
        "[2]": [fact("Bram Holloway", "age", "fifty-two", "Bram was fifty-two then")],
        "[3]": [fact("Bram Holloway", "age", "sixty-two", "He was sixty-two now")]}))
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    r2 = client.post("/chapters", json={"chapter_id": "c2", "text": "Fourteen years before the fall, it rained. [2]"}).json()
    assert r2["contradictions"] == []                                      # younger in a flashback: fine
    r3 = client.post("/chapters", json={"chapter_id": "c3", "text": "Four months later, he came back. [3]"}).json()
    [w] = [c for c in r3["contradictions"] if c["source"] == "story clock"]
    assert "66" in w["explanation"] and "62" in w["explanation"]


def test_hedged_or_long_death_statements_do_not_make_someone_dead():
    assert is_death({"attribute": "status", "value": "dead"})
    assert not is_death({"attribute": "status", "value": "deceased (implied - fought for by Bram after him)"})
    assert not is_death({"attribute": "speech", "value": "I sold the grain. Your sons drowned at the rocks because of me"})


def test_backstory_about_the_dead_is_not_acting(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("King Oren", "status", "dead", "King Oren died that winter")],
        "[2]": [fact("King Oren", "action", "marched on the salt coast",
                     "When you were two years old, Oren marched on the salt coast")]}))
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    assert client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()["contradictions"] == []


def test_the_ai_does_not_judge_ages(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Tam", "age", "four", "Tam, four years old")],
        "[2]": [fact("Tam", "age", "six", "Tam, six years old")]}))
    fake_ai.on("record_timing", lambda p: {"setting": "time skip", "description": "two years later"})
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [{"entity_number": 1, "new_fact_index": 0,
        "existing_fact_index": 0, "contradiction_type": "timeline", "confidence": 0.9, "explanation": "4 to 6 in 12 years"}]})
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    assert client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()["contradictions"] == []


def _cross_all(fake_ai):
    sent = []
    def handler(p):
        sent.append(p)
        return {"contradictions": [{"pair_index": i, "same_entity_confidence": 0.95, "contradiction_type": "status",
                                    "confidence": 0.9, "explanation": "x"} for i in range(p.count("<->"))]}
    fake_ai.on("report_cross_contradictions", handler)
    fake_ai.on("link_names", lambda p: {"resolutions": []})
    return sent


def test_safety_net_skips_unrelated_names_and_family_ties(client, fake_ai):
    sent = _cross_all(fake_ai)
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Venn fleet", "status", "broken on the shoals", "The Venn fleet lay broken", entity_type="other"),
                fact("Oren", "relationship", "parent of Aurel", "Aurel's father Oren")],
        "[2]": [fact("Admiral Kell", "destination", "the southern isles", "Kell sailed for the southern isles"),
                fact("Aurel", "relationship", "parent of Oren", "Aurel and Oren")]}))
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    assert client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()["contradictions"] == []
    assert all("Venn fleet" not in p and "parent of" not in p for p in sent)


def test_safety_net_still_compares_a_name_mentioned_in_the_other_fact(client, fake_ai):
    _cross_all(fake_ai)
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Ember", "physical description", "grey stallion", "Ember, a grey stallion", entity_type="other")],
        "[2]": [fact("Aurel", "companion", "Ember, the black stallion", "Ember, the black stallion")]}))
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    [w] = client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()["contradictions"]
    assert w["source"] == "safety net" and w["new_value"] == "Ember, the black stallion"


def test_repeated_relative_skips_add_up():
    notes = {1: "continues: start", 2: "time skip: two years later", 3: "time skip: two years later"}
    assert storyclock._elapsed(notes, 1, 3) == (4.0, False)


def test_other_peoples_ages_and_future_ages_are_not_this_characters_age():
    assert parse_age("son_age", "eight years old") is None
    assert parse_age("age", "twenty-five", "the regency lasts until Tam is twenty-five") is None
    assert parse_age("age", "thirty-eight", "He turned thirty-eight that winter") == 38

"""
The failures found in the 4 Oct 2026 lighthouse evaluation (Lightning as judge), rebuilt as
tests: a right idea attached to the wrong fact (T1, A2), vague time skips (A5), a storm that
moves from Tuesday to Friday (T2), a dead dog barking (S1), and "ally" vs "mentor".
"""
import pytest
from conftest import fact, facts_by_marker


def timing(notes):
    def handler(prompt):
        text = prompt.split("Chapter text:")[1]
        for marker, (setting, description) in notes.items():
            if marker in text:
                return {"setting": setting, "description": description}
        return {"setting": "continues", "description": "the next day"}
    return handler


def post(client, cid, text):
    r = client.post("/chapters", json={"chapter_id": cid, "text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_T1_right_idea_wrong_index_is_moved_to_the_right_fact(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Ines Calloway", "age", "fifty-two", "She was fifty-two that spring"),
                fact("Ines Calloway", "years as keeper", "twenty years", "she had kept the light twenty years")],
        "[5]": [fact("Ines Calloway", "years as keeper", "eight years", "In my eight years as keeper")]}))
    # The model points at fact 0 (the age) but copies the value it actually compared.
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [{
        "entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0,
        "new_value": "eight years", "existing_value": "twenty years",
        "contradiction_type": "timeline", "confidence": 0.9, "explanation": "twenty years vs eight"}]})
    post(client, "ch1", "[1]")
    [w] = post(client, "ch5", "[5]")["contradictions"]
    assert w["conflicting_quote"] == "she had kept the light twenty years"     # not the age quote


def test_A2_wrong_entity_number_is_found_in_the_right_section(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Ines Calloway", "eyes", "grey", "grey eyes"),
                fact("Tobias Calloway", "relation to Ines", "older brother", "her older brother Tobias")],
        "[5]": [fact("Ines Calloway", "eyes", "grey", "the same grey eyes"),
                fact("Tobias Calloway", "relation to Ines", "younger brother", "her younger brother Tobias")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [{
        "entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0,      # points at Ines's eyes
        "new_value": "younger brother", "existing_value": "older brother",
        "contradiction_type": "attribute", "confidence": 0.9, "explanation": "older vs younger"}]})
    post(client, "ch1", "[1]")
    [w] = post(client, "ch5", "[5]")["contradictions"]
    assert w["entity"] == "Tobias Calloway" and w["new_value"] == "younger brother"


def test_a_warning_whose_values_match_no_fact_is_dropped(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Ines Calloway", "eyes", "grey", "grey eyes")],
        "[2]": [fact("Ines Calloway", "eyes", "grey", "still grey eyes")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [{
        "entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0,
        "new_value": "walked to the harbour", "existing_value": "never left the tower",
        "contradiction_type": "status", "confidence": 0.9, "explanation": "misread"}]})
    post(client, "ch1", "[1]")
    assert post(client, "ch2", "[2]")["contradictions"] == []


def test_A5_age_jump_within_a_vague_few_weeks_is_caught(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[3]": [fact("Pip Aldane", "age", "ten years old", "Pip was ten years old")],
        "[6]": [fact("Pip Aldane", "age", "Twelve-year-old", "the twelve-year-old Pip")]}))
    fake_ai.on("record_timing", timing({"[6]": ("time skip", "a few weeks later, still that autumn")}))
    post(client, "ch3", "[3]")
    [w] = [c for c in post(client, "ch6", "[6]")["contradictions"] if c["source"] == "story clock"]
    assert "less than a year" in w["explanation"]


def test_T2_storm_on_tuesday_then_friday_is_caught(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[4]": [fact("storm", "day", "Tuesday night", "the storm broke on Tuesday night", entity_type="event")],
        "[6]": [fact("storm", "occurred on", "Friday", "the storm on Friday", entity_type="event")]}))
    post(client, "ch4", "[4]")
    [w] = post(client, "ch6", "[6]")["contradictions"]
    assert w["source"] == "story clock" and "Tuesday" in w["explanation"] and "Friday" in w["explanation"]


def test_recurring_weekdays_of_non_events_are_left_alone(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("market", "day", "Tuesday", "market on Tuesday", entity_type="location")],
        "[2]": [fact("market", "day", "Friday", "the Friday market", entity_type="location")]}))
    post(client, "ch1", "[1]")
    assert post(client, "ch2", "[2]")["contradictions"] == []


def test_S1_dead_dog_barking_is_caught_but_memories_are_not(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[3]": [fact("Bramble", "status", "dead", "Bramble had died in the night")],
        "[4]": [fact("Bramble", "action", "remembered barking at the gulls", "she remembered Bramble barking")],
        "[5]": [fact("Bramble", "action", "barked at the gulls from the rocks", "Bramble barked at the gulls")]}))
    post(client, "ch3", "[3]")
    assert post(client, "ch4", "[4]")["contradictions"] == []          # a memory, not a mistake
    [w] = post(client, "ch5", "[5]")["contradictions"]
    assert w["source"] == "story clock" and w["contradiction_type"] == "status"


def test_acting_after_death_is_fine_in_a_flashback(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[3]": [fact("Bramble", "status", "dead", "Bramble had died")],
        "[4]": [fact("Bramble", "action", "barked at the gulls", "young Bramble barked at the gulls")]}))
    fake_ai.on("record_timing", timing({"[4]": ("flashback", "Bramble's first summer")}))
    post(client, "ch3", "[3]")
    assert post(client, "ch4", "[4]")["contradictions"] == []


def test_social_ties_are_kept_for_the_map_but_not_checked(client, fake_ai):
    rel = lambda a, r, b, q: {"person": a, "relation": r, "other_person": b, "source_quote": q}

    def reader(prompt):
        text = prompt.split("Chapter text:")[1]
        if "[1]" in text:
            return {"facts": [], "relationships": [rel("Pip Aldane", "apprentice", "Ines Calloway", "Pip, Ines's apprentice")]}
        return {"facts": [], "relationships": [rel("Pip Aldane", "ally", "Ines Calloway", "Pip stood with Ines as an ally")]}
    fake_ai.on("record_facts", reader)
    prompts = []
    fake_ai.on("report_contradictions", lambda p: prompts.append(p) or {"contradictions": []})
    post(client, "ch1", "[1]")
    post(client, "ch2", "[2]")
    assert prompts == []                                    # nothing social was sent to the checker
    m = client.get("/characters/map").json()
    assert {e["kind"] for e in m["edges"]} == {"mentor", "ally"}   # but the map has both ties


# --- from the second 4 Oct report (lighthouse-20261004-115953) -------------------------------
def test_the_same_new_fact_flagged_by_several_stages_is_one_warning(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Tobias Calloway", "plan", "might come before the autumn gales", "might come before the autumn gales")],
        "[2]": [fact("Tobias Calloway", "arrival", "three days before the storm", "arrived three days before the storm")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [{
        "entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "timeline",
        "confidence": c, "explanation": "x"} for c in (0.7, 0.8)]})
    fake_ai.on("report_cross_contradictions", lambda p: {"contradictions": [
        {"pair_index": i, "same_entity_confidence": 0.9, "contradiction_type": "timeline", "confidence": 0.6,
         "explanation": "y"} for i in range(p.count("<->"))]})
    post(client, "ch1", "[1]")
    assert len(post(client, "ch2", "[2]")["contradictions"]) == 1


def test_warnings_the_model_itself_doubts_are_dropped(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Ines Calloway", "eyes", "grey", "grey eyes")],
        "[2]": [fact("Ines Calloway", "eyes", "green", "green eyes")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [{
        "entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "attribute",
        "confidence": 0.3, "explanation": "The new fact is truncated; cannot assert contradiction; low confidence."}]})
    post(client, "ch1", "[1]")
    assert post(client, "ch2", "[2]")["contradictions"] == []


def test_buried_counts_as_dead(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[3]": [fact("Bramble", "fate", "buried behind the cottage under thrift flowers", "Ines buried him behind the cottage")],
        "[5]": [fact("Bramble", "behavior", "barked at the gulls from the rocks", "Bramble barked at the gulls")]}))
    post(client, "ch3", "[3]")
    [w] = post(client, "ch5", "[5]")["contradictions"]
    assert w["source"] == "story clock"


def test_killing_something_else_does_not_make_you_dead(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Tobias Calloway", "action", "killed a gull with a stone", "Tobias killed a gull")],
        "[2]": [fact("Tobias Calloway", "action", "walked to the harbour", "Tobias walked to the harbour")]}))
    post(client, "ch1", "[1]")
    assert post(client, "ch2", "[2]")["contradictions"] == []


def test_weekday_rule_works_when_the_storm_is_not_labelled_an_event(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[4]": [fact("storm", "day", "Tuesday night", "the storm broke on Tuesday night", entity_type="other")],
        "[6]": [fact("storm", "date reference", "Friday", "the storm on Friday", entity_type="other")]}))
    post(client, "ch4", "[4]")
    [w] = post(client, "ch6", "[6]")["contradictions"]
    assert "Tuesday" in w["explanation"]


# --- from the 3-run Ultra report (lighthouse-judge-...-20261004-232753) ----------------------
def test_burying_someone_else_does_not_make_you_dead(client, fake_ai):
    """D1 was flagged 3/3: "Ines | buried Bramble..." made the after-death rule think Ines was dead."""
    fake_ai.on("record_facts", facts_by_marker({
        "[3]": [fact("Ines Calloway", "action", "buried Bramble behind the cottage", "Ines buried Bramble")],
        "[4]": [fact("Ines Calloway", "activity", "feeding the flame", "Ines fed the flame all night")],
        "[6]": [fact("Ines Calloway", "action", "moved into the village for the winter", "she moved into the village")]}))
    post(client, "ch3", "[3]")
    assert post(client, "ch4", "[4]")["contradictions"] == []
    assert post(client, "ch6", "[6]")["contradictions"] == []


def test_something_dying_later_is_the_story_moving_forward(client, fake_ai):
    """Bramble alive (ch1) then buried (ch3) was flagged three times: set aside, not shown."""
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Bramble", "location", "asleep by the stove", "Bramble asleep by the stove")],
        "[3]": [fact("Bramble", "fate", "buried behind the cottage", "Ines buried him behind the cottage")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [{
        "entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "status",
        "confidence": 0.95, "explanation": "alive in ch1 but buried in ch3"}]})
    post(client, "ch1", "[1]")
    # "asleep by the stove" is a passing fact: no longer evidence at all (lasting.py), so no
    # warning is even raised; before, one was raised and set aside.
    assert all(w["status"] == "dismissed" for w in post(client, "ch3", "[3]")["contradictions"])


def test_the_reverse_dead_then_acting_is_still_a_mistake(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[3]": [fact("Bramble", "fate", "buried behind the cottage", "Ines buried him behind the cottage")],
        "[5]": [fact("Bramble", "behaviour", "barked at the gulls", "Bramble barked at the gulls")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [{
        "entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "status",
        "confidence": 0.95, "explanation": "buried but barking"}]})
    post(client, "ch3", "[3]")
    open_ = [c for c in post(client, "ch5", "[5]")["contradictions"] if c["status"] == "open"]
    assert len(open_) == 1


# --- from the 5 Oct report (lighthouse-judge-...-20261005-002647) -----------------------------
def _cross(explanation):
    return lambda p: {"contradictions": [
        {"pair_index": i, "same_entity_confidence": 0.9, "contradiction_type": "attribute", "confidence": 0.85,
         "explanation": explanation} for i in range(p.count("<->"))]}


def _two_names(fake_ai, a, a_fact, b, b_fact):
    fake_ai.on("record_facts", facts_by_marker({"[1]": [fact(a, *a_fact)], "[2]": [fact(b, *b_fact)]}))
    fake_ai.on("link_names", lambda p: {"resolutions": []})       # never linked: only the safety net sees it


def test_safety_net_drops_pairs_the_model_itself_says_are_different_people(client, fake_ai):
    _two_names(fake_ai, "Pip Aldane", ("role", "boy sent by the harbourmaster", "a boy the harbourmaster sent"),
               "Silas Rudd", ("role", "harbourmaster", "Silas Rudd, harbourmaster of Port Wick"))
    fake_ai.on("report_cross_contradictions", _cross("They cannot be the same person: one is a boy, one the harbourmaster."))
    post(client, "ch1", "[1]")
    assert post(client, "ch2", "[2]")["contradictions"] == []


def test_safety_net_keeps_a_secret_identity(client, fake_ai):
    """Glassmaker S3: Rook lost two fingers; Edwin Marsh (the same man) spreads all ten."""
    _two_names(fake_ai, "Rook", ("hands", "lost two fingers", "Rook lost two fingers"),
               "Edwin Marsh", ("hands", "spreads all ten fingers", "Edwin Marsh spread all ten fingers"))
    fake_ai.on("report_cross_contradictions", _cross("Edwin Marsh is Rook under a new name, but now has ten fingers."))
    post(client, "ch1", "[1]")
    [w] = post(client, "ch2", "[2]")["contradictions"]
    assert w["status"] == "open"


def test_something_dying_later_is_set_aside_as_a_timeline_warning_too(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Bramble", "home", "slept by the stove", "Bramble slept by the stove")],
        "[3]": [fact("Bramble", "fate", "buried behind the cottage", "Ines buried Bramble")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [{
        "entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "timeline",
        "confidence": 0.8, "explanation": "alive earlier, buried now, no death described"}]})
    post(client, "ch1", "[1]")
    [w] = post(client, "ch3", "[3]")["contradictions"]
    assert w["status"] == "dismissed"


def test_the_judge_uses_no_randomness(client, fake_ai, monkeypatch):
    import llm
    seen = {}
    real = llm.client.chat.completions.create

    def create(**kw):
        seen[kw["tools"][0]["function"]["name"]] = kw["temperature"]
        return real(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    llm.call_tool("x", {"type": "function", "function": {"name": "review_warnings", "parameters": {}}}, role="judge")
    assert seen["review_warnings"] == 0.0


# --- from the glassmaker report (glassmaker-judge-...-20261005-102142) ------------------------
def test_two_toms_bare_first_name_means_the_full_name_in_this_chapter(client, fake_ai):
    """D6, 3/3 runs: "Tom" beside "Tom Brisk" was linked to the drowned Tom Fenner."""
    fake_ai.on("record_facts", facts_by_marker({
        "[2]": [fact("Tom Fenner", "status", "drowned", "Tom Fenner drowned before anyone could reach him")],
        "[5]": [fact("Tom Brisk", "role", "captain's clerk", "Tom Brisk, the captain's clerk"),
                fact("Tom", "action", "took notes", "Tom took notes")]}))
    post(client, "ch2", "[2]")
    r = post(client, "ch5", "[5]")
    links = {l["name"]: l["canonical_name"] for l in r["entity_links"]}
    assert links["Tom"] == "Tom Brisk" and r["contradictions"] == []


def test_a_bare_first_name_with_two_full_names_in_the_chapter_is_left_alone(client, fake_ai):
    from entities import Resolution, prefer_same_chapter_full_names
    res = {"tom": Resolution("Tom", "character", 1, "Tom Fenner", "known name", 1.0),
           "tom brisk": Resolution("Tom Brisk", "character", None, "Tom Brisk", "new", 1.0),
           "tom fenner": Resolution("Tom Fenner", "character", 1, "Tom Fenner", "known name", 1.0)}
    prefer_same_chapter_full_names(res)
    assert res["tom"].canonical_name == "Tom Fenner"


def test_a_stated_real_name_links_the_secret_identity(client, fake_ai):
    """T2: Rook is 16 (ch1); 'Rook's real name is Edwin Marsh' (ch2); Edwin is 22 three years later (ch4)."""
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Rook", "age", "sixteen", "Rook was sixteen")],
        "[2]": [fact("Rook", "real name", "Edwin Marsh", "his real name was Edwin Marsh")],
        "[4]": [fact("Edwin Marsh", "age", "twenty-two", "Edwin Marsh, twenty-two now")]}))
    fake_ai.on("record_timing", timing({"[4]": ("time skip", "three years after the fire")}))
    post(client, "ch1", "[1]")
    post(client, "ch2", "[2]")
    r = post(client, "ch4", "[4]")
    assert {l["name"]: l["canonical_name"] for l in r["entity_links"]}["Edwin Marsh"] == "Rook"
    [w] = [c for c in r["contradictions"] if c["source"] == "story clock"]
    assert "about 19" in w["explanation"]


def test_a_stated_alias_merges_two_existing_entries(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Rook", "hands", "lost two fingers", "Rook lost two fingers")],
        "[2]": [fact("Edwin Marsh", "home", "the docks", "Edwin Marsh lived by the docks")],
        "[3]": [fact("Rook", "true name", "Edwin Marsh", "Rook's true name was Edwin Marsh")]}))
    fake_ai.on("link_names", lambda p: {"resolutions": []})
    post(client, "ch1", "[1]")
    post(client, "ch2", "[2]")
    post(client, "ch3", "[3]")
    names = [e["canonical_name"] for e in client.get("/entities").json()["entities"]]
    assert names.count("Rook") == 1 and "Edwin Marsh" not in names


def _judged(fake_ai, kind, explanation):
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [{
        "entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": kind,
        "confidence": 0.9, "explanation": explanation}]})


def test_a_warning_that_admits_consistency_is_set_aside(client, fake_ai):
    """D3, 3/3 runs: 'this is mathematically consistent. However...'"""
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Orla Venn", "age", "thirty-four", "Orla was thirty-four")],
        "[3]": [fact("Orla Venn", "age", "twenty-two", "Orla was twenty-two")]}))
    fake_ai.on("record_timing", timing({"[3]": ("flashback", "twelve years before the fire")}))
    _judged(fake_ai, "timeline", "22 twelve years earlier is mathematically consistent. However, the furnace...")
    post(client, "ch1", "[1]")
    [w] = post(client, "ch3", "[3]")["contradictions"]
    assert w["status"] == "dismissed" and "consistent" in w["review_note"]


def test_unmarked_in_a_flashback_then_scarred_later_is_set_aside(client, fake_ai):
    """D2: in the flashback (12 years earlier) Orla's palms are unmarked; the scar comes later."""
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Orla Venn", "hand", "pale scar across her right palm", "a pale scar ran across her right palm")],
        "[3]": [fact("Orla Venn", "hands", "palms unmarked by any burn or cut", "her palms unmarked")]}))
    fake_ai.on("record_timing", timing({"[3]": ("flashback", "twelve years before the fire")}))
    _judged(fake_ai, "attribute", "palms unmarked but scarred in chapter 1")
    post(client, "ch1", "[1]")
    [w] = post(client, "ch3", "[3]")["contradictions"]
    assert w["status"] == "dismissed"


def test_an_object_in_pieces_after_it_shattered_is_set_aside(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Sunstone lens", "state", "whole, wrapped in felt", "the lens lay whole, wrapped in felt")],
        "[4]": [fact("Sunstone lens", "state", "kept in pieces in a box", "the pieces of the Sunstone lens")]}))
    _judged(fake_ai, "attribute", "whole in chapter 1 but in pieces now")
    post(client, "ch1", "[1]")
    assert all(w["status"] == "dismissed" for w in post(client, "ch4", "[4]")["contradictions"])


@pytest.mark.parametrize("old,new", [
    # glassmaker A1: both sides scarred: a real mistake (which palm)
    (("hand", "pale scar across her right palm", "a pale scar ran across her right palm"),
     ("hand", "old scar on her left palm", "her left palm, where the old scar ran")),
    # glassmaker S4: mended seamlessly, then 'still cracked': the earlier side mentions breaking
    (("state", "mended whole and seamless", "whole and seamless, without a line to show where it had broken"),
     ("state", "still cracked down the middle", "still cracked down the middle, as since the fire")),
])
def test_real_mistakes_involving_injuries_or_breakage_stay_open(client, fake_ai, old, new):
    fake_ai.on("record_facts", facts_by_marker({"[1]": [fact("Orla Venn", *old)], "[2]": [fact("Orla Venn", *new)]}))
    _judged(fake_ai, "attribute", "contradiction")
    post(client, "ch1", "[1]")
    assert post(client, "ch2", "[2]")["contradictions"][0]["status"] == "open"


def test_identity_stated_in_the_same_chapter_is_merged_before_checking(client, fake_ai):
    """5 Oct log: 'merged' printed AFTER chapter 4 was checked, so T2 (Edwin 22, should be 19) was missed."""
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Rook", "age", "sixteen", "Rook was sixteen")],
        "[2]": [fact("Edwin Marsh", "description", "runaway son", "the runaway son, Edwin Marsh")],
        "[4]": [fact("Rook", "real name", "Edwin Marsh", "Rook, whose real name was Edwin Marsh"),
                fact("Edwin Marsh", "age", "twenty-two", "Edwin Marsh, twenty-two now")]}))
    fake_ai.on("link_names", lambda p: {"resolutions": []})
    fake_ai.on("record_timing", timing({"[2]": ("continues", "the same night"),
                                        "[4]": ("time skip", "three years after the fire")}))
    post(client, "ch1", "[1]")
    post(client, "ch2", "[2]")
    r = post(client, "ch4", "[4]")
    [w] = [c for c in r["contradictions"] if c["source"] == "story clock"]
    assert "about 19" in w["explanation"] and w["entity"] == "Rook"
    names = [e["canonical_name"] for e in client.get("/entities").json()["entities"]]
    assert "Edwin Marsh" not in names

"""Fewer requests (batched checks) and fewer false alarms (grounding and the double-check)."""
import re
import extract
from conftest import fact, facts_by_marker

STORY = {
    "[1]": [fact("Ada", "hair", "red", "Ada's red hair"), fact("Ben", "hair", "black", "Ben's black hair"),
            fact("Cy", "hair", "blond", "Cy's blond hair"), fact("Di", "hair", "brown", "Di's brown hair"),
            fact("Ed", "hair", "dark", "Ed's dark hair")],
    "[2]": [fact("Ada", "hair", "grey", "Ada's grey hair"), fact("Ben", "hair", "white", "Ben's white hair"),
            fact("Cy", "hair", "brown", "Cy's brown hair"), fact("Di", "hair", "red", "Di's red hair"),
            fact("Ed", "hair", "fair", "Ed's fair hair")],
}


def test_several_entities_share_one_request(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(STORY))
    prompts = []
    def check(p):
        prompts.append(p)
        # flag the entity in section 2 of the first request
        return {"contradictions": [{"entity_number": 2, "new_fact_index": 0, "existing_fact_index": 0,
                                    "contradiction_type": "attribute", "confidence": 0.9, "explanation": "hair"}]}
    fake_ai.on("report_contradictions", check)
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    r = client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()
    assert len(prompts) == 2                                   # 5 entities -> 2 requests (4 + 1), not 5
    assert prompts[0].count("ENTITY ") == 4
    flagged = {c["entity"] for c in r["contradictions"]}
    second_in_first_batch = re.findall(r'ENTITY 2: This entity is "(.+?)"', prompts[0])[0]
    assert second_in_first_batch in flagged                   # the answer was matched to the right section


def test_made_up_entity_numbers_are_ignored(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(STORY))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [
        {"entity_number": 9, "new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "attribute",
         "confidence": 0.9, "explanation": "no such section"}]})
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    assert client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()["contradictions"] == []


def test_double_check_dismisses_with_a_reason_but_keeps_the_warning(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({"[1]": [fact("Rex", "status", "alive", "Rex slept by the stove")],
                                                "[2]": [fact("Rex", "status", "dead", "Rex died in the night")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [
        {"entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "status",
         "confidence": 0.9, "explanation": "alive then dead"}]})
    reviews = []
    fake_ai.on("review_warnings", lambda p: reviews.append(p) or {"reviews": [
        {"warning_index": 0, "keep": False, "reason": "The dog dying later is the story moving forward."}]})
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    r = client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()
    assert "Rex died in the night" in reviews[0] and "Rex slept by the stove" in reviews[0]
    assert r["contradictions"][0]["status"] == "dismissed"
    assert client.get("/contradictions?status=open").json()["contradictions"] == []
    dismissed = client.get("/contradictions?status=dismissed").json()["contradictions"]
    assert dismissed[0]["review_note"].startswith("Double-check: The dog dying later")


def test_double_check_failure_keeps_every_warning(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({"[1]": [fact("Rex", "eyes", "blue", "blue eyes")],
                                                "[2]": [fact("Rex", "eyes", "green", "green eyes")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [
        {"entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "attribute",
         "confidence": 0.9, "explanation": "eyes"}]})
    def broken(p):
        raise RuntimeError("500 Internal server error")
    fake_ai.on("review_warnings", broken)
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    r = client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"})
    assert r.status_code == 200 and r.json()["contradictions"][0]["status"] == "open"


def test_invented_days_and_quotes_are_dropped(client, fake_ai, monkeypatch):
    monkeypatch.setattr(extract, "CHECK_GROUNDING", True)
    fake_ai.on("record_facts", lambda p: {"facts": [
        fact("the storm", "day", "Monday", "The storm broke", "event"),             # Monday isn't in the text
        fact("the storm", "day", "Tuesday night", "The storm broke on Tuesday night", "event"),
        fact("Ines", "eyes", "grey", "her silver eyes gleamed like distant lanterns"),   # quote isn't in the text
    ]})
    r = client.post("/extract", json={"chapter_id": "c", "text": "The storm broke on Tuesday night."}).json()
    assert [f["value"] for f in r["facts"]] == ["Tuesday night"]


def test_the_storm_links_to_the_storm_on_friday(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("the storm", "day", "Tuesday", "the storm broke on Tuesday", "event")],
        "[2]": [fact("the storm on Friday", "day", "Friday", "since the storm on Friday", "event")]}))
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1] the storm broke on Tuesday"})
    r = client.post("/chapters", json={"chapter_id": "c2", "text": "[2] since the storm on Friday"}).json()
    assert r["entity_links"][0]["method"] == "name match"
    assert r["entity_links"][0]["canonical_name"] == "the storm"

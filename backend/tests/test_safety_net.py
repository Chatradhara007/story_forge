"""The safety net: conflicts between facts filed under different names are still found."""
import llm
from conftest import fact, facts_by_marker

STORY = {
    "[1]": [fact("Ines Calloway", "eye colour", "grey", "Ines Calloway's grey eyes")],
    "[2]": [fact("The old keeper", "eye colour", "green", "the old keeper's green eyes")],
}


def setup(fake_ai):
    fake_ai.on("record_facts", facts_by_marker(STORY))
    fake_ai.on("link_names", lambda p: {"resolutions": []})     # linking FAILS: two separate cards


def test_split_pair_is_caught_by_the_safety_net(client, fake_ai):
    setup(fake_ai)
    prompts = []
    fake_ai.on("report_cross_contradictions", lambda p: prompts.append(p) or {"contradictions": [
        {"pair_index": 0, "same_entity_confidence": 0.9, "contradiction_type": "attribute",
         "confidence": 0.95, "explanation": "grey vs green eyes"}]})
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    r = client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()
    assert "The old keeper" in prompts[0] and "Ines Calloway" in prompts[0]
    assert len(r["contradictions"]) == 1
    c = r["contradictions"][0]
    assert c["entity"] == "Ines Calloway" and c["conflicting_chapter_id"] == "c1"
    assert "safety-net check" in r["timings_seconds"]


def test_unsure_same_entity_is_not_reported(client, fake_ai):
    setup(fake_ai)
    fake_ai.on("report_cross_contradictions", lambda p: {"contradictions": [
        {"pair_index": 0, "same_entity_confidence": 0.4, "contradiction_type": "attribute",
         "confidence": 0.95, "explanation": "maybe a different person"}]})
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    assert client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()["contradictions"] == []


def test_no_duplicate_when_normal_check_already_found_it(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(STORY))
    # linking succeeds this time, so the normal check finds it...
    fake_ai.on("link_names", lambda p: {"resolutions": [
        {"name": "The old keeper", "existing_entity_id": 1, "canonical_name": "Ines Calloway", "confidence": 0.9}]})
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [
        {"new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "attribute", "confidence": 0.9, "explanation": "eyes"}]})
    fake_ai.on("report_cross_contradictions", lambda p: {"contradictions": [
        {"pair_index": 0, "same_entity_confidence": 0.9, "contradiction_type": "attribute", "confidence": 0.9, "explanation": "eyes"}]})
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    r = client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()
    assert len(r["contradictions"]) == 1
    # ...and same-card pairs aren't even sent to the safety net
    assert fake_ai.calls.get("report_cross_contradictions", 0) == 0


def test_answers_use_low_randomness(client, fake_ai, monkeypatch):
    seen = []
    original = fake_ai._chat
    monkeypatch.setattr(llm.client.chat.completions, "create", lambda **kw: seen.append(kw.get("temperature")) or original(**kw))
    client.post("/extract", json={"chapter_id": "c", "text": "x"})
    assert seen[-1] == llm.TEMPERATURE == 0.2

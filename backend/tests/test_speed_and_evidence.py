"""Parallel checking, evidence filed under other entities, de-duplication, timings."""
import threading
import time
import llm
from conftest import fact, facts_by_marker

STORY = {
    "[ch1]": [fact("Ada", "hair", "red", "Ada's red hair"), fact("Ben", "hair", "black", "Ben's black hair"),
              fact("Cy", "hair", "blond", "Cy's blond hair"),
              fact("Ada", "threw", "the silver ring into the river", "Ada threw the silver ring into the river"),
              fact("The silver ring", "owner", "Ada", "Ada's silver ring", "item")],
    "[ch2]": [fact("Ada", "hair", "grey", "Ada's grey hair"), fact("Ben", "hair", "white", "Ben's white hair"),
              fact("Cy", "hair", "brown", "Cy's brown hair"),
              fact("The silver ring", "status", "being worn", "wearing the silver ring", "item")],
}


def test_entities_are_checked_at_the_same_time(client, fake_ai, monkeypatch):
    import contradictions
    monkeypatch.setattr(llm, "MAX_PARALLEL_AI_CALLS", 4)
    monkeypatch.setattr(contradictions, "CHECK_BATCH_SIZE", 1)     # one entity per request here
    fake_ai.on("record_facts", facts_by_marker(STORY))
    running, peak, lock = [0], [0], threading.Lock()

    def slow_check(prompt):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.3)
        with lock:
            running[0] -= 1
        return {"contradictions": []}
    fake_ai.on("report_contradictions", slow_check)
    client.post("/chapters", json={"chapter_id": "ch1", "text": "[ch1]"})
    started = time.time()
    r = client.post("/chapters", json={"chapter_id": "ch2", "text": "[ch2]"}).json()
    assert fake_ai.calls["report_contradictions"] == 4          # Ada, Ben, Cy, the ring
    assert peak[0] > 1                                          # ran at the same time
    assert time.time() - started < 1.0                          # 4 x 0.3s one-by-one would be 1.2s+
    assert set(r["timings_seconds"]) == {"reading facts", "linking names", "preparing search",
                                         "checking for mistakes", "story clock", "safety-net check", "double-checking", "saving"}


def test_evidence_filed_under_someone_else_is_shown(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(STORY))
    prompts = []
    fake_ai.on("report_contradictions", lambda p: prompts.append(p) or {"contradictions": []})
    client.post("/chapters", json={"chapter_id": "ch1", "text": "[ch1]"})
    client.post("/chapters", json={"chapter_id": "ch2", "text": "[ch2]"})
    ring_prompt = next(p for p in prompts if 'This entity is "The silver ring"' in p)
    assert "threw | the silver ring into the river" in ring_prompt


def test_one_warning_per_existing_fact(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({"[a]": [fact("Dog", "status", "dead", "the dog died")],
                                                "[b]": [fact("Dog", "action", "barked", "the dog barked"),
                                                        fact("Dog", "action2", "ran", "the dog ran")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [
        {"new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "status", "confidence": 0.9, "explanation": "barks"},
        {"new_fact_index": 1, "existing_fact_index": 0, "contradiction_type": "status", "confidence": 0.9, "explanation": "runs"}]})
    client.post("/chapters", json={"chapter_id": "a", "text": "[a]"})
    r = client.post("/chapters", json={"chapter_id": "b", "text": "[b]"}).json()
    assert len(r["contradictions"]) == 1


def test_one_warning_per_new_fact(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[a]": [fact("Rudd", "where", "harbour office", "stayed in the office"),
                fact("Rudd", "left", "not until dawn", "did not leave until dawn")],
        "[b]": [fact("Rudd", "action", "rowed out", "rowed out that night")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [
        {"new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "status", "confidence": 0.9, "explanation": "office"},
        {"new_fact_index": 0, "existing_fact_index": 1, "contradiction_type": "status", "confidence": 0.9, "explanation": "dawn"}]})
    client.post("/chapters", json={"chapter_id": "a", "text": "[a]"})
    r = client.post("/chapters", json={"chapter_id": "b", "text": "[b]"}).json()
    assert len(r["contradictions"]) == 1


def test_new_entities_are_checked_against_earlier_mentions(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[a]": [fact("Tuesday night", "day", "Tuesday", "The gale broke on Tuesday night", "event")],
        "[b]": [fact("The gale", "day", "Friday", "since the gale on Friday", "event"),
                fact("Nobody Else", "x", "y", "unrelated", "other")]}))
    fake_ai.on("link_names", lambda p: {"resolutions": []})   # everything stays new
    prompts = []
    fake_ai.on("report_contradictions", lambda p: prompts.append(p) or {"contradictions": [
        {"new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "timeline", "confidence": 0.9, "explanation": "Tuesday vs Friday"}]})
    client.post("/chapters", json={"chapter_id": "a", "text": "[a]"})
    r = client.post("/chapters", json={"chapter_id": "b", "text": "[b]"}).json()
    assert len(prompts) == 1                              # "Nobody Else" has no mentions: no AI call
    assert "The gale broke on Tuesday night" in prompts[0]
    assert r["contradictions"][0]["entity"] == "The gale"

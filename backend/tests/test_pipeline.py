"""Step 1 behaviour: ordering, no duplicates, all-or-nothing saving, retries, validation."""
from conftest import fact, facts_by_marker
from extract import split_into_pieces

EYES = {
    "[blue]": [fact("Marcus", "eye_color", "blue", "his blue eyes")],
    "[brown]": [fact("marcus", "eye_color", "brown", "his brown eyes", confidence=1.7),
                fact("marcus", "eye_color", "brown", "duplicate"),
                fact("Bad", "x", "y", "z", entity_type="spaceship")],
}


def flag_first(prompt):
    return {"contradictions": [
        {"new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "attribute", "confidence": 0.95, "explanation": "eyes changed"},
        {"new_fact_index": 9, "existing_fact_index": 0, "contradiction_type": "attribute", "confidence": 0.9, "explanation": "bad index"},
        {"new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "vibes", "confidence": 0.9, "explanation": "bad type"},
    ]}


def test_chapters_numbered_and_ordered(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(EYES))
    fake_ai.on("report_contradictions", flag_first)
    assert client.post("/chapters", json={"chapter_id": "ch1", "text": "[blue]"}).json()["chapter_number"] == 1
    assert client.post("/chapters", json={"chapter_id": "ch2", "text": "nothing"}).json()["chapter_number"] == 2
    r = client.post("/chapters", json={"chapter_id": "ch10", "text": "[brown]", "chapter_number": 10}).json()
    assert [c["chapter_id"] for c in client.get("/chapters").json()["chapters"]] == ["ch1", "ch2", "ch10"]
    assert [f["chapter_id"] for f in client.get("/facts/MARCUS").json()["facts"]] == ["ch1", "ch10"]
    # bad + duplicate facts dropped, confidence clamped
    assert len(r["facts"]) == 1 and r["facts"][0]["confidence"] == 1.0
    # only the valid contradiction kept
    assert len(r["contradictions"]) == 1 and r["contradictions"][0]["conflicting_chapter_id"] == "ch1"


def test_resubmitting_replaces_instead_of_duplicating(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(EYES))
    fake_ai.on("report_contradictions", flag_first)
    client.post("/chapters", json={"chapter_id": "ch1", "text": "[blue]"})
    client.post("/chapters", json={"chapter_id": "ch2", "text": "[brown]"})
    r = client.post("/chapters", json={"chapter_id": "ch2", "text": "[brown]"})
    assert r.json()["chapter_number"] == 2
    assert len(client.get("/facts/marcus").json()["facts"]) == 2
    assert len(client.get("/contradictions").json()["contradictions"]) == 1


def test_failure_saves_nothing_and_explains(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(EYES))
    client.post("/chapters", json={"chapter_id": "ch1", "text": "[blue]"})

    def broken(prompt):
        raise RuntimeError("AI down")
    fake_ai.on("report_contradictions", broken)
    r = client.post("/chapters", json={"chapter_id": "ch2", "text": "[brown]"})
    assert r.status_code == 502 and "failed after 6 tries" in r.json()["detail"]
    assert "ch2" not in [c["chapter_id"] for c in client.get("/chapters").json()["chapters"]]


def test_temporary_failures_and_garbled_answers_are_retried(client, fake_ai):
    fake_ai.fail_next = 2
    assert client.post("/extract", json={"chapter_id": "t", "text": "hi"}).status_code == 200
    answers = iter([None, "{not json", {"facts": []}])
    fake_ai.on("record_facts", lambda p: next(answers))
    assert client.post("/extract", json={"chapter_id": "t", "text": "hi"}).status_code == 200


def test_embeddings_are_batched(client, fake_ai):
    many = [fact(f"E{i}", "a", str(i), "q", entity_type="other") for i in range(70)]
    fake_ai.on("record_facts", lambda p: {"facts": many})
    fake_ai.on("link_names", lambda p: {"resolutions": []})
    client.post("/chapters", json={"chapter_id": "big", "text": "x"})
    assert fake_ai.calls["embed"] == 3


def test_long_chapters_are_split_without_losing_text():
    text = "\n".join(["word " * 200] * 60) + "\n" + "z" * 30000
    pieces = split_into_pieces(text)
    assert len(pieces) > 1 and all(len(p) <= 12000 for p in pieces)
    assert "".join(pieces).replace("\n", "") == text.replace("\n", "")


def test_input_validation_and_cors(client):
    assert client.post("/chapters", json={"chapter_id": "", "text": ""}).status_code == 422
    r = client.options("/chapters", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:3000")

"""Steps 4-5 backend features used by the website."""
from conftest import fact, facts_by_marker

STORY = {
    "[ch1]": [fact("Mira", "eye_color", "blue", "Mira's blue eyes"),
              fact("The flood", "happened", "the river burst its banks", "the river burst its banks", "event")],
    "[ch2]": [fact("Mira", "eye_color", "green", "Mira's green eyes"),
              fact("The wedding", "happened", "Mira married Joss", "Mira married Joss", "event")],
}


def setup(fake_ai, client):
    fake_ai.on("record_facts", facts_by_marker(STORY))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [
        {"new_fact_index": 0, "existing_fact_index": 0, "contradiction_type": "attribute",
         "confidence": 0.9, "explanation": "blue vs green"}]})
    client.post("/chapters", json={"chapter_id": "ch1", "text": "[ch1] The river rose."})
    client.post("/chapters", json={"chapter_id": "ch2", "text": "[ch2] A wedding."})


def test_chapter_detail_and_delete(client, fake_ai):
    setup(fake_ai, client)
    ch = client.get("/chapters/ch1").json()
    assert ch["text"].startswith("[ch1]") and len(ch["facts"]) == 2 and "fact_id" in ch["facts"][0]
    assert client.get("/chapters/nope").status_code == 404
    assert client.delete("/chapters/ch2").status_code == 200
    assert [c["chapter_id"] for c in client.get("/chapters").json()["chapters"]] == ["ch1"]
    assert client.get("/contradictions").json()["contradictions"] == []


def test_fact_correction_is_saved_and_logged(client, fake_ai):
    setup(fake_ai, client)
    fact_id = client.get("/chapters/ch1").json()["facts"][0]["fact_id"]
    edited = client.patch(f"/facts/{fact_id}", json={"value": "hazel"}).json()
    assert edited["value"] == "hazel" and edited["confidence"] == 1.0
    assert client.patch(f"/facts/{fact_id}", json={}).status_code == 400
    assert client.delete(f"/facts/{fact_id}").status_code == 200
    assert client.delete(f"/facts/{fact_id}").status_code == 404
    import storage
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("SELECT action FROM fact_corrections ORDER BY id")
        assert [r[0] for r in cur.fetchall()] == ["edit", "delete"]


def test_dismissing_a_warning(client, fake_ai):
    setup(fake_ai, client)
    warning = client.get("/contradictions?status=open").json()["contradictions"][0]
    assert warning["new_chapter_number"] == 2 and warning["conflicting_chapter_number"] == 1
    assert client.patch(f"/contradictions/{warning['id']}", json={"status": "dismissed"}).status_code == 200
    assert client.get("/contradictions?status=open").json()["contradictions"] == []
    assert len(client.get("/contradictions?status=dismissed").json()["contradictions"]) == 1
    assert client.patch("/contradictions/999", json={"status": "dismissed"}).status_code == 404


def test_timeline_lists_events_in_reading_order(client, fake_ai):
    setup(fake_ai, client)
    events = client.get("/timeline").json()["events"]
    assert [e["entity"] for e in events] == ["The flood", "The wedding"]


def test_ask_answers_from_stored_facts(client, fake_ai):
    assert client.post("/ask", json={"question": "Anything?"}).json()["answer"] == "No chapters have been added yet."
    setup(fake_ai, client)
    fake_ai.on("ask", lambda p: "<think>private</think>Mira's eyes are blue (ch. 1) but green (ch. 2).")
    r = client.post("/ask", json={"question": "What colour are Mira's eyes?"}).json()
    assert r["answer"] == "Mira's eyes are blue (ch. 1) but green (ch. 2)."
    assert len(r["sources"]) == 4


def test_website_is_served(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/app/"
    page = client.get("/app/")
    assert page.status_code == 200 and "StoryForge" in page.text

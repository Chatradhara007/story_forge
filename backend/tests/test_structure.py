"""Reading in passages, chapter timing notes, and title + surname linking."""
import re
import extract
from conftest import fact, facts_by_marker


def test_chapters_are_read_in_passages_with_context(client, fake_ai, monkeypatch):
    monkeypatch.setattr(extract, "READ_PASSAGE_CHARS", 200)
    paragraphs = [f"Paragraph {i}. " + "Some words here. " * 8 for i in range(4)]
    text = "\n\n".join(paragraphs)
    prompts = []
    fake_ai.on("record_facts", lambda p: prompts.append(p) or {"facts": []})
    client.post("/extract", json={"chapter_id": "c", "text": text})
    assert len(prompts) >= 3                                      # several passages, not one call
    assert "EARLIER IN THE SAME CHAPTER" not in prompts[0]        # first passage: no context
    later = next(p for p in prompts if "Chapter text:\nParagraph 2." in p)
    assert "EARLIER IN THE SAME CHAPTER" in later and "Paragraph 1." in later.split("Chapter text:")[0]


def test_passages_keep_all_the_text():
    text = "\n\n".join(["Short one.", "A much longer paragraph. " * 60, "End."])
    passages = extract.split_into_passages(text, 300)
    assert all(len(p) <= 300 for p in passages)
    assert re.sub(r"\s+", "", "".join(passages)) == re.sub(r"\s+", "", text)


def test_timing_notes_are_saved_and_shown_to_the_checker(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Orla", "palm", "scarred", "a scar across her palm")],
        "[2]": [fact("Orla", "palm", "unmarked", "her palms unmarked")]}))
    fake_ai.on("record_timing", lambda p: {"setting": "flashback", "description": "twelve years before the fire"}
               if "[2]" in p else {"setting": "continues", "description": "the night of the festival"})
    prompts = []
    fake_ai.on("report_contradictions", lambda p: prompts.append(p) or {"contradictions": []})
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    r = client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()
    assert r["time_note"] == "flashback: twelve years before the fire"
    assert "chapter 1: continues: the night of the festival" in prompts[0]
    assert "chapter 2 (the NEW chapter): flashback: twelve years before the fire" in prompts[0]
    assert client.get("/chapters/c2").json()["time_note"].startswith("flashback")


def test_title_and_surname_link_when_the_surname_is_unique(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Aldous Crane", "height", "tall", "tall and stooping")],
        "[2]": [fact("Captain Crane", "height", "short", "the short captain")]}))
    fake_ai.on("link_names", lambda p: {"resolutions": []})
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    r = client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()
    assert r["entity_links"][0]["method"] == "name match"
    assert r["entity_links"][0]["canonical_name"] == "Aldous Crane"


def test_title_and_shared_surname_is_left_to_the_ai(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Ines Calloway", "eyes", "grey", "grey eyes"), fact("Mara Calloway", "age", "20", "twenty")],
        "[2]": [fact("Keeper Calloway", "eyes", "green", "green eyes")]}))
    fake_ai.on("link_names", lambda p: {"resolutions": [
        {"name": n, "existing_entity_id": 0, "canonical_name": n, "confidence": 0.9}
        for n in re.findall(r"^- (.+?) \|", p, re.M)]})
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    r = client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"}).json()
    assert r["entity_links"][0]["method"] == "new"

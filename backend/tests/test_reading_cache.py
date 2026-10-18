"""
READING_CACHE (reading_cache.py): the same chapter text is read once; checking it again (a demo
rehearsed beforehand, an unchanged chapter re-submitted) uses the saved reading and vectors.
"""
import reading_cache
from conftest import fact, facts_by_marker


def test_the_same_text_is_read_once(client, fake_ai, monkeypatch, tmp_path):
    monkeypatch.setattr(reading_cache, "_FOLDER", str(tmp_path))
    fake_ai.on("record_facts", facts_by_marker({"[1]": [fact("Ines Calloway", "eyes", "grey", "grey eyes")]}))
    first = client.post("/chapters", json={"chapter_id": "a", "text": "[1] The light."}).json()
    reads, embeds = fake_ai.calls["record_facts"], fake_ai.calls.get("embed", 0)
    again = client.post("/chapters", json={"chapter_id": "b", "text": "[1]   The light.\n"}).json()
    assert fake_ai.calls["record_facts"] == reads                     # not read again
    assert fake_ai.calls.get("embed", 0) == embeds                    # vectors reused too
    assert [f["value"] for f in again["facts"]] == [f["value"] for f in first["facts"]] == ["grey"]
    assert again["chapter_id"] == "b"


def test_without_the_setting_nothing_is_saved(client, fake_ai, tmp_path):
    fake_ai.on("record_facts", facts_by_marker({"[1]": [fact("A", "x", "1", "q")]}))
    client.post("/chapters", json={"chapter_id": "a", "text": "[1]"})
    client.post("/chapters", json={"chapter_id": "b", "text": "[1]"})
    assert fake_ai.calls["record_facts"] >= 2
    assert not list(tmp_path.iterdir())

"""Step 2 behaviour: different names for the same entity are linked (and wrong links are avoided)."""
import re
from conftest import fact, facts_by_marker

STORY = {
    "[ch1]": [fact("Marcus Vale", "eye_color", "blue", "Marcus Vale's blue eyes"),
              fact("Marcus", "rank", "captain", "Marcus, captain of the guard"),
              fact("The Rusty Anchor", "type", "tavern", "the Rusty Anchor tavern", "location"),
              fact("he", "mood", "angry", "he was angry")],
    "[ch2]": [fact("Captain Vale", "eye_color", "brown", "Captain Vale's brown eyes")],
    "[ch3]": [fact("captain vale", "age", "40", "forty years old")],
    "[ch4]": [fact("Elena Vale", "eye_color", "green", "his sister Elena Vale, green-eyed")],
    "[ch5]": [fact("The Stranger", "eye_color", "grey", "grey eyes"),
              fact("Old Tom", "job", "barman", "Old Tom the barman"),
              fact("Anchor", "owner", "Tom", "the Anchor was Tom's")],
}
# lowercase new name -> (known canonical name to link to, or None; canonical_name; confidence)
LINKS = {
    "marcus": (None, "Marcus Vale", 0.9), "marcus vale": (None, "Marcus Vale", 0.95),
    "captain vale": ("Marcus Vale", "Marcus Vale", 0.85), "elena vale": (None, "Elena Vale", 0.9),
    "the stranger": ("Marcus Vale", "The Stranger", 0.5),      # too unsure
    "old tom": ("Nobody Real", "Old Tom", 0.99),                # points at nothing
    "anchor": ("The Rusty Anchor", "Anchor", 0.95),             # person -> place
}


def link_names(prompt):
    known = {n.strip(): int(i) for i, n in re.findall(r"^\[(\d+)\] (.+?) \|", prompt, re.M)}
    out = []
    for name in re.findall(r"^- (.+?) \|", prompt, re.M):
        target, canonical, conf = LINKS.get(name.lower(), (None, name, 0.9))
        out.append({"name": name, "existing_entity_id": known.get(target, 0) if target else 0,
                    "canonical_name": canonical, "confidence": conf})
    return {"resolutions": out}


def eye_conflicts(prompt):
    head, tail = prompt.split("EXISTING facts (index")
    new = re.findall(r"^(\d+): .+? \| eye_color \| (\w+) \|", head, re.M)
    old = re.findall(r"^(\d+): .+? \| eye_color \| (\w+) \| chapter", tail, re.M)
    return {"contradictions": [
        {"new_fact_index": int(n), "existing_fact_index": int(o), "contradiction_type": "attribute",
         "confidence": 0.9, "explanation": f"{ov} vs {nv}"}
        for n, nv in new for o, ov in old if nv != ov][:1]}


def setup(fake_ai):
    fake_ai.on("record_facts", facts_by_marker(STORY))
    fake_ai.on("link_names", link_names)
    fake_ai.on("report_contradictions", eye_conflicts)


def test_names_are_linked_and_mistakes_caught_across_names(client, fake_ai):
    setup(fake_ai)
    r1 = client.post("/chapters", json={"chapter_id": "ch1", "text": "[ch1]"}).json()
    assert not any(f["entity"] == "he" for f in r1["facts"])
    people = [e for e in client.get("/entities").json()["entities"] if e["entity_type"] == "character"]
    assert len(people) == 1 and set(people[0]["aliases"]) == {"Marcus", "Marcus Vale"}

    r2 = client.post("/chapters", json={"chapter_id": "ch2", "text": "[ch2]"}).json()
    assert r2["entity_links"][0]["method"] == "AI match"
    assert len(r2["contradictions"]) == 1
    assert r2["contradictions"][0]["entity"] == "Marcus Vale"
    assert "Captain Vale" in fake_ai.prompts["report_contradictions"]

    calls_before = fake_ai.calls["link_names"]
    r3 = client.post("/chapters", json={"chapter_id": "ch3", "text": "[ch3]"}).json()
    assert fake_ai.calls["link_names"] == calls_before
    assert r3["entity_links"][0]["method"] == "known name"

    facts = client.get("/facts/Captain Vale").json()
    assert facts["canonical_name"] == "Marcus Vale"
    assert {f["chapter_id"] for f in facts["facts"]} == {"ch1", "ch2", "ch3"}


def test_unsafe_links_are_rejected(client, fake_ai):
    setup(fake_ai)
    for ch in ("ch1", "ch4", "ch5"):
        r = client.post("/chapters", json={"chapter_id": ch, "text": f"[{ch}]"}).json()
    methods = {l["name"]: l["method"] for l in r["entity_links"]}
    assert methods == {"The Stranger": "new", "Old Tom": "new", "Anchor": "new"}
    names = [e["canonical_name"] for e in client.get("/entities").json()["entities"]]
    assert "Elena Vale" in names and "Marcus Vale" in names
    assert not client.get("/contradictions").json()["contradictions"]


def test_merge_and_detach(client, fake_ai):
    setup(fake_ai)
    client.post("/chapters", json={"chapter_id": "ch1", "text": "[ch1]"})
    client.post("/chapters", json={"chapter_id": "ch5", "text": "[ch5]"})
    entities = {e["canonical_name"]: e["id"] for e in client.get("/entities").json()["entities"]}
    merged = client.post("/entities/merge", json={"keep_entity_id": entities["Marcus Vale"],
                                                  "merge_entity_id": entities["The Stranger"]}).json()
    assert "The Stranger" in merged["aliases"]
    split = client.post(f"/entities/{entities['Marcus Vale']}/detach", json={"name": "The Stranger"}).json()
    assert split["split_off"]["canonical_name"] == "The Stranger" and split["split_off"]["fact_count"] == 1
    assert client.post(f"/entities/{entities['Marcus Vale']}/detach", json={"name": "Gandalf"}).status_code == 400
    assert client.get("/facts/Nobody").status_code == 404

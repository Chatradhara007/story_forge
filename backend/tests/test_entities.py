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
    # "Captain Vale" is linked by the title + surname rule (the only Vale known so far)
    assert r2["entity_links"][0]["method"] == "name match"
    assert r2["entity_links"][0]["canonical_name"] == "Marcus Vale"
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


def test_name_rule_links_first_names_without_the_ai(client, fake_ai):
    table = {
        "[a]": [fact("Tobias", "relation", "older brother", "her older brother Tobias"),
                fact("Ines Calloway", "eyes", "grey", "grey eyes")],
        "[b]": [fact("Tobias Calloway", "hand", "lost left hand", "lost his left hand"),
                fact("Calloway", "note", "x", "the Calloway family"),       # surname only: not by rule
                fact("Keeper", "note", "y", "the keeper")],                   # title only: not by rule
    }
    fake_ai.on("record_facts", facts_by_marker(table))
    fake_ai.on("link_names", lambda p: {"resolutions": []})
    client.post("/chapters", json={"chapter_id": "a", "text": "[a]"})
    r = client.post("/chapters", json={"chapter_id": "b", "text": "[b]"}).json()
    methods = {l["name"]: l["method"] for l in r["entity_links"]}
    assert methods["Tobias Calloway"] == "name match"
    assert methods["Calloway"] == "new" and methods["Keeper"] == "new"
    assert "Tobias Calloway" in client.get("/facts/Tobias").json()["aliases"]


def test_name_rule_skips_ambiguous_first_names(client, fake_ai):
    table = {"[a]": [fact("Tom Reed", "job", "baker", "Tom Reed the baker"),
                     fact("Tom Hale", "job", "smith", "Tom Hale the smith")],
             "[b]": [fact("Tom", "mood", "happy", "Tom smiled")]}
    fake_ai.on("record_facts", facts_by_marker(table))
    fake_ai.on("link_names", lambda p: {"resolutions": [
        {"name": n, "existing_entity_id": 0, "canonical_name": n, "confidence": 0.9}
        for n in re.findall(r"^- (.+?) \|", p, re.M)]})
    client.post("/chapters", json={"chapter_id": "a", "text": "[a]"})
    r = client.post("/chapters", json={"chapter_id": "b", "text": "[b]"}).json()
    assert r["entity_links"][0]["method"] == "new"     # two Toms: left to the AI, which said new


def test_sister_is_not_linked_to_titled_brother(client, fake_ai):
    """Marcus Vale is also 'Captain Vale'; his sister Elena Vale must stay separate."""
    setup(fake_ai)
    for ch in ("ch1", "ch2"):
        client.post("/chapters", json={"chapter_id": ch, "text": f"[{ch}]"})
    r = client.post("/chapters", json={"chapter_id": "ch4", "text": "[ch4]"}).json()
    assert r["entity_links"][0]["name"] == "Elena Vale" and r["entity_links"][0]["method"] == "new"


def test_a_name_that_is_only_an_article_does_not_crash(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({"[a]": [fact("A", "x", "1", "q")],
                                                "[b]": [fact("The", "x", "2", "q"), fact("A", "x", "3", "q")]}))
    client.post("/chapters", json={"chapter_id": "a", "text": "[a]"})
    assert client.post("/chapters", json={"chapter_id": "b", "text": "[b]"}).status_code == 200

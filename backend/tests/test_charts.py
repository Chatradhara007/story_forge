"""Relationships, the character map, the presence map and the book shelf."""
from conftest import fact


def rel(person, relation, other, quote):
    return {"person": person, "relation": relation, "other_person": other, "source_quote": quote}


def reader(table):
    """Fake extractor returning facts AND relationships by marker."""
    def handler(prompt):
        text = prompt.split("Chapter text:")[1]
        for marker, (facts, rels) in table.items():
            if marker in text:
                return {"facts": facts, "relationships": rels}
        return {"facts": []}
    return handler


STORY = {
    "[1]": ([fact("Ines Calloway", "eyes", "grey", "grey eyes")],
            [rel("Edmund Hale", "father", "Ines Calloway", "Edmund Hale, father of Ines"),
             rel("Rook", "son", "Ines Calloway", "her son Rook"),
             rel("Ines Calloway", "wife", "Tobias Calloway", "Ines and her husband Tobias"),
             rel("Mara Calloway", "sister", "Ines Calloway", "her sister Mara"),
             rel("he", "friend", "Ines Calloway", "he was her friend")]),          # pronoun: dropped
    "[2]": ([fact("Tobias Calloway", "status", "drowned", "Tobias drowned")],
            [rel("Marcus Vale", "sworn enemy", "Tobias Calloway", "Marcus, Tobias's sworn enemy")]),
    "[3]": ([], [rel("Mara Calloway", "cousin", "Ines Calloway", "her cousin Mara")]),
}


def load(client, fake_ai):
    fake_ai.on("record_facts", reader(STORY))
    for i in (1, 2, 3):
        assert client.post("/chapters", json={"chapter_id": f"c{i}", "text": f"[{i}]"}).status_code == 200


def test_relationships_are_normalised_and_mapped(client, fake_ai):
    load(client, fake_ai)
    m = client.get("/characters/map").json()
    names = {p["id"]: p["name"] for p in m["people"]}
    edges = {(names[e["from"]], e["kind"], names[e["to"]]) for e in m["edges"]}
    assert ("Edmund Hale", "parent", "Ines Calloway") in edges
    assert ("Ines Calloway", "parent", "Rook") in edges                     # "son of" reversed
    assert any(k == "spouse" for _, k, _ in edges)
    assert ("Marcus Vale", "enemy", "Tobias Calloway") in edges or ("Tobias Calloway", "enemy", "Marcus Vale") in edges
    assert not any("he" in (a.lower(), b.lower()) for a, _, b in edges)
    people = {p["name"]: p for p in m["people"]}
    assert people["Tobias Calloway"]["died_chapter"] == 2
    assert people["Marcus Vale"]["first_chapter"] == 2


def test_impossible_family_ties_are_marked(client, fake_ai):
    load(client, fake_ai)
    m = client.get("/characters/map").json()
    mara = [e for e in m["edges"] if e["kind"] in ("sibling", "relative")]
    assert len(mara) == 2 and all(e.get("conflicts") for e in mara)
    sibling = next(e for e in mara if e["kind"] == "sibling")
    assert sibling["conflicts"][0]["first_chapter"] == 3 and "cousin" in sibling["conflicts"][0]["quote"]


def test_relationships_become_facts_for_the_checker(client, fake_ai):
    load(client, fake_ai)
    facts = client.get("/facts/Mara Calloway").json()["facts"]
    assert {"sibling of Ines Calloway", "related to Ines Calloway"} <= {f["value"] for f in facts}


def test_resubmitting_replaces_relationships_and_merge_moves_them(client, fake_ai):
    load(client, fake_ai)
    client.post("/chapters", json={"chapter_id": "c3", "text": "nothing now"})
    assert not any(e.get("conflicts") for e in client.get("/characters/map").json()["edges"])
    ids = {e["canonical_name"]: e["id"] for e in client.get("/entities").json()["entities"]}
    client.post("/entities/merge", json={"keep_entity_id": ids["Ines Calloway"], "merge_entity_id": ids["Mara Calloway"]})
    m = client.get("/characters/map").json()
    assert all(e["from"] != e["to"] for e in m["edges"])                    # no self-relationships


def test_presence_map(client, fake_ai):
    load(client, fake_ai)
    p = client.get("/presence").json()
    assert [c["chapter_id"] for c in p["chapters"]] == ["c1", "c2", "c3"]
    ines = next(e for e in p["entities"] if e["name"] == "Ines Calloway")
    assert set(ines["cells"]) == {"c1", "c3"}


def test_book_shelf_fields_and_activity(client, fake_ai):
    b = client.post("/projects", json={"name": "The Fallen King", "kind": "novel",
                                       "synopsis": "A king loses everything.", "cover_color": "sage"}).json()
    assert b["cover_color"] == "sage"
    assert client.patch(f"/projects/{b['id']}", json={"cover_color": "plum", "kind": "serial"}).json()["kind"] == "serial"
    assert client.patch(f"/projects/{b['id']}", json={"cover_color": "neon"}).status_code == 422
    client.post(f"/projects/{b['id']}/chapters/jobs", json={"chapter_id": "c1", "text": "x"})
    shelf = client.get("/projects").json()["projects"][0]
    assert shelf["cover_color"] == "plum" and shelf["last_edited"]
    assert client.get("/activity").json()["activity"][0]["project_name"] == "The Fallen King"

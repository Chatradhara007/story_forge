"""Several books in one database: nothing may mix between them."""
from conftest import fact, facts_by_marker

BOOK_ONE = {"[b1]": [fact("Tom", "job", "ferryman", "Tom the ferryman"), fact("Tom", "eyes", "blue", "Tom's blue eyes")]}
BOOK_TWO = {"[b2]": [fact("Tom", "job", "clerk", "Tom the clerk"), fact("Tom", "eyes", "brown", "Tom's brown eyes")]}


def new_book(client, name):
    r = client.post("/projects", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


def test_books_are_created_listed_renamed_and_counted(client, fake_ai):
    one = new_book(client, "The Glassmaker")
    two = new_book(client, "Lighthouse")
    names = [p["name"] for p in client.get("/projects").json()["projects"]]
    assert names == ["Lighthouse", "The Glassmaker"]                   # alphabetical
    assert client.post("/projects", json={"name": "lighthouse"}).status_code == 409   # names are unique
    assert client.patch(f"/projects/{two}", json={"name": "The Gullstone Light"}).json()["name"] == "The Gullstone Light"
    assert client.patch(f"/projects/{one}", json={"name": "The Gullstone Light"}).status_code == 409
    fake_ai.on("record_facts", facts_by_marker(BOOK_ONE))
    client.post(f"/projects/{one}/chapters", json={"chapter_id": "ch1", "text": "[b1]"})
    counts = {p["name"]: p["chapter_count"] for p in client.get("/projects").json()["projects"]}
    assert counts == {"The Glassmaker": 1, "The Gullstone Light": 0}


def test_same_names_in_two_books_never_mix(client, fake_ai):
    one, two = new_book(client, "Book one"), new_book(client, "Book two")
    fake_ai.on("record_facts", facts_by_marker({**BOOK_ONE, **BOOK_TWO}))
    checks = []
    fake_ai.on("report_contradictions", lambda p: checks.append(p) or {"contradictions": []})
    fake_ai.on("report_cross_contradictions", lambda p: checks.append(p) or {"contradictions": []})
    # both books have a "ch1" and a "Tom"
    assert client.post(f"/projects/{one}/chapters", json={"chapter_id": "ch1", "text": "[b1]"}).status_code == 200
    r = client.post(f"/projects/{two}/chapters", json={"chapter_id": "ch1", "text": "[b2]"}).json()
    assert r["chapter_number"] == 1                                   # numbering is per book
    assert all(l["method"] == "new" for l in r["entity_links"])       # book two's Tom is NOT book one's Tom
    assert checks == []                                               # nothing from book one was compared
    tom1 = client.get(f"/projects/{one}/facts/Tom").json()
    tom2 = client.get(f"/projects/{two}/facts/Tom").json()
    assert {f["value"] for f in tom1["facts"]} == {"ferryman", "blue"}
    assert {f["value"] for f in tom2["facts"]} == {"clerk", "brown"}
    assert len(client.get(f"/projects/{one}/entities").json()["entities"]) == 1
    assert client.get(f"/projects/{two}/chapters/ch1").json()["text"] == "[b2]"


def test_things_from_another_book_cannot_be_reached(client, fake_ai):
    one, two = new_book(client, "Book one"), new_book(client, "Book two")
    fake_ai.on("record_facts", facts_by_marker(BOOK_ONE))
    client.post(f"/projects/{one}/chapters", json={"chapter_id": "ch1", "text": "[b1]"})
    entity_id = client.get(f"/projects/{one}/entities").json()["entities"][0]["id"]
    fact_id = client.get(f"/projects/{one}/chapters/ch1").json()["facts"][0]["fact_id"]
    assert client.get(f"/projects/{two}/entities/{entity_id}").status_code == 404
    assert client.patch(f"/projects/{two}/facts/{fact_id}", json={"value": "x"}).status_code == 404
    assert client.delete(f"/projects/{two}/facts/{fact_id}").status_code == 404
    assert client.delete(f"/projects/{two}/chapters/ch1").status_code == 404
    assert client.get("/projects/999/chapters").status_code == 404


def test_deleting_a_book_removes_everything_in_it_and_nothing_else(client, fake_ai):
    one, two = new_book(client, "Book one"), new_book(client, "Book two")
    fake_ai.on("record_facts", facts_by_marker({**BOOK_ONE, **BOOK_TWO}))
    client.post(f"/projects/{one}/chapters", json={"chapter_id": "ch1", "text": "[b1]"})
    client.post(f"/projects/{two}/chapters", json={"chapter_id": "ch1", "text": "[b2]"})
    assert client.delete(f"/projects/{one}").status_code == 200
    assert client.get(f"/projects/{one}").status_code == 404
    import storage
    with storage.db() as conn, conn.cursor() as cur:
        for table in ("chapters", "facts", "entities", "entity_aliases"):
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id = %s", (one,))
            assert cur.fetchone()[0] == 0, table
    assert len(client.get(f"/projects/{two}/entities").json()["entities"]) == 1


def test_short_addresses_use_the_first_book(client, fake_ai):
    assert client.get("/projects").json()["projects"] == []
    fake_ai.on("record_facts", facts_by_marker(BOOK_ONE))
    client.post("/chapters", json={"chapter_id": "ch1", "text": "[b1]"})     # creates "My story"
    books = client.get("/projects").json()["projects"]
    assert [b["name"] for b in books] == ["My story"]
    assert client.get(f"/projects/{books[0]['id']}/chapters").json()["chapters"][0]["chapter_id"] == "ch1"

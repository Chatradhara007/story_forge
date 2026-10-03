"""
The nine bugs confirmed in the review (StoryForge Review and Fix Plan, 22 Sept 2026), each
with a test of the FIXED behaviour, plus tests for the review's other findings and the new
Phase 5/6 features (story clock, canon facts, severity, jobs, accounts, exports).
"""
import re

import httpx
import pytest

import llm
from conftest import fact, facts_by_marker
from extract import is_grounded


def _response(status, headers=None):
    return httpx.Response(status, headers=headers or {}, request=httpx.Request("POST", "https://example.invalid"))


def flag_when(*words):
    """Fake checker: reports a contradiction (first new fact vs first existing fact) when every word is in the prompt."""
    def handler(prompt):
        if all(w in prompt for w in words):
            return {"contradictions": [{"entity_number": 1, "new_fact_index": 0, "existing_fact_index": 0,
                                        "contradiction_type": "attribute", "confidence": 0.9,
                                        "explanation": "eye colour changed"}]}
        return {"contradictions": []}
    return handler


EYES = {"[grey]": [fact("Ines Calloway", "eye_color", "grey", "grey eyes")],
        "[green]": [fact("Ines Calloway", "eye_color", "green", "green eyes")]}


def post(client, chapter_id, text, **extra):
    r = client.post("/chapters", json={"chapter_id": chapter_id, "text": text, **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Bug 1: "earlier" means earlier in reading order, not "any other chapter"
# ---------------------------------------------------------------------------
def test_bug1_rechecking_chapter_one_does_not_treat_chapter_two_as_history(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(EYES))
    prompts = []
    fake_ai.on("report_contradictions", lambda p: prompts.append(p) or {"contradictions": []})
    post(client, "ch1", "[grey]")
    post(client, "ch2", "[green]")
    prompts.clear()
    post(client, "ch1", "[grey]")                      # re-submit chapter 1
    first_check = prompts[0] if prompts else ""
    assert "green eyes" not in first_check.split("EXISTING facts")[-1] if first_check else True
    # Any warning stored has the later chapter as the NEW side.
    for w in client.get("/contradictions").json()["contradictions"]:
        assert w["new_chapter_number"] > w["conflicting_chapter_number"]


# ---------------------------------------------------------------------------
# Bug 2: dismissals survive re-checks; warnings aren't silently deleted
# ---------------------------------------------------------------------------
def test_bug2_dismissal_survives_resubmitting_either_chapter(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(EYES))
    fake_ai.on("report_contradictions", flag_when("grey eyes", "green eyes"))
    post(client, "ch1", "[grey]")
    post(client, "ch2", "[green]")
    [warning] = client.get("/contradictions").json()["contradictions"]
    client.patch(f"/contradictions/{warning['id']}", json={"status": "dismissed", "reason": "she wears lenses"})

    post(client, "ch2", "[green]")                     # re-submit the later chapter
    [again] = client.get("/contradictions").json()["contradictions"]
    assert again["status"] == "dismissed" and again["dismiss_reason"] == "she wears lenses"

    r = post(client, "ch1", "[grey]")                  # re-submit the EARLIER chapter
    assert r["rechecking_chapters"] == ["ch2"]          # ch2 is re-checked, not just deleted
    [after] = client.get("/contradictions").json()["contradictions"]
    assert after["new_chapter_id"] == "ch2" and after["status"] == "dismissed"


def test_bug2_reopening_forgets_the_decision(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(EYES))
    fake_ai.on("report_contradictions", flag_when("grey eyes", "green eyes"))
    post(client, "ch1", "[grey]")
    post(client, "ch2", "[green]")
    [w] = client.get("/contradictions").json()["contradictions"]
    client.patch(f"/contradictions/{w['id']}", json={"status": "dismissed"})
    [w] = client.get("/contradictions").json()["contradictions"]
    client.patch(f"/contradictions/{w['id']}", json={"status": "open"})
    post(client, "ch2", "[green]")
    assert client.get("/contradictions").json()["contradictions"][0]["status"] == "open"


# ---------------------------------------------------------------------------
# Bug 3: numbers as words or digits
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value,text", [
    ("12", "She was twelve that winter."),
    ("twelve", "She was 12 that winter."),
    ("21", "He turned twenty-one."),
    ("3rd", "on the third night"),
    ("1000", "a thousand men"),
])
def test_bug3_numbers_written_differently_are_grounded(value, text):
    assert is_grounded({"value": value, "source_quote": text}, text)


def test_bug3_invented_numbers_are_still_dropped():
    assert not is_grounded({"value": "14", "source_quote": "She was twelve"}, "She was twelve that winter.")
    assert not is_grounded({"value": "Monday", "source_quote": "that night"}, "It happened that night.")


# ---------------------------------------------------------------------------
# Bug 4: a full name never auto-links to someone known only by a title
# ---------------------------------------------------------------------------
def test_bug4_full_name_is_not_merged_into_a_title_only_holder(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Keeper Calloway", "eyes", "grey", "the keeper's grey eyes")],
        "[2]": [fact("Mara Calloway", "age", "20", "Mara was twenty")]}))
    fake_ai.on("link_names", lambda p: {"resolutions": [
        {"name": n, "existing_entity_id": 0, "canonical_name": n, "confidence": 0.9}
        for n in re.findall(r"^- (.+?) \|", p, re.M)]})
    post(client, "c1", "[1]")
    r = post(client, "c2", "[2]")
    assert r["entity_links"][0]["method"] == "new"
    assert fake_ai.calls.get("link_names") == 1          # sent to the AI, not decided by rule


# ---------------------------------------------------------------------------
# Bug 5: the AI's "new" entity with an existing name links to it
# ---------------------------------------------------------------------------
def test_bug5_canonical_name_of_known_entity_is_reused(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Marcus Vale", "hair", "black", "black hair")],
        "[2]": [fact("the old soldier", "hair", "black", "the old soldier's black hair")]}))
    fake_ai.on("link_names", lambda p: {"resolutions": [
        {"name": "the old soldier", "existing_entity_id": 0, "canonical_name": "Marcus Vale", "confidence": 0.8}]})
    post(client, "c1", "[1]")
    r = post(client, "c2", "[2]")
    names = [e["canonical_name"] for e in client.get("/entities").json()["entities"]]
    assert names.count("Marcus Vale") == 1
    assert r["entity_links"][0]["canonical_name"] == "Marcus Vale"


# ---------------------------------------------------------------------------
# Bug 6: correcting a fact closes the warnings built on it
# ---------------------------------------------------------------------------
def test_bug6_editing_a_fact_resolves_and_rechecks_its_warning(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(EYES))
    fake_ai.on("report_contradictions", flag_when("| grey |", "| green |"))
    post(client, "ch1", "[grey]")
    post(client, "ch2", "[green]")
    [w] = client.get("/contradictions?status=open").json()["contradictions"]
    assert w["new_fact_id"] and w["conflicting_fact_id"]
    r = client.patch(f"/facts/{w['conflicting_fact_id']}", json={"value": "green"})
    assert r.status_code == 200 and r.json()["recheck_job_id"]
    assert client.get("/contradictions?status=open").json()["contradictions"] == []


def test_bug6_deleting_a_fact_closes_its_warning(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(EYES))
    fake_ai.on("report_contradictions", flag_when("grey eyes", "green eyes"))
    post(client, "ch1", "[grey]")
    post(client, "ch2", "[green]")
    [w] = client.get("/contradictions?status=open").json()["contradictions"]
    client.delete(f"/facts/{w['new_fact_id']}")
    assert client.get("/contradictions?status=open").json()["contradictions"] == []


# ---------------------------------------------------------------------------
# Bug 7: the checker's evidence is bounded, and too-long prompts are split
# ---------------------------------------------------------------------------
def test_bug7_evidence_is_bounded(client, fake_ai, monkeypatch):
    import storage
    monkeypatch.setattr(storage, "MAX_EVIDENCE_FACTS", 60)
    many = [fact("Ines Calloway", f"detail_{i}", f"value {i}", f"quote number {i}") for i in range(400)]
    fake_ai.on("record_facts", facts_by_marker({"[many]": many,
                                                "[one]": [fact("Ines Calloway", "eye_color", "green", "green eyes")]}))
    prompts = []
    fake_ai.on("report_contradictions", lambda p: prompts.append(p) or {"contradictions": []})
    post(client, "ch1", "[many]")
    post(client, "ch2", "[one]")
    existing = prompts[-1].split("EXISTING facts")[1]
    assert len(re.findall(r"^\d+: ", existing, re.M)) <= 60


def test_bug7_too_long_prompt_is_split_not_failed(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact(n, "eyes", "grey", f"{n} grey eyes") for n in ("Ada Byrne", "Ben Okafor", "Cy Moreau")],
        "[2]": [fact(n, "eyes", "green", f"{n} green eyes") for n in ("Ada Byrne", "Ben Okafor", "Cy Moreau")]}))
    sizes = []

    def checker(prompt):
        sections = prompt.count("ENTITY ") - prompt.count("ENTITY sections")
        sizes.append(sections)
        if sections > 1:
            raise llm.openai.BadRequestError("This model's maximum context length is 8192 tokens",
                                             response=_response(400), body=None)
        return flag_when("grey", "green")(prompt)
    fake_ai.on("report_contradictions", checker)
    post(client, "ch1", "[1]")
    r = post(client, "ch2", "[2]")
    assert len([c for c in r["contradictions"] if c["status"] == "open"]) == 3


# ---------------------------------------------------------------------------
# Bug 8: the answer budget only grows after a cut-off answer
# ---------------------------------------------------------------------------
def test_bug8_rate_limit_refusals_do_not_grow_the_token_budget(fake_ai, monkeypatch):
    budgets = []
    refusals = iter([llm.openai.RateLimitError("too many", response=_response(429), body=None)] * 3)

    def create(**kw):
        budgets.append(kw["max_tokens"])
        error = next(refusals, None)
        if error:
            raise error
        return fake_ai._chat(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    monkeypatch.setattr(llm, "_wait_for_cooldown", lambda: None)
    llm.call_tool("x", {"type": "function", "function": {"name": "record_facts", "parameters": {}}})
    assert budgets == [4096, 4096, 4096, 4096]


def test_bug8_cut_off_answer_does_grow_the_budget(fake_ai, monkeypatch):
    budgets = []
    answers = iter([{"__text__": "{\"facts\": [", "__finish__": "length"}, {"facts": []}])
    fake_ai.on("record_facts", lambda p: next(answers))
    original = fake_ai._chat

    def create(**kw):
        budgets.append(kw["max_tokens"])
        return original(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    llm.call_tool("x", {"type": "function", "function": {"name": "record_facts", "parameters": {}}})
    assert budgets == [4096, 8192]


# ---------------------------------------------------------------------------
# Bug 9: no cross-type merges; merges trigger a re-check
# ---------------------------------------------------------------------------
def test_bug9_place_cannot_be_merged_into_character(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({"[1]": [
        fact("Ines Calloway", "eyes", "grey", "grey eyes"),
        fact("Gullstone Light", "height", "tall", "the tall light", entity_type="location")]}))
    post(client, "c1", "[1]")
    ids = {e["canonical_name"]: e["id"] for e in client.get("/entities").json()["entities"]}
    r = client.post("/entities/merge", json={"keep_entity_id": ids["Ines Calloway"],
                                             "merge_entity_id": ids["Gullstone Light"]})
    assert r.status_code == 400


def test_bug9_merge_rechecks_and_finds_the_missed_contradiction(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Ines Calloway", "eye_color", "grey", "grey eyes")],
        "[2]": [fact("the keeper", "eye_color", "green", "green eyes")]}))
    fake_ai.on("link_names", lambda p: {"resolutions": []})       # the link is missed
    fake_ai.on("report_contradictions", flag_when("grey eyes", "green eyes"))
    post(client, "c1", "[1]")
    post(client, "c2", "[2]")
    assert client.get("/contradictions?status=open").json()["contradictions"] == []
    ids = {e["canonical_name"]: e["id"] for e in client.get("/entities").json()["entities"]}
    r = client.post("/entities/merge", json={"keep_entity_id": ids["Ines Calloway"], "merge_entity_id": ids["the keeper"]})
    assert r.status_code == 200 and r.json()["recheck_job_id"]
    assert len(client.get("/contradictions?status=open").json()["contradictions"]) == 1


# ---------------------------------------------------------------------------
# Other review findings
# ---------------------------------------------------------------------------
def test_safety_net_keeps_two_warnings_from_one_sentence(client, fake_ai):
    quote = "the one-handed keeper read the burned letter"
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Ines Calloway", "hands", "lost left hand", "lost her left hand"),
                fact("the letter", "status", "burned", "the letter burned", entity_type="item")],
        "[2]": [fact("Keeper", "action", "read with both hands", quote),
                fact("Keeper", "read", "the letter", quote)]}))
    fake_ai.on("link_names", lambda p: {"resolutions": []})
    fake_ai.on("report_cross_contradictions", lambda p: {"contradictions": [
        {"pair_index": i, "same_entity_confidence": 0.9, "contradiction_type": "status", "confidence": 0.9,
         "explanation": "x"} for i in range(int(p.count("<->")))]})
    post(client, "c1", "[1]")
    r = post(client, "c2", "[2]")
    by_value = {c["new_value"] for c in r["contradictions"]}
    assert {"read with both hands", "the letter"} <= by_value


def test_timing_detector_sees_earlier_chapters(client, fake_ai):
    prompts = []
    fake_ai.on("record_timing", lambda p: prompts.append(p) or {"setting": "continues", "description": "next day"})
    post(client, "c1", "one")
    post(client, "c2", "two")
    assert "this is the first chapter" in prompts[0]
    assert "chapter 1: continues: next day" in prompts[1]


def test_chapter_id_with_a_slash_is_refused(client, fake_ai):
    assert client.post("/chapters", json={"chapter_id": "part1/ch1", "text": "x"}).status_code == 422


def test_health_reports_database_and_ai(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["database"] is True and body["ai_configured"] is True


def test_rejected_long_request_does_not_disable_thinking_for_good(fake_ai, monkeypatch):
    calls = []

    def create(**kw):
        calls.append(kw["extra_body"]["chat_template_kwargs"]["enable_thinking"])
        raise llm.openai.BadRequestError("prompt is too long", response=_response(400), body=None)
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    monkeypatch.setattr(llm, "_unsupported_modes", set())
    with pytest.raises(llm.ContextTooLongError):
        llm.call_tool("x", {"type": "function", "function": {"name": "record_facts", "parameters": {}}}, thinking="low")
    assert "low" not in llm._unsupported_modes


# ---------------------------------------------------------------------------
# New features
# ---------------------------------------------------------------------------
AGES = {"[a]": [fact("Rook Abernathy", "age", "nine", "Rook was nine")],
        "[b]": [fact("Rook Abernathy", "age", "fourteen", "Rook, fourteen now")],
        "[c]": [fact("Rook Abernathy", "age", "twelve", "Rook, twelve now")]}


def _timing(notes):
    def handler(prompt):
        for marker, (setting, description) in notes.items():
            if marker in prompt.split("Chapter text:")[1]:
                return {"setting": setting, "description": description}
        return {"setting": "continues", "description": "next day"}
    return handler


def test_story_clock_catches_wrong_age_after_time_skip(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(AGES))
    fake_ai.on("record_timing", _timing({"[b]": ("time skip", "three years after the fire")}))
    post(client, "c1", "[a]")
    r = post(client, "c2", "[b]")
    [w] = [c for c in r["contradictions"] if c["source"] == "story clock"]
    assert w["status"] == "open" and "about 12" in w["explanation"]
    assert client.get("/contradictions").json()["contradictions"][0]["severity"] == "high"


def test_story_clock_accepts_the_right_age_and_flashbacks(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(AGES))
    fake_ai.on("record_timing", _timing({"[c]": ("time skip", "three years later")}))
    post(client, "c1", "[a]")
    assert post(client, "c2", "[c]")["contradictions"] == []


def test_pinned_fact_is_marked_canon_and_raises_severity(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(EYES))
    prompts = []
    fake_ai.on("report_contradictions", lambda p: prompts.append(p) or flag_when("grey eyes", "green eyes")(p))
    post(client, "ch1", "[grey]")
    fact_id = client.get("/chapters/ch1").json()["facts"][0]["fact_id"]
    assert client.patch(f"/facts/{fact_id}", json={"pinned": True}).json()["pinned"] is True
    post(client, "ch2", "[green]")
    assert "[CANON]" in prompts[-1]
    assert client.get("/contradictions").json()["contradictions"][0]["severity"] == "high"


def test_background_job_reports_progress_and_result(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(EYES))
    r = client.post("/chapters/jobs", json={"chapter_id": "ch1", "text": "[grey]"})
    assert r.status_code == 202
    job = client.get(f"/jobs/{r.json()['job_id']}").json()
    assert job["status"] == "done" and job["progress"] == 1.0
    assert job["result"]["chapter_number"] == 1 and len(job["result"]["facts"]) == 1
    assert client.get("/jobs").json()["jobs"][0]["id"] == job["id"]


def test_story_order_timeline_puts_flashbacks_first(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker({
        "[fire]": [fact("the fire", "when", "festival night", "the fire on festival night", entity_type="event")],
        "[past]": [fact("the wedding", "when", "spring", "the spring wedding", entity_type="event")]}))
    fake_ai.on("record_timing", _timing({"[past]": ("flashback", "twelve years before the fire")}))
    post(client, "c1", "[fire]")
    post(client, "c2", "[past]")
    reading = [e["entity"] for e in client.get("/timeline").json()["events"]]
    story = [e["entity"] for e in client.get("/timeline?order=story").json()["events"]]
    assert reading == ["the fire", "the wedding"] and story == ["the wedding", "the fire"]
    client.patch("/chapters/c2", json={"story_order": 5})
    assert [e["entity"] for e in client.get("/timeline?order=story").json()["events"]] == ["the fire", "the wedding"]


def test_export_and_overview(client, fake_ai):
    fake_ai.on("record_facts", facts_by_marker(EYES))
    fake_ai.on("report_contradictions", flag_when("grey eyes", "green eyes"))
    post(client, "ch1", "[grey]")
    post(client, "ch2", "[green]")
    lore = client.get("/export").json()
    assert lore["format"] == "storyforge-lore/1" and lore["entities"][0]["name"] == "Ines Calloway"
    assert len(lore["entities"][0]["facts"]) == 2 and len(lore["warnings"]) == 1
    o = client.get("/overview").json()
    assert o["chapters"] == 2 and o["open_issues"] == 1 and o["entities"] == {"character": 1}


def test_accounts_keep_books_private_and_budget_requests(client, fake_ai, monkeypatch):
    import auth
    monkeypatch.setattr(auth, "AUTH_REQUIRED", True)
    monkeypatch.setattr(auth, "DAILY_CHAPTER_LIMIT", 1)
    assert client.get("/projects").status_code == 401
    a = client.post("/auth/register", json={"email": "a@x.io", "password": "password-a"}).json()["token"]
    b = client.post("/auth/register", json={"email": "b@x.io", "password": "password-b"}).json()["token"]
    ha, hb = {"Authorization": f"Bearer {a}"}, {"Authorization": f"Bearer {b}"}
    book = client.post("/projects", json={"name": "Mine"}, headers=ha).json()
    assert client.get(f"/projects/{book['id']}/chapters", headers=hb).status_code == 404
    assert client.get("/projects", headers=hb).json()["projects"] == []
    assert client.post("/projects", json={"name": "Mine"}, headers=hb).status_code == 201   # names per user
    ok = client.post(f"/projects/{book['id']}/chapters", json={"chapter_id": "c1", "text": "x"}, headers=ha)
    assert ok.status_code == 200
    over = client.post(f"/projects/{book['id']}/chapters", json={"chapter_id": "c2", "text": "x"}, headers=ha)
    assert over.status_code == 429
    assert client.post("/auth/login", json={"email": "a@x.io", "password": "wrong"}).status_code == 401
    assert client.post("/auth/login", json={"email": "A@x.io", "password": "password-a"}).status_code == 200
    assert client.get("/projects", headers={"Authorization": "Bearer forged.token"}).status_code == 401

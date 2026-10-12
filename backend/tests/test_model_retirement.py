"""NVIDIA retires models (410 Gone): fail fast, fall back to the next model, guard embeddings."""
import httpx
import openai
import pytest

import llm
import storage


def gone(model):
    return openai.APIStatusError(
        f"The model '{model}' has reached its end of life", body={"detail": f"The model '{model}' has reached its end of life"},
        response=httpx.Response(410, request=httpx.Request("POST", "https://example.invalid")))


def test_retired_model_is_not_retried_and_the_next_one_is_used(client, fake_ai, monkeypatch):
    monkeypatch.setattr(llm, "CHAT_MODELS", ["old/model", "new/model"])
    asked = []
    real = llm.client.chat.completions.create

    def create(**kw):
        asked.append(kw["model"])
        if kw["model"] == "old/model":
            raise gone("old/model")
        return real(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    assert client.post("/chapters", json={"chapter_id": "c1", "text": "x"}).status_code == 200
    assert asked.count("old/model") == 1                       # asked once, never retried
    assert "new/model" in asked
    asked.clear()
    client.post("/chapters", json={"chapter_id": "c2", "text": "y"})
    assert "old/model" not in asked                            # remembered as retired
    health = client.get("/health").json()
    assert health["chat_model"] == "new/model" and health["chat_models_retired"] == ["old/model"]


def test_when_every_model_is_retired_the_message_says_what_to_do(client, fake_ai, monkeypatch):
    monkeypatch.setattr(llm, "CHAT_MODELS", ["a/one", "b/two"])
    calls = []

    def create(**kw):
        calls.append(kw["model"])
        raise gone(kw["model"])
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    r = client.post("/chapters", json={"chapter_id": "c1", "text": "x"})
    assert r.status_code == 502 and "check_models.py" in r.json()["detail"]
    assert sorted(set(calls)) == ["a/one", "b/two"] and len(calls) <= 4     # no six-fold retries


def test_changed_embedding_model_is_refused_until_reembedded(client, fake_ai, monkeypatch):
    client.post("/chapters", json={"chapter_id": "c1", "text": "x"})
    monkeypatch.setattr(llm, "EMBED_MODEL", "nvidia/some-new-embedder")
    health = client.get("/health").json()
    assert health["embeddings_ok"] is False and "reembed.py" in health["embeddings_problem"]
    r = client.post("/chapters", json={"chapter_id": "c2", "text": "y"})
    assert r.status_code == 502 and "reembed.py" in r.json()["detail"]

    import reembed
    assert reembed.main() == 0                                  # same vector size: re-index in place
    assert storage.STORED_EMBED_MODEL == "nvidia/some-new-embedder"
    assert client.get("/health").json()["embeddings_ok"] is True
    assert client.post("/chapters", json={"chapter_id": "c2", "text": "y"}).status_code == 200
    monkeypatch.setattr(storage, "STORED_EMBED_MODEL", llm.EMBED_MODEL)


@pytest.fixture(autouse=True)
def _restore_embed_setting():
    yield
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE app_settings SET value = %s WHERE key = 'embed_model'", (storage.LEGACY_EMBED_MODEL,))
    storage.STORED_EMBED_MODEL = storage.LEGACY_EMBED_MODEL


def test_judgments_go_to_the_judge_model_and_reading_to_the_reader(client, fake_ai, monkeypatch):
    from conftest import fact, facts_by_marker
    monkeypatch.setattr(llm, "CHAT_MODELS", ["fast/reader"])
    monkeypatch.setattr(llm, "JUDGE_MODELS", ["smart/judge"])
    used = {}
    real = llm.client.chat.completions.create

    def create(**kw):
        used.setdefault(kw["tools"][0]["function"]["name"], set()).add(kw["model"])
        return real(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    fake_ai.on("record_facts", facts_by_marker({
        "[1]": [fact("Ines Calloway", "eyes", "grey", "grey eyes")],
        "[2]": [fact("Ines Calloway", "eyes", "green", "green eyes"), fact("the keeper", "age", "40", "aged 40")]}))
    fake_ai.on("report_contradictions", lambda p: {"contradictions": [{"entity_number": 1, "new_fact_index": 0,
        "existing_fact_index": 0, "contradiction_type": "attribute", "confidence": 0.9, "explanation": "x"}]})
    client.post("/chapters", json={"chapter_id": "c1", "text": "[1]"})
    client.post("/chapters", json={"chapter_id": "c2", "text": "[2]"})
    assert used["record_facts"] == {"fast/reader"} and used["record_timing"] == {"fast/reader"}
    for judged in ("report_contradictions", "review_warnings", "link_names"):
        assert used[judged] == {"smart/judge"}, judged
    health = client.get("/health").json()
    assert health["chat_model"] == "fast/reader" and health["judge_model"] == "smart/judge"


def test_judging_falls_back_to_the_reader_when_every_judge_is_retired(client, fake_ai, monkeypatch):
    monkeypatch.setattr(llm, "CHAT_MODELS", ["fast/reader"])
    monkeypatch.setattr(llm, "JUDGE_MODELS", ["gone/judge"])
    real = llm.client.chat.completions.create

    def create(**kw):
        if kw["model"] == "gone/judge":
            raise gone("gone/judge")
        return real(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    assert llm.call_tool("x", {"type": "function", "function": {"name": "review_warnings", "parameters": {}}},
                         role="judge") is not None
    assert llm.current_chat_model("judge") == "fast/reader"


def server_error():
    return openai.InternalServerError("Internal server error", body=None,
        response=httpx.Response(500, request=httpx.Request("POST", "https://example.invalid")))


def test_a_struggling_model_is_set_aside_instead_of_waited_on(client, fake_ai, monkeypatch):
    """500s on the judge: switch to the next model after 2 tries, not 6 tries over minutes."""
    monkeypatch.setattr(llm, "CHAT_MODELS", ["fast/reader"])
    monkeypatch.setattr(llm, "JUDGE_MODELS", ["broken/judge"])
    calls = []
    real = llm.client.chat.completions.create

    def create(**kw):
        calls.append(kw["model"])
        if kw["model"] == "broken/judge":
            raise server_error()
        return real(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    tool = {"type": "function", "function": {"name": "link_names", "parameters": {}}}
    assert llm.call_tool("x", tool, role="judge", thinking="off") is not None
    assert calls.count("broken/judge") == llm.FAILOVER_AFTER and calls[-1] == "fast/reader"
    calls.clear()
    llm.call_tool("x", tool, role="judge", thinking="off")
    assert calls == ["fast/reader"]                              # set aside for a while
    assert client.get("/health").json()["chat_models_struggling"] == ["broken/judge"]
    llm._unhealthy_until["broken/judge"] = 0                     # ... and tried again later
    assert llm.current_chat_model("judge") == "broken/judge"


def test_with_no_other_model_a_struggling_one_is_still_retried(fake_ai, monkeypatch):
    monkeypatch.setattr(llm, "CHAT_MODELS", ["only/model"])
    monkeypatch.setattr(llm, "JUDGE_MODELS", [])
    tries = iter([server_error(), server_error(), server_error()])
    real = llm.client.chat.completions.create

    def create(**kw):
        error = next(tries, None)
        if error:
            raise error
        return real(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    tool = {"type": "function", "function": {"name": "record_facts", "parameters": {}}}
    assert llm.call_tool("x", tool) is not None                  # patience when there's no alternative


def test_a_model_that_crashes_with_thinking_keeps_working_without_it(fake_ai, monkeypatch):
    monkeypatch.setattr(llm, "CHAT_MODELS", ["fast/reader"])
    monkeypatch.setattr(llm, "JUDGE_MODELS", ["picky/judge"])
    real = llm.client.chat.completions.create
    sent = []

    def create(**kw):
        thinking = kw["extra_body"]["chat_template_kwargs"]["enable_thinking"]
        sent.append((kw["model"], thinking))
        if kw["model"] == "picky/judge" and thinking:
            raise server_error()
        return real(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    tool = {"type": "function", "function": {"name": "review_warnings", "parameters": {}}}
    for _ in range(3):
        llm.call_tool("x", tool, role="judge", thinking="low")
    assert "picky/judge|low" in llm._unsupported_modes            # after two crashes
    assert sent[-1] == ("picky/judge", False)                     # now asked without thinking at once
    assert llm.current_chat_model("judge") == "picky/judge"       # and still the judge
    llm.call_tool("x", tool, role="reader", thinking="low")
    assert sent[-1] == ("fast/reader", True)                      # other models keep their thinking

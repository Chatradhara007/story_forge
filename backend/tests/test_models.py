"""Model roles, failover when NVIDIA retires a model, and per-family thinking settings."""
import httpx
import pytest
import llm
from conftest import fact, facts_by_marker


def _gone(model, status=410):
    request = httpx.Request("POST", "https://example.invalid")
    response = httpx.Response(status, request=request)
    if status == 404:
        return llm.openai.NotFoundError(f"model {model} not found", response=response, body=None)
    return llm.openai.APIStatusError(f"Gone: {model}", response=response, body=None)


@pytest.fixture
def fresh_models(monkeypatch):
    monkeypatch.setattr(llm, "_retired", {})
    monkeypatch.setattr(llm, "_switch_notes", [])
    monkeypatch.setattr(llm, "READING_MODEL", "vendor/reader-a")
    monkeypatch.setattr(llm, "JUDGING_MODEL", "vendor/judge-a")
    monkeypatch.setattr(llm, "FALLBACK_MODELS", ["vendor/backup-b", "vendor/backup-c"])


def test_reading_and_judging_use_their_own_models(client, fake_ai, fresh_models, monkeypatch):
    used = {}
    original = fake_ai._chat
    def spy(**kw):
        used.setdefault(kw["tools"][0]["function"]["name"] if "tools" in kw else "ask", set()).add(kw["model"])
        return original(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", spy)
    fake_ai.on("record_facts", facts_by_marker({"[1]": [fact("Ann", "eyes", "blue", "q")],
                                                "[2]": [fact("Ann", "eyes", "green", "q")]}))
    client.post("/chapters", json={"chapter_id": "1", "text": "[1]"})
    client.post("/chapters", json={"chapter_id": "2", "text": "[2]"})
    assert used["record_facts"] == {"vendor/reader-a"}
    assert used["report_contradictions"] == {"vendor/judge-a"}
    assert used["record_timing"] == {"vendor/judge-a"}


@pytest.mark.parametrize("status", [404, 410])
def test_retired_model_switches_to_the_next_one_without_retrying(client, fake_ai, fresh_models, monkeypatch, status):
    calls = []
    original = fake_ai._chat
    def nvidia(**kw):
        calls.append(kw["model"])
        if kw["model"] == "vendor/reader-a":
            raise _gone(kw["model"], status)
        return original(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", nvidia)
    r = client.post("/extract", json={"chapter_id": "c", "text": "x"})
    assert r.status_code == 200
    assert calls.count("vendor/reader-a") == 1           # a retired model is not retried 6 times
    assert "vendor/backup-b" in calls
    # Later requests go straight to the replacement.
    calls.clear()
    client.post("/extract", json={"chapter_id": "c", "text": "x"})
    assert calls == ["vendor/backup-b"]
    health = client.get("/health").json()
    assert health["models"]["reading"] == "vendor/backup-b"
    assert "vendor/reader-a" in health["models"]["retired"]


def test_all_models_gone_gives_a_clear_error(client, fake_ai, fresh_models, monkeypatch):
    monkeypatch.setattr(llm.client.chat.completions, "create", lambda **kw: (_ for _ in ()).throw(_gone(kw["model"])))
    r = client.post("/extract", json={"chapter_id": "c", "text": "x"})
    assert r.status_code == 502
    assert "probe_models" in r.json()["detail"] or "none of the configured models" in r.json()["detail"]


def test_thinking_fields_match_the_model_family():
    assert llm._thinking_options("off", "nvidia/nemotron-3-ultra-550b-a55b") == \
        {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    assert llm._thinking_options("low", "openai/gpt-oss-120b") == {"reasoning_effort": "low"}
    assert llm._thinking_options("on", "deepseek-ai/deepseek-v4") == \
        {"extra_body": {"chat_template_kwargs": {"thinking": True}}}
    assert llm._thinking_options("low", "some/other-model") == {}


def test_client_does_not_retry_on_its_own():
    assert llm.client.max_retries == 0
    assert llm.client.timeout == llm.REQUEST_TIMEOUT

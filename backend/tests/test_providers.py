"""
Free providers chained in one model list (llm.PROVIDERS): 'groq:...', 'ollama:...', 'nvidia:...'.
A missing key skips that model; running out of free requests hands over to the next at once.
"""
import json
import types

import llm


def test_provider_labels():
    assert llm.split_model("groq:llama-3.3-70b-versatile") == ("groq", "llama-3.3-70b-versatile")
    assert llm.split_model("ollama:qwen2.5:7b-instruct") == ("ollama", "qwen2.5:7b-instruct")
    assert llm.split_model("openrouter:meta-llama/llama-3.3-70b-instruct:free") == (
        "openrouter", "meta-llama/llama-3.3-70b-instruct:free")
    assert llm.split_model("qwen2.5:7b-instruct") == (None, "qwen2.5:7b-instruct")     # no label: AI_BASE_URL
    assert llm.split_model("nvidia/nemotron-3.5-lightning-30b-a3b")[0] is None


def _answers(name, calls, refuse=False):
    def create(**kw):
        calls.append((name, kw["model"], "extra_body" in kw))
        if refuse:
            error = Exception("Too Many Requests")
            error.status_code = 429
            raise error
        msg = types.SimpleNamespace(tool_calls=[types.SimpleNamespace(
            function=types.SimpleNamespace(arguments=json.dumps({"from": name})))], content=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg, finish_reason="stop")])
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))


def test_missing_key_is_skipped_and_free_limit_hands_over(fake_ai, monkeypatch):
    calls = []
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(llm, "CHAT_MODELS", ["groq:llama-3.3-70b-versatile", "ollama:qwen2.5:7b-instruct",
                                             "nvidia/nemotron-3.5-lightning-30b-a3b"])
    monkeypatch.setattr(llm, "_provider_clients", {"ollama": _answers("ollama", calls, refuse=True)})
    monkeypatch.setattr(llm, "client", _answers("default", calls))
    monkeypatch.setattr(llm, "_gates", {})
    tool = {"type": "function", "function": {"name": "record_facts", "parameters": {}}}
    assert llm.call_tool("x", tool) == {"from": "default"}
    assert calls[0][:2] == ("ollama", "qwen2.5:7b-instruct") and calls[0][2] is False   # no NVIDIA options
    assert calls[-1][0] == "default" and len([c for c in calls if c[0] == "ollama"]) == 1

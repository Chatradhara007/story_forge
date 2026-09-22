"""The AI connection copes with answers that aren't in the structured format."""
import pytest
import llm
from conftest import fact


def test_plain_text_json_answer_is_accepted(client, fake_ai):
    fake_ai.on("record_facts", lambda p: {"__text__": '<think>let me see</think>Here you go:\n```json\n'
                                          '{"facts": [{"entity": "Ann", "entity_type": "character", "attribute": "age", '
                                          '"value": "9", "source_quote": "Ann, nine", "confidence": 0.9}]}\n```'})
    r = client.post("/extract", json={"chapter_id": "c", "text": "x"})
    assert r.status_code == 200 and r.json()["facts"][0]["entity"] == "Ann"


def test_tool_call_written_as_text_is_accepted(client, fake_ai):
    fake_ai.on("record_facts", lambda p: {"__text__": '{"name": "record_facts", "arguments": "{\\"facts\\": []}"}'})
    assert client.post("/extract", json={"chapter_id": "c", "text": "x"}).status_code == 200


def test_running_out_of_space_gets_more_room_next_time(client, fake_ai):
    answers = iter([{"__text__": "I am still thinking about", "__finish__": "length"},
                    {"facts": [fact("Bo", "age", "5", "Bo, five")]}])
    fake_ai.on("record_facts", lambda p: next(answers))
    r = client.post("/extract", json={"chapter_id": "c", "text": "x"})
    assert r.status_code == 200
    assert fake_ai.max_tokens[-2:] == [8192, 16384]      # the Reader starts with 8192


def test_error_message_says_what_happened(client, fake_ai):
    fake_ai.on("record_facts", lambda p: {"__text__": "Sorry, I cannot", "__finish__": "length"})
    r = client.post("/extract", json={"chapter_id": "c", "text": "x"})
    assert r.status_code == 502
    assert "ran out of space" in r.json()["detail"] and "Sorry, I cannot" in r.json()["detail"]


def test_thinking_is_off_by_default(client, fake_ai, monkeypatch):
    seen = []
    original = fake_ai._chat
    def spy(**kw):
        seen.append(kw.get("extra_body"))
        return original(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", spy)
    client.post("/extract", json={"chapter_id": "c", "text": "x"})
    assert seen[-1] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_judging_steps_use_their_own_thinking_setting(client, fake_ai, monkeypatch):
    from conftest import facts_by_marker
    seen = {}
    original = fake_ai._chat
    def spy(**kw):
        seen.setdefault(kw["tools"][0]["function"]["name"] if "tools" in kw else "ask", kw.get("extra_body"))
        return original(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", spy)
    fake_ai.on("record_facts", facts_by_marker({"[1]": [fact("A", "x", "1", "q")], "[2]": [fact("B", "x", "2", "q"), fact("A", "x", "3", "q")]}))
    client.post("/chapters", json={"chapter_id": "1", "text": "[1]"})
    client.post("/chapters", json={"chapter_id": "2", "text": "[2]"})
    assert seen["record_facts"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert seen["link_names"] == {"chat_template_kwargs": {"enable_thinking": True, "low_effort": True}}
    assert seen["report_contradictions"] == {"chat_template_kwargs": {"enable_thinking": True, "low_effort": True}}


def test_rejected_thinking_setting_falls_back_to_off(client, fake_ai, monkeypatch):
    import httpx
    from conftest import facts_by_marker
    monkeypatch.setattr(llm, "_unsupported_modes", set())
    original = fake_ai._chat
    def picky(**kw):
        if kw.get("extra_body", {}).get("chat_template_kwargs", {}).get("low_effort"):
            request = httpx.Request("POST", "https://example.invalid")
            raise llm.openai.BadRequestError("low_effort not supported", response=httpx.Response(400, request=request), body=None)
        return original(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", picky)
    fake_ai.on("record_facts", facts_by_marker({"[1]": [fact("A", "x", "1", "q")], "[2]": [fact("B", "x", "2", "q")]}))
    client.post("/chapters", json={"chapter_id": "1", "text": "[1]"})
    assert client.post("/chapters", json={"chapter_id": "2", "text": "[2]"}).status_code == 200
    assert "low" in llm._unsupported_modes

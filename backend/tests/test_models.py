"""
Model settings that test_model_retirement.py doesn't cover: the older setting names, how
each model family is told to think (or not), and the client's own timeout / retries.
"""
import llm


def test_thinking_fields_match_the_model_family():
    assert llm._thinking_options("off", "nvidia/nemotron-3-ultra-550b-a55b") == \
        {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    assert llm._thinking_options("low", "nvidia/nemotron-3.5-lightning-30b-a3b") == \
        {"extra_body": {"chat_template_kwargs": {"enable_thinking": True, "low_effort": True}}}
    assert llm._thinking_options("low", "openai/gpt-oss-120b") == {"reasoning_effort": "low"}
    assert llm._thinking_options("on", "deepseek-ai/deepseek-v4") == \
        {"extra_body": {"chat_template_kwargs": {"thinking": True}}}
    assert llm._thinking_options("low", "meta/llama-3.2-90b-vision-instruct") == {}


def test_answer_space_includes_room_to_think():
    assert llm._answer_space(300, "off") == 300
    assert llm._answer_space(300, "low") == 300 + llm.THINKING_BUDGET
    assert llm._answer_space(16000, "on") == llm.MAX_TOKENS_CEILING


def test_client_does_not_retry_on_its_own():
    assert llm.client.max_retries == 0                # StoryForge's own retries honour the pacing
    assert llm.client.timeout == llm.REQUEST_TIMEOUT  # not the library's 10 minutes


def test_model_lists_and_older_setting_names():
    readers, judges = llm.configured_models({"CHAT_MODEL": "a/reader, b/reader", "JUDGE_MODEL": "c/judge"})
    assert readers == ["a/reader", "b/reader"] and judges == ["c/judge"]
    # The 12 Oct names still work: they go first in their list.
    readers, judges = llm.configured_models({"CHAT_MODEL": "a/reader", "JUDGE_MODEL": "c/judge",
                                             "CHAT_MODEL_READING": "x/fast", "CHAT_MODEL_JUDGING": "y/careful",
                                             "CHAT_MODEL_FALLBACKS": "z/spare"})
    assert readers == ["x/fast", "a/reader", "z/spare"] and judges == ["y/careful", "c/judge"]
    readers, judges = llm.configured_models({})
    assert readers[0] == "nvidia/nemotron-3.5-lightning-30b-a3b" and judges[0] == "nvidia/nemotron-3-ultra-550b-a55b"


def test_judging_falls_back_to_the_readers(monkeypatch):
    monkeypatch.setattr(llm, "CHAT_MODELS", ["a/reader", "b/reader"])
    monkeypatch.setattr(llm, "JUDGE_MODELS", ["c/judge"])
    assert llm._chain("judge") == ["c/judge", "a/reader", "b/reader"]
    assert llm._chain("reader") == ["a/reader", "b/reader"]

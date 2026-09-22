"""Staying reliable when NVIDIA's service is overloaded or flaky."""
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import llm
import extract
from conftest import fact, facts_by_marker


def _response(status, headers=None):
    return httpx.Response(status, headers=headers or {}, request=httpx.Request("POST", "https://example.invalid"))


def test_total_requests_in_flight_never_exceed_the_limit(client, fake_ai, monkeypatch):
    monkeypatch.setattr(llm, "_slots", threading.BoundedSemaphore(2))
    monkeypatch.setattr(extract, "READ_PASSAGE_CHARS", 200)
    in_flight, peak, lock = [0], [0], threading.Lock()
    original = fake_ai._chat

    def slow(**kw):
        with lock:
            in_flight[0] += 1
            peak[0] = max(peak[0], in_flight[0])
        time.sleep(0.05)
        with lock:
            in_flight[0] -= 1
        return original(**kw)
    monkeypatch.setattr(llm.client.chat.completions, "create", slow)
    text = "\n\n".join(f"Paragraph {i}. " + "Words and more words. " * 8 for i in range(6))
    client.post("/chapters", json={"chapter_id": "c", "text": text})    # passages + timing, nested
    assert peak[0] == 2


def test_bad_api_key_stops_at_once_with_a_clear_message(client, fake_ai, monkeypatch):
    calls = []
    def rejected(**kw):
        calls.append(1)
        raise llm.openai.AuthenticationError("bad key", response=_response(401), body=None)
    monkeypatch.setattr(llm.client.chat.completions, "create", rejected)
    r = client.post("/extract", json={"chapter_id": "c", "text": "x"})
    assert r.status_code == 502 and "API key" in r.json()["detail"]
    assert len(calls) == 1                                    # no pointless retries


def test_retired_model_stops_at_once(client, fake_ai, monkeypatch):
    def missing(**kw):
        raise llm.openai.NotFoundError("no such model", response=_response(404), body=None)
    monkeypatch.setattr(llm.client.chat.completions, "create", missing)
    r = client.post("/extract", json={"chapter_id": "c", "text": "x"})
    assert "retired" in r.json()["detail"]


def test_other_errors_wait_longer_each_time(monkeypatch):
    waits = []
    monkeypatch.setattr(llm, "_pause", lambda s: waits.append(s))
    attempts = iter([RuntimeError("500 Internal server error"), RuntimeError("502 Bad Gateway")])
    def action():
        error = next(attempts, None)
        if error:
            raise error
        return "ok"
    assert llm.with_retries(action, "test") == "ok"
    assert 2 <= waits[0] < 4 and 4 <= waits[1] < 6        # 2s then 4s (+ up to 1.5s randomness)


def _refusal(retry_after=None):
    headers = {"retry-after": str(retry_after)} if retry_after else {}
    return llm.openai.RateLimitError("too many", response=_response(429, headers), body=None)


def test_too_many_requests_pauses_everything_and_is_patient(monkeypatch):
    pauses = []
    monkeypatch.setattr(llm, "_pause", lambda s: pauses.append(s))
    monkeypatch.setattr(llm, "_cooldown_until", 0.0)
    monkeypatch.setattr(llm, "_refusals_in_a_row", 0)
    refusals = iter([_refusal()] * 8)             # more than the 6 tries other errors get
    def action():
        error = next(refusals, None)
        if error:
            raise error
        return "ok"
    assert llm.with_retries(action, "test") == "ok"
    assert len(pauses) == 8
    assert 9 <= pauses[0] <= 10 and 19 <= pauses[1] <= 20       # 10s, 20s, 40s ... shared pause
    assert max(pauses) <= 120                                     # never more than 2 minutes


def test_a_refusal_makes_other_requests_wait_too(monkeypatch):
    pauses = []
    monkeypatch.setattr(llm, "_pause", lambda s: pauses.append(s))
    monkeypatch.setattr(llm, "_cooldown_until", 0.0)
    monkeypatch.setattr(llm, "_refusals_in_a_row", 0)
    llm._start_cooldown(_refusal(retry_after=45))                 # someone else was refused
    llm._call_api(lambda: "sent")                                 # this request waits first
    assert pauses and pauses[0] >= 44                             # honoured NVIDIA's Retry-After


def test_gives_up_with_a_clear_message_when_the_limit_is_used_up(monkeypatch):
    monkeypatch.setattr(llm, "_pause", lambda s: None)
    def always_refused():
        raise _refusal()
    with pytest.raises(llm.AIServiceError, match="usage limit is probably used up"):
        llm.with_retries(always_refused, "test")


def test_requests_are_paced_by_default():
    # the tests switch pacing off, so check the setting's default in the code itself
    import inspect
    assert 'os.getenv("MAX_REQUESTS_PER_MINUTE", "30")' in inspect.getsource(llm)


def test_requests_per_minute_cap(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(llm, "MAX_REQUESTS_PER_MINUTE", 2)
    monkeypatch.setattr(llm, "_current_rpm", None)
    monkeypatch.setattr(llm, "_next_start", 0.0)
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(llm.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    for _ in range(3):
        llm._call_api(lambda: None)
    assert clock[0] >= 60            # the third request had to wait for the minute to pass


def test_evaluation_keeps_going_when_one_run_fails():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
    from run_eval import run_many

    def one_run(n):
        if n == 2:
            raise llm.AIServiceError("AI call failed after 6 tries")
        return {"run": n}
    runs, failed = run_many(3, one_run, llm.AIServiceError)
    assert [r["run"] for r in runs] == [1, 3]
    assert failed[0][0] == 2


def test_pacing_slows_down_when_refused_and_recovers(monkeypatch):
    monkeypatch.setattr(llm, "MAX_REQUESTS_PER_MINUTE", 30)
    monkeypatch.setattr(llm, "_current_rpm", None)
    monkeypatch.setattr(llm, "_accepted_since_change", 0)
    llm._slow_down()
    assert llm._effective_rpm() == 15
    llm._slow_down(); llm._slow_down(); llm._slow_down(); llm._slow_down()
    assert llm._effective_rpm() == llm.MIN_REQUESTS_PER_MINUTE        # never below the minimum
    for _ in range(20):
        llm._speed_up_gradually()
    assert llm._effective_rpm() == llm.MIN_REQUESTS_PER_MINUTE + 2      # +1 per 10 accepted


def test_requests_are_spaced_evenly_not_in_bursts(monkeypatch):
    clock, starts = [0.0], []
    monkeypatch.setattr(llm, "MAX_REQUESTS_PER_MINUTE", 30)
    monkeypatch.setattr(llm, "_current_rpm", None)
    monkeypatch.setattr(llm, "_next_start", 0.0)
    monkeypatch.setattr(llm, "_cooldown_until", 0.0)          # no pause left over from other tests
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(llm.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    for _ in range(4):
        llm._call_api(lambda: starts.append(clock[0]))
    assert starts == [0.0, 2.0, 4.0, 6.0]                                  # 30 per minute = one every 2 s


def test_refusals_are_counted(monkeypatch):
    monkeypatch.setattr(llm, "_pause", lambda s: None)
    before_sent, before_refused = llm.request_count, llm.refused_count
    tries = iter([_refusal(), None])
    def request():
        error = next(tries)
        if error:
            raise error
        return "ok"
    assert llm.with_retries(lambda: llm._call_api(request), "test") == "ok"
    assert llm.request_count - before_sent == 2 and llm.refused_count - before_refused == 1

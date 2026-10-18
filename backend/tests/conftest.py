"""
Shared test setup. The tests use:
  - a SEPARATE database (storyforge_test), wiped before every test, so your real data is safe;
  - a FAKE AI, so tests are free, fast, and don't need an NVIDIA key or internet.

Run from the backend folder:   pytest
Needs the Docker database running (docker compose up -d).
"""
import json
import os
import sys
import types
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from dotenv import dotenv_values, load_dotenv
_FILE = {k: v for k, v in dotenv_values(BACKEND / ".env").items() if v}
_SET_BEFORE = {k: os.environ[k] for k in ("DATABASE_URL", "TEST_DATABASE_URL") if os.environ.get(k)}
load_dotenv(BACKEND / ".env")       # so DATABASE_URL (e.g. port 5433) comes from your .env


def _where(name: str) -> str:
    if name in _SET_BEFORE:
        return (f"{name} is set in Windows or this PowerShell window ({_SET_BEFORE[name]}), and that beats "
                f"backend/.env. Remove it: Remove-Item Env:{name}; "
                f"[Environment]::SetEnvironmentVariable('{name}', $null, 'User')")
    if name in _FILE:
        return f"{name} comes from backend/.env"
    return f"{name} is not set anywhere, so the default (port 5432) was used"


MAIN_URL = os.environ.get("DATABASE_URL", "postgresql://storyforge:storyforge@localhost:5432/storyforge")
TEST_URL = os.environ.get("TEST_DATABASE_URL") or urlunparse(urlparse(MAIN_URL)._replace(path="/storyforge_test"))
URL_SOURCE = _where("TEST_DATABASE_URL") if os.environ.get("TEST_DATABASE_URL") else _where("DATABASE_URL")
os.environ["DATABASE_URL"] = TEST_URL
os.environ["NVIDIA_API_KEY"] = "fake-key-for-tests"
os.environ["JOBS_INLINE"] = "true"          # background jobs run at once, so tests see their results
os.environ.setdefault("AUTH_REQUIRED", "false")
os.environ.setdefault("TRAIT_CHECKS", "off")   # most tests use eye colour as their AI-checker example; test_traits.py tests the rules directly
# The tests are written for the default judging setting; a deployment .env may say "off".
os.environ["CHAT_THINKING_JUDGING"] = "low"
os.environ["SAFETY_NET"] = "on"          # the tests cover the safety net; it is off by default in the app
# Your .env tunes the app for real runs (a different judge, the checker off, fewer retries).
# The tests are written for the defaults, so those settings are pinned here and never leak in.
os.environ["CHECKER"] = "on"
os.environ["NAME_LINKING"] = "ai"
os.environ["NAME_LINKING_PAUSE"] = "0"   # each test starts with the AI available
os.environ["AI_BASE_URL"] = "https://integrate.api.nvidia.com/v1"   # a local model in .env must not leak in
os.environ["AI_PROVIDER"] = ""
os.environ["EMBED_BASE_URL"] = ""
os.environ["AI_API_KEY"] = ""
os.environ["READING_CACHE"] = ""         # a demo cache in .env must never feed the fake AI's answers back
os.environ["AI_RETRY_ATTEMPTS"] = "6"
os.environ["CHAT_MODEL"] = "nvidia/nemotron-3.5-lightning-30b-a3b,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
os.environ["JUDGE_MODEL"] = "nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3.5-lightning-30b-a3b"
for _setting in ("CHAT_MODEL_READING", "CHAT_MODEL_JUDGING", "CHAT_MODEL_FALLBACKS", "CHAT_DISABLE_THINKING"):
    os.environ[_setting] = ""             # empty, not removed: .env is loaded later and never overrides


def _database_available() -> bool:
    import psycopg2
    try:
        psycopg2.connect(TEST_URL).close()
        return True
    except psycopg2.OperationalError as error:
        if "does not exist" not in str(error):
            return False
    try:  # create the test database the first time
        conn = psycopg2.connect(MAIN_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{urlparse(TEST_URL).path.lstrip("/")}"')
        conn.close()
        return True
    except psycopg2.Error:
        return False


DB_OK = _database_available()


class FakeAI:
    """
    Stands in for NVIDIA's API. Tests register a handler per tool:
        fake_ai.on("record_facts", lambda prompt: {"facts": [...]})
    Embeddings are always a fixed vector.
    """
    def __init__(self):
        self.handlers = {}
        self.calls = {}
        self.fail_next = 0
        self.prompts = {}

    def on(self, tool_name, handler):
        self.handlers[tool_name] = handler

    def _chat(self, **kw):
        if self.fail_next:
            self.fail_next -= 1
            raise RuntimeError("temporary outage")
        prompt = kw["messages"][0]["content"]
        if "tools" not in kw:  # plain-text answer (the Ask box)
            name = "ask"
            out = self.handlers.get(name, lambda p: "An answer. (ch. 1)")(prompt)
            self.calls[name] = self.calls.get(name, 0) + 1
            return _obj(choices=[_obj(message=_obj(content=out, tool_calls=None))])
        name = kw["tools"][0]["function"]["name"]
        self.calls[name] = self.calls.get(name, 0) + 1
        self.prompts[name] = prompt
        default = {"record_facts": {"facts": []}, "link_names": {"resolutions": []},
                   "report_contradictions": {"contradictions": []},
                   "report_cross_contradictions": {"contradictions": []},
                   "record_timing": {"setting": "continues", "description": "follows on"},
                   "review_warnings": {"reviews": []}}[name]
        self.max_tokens = getattr(self, "max_tokens", []) + [kw.get("max_tokens")]
        out = self.handlers.get(name, lambda p: default)(prompt)
        if isinstance(out, dict) and "__text__" in out:  # model answered in plain text
            return _obj(choices=[_obj(finish_reason=out.get("__finish__", "stop"),
                                      message=_obj(tool_calls=None, content=out["__text__"]))])
        if out is None:
            tool_calls = None
        else:
            tool_calls = [_obj(function=_obj(arguments=out if isinstance(out, str) else json.dumps(out)))]
        return _obj(choices=[_obj(message=_obj(tool_calls=tool_calls, content=None))])

    def _embed(self, input, **kw):
        self.calls["embed"] = self.calls.get("embed", 0) + 1
        items = input if isinstance(input, list) else [input]
        return _obj(data=[_obj(index=i, embedding=[0.01 * ((i % 7) + 1)] * 2048) for i in range(len(items))])


def _obj(**kw):
    return types.SimpleNamespace(**kw)


@pytest.fixture
def fake_ai(monkeypatch):
    if not DB_OK:
        # A FAILURE, not a skip: a skipped suite looks green with zero tests run.
        # Set SKIP_DB_TESTS=1 to skip on purpose.
        message = f"Test database not reachable at {TEST_URL}. ({URL_SOURCE}.) If the address is right, start it with: docker compose up -d"
        if os.environ.get("SKIP_DB_TESTS") == "1":
            pytest.skip(message)
        pytest.fail(message)
    import llm
    fake = FakeAI()
    monkeypatch.setattr(llm, "client", _obj(chat=_obj(completions=_obj(create=fake._chat)),
                                            embeddings=_obj(create=fake._embed)))
    monkeypatch.setattr(llm, "_pause", lambda s: None)  # no waiting between retries
    # Model health is remembered for the whole process; a test's retired / struggling /
    # no-thinking models must not leak into the next test.
    for name, fresh in (("_retired", {}), ("_switch_notes", []), ("_unhealthy_until", {}), ("_verified", set()),
                        ("_unsupported_modes", set()), ("_thinking_crashes", {})):
        monkeypatch.setattr(llm, name, fresh)
    monkeypatch.setattr(llm, "MAX_REQUESTS_PER_MINUTE", 0)  # no pacing in tests
    import extract
    monkeypatch.setattr(extract, "CHECK_GROUNDING", False)  # pretend chapters are markers, not real text
    return fake


@pytest.fixture
def client(fake_ai):
    from fastapi.testclient import TestClient
    import main
    import storage
    import auth
    auth.reset_limits()              # sign-in / question counters live in memory
    with TestClient(main.app) as c:  # start-up creates the tables
        with storage.db() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE contradictions, facts, chapters, entity_aliases, entities, projects, "
                        "fact_corrections, warning_decisions, jobs, usage_counters, users "
                        "RESTART IDENTITY CASCADE")
        yield c


def fact(entity, attribute, value, quote, entity_type="character", confidence=0.9):
    """Shortcut for building a fact the fake AI can 'extract'."""
    return {"entity": entity, "entity_type": entity_type, "attribute": attribute,
            "value": value, "source_quote": quote, "confidence": confidence}


def facts_by_marker(table: dict):
    """Fake extractor: returns the facts whose marker (e.g. '[ch1]') appears in the chapter text."""
    def handler(prompt):
        text = prompt.split("Chapter text:")[1]
        for marker, facts in table.items():
            if marker in text:
                return {"facts": facts}
        return {"facts": []}
    return handler

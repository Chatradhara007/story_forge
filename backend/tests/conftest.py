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

MAIN_URL = os.environ.get("DATABASE_URL", "postgresql://storyforge:storyforge@localhost:5432/storyforge")
TEST_URL = os.environ.get("TEST_DATABASE_URL") or urlunparse(urlparse(MAIN_URL)._replace(path="/storyforge_test"))
os.environ["DATABASE_URL"] = TEST_URL
os.environ["NVIDIA_API_KEY"] = "fake-key-for-tests"


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
                   "report_contradictions": {"contradictions": []}}[name]
        out = self.handlers.get(name, lambda p: default)(prompt)
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
        pytest.skip(f"Test database not reachable at {TEST_URL}. Start it with: docker compose up -d")
    import llm
    fake = FakeAI()
    monkeypatch.setattr(llm, "client", _obj(chat=_obj(completions=_obj(create=fake._chat)),
                                            embeddings=_obj(create=fake._embed)))
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)  # no waiting between retries
    return fake


@pytest.fixture
def client(fake_ai):
    from fastapi.testclient import TestClient
    import main
    import storage
    with TestClient(main.app) as c:  # start-up creates the tables
        with storage.db() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE contradictions, facts, chapters, entity_aliases, entities, "
                        "fact_corrections RESTART IDENTITY CASCADE")
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

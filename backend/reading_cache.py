"""
A saved copy of each chapter's reading (the facts and timing the Reader found) and of its fact
vectors, reused when the SAME text is checked again.

Switched on by READING_CACHE=<folder> in backend/.env. Uses:
  - demos and pitches: check the chapters once beforehand (a rehearsal); on the day the same
    chapters are checked in seconds, even if the free NVIDIA tier is slow or down;
  - re-submitting an unchanged chapter, or a new book with the same text, costs no AI requests.

The key is the chapter text (spacing ignored) plus the reader model and passage size, so a
different model or setting reads again. Everything else (name linking, the checks, saving)
runs as usual, so the warnings always reflect the current code and the current book.
Delete the folder to start fresh.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from models import ExtractionResult

_FOLDER = os.getenv("READING_CACHE", "").strip()


def enabled() -> bool:
    return bool(_FOLDER)


def _key(text: str) -> str:
    from extract import READ_PASSAGE_CHARS
    from llm import CHAT_MODEL
    normal = re.sub(r"\s+", " ", text or "").strip()
    return hashlib.sha1(f"{CHAT_MODEL}|{READ_PASSAGE_CHARS}|{normal}".encode("utf-8")).hexdigest()


def _path(text: str, kind: str) -> Path:
    if kind == "vectors":                           # vectors belong to the embedding model too
        from llm import EMBED_MODEL
        kind = f"{hashlib.sha1(EMBED_MODEL.encode()).hexdigest()[:8]}.vectors"
    return Path(_FOLDER) / f"{_key(text)}.{kind}.json"


def load(text: str):
    """(ExtractionResult, time note) saved for this text, or None."""
    if not enabled():
        return None
    try:
        data = json.loads(_path(text, "reading").read_text(encoding="utf-8"))
        result = ExtractionResult(chapter_id=data.get("chapter_id", ""), facts=data["facts"],
                                  relationships=data.get("relationships", []))
        return result, data.get("time_note")
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save(text: str, result: ExtractionResult, time_note: str | None) -> None:
    if not enabled():
        return
    try:
        Path(_FOLDER).mkdir(parents=True, exist_ok=True)
        data = {"chapter_id": result.chapter_id, "time_note": time_note,
                "facts": [f.model_dump() for f in result.facts],
                "relationships": [r.model_dump() for r in result.relationships]}
        _path(text, "reading").write_text(json.dumps(data), encoding="utf-8")
    except OSError as error:                       # a cache problem never fails a chapter
        print(f"  [note] could not save the reading cache: {error}", flush=True)


def load_vectors(text: str, count: int):
    """The fact vectors saved for this text, if there is one per fact."""
    if not enabled():
        return None
    try:
        vectors = json.loads(_path(text, "vectors").read_text(encoding="utf-8"))
        return vectors if isinstance(vectors, list) and len(vectors) == count else None
    except (OSError, ValueError):
        return None


def save_vectors(text: str, vectors: list) -> None:
    if not enabled():
        return
    try:
        Path(_FOLDER).mkdir(parents=True, exist_ok=True)
        _path(text, "vectors").write_text(json.dumps(vectors), encoding="utf-8")
    except OSError as error:
        print(f"  [note] could not save the reading cache: {error}", flush=True)

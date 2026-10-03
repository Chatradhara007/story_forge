"""
Background jobs. Adding a chapter takes minutes, which is longer than browsers and hosting
proxies wait for one request ("can't reach backend" while the work carried on unseen).
Now the website starts a job, gets its id at once, and asks for its progress.

One book = one job at a time (a per-book lock), so two browser tabs adding chapters to the
same book can't create duplicate characters or chapter numbers. Different books run side by
side. Jobs are recorded in the database, so progress survives a page reload.

This runs inside the web process: deploy with ONE worker process (the Dockerfile does).
"""
import json
import os
import threading
import traceback
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import storage
from llm import AIServiceError

# Tests set this to True so jobs run immediately, in order, in the calling thread.
RUN_INLINE = os.getenv("JOBS_INLINE", "false").lower() == "true"
MAX_PARALLEL_JOBS = max(1, int(os.getenv("MAX_PARALLEL_JOBS", "2")))

_executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_JOBS, thread_name_prefix="storyforge-job")
_locks_guard = threading.Lock()
_book_locks: dict[int, threading.RLock] = defaultdict(threading.RLock)


def book_lock(project_id: int) -> threading.RLock:
    """The lock that keeps one book's chapter work in single file."""
    with _locks_guard:
        return _book_locks[project_id]


def _update(job_id: str, **fields) -> None:
    if "result" in fields:
        fields["result"] = json.dumps(fields["result"], default=str)
    sets = ", ".join(f"{k} = %s" for k in fields)
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE jobs SET {sets}, updated_at = now() WHERE id = %s", (*fields.values(), job_id))


def submit(project_id: int, kind: str, chapter_id: str | None, work) -> str:
    """
    Queue work(progress) for this book; returns the job id at once.
    work calls progress(stage, fraction=None) as it goes and returns a JSON-able result.
    """
    from pipeline import STAGE_PROGRESS
    job_id = uuid.uuid4().hex[:16]
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO jobs (id, project_id, kind, chapter_id, status, stage) "
                    "VALUES (%s, %s, %s, %s, 'queued', 'waiting for the book to be free')",
                    (job_id, project_id, kind, chapter_id))

    def progress(stage: str, fraction: float | None = None) -> None:
        start = STAGE_PROGRESS.get(stage)
        if start is None:              # a stage of its own, e.g. "re-checking ch3 (1 of 4)"
            if fraction is None:
                _update(job_id, stage=stage)
            else:
                _update(job_id, stage=stage, progress=round(fraction, 3))
            return
        later = [v for v in STAGE_PROGRESS.values() if v > start]
        end = min(later) if later else 1.0
        value = start + (end - start) * (fraction or 0.0)
        label = stage if fraction is None else f"{stage} ({round(fraction * 100)}%)"
        _update(job_id, stage=label, progress=round(value, 3))

    def run() -> None:
        with book_lock(project_id):
            try:
                _update(job_id, status="running", stage="starting")
                result = work(progress)
                _update(job_id, status="done", stage="done", progress=1.0, result=result)
            except AIServiceError as error:
                _update(job_id, status="failed", stage="failed", error=str(error))
            except Exception as error:          # never leave a job "running" forever
                traceback.print_exc()
                _update(job_id, status="failed", stage="failed", error=f"Unexpected error: {error}")

    if RUN_INLINE:
        run()
    else:
        _executor.submit(run)
    return job_id


def get(project_id: int, job_id: str) -> dict | None:
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute("SELECT id, project_id, kind, chapter_id, status, stage, progress, result, error, "
                    "created_at, updated_at FROM jobs WHERE project_id = %s AND id = %s", (project_id, job_id))
        return cur.fetchone()


def recent(project_id: int, limit: int = 20) -> list[dict]:
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute("SELECT id, kind, chapter_id, status, stage, progress, error, created_at, updated_at "
                    "FROM jobs WHERE project_id = %s ORDER BY created_at DESC LIMIT %s", (project_id, limit))
        return cur.fetchall()


def submit_rechecks(project_id: int, chapter_ids: list[str], reason: str) -> str | None:
    """Queue one job that re-checks these chapters, in reading order. None if there are none."""
    from pipeline import recheck_chapter
    chapter_ids = list(dict.fromkeys(chapter_ids))
    if not chapter_ids:
        return None

    def work(progress):
        results = []
        for i, chapter_id in enumerate(chapter_ids, start=1):
            progress(f"re-checking {chapter_id} ({i} of {len(chapter_ids)})", (i - 1) / len(chapter_ids))
            outcome = recheck_chapter(project_id, chapter_id)
            if outcome:
                results.append(outcome)
        return {"reason": reason, "rechecked": results}

    label = chapter_ids[0] if len(chapter_ids) == 1 else f"{len(chapter_ids)} chapters"
    return submit(project_id, "recheck", label, work)

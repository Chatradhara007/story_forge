"""
Everything that reads or writes the database.

Every function works inside ONE book (project): chapters, facts, characters and
warnings never mix between books.
"""
import os
import re
import json
import hashlib
import threading
import time
from contextlib import contextmanager
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv
from models import Fact, Contradiction
from llm import embed_texts

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
DEFAULT_PROJECT_NAME = "My story"

# A chapter row joined to a fact row: both must be in the same book.
_CHAPTER_JOIN = "JOIN chapters c ON c.project_id = f.project_id AND c.id = f.chapter_id"


# Connections are re-used from a pool instead of opening a new one for every query.
# The semaphore makes callers WAIT for a free connection instead of failing when the
# pool is busy (psycopg2's pool raises an error instead of waiting).
DB_POOL_MAX = max(2, int(os.getenv("DB_POOL_MAX", "10")))
_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()
_pool_slots = threading.BoundedSemaphore(DB_POOL_MAX)
_last_used: dict[int, float] = {}
STALE_AFTER_SECONDS = 60      # hosted databases drop idle connections; test them before re-use


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadedConnectionPool(
                1, DB_POOL_MAX, DATABASE_URL,
                keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
            )
        return _pool


def _healthy(conn) -> bool:
    if conn.closed:
        return False
    if time.monotonic() - _last_used.get(id(conn), 0) < STALE_AFTER_SECONDS:
        return True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.rollback()
        return True
    except psycopg2.Error:
        return False


@contextmanager
def db():
    """
    Borrow a database connection for a block of work.
    If everything in the block succeeds, all changes are saved together.
    If anything fails, NOTHING from the block is saved (no half-finished data).
    """
    _pool_slots.acquire()
    pool = _get_pool()
    conn = None
    broken = False
    try:
        conn = pool.getconn()
        for _ in range(3):
            if _healthy(conn):
                break
            pool.putconn(conn, close=True)
            conn = pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception as error:
            broken = bool(conn.closed) or isinstance(error, (psycopg2.OperationalError, psycopg2.InterfaceError))
            try:
                conn.rollback()
            except psycopg2.Error:
                broken = True
            raise
    finally:
        if conn is not None:
            _last_used[id(conn)] = time.monotonic()
            pool.putconn(conn, close=broken)
        _pool_slots.release()


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.closeall()
            _pool = None


# Similarity search uses the half-precision index when the database supports it.
HALFVEC = False


def _distance(column: str, param: str = "%s") -> str:
    if HALFVEC:
        return f"({column}::halfvec(2048) <=> {param}::halfvec(2048))"
    return f"({column} <=> {param}::vector)"


def _dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _to_vector(values: list[float]) -> str:
    """Format a list of numbers the way the database's vector type expects: [0.1,0.2,...]"""
    return "[" + ",".join(str(v) for v in values) + "]"


def fact_to_embedding_text(fact: Fact) -> str:
    # Embed a compact sentence describing the fact, not just the raw value —
    # this makes semantic search match on meaning later.
    return f"{fact.entity} {fact.attribute}: {fact.value}. {fact.source_quote}"


def embed_facts(facts: list[Fact]) -> list[list[float]]:
    return embed_texts([fact_to_embedding_text(f) for f in facts], input_type="passage")


def _remove_orphan_entities(cur, project_id: int) -> None:
    """Entities left with no facts at all (e.g. after re-submitting a chapter) are removed."""
    cur.execute(
        "DELETE FROM entities e WHERE e.project_id = %s "
        "AND NOT EXISTS (SELECT 1 FROM facts f WHERE f.entity_id = e.id)",
        (project_id,),
    )


# ---------------------------------------------------------------------------
# Books (projects)
# ---------------------------------------------------------------------------
# owner_id: the signed-in user. None = login is switched off (local use): every book is
# shared, exactly as before accounts existed.
def list_projects(owner_id: int | None = None) -> list[dict]:
    """Every book (of this owner), with how many chapters and open warnings it has."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            """
            SELECT p.id, p.name, p.created_at, p.kind, p.synopsis, p.cover_color,
                   (SELECT MAX(c.updated_at) FROM chapters c WHERE c.project_id = p.id) AS last_edited,
                   (SELECT COUNT(*) FROM chapters c WHERE c.project_id = p.id) AS chapter_count,
                   (SELECT COUNT(*) FROM contradictions x
                    WHERE x.project_id = p.id AND x.status = 'open') AS open_issue_count,
                   (SELECT COUNT(*) FROM contradictions x
                    WHERE x.project_id = p.id AND x.status = 'open' AND x.severity = 'high') AS high_issue_count,
                   (SELECT COUNT(*) FROM entities e WHERE e.project_id = p.id) AS entity_count,
                   (SELECT COALESCE(SUM(length(c.text) - length(replace(c.text, ' ', '')) + 1), 0)
                    FROM chapters c WHERE c.project_id = p.id) AS word_count
            FROM projects p
            WHERE (%s::int IS NULL OR p.owner_id = %s)
            ORDER BY lower(p.name), p.id
            """,
            (owner_id, owner_id),
        )
        return cur.fetchall()


def get_project(project_id: int, owner_id: int | None = None) -> dict | None:
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute("SELECT id, name, created_at, owner_id, kind, synopsis, cover_color FROM projects "
                    "WHERE id = %s AND (%s::int IS NULL OR owner_id = %s)",
                    (project_id, owner_id, owner_id))
        return cur.fetchone()


def project_name_taken(name: str, except_id: int | None = None, owner_id: int | None = None) -> bool:
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM projects WHERE lower(name) = lower(%s) AND id IS DISTINCT FROM %s "
            "AND coalesce(owner_id, 0) = coalesce(%s, 0)",
            (name.strip(), except_id, owner_id),
        )
        return cur.fetchone() is not None


def create_project(name: str, owner_id: int | None = None, kind: str = "novel",
                   synopsis: str | None = None, cover_color: str | None = None) -> dict:
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute("INSERT INTO projects (name, owner_id, kind, synopsis, cover_color) VALUES (%s, %s, %s, %s, %s) "
                    "RETURNING id, name, created_at, kind, synopsis, cover_color",
                    (name.strip(), owner_id, kind, synopsis, cover_color))
        return cur.fetchone()


def rename_project(project_id: int, name: str) -> dict | None:
    return update_project(project_id, {"name": name.strip()})


def update_project(project_id: int, changes: dict) -> dict | None:
    """Change a book's name, kind, synopsis or cover colour."""
    allowed = {k: v for k, v in changes.items() if k in ("name", "kind", "synopsis", "cover_color")}
    if not allowed:
        return get_project(project_id)
    sets = ", ".join(f"{k} = %s" for k in allowed)
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(f"UPDATE projects SET {sets} WHERE id = %s RETURNING id, name, created_at, kind, synopsis, cover_color",
                    (*allowed.values(), project_id))
        return cur.fetchone()


def delete_project(project_id: int) -> bool:
    """Delete a book and EVERYTHING in it (chapters, facts, characters, warnings)."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM fact_corrections WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        return cur.rowcount == 1


def default_project_id(owner_id: int | None = None) -> int:
    """The first book (of this owner), created as "My story" if there are none. Used by the short addresses."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM projects WHERE (%s::int IS NULL OR owner_id = %s) ORDER BY id LIMIT 1",
                    (owner_id, owner_id))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO projects (name, owner_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING id",
            (DEFAULT_PROJECT_NAME, owner_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("SELECT id FROM projects WHERE (%s::int IS NULL OR owner_id = %s) ORDER BY id LIMIT 1",
                    (owner_id, owner_id))
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------
def resolve_chapter_number(project_id: int, chapter_id: str, requested: int | None) -> int:
    """
    Work out the reading-order number for a chapter:
    1. use the number you sent, if you sent one;
    2. otherwise keep the number it already had (when re-submitting a chapter);
    3. otherwise put it after the last chapter of this book.
    """
    if requested is not None:
        return requested
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT chapter_number FROM chapters WHERE project_id = %s AND id = %s",
                    (project_id, chapter_id))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("SELECT COALESCE(MAX(chapter_number), 0) + 1 FROM chapters WHERE project_id = %s",
                    (project_id,))
        return cur.fetchone()[0]


def warning_fingerprint(c: Contradiction) -> str:
    """
    Identifies "the same warning" across re-checks: the entity, the attribute and BOTH
    values. Re-submitting a chapter re-creates its warnings, and a warning the writer
    dismissed must come back dismissed, not open.
    """
    norm = lambda v: " ".join(str(v or "").lower().split())
    key = "|".join(norm(x) for x in (c.entity, c.new_attribute, c.new_value, c.conflicting_value))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]


def _severity(c: Contradiction, pinned_ids: set[int]) -> str:
    """high: a pinned canon fact is broken, or a confident status/timeline reversal. low: unsure."""
    if c.conflicting_fact_id in pinned_ids:
        return "high"
    if c.confidence < 0.5:
        return "low"
    if c.confidence >= 0.8 and (c.contradiction_type in ("status", "timeline") or c.source == "story clock"):
        return "high"
    return "medium" if c.confidence < 0.9 else "high"


def _insert_contradictions(cur, project_id: int, contradictions: list[Contradiction]) -> None:
    """Save warnings, applying the writer's earlier decisions (by fingerprint)."""
    if not contradictions:
        return
    cur.execute("SELECT fingerprint, status, reason FROM warning_decisions WHERE project_id = %s", (project_id,))
    decisions = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
    conflicting_ids = [c.conflicting_fact_id for c in contradictions if c.conflicting_fact_id]
    pinned: set[int] = set()
    if conflicting_ids:
        cur.execute("SELECT id FROM facts WHERE id = ANY(%s) AND pinned", (conflicting_ids,))
        pinned = {row[0] for row in cur.fetchall()}
    for c in contradictions:
        c.fingerprint = c.fingerprint or warning_fingerprint(c)
        c.severity = _severity(c, pinned)
        dismiss_reason = None
        if c.fingerprint in decisions and c.status == "open":
            c.status, dismiss_reason = decisions[c.fingerprint]
        cur.execute(
            """
            INSERT INTO contradictions
                (project_id, entity, new_chapter_id, new_attribute, new_value, new_quote,
                 conflicting_chapter_id, conflicting_value, conflicting_quote,
                 contradiction_type, confidence, explanation, status, review_note,
                 new_fact_id, conflicting_fact_id, fingerprint, severity, source, dismiss_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (project_id, c.entity, c.new_chapter_id, c.new_attribute, c.new_value, c.new_quote,
             c.conflicting_chapter_id, c.conflicting_value, c.conflicting_quote,
             c.contradiction_type, c.confidence, c.explanation, c.status, c.review_note,
             c.new_fact_id, c.conflicting_fact_id, c.fingerprint, c.severity, c.source, dismiss_reason),
        )


def save_chapter_results(
    project_id: int,
    chapter_id: str,
    chapter_number: int,
    text: str,
    facts: list[Fact],
    embeddings: list[list[float]],
    contradictions: list[Contradiction],
    resolutions: dict,
    time_note: str | None = None,
    relationships: list | None = None,
) -> dict:
    """
    Save a chapter, its facts, its contradictions and any newly learned names —
    all at once, or not at all. If the chapter was submitted before, its old facts
    and contradictions are replaced instead of piling up as duplicates.

    resolutions: {lowercase name: entities.Resolution} from resolve_entities().
    Returns {"new_entity_ids": {lowercase canonical name: id}, "fact_ids": [...],
             "later_chapters": [chapter ids that must be re-checked]}.
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chapters (project_id, id, chapter_number, text, time_note)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (project_id, id) DO UPDATE
                SET chapter_number = EXCLUDED.chapter_number,
                    text = EXCLUDED.text,
                    time_note = EXCLUDED.time_note,
                    updated_at = now()
            """,
            (project_id, chapter_id, chapter_number, text, time_note),
        )
        # Clear out what this chapter produced last time. Warnings where this chapter was
        # the EARLIER side pointed at text that no longer exists; the later chapters are
        # re-checked afterwards (see "later_chapters"), and the writer's dismissals are
        # kept by fingerprint, so nothing silently vanishes or comes back.
        cur.execute(
            "DELETE FROM contradictions WHERE project_id = %s "
            "AND (new_chapter_id = %s OR conflicting_chapter_id = %s)",
            (project_id, chapter_id, chapter_id),
        )
        cur.execute("DELETE FROM facts WHERE project_id = %s AND chapter_id = %s", (project_id, chapter_id))
        cur.execute("DELETE FROM relationships WHERE project_id = %s AND chapter_id = %s", (project_id, chapter_id))

        # Create one new entity per group of new names (names the AI gave the same
        # canonical_name belong together, e.g. "Elena" + "Elena Vale").
        new_entity_ids: dict[str, int] = {}
        for r in resolutions.values():
            key = r.canonical_name.lower()
            if r.is_new and key not in new_entity_ids:
                cur.execute(
                    "INSERT INTO entities (project_id, canonical_name, entity_type) VALUES (%s, %s, %s) RETURNING id",
                    (project_id, r.canonical_name, r.entity_type),
                )
                new_entity_ids[key] = cur.fetchone()[0]
                _add_alias(cur, project_id, new_entity_ids[key], r.canonical_name)

        def entity_id_for(name: str) -> int:
            r = resolutions[name.lower()]
            return r.existing_entity_id or new_entity_ids[r.canonical_name.lower()]

        # Remember every name used in this chapter, so next time it links instantly.
        for r in resolutions.values():
            _add_alias(cur, project_id, entity_id_for(r.name), r.name)

        fact_ids: list[int] = []
        for fact, embedding in zip(facts, embeddings):
            cur.execute(
                """
                INSERT INTO facts
                    (project_id, chapter_id, entity_id, entity, entity_type, attribute, value,
                     source_quote, confidence, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                RETURNING id
                """,
                (project_id, chapter_id, entity_id_for(fact.entity), fact.entity, fact.entity_type,
                 fact.attribute, fact.value, fact.source_quote, fact.confidence, _to_vector(embedding)),
            )
            fact_ids.append(cur.fetchone()[0])

        for r in relationships or []:
            if r.from_name.lower() not in resolutions or r.to_name.lower() not in resolutions:
                continue
            cur.execute(
                """INSERT INTO relationships (project_id, chapter_id, from_entity_id, to_entity_id, from_name, to_name,
                                              kind, category, source_quote, confidence)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (project_id, chapter_id, entity_id_for(r.from_name), entity_id_for(r.to_name), r.from_name, r.to_name,
                 r.kind, r.category, r.source_quote, r.confidence))

        _remove_orphan_entities(cur, project_id)

        for c in contradictions:
            if c.new_fact_index is not None and 0 <= c.new_fact_index < len(fact_ids):
                c.new_fact_id = fact_ids[c.new_fact_index]
        _insert_contradictions(cur, project_id, contradictions)

        cur.execute(
            "SELECT id FROM chapters WHERE project_id = %s AND chapter_number > %s ORDER BY chapter_number, id",
            (project_id, chapter_number),
        )
        later = [row[0] for row in cur.fetchall()]
    return {"new_entity_ids": new_entity_ids, "fact_ids": fact_ids, "later_chapters": later}


def load_chapter_for_recheck(project_id: int, chapter_id: str) -> dict | None:
    """A saved chapter's facts (with ids, entities and search vectors), for re-checking without re-reading."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute("SELECT chapter_number, time_note FROM chapters WHERE project_id = %s AND id = %s",
                    (project_id, chapter_id))
        chapter = cur.fetchone()
        if chapter is None:
            return None
        cur.execute(
            """
            SELECT f.id, f.entity_id, e.canonical_name, f.entity, f.entity_type, f.attribute, f.value,
                   f.source_quote, f.confidence, f.embedding::text AS embedding
            FROM facts f LEFT JOIN entities e ON e.id = f.entity_id
            WHERE f.project_id = %s AND f.chapter_id = %s ORDER BY f.id
            """,
            (project_id, chapter_id),
        )
        rows = cur.fetchall()
    for row in rows:
        row["embedding"] = json.loads(row["embedding"]) if row["embedding"] else None
    return {**chapter, "facts": rows}


def replace_chapter_warnings(project_id: int, chapter_id: str, contradictions: list[Contradiction]) -> None:
    """After a re-check: this chapter's warnings (as the NEW side) are replaced, decisions kept."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contradictions WHERE project_id = %s AND new_chapter_id = %s",
                    (project_id, chapter_id))
        _insert_contradictions(cur, project_id, contradictions)


def list_chapters(project_id: int) -> list[dict]:
    """All chapters of a book in reading order, with how many facts each produced."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            """
            SELECT c.id AS chapter_id, c.chapter_number, c.time_note, c.story_order, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM facts f WHERE f.project_id = c.project_id AND f.chapter_id = c.id)
                       AS fact_count,
                   (SELECT COUNT(*) FROM contradictions x WHERE x.project_id = c.project_id
                       AND x.new_chapter_id = c.id AND x.status = 'open') AS open_issue_count,
                   length(c.text) - length(replace(c.text, ' ', '')) + 1 AS word_count
            FROM chapters c
            WHERE c.project_id = %s
            ORDER BY c.chapter_number, c.id
            """,
            (project_id,),
        )
        return cur.fetchall()


def get_chapter(project_id: int, chapter_id: str) -> dict | None:
    """One chapter with its text and every fact taken from it."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            "SELECT id AS chapter_id, chapter_number, text, time_note, story_order, created_at, updated_at "
            "FROM chapters WHERE project_id = %s AND id = %s",
            (project_id, chapter_id),
        )
        chapter = cur.fetchone()
        if chapter is None:
            return None
        cur.execute(
            """
            SELECT f.id AS fact_id, f.entity, f.entity_id, e.canonical_name, f.entity_type,
                   f.attribute, f.value, f.source_quote, f.confidence, f.pinned
            FROM facts f LEFT JOIN entities e ON e.id = f.entity_id
            WHERE f.project_id = %s AND f.chapter_id = %s
            ORDER BY lower(coalesce(e.canonical_name, f.entity)), f.id
            """,
            (project_id, chapter_id),
        )
        chapter["facts"] = cur.fetchall()
        return chapter


def delete_chapter(project_id: int, chapter_id: str) -> bool:
    """Remove a chapter with its facts and warnings; entities left with no facts go too."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM chapters WHERE project_id = %s AND id = %s", (project_id, chapter_id))
        deleted = cur.rowcount == 1
        _remove_orphan_entities(cur, project_id)
        return deleted


def get_time_notes(project_id: int) -> list[dict]:
    """Each saved chapter's number and timing note, in reading order."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            "SELECT id AS chapter_id, chapter_number, time_note FROM chapters "
            "WHERE project_id = %s ORDER BY chapter_number, id",
            (project_id,),
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Characters, places, items, events (entities) and their names
# ---------------------------------------------------------------------------
def _add_alias(cur, project_id: int, entity_id: int, name: str) -> None:
    """Remember that `name` refers to this entity. A name already taken in this book is left alone."""
    cur.execute(
        """
        INSERT INTO entity_aliases (entity_id, project_id, alias, alias_lower)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (project_id, alias_lower) DO NOTHING
        """,
        (entity_id, project_id, name, name.lower()),
    )


def find_entities_by_alias(project_id: int, names: list[str]) -> dict[str, tuple[int, str]]:
    """For names already known in this book: {lowercase name: (entity id, canonical name)}."""
    if not names:
        return {}
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.alias_lower, e.id, e.canonical_name
            FROM entity_aliases a JOIN entities e ON e.id = a.entity_id
            WHERE a.project_id = %s AND a.alias_lower = ANY(%s)
            """,
            (project_id, [n.lower() for n in names]),
        )
        return {row[0]: (row[1], row[2]) for row in cur.fetchall()}


_ENTITY_COLUMNS = """
    e.id, e.canonical_name, e.entity_type,
    COALESCE((SELECT array_agg(a.alias ORDER BY a.alias)
              FROM entity_aliases a WHERE a.entity_id = e.id), '{}') AS aliases,
    (SELECT COUNT(*) FROM facts f WHERE f.entity_id = e.id) AS fact_count
"""


def get_all_entities_with_context(project_id: int, sample_facts: int = 3) -> list[dict]:
    """Every entity in the book with all its names and a few facts — the AI's evidence for matching."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            """
            SELECT e.id, e.canonical_name, e.entity_type,
                   COALESCE((SELECT array_agg(a.alias ORDER BY a.alias)
                             FROM entity_aliases a WHERE a.entity_id = e.id), '{}') AS aliases,
                   COALESCE((SELECT array_agg(s.attribute || ': ' || s.value)
                             FROM (SELECT attribute, value FROM facts f
                                   WHERE f.entity_id = e.id ORDER BY f.id LIMIT %s) s), '{}') AS sample_facts
            FROM entities e
            WHERE e.project_id = %s
            ORDER BY e.id
            """,
            (sample_facts, project_id),
        )
        return cur.fetchall()


def get_entity(project_id: int, entity_id: int) -> dict | None:
    """One entity of this book (None if it doesn't exist or belongs to another book)."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(f"SELECT {_ENTITY_COLUMNS} FROM entities e WHERE e.project_id = %s AND e.id = %s",
                    (project_id, entity_id))
        return cur.fetchone()


def list_entities(project_id: int) -> list[dict]:
    """Every entity in the book with all its names and how many facts it has."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            f"SELECT {_ENTITY_COLUMNS} FROM entities e WHERE e.project_id = %s "
            "ORDER BY e.entity_type, lower(e.canonical_name)",
            (project_id,),
        )
        return cur.fetchall()


_FACT_COLUMNS = """f.id AS fact_id, f.entity, f.entity_type, f.attribute, f.value, f.source_quote,
                   f.confidence, f.pinned, f.chapter_id, c.chapter_number"""


def get_facts_for_entity_id(entity_id: int, exclude_chapter_id: str | None = None,
                            before_chapter_number: int | None = None) -> list[dict]:
    """
    Everything stored about one entity, under ANY of its names, in reading order.
    before_chapter_number: only facts from chapters EARLIER in reading order (the
    established history when checking that chapter).
    """
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT {_FACT_COLUMNS}
            FROM facts f
            {_CHAPTER_JOIN}
            WHERE f.entity_id = %s
              AND (%s::text IS NULL OR f.chapter_id <> %s)
              AND (%s::int IS NULL OR c.chapter_number < %s)
            ORDER BY c.chapter_number, f.id
            """,
            (entity_id, exclude_chapter_id, exclude_chapter_id, before_chapter_number, before_chapter_number),
        )
        return cur.fetchall()


# Facts about states that can't simply be undone (death, destruction, loss, birth, age...).
# The checker always sees these, however long the entity's history is.
PERMANENT_PATTERN = (r"(status|dead|died|death|dies|kill|murder|destroy|burn|burnt|lost|loses|lose|"
                     r"broke|broken|shatter|sank|sunk|threw|thrown|buried|born|birth|age|years? old|"
                     r"amputat|blind|missing|married|widow|eye|scar|name|day|date|year)")
MAX_EVIDENCE_FACTS = int(os.getenv("MAX_EVIDENCE_FACTS", "60"))


def get_entity_evidence(entity_id: int, chapter_id: str, before_chapter_number: int,
                        focus_vector: list[float] | None = None, limit: int | None = None) -> list[dict]:
    """
    The earlier facts the checker sees for one entity, BOUNDED so a long novel never
    overflows the AI's context: every pinned fact, the facts about permanent states, and
    the facts closest in meaning to the new chapter's facts (focus_vector); in reading order.
    Short histories are returned whole.
    """
    limit = limit or MAX_EVIDENCE_FACTS
    base = f"""FROM facts f {_CHAPTER_JOIN}
               WHERE f.entity_id = %s AND f.chapter_id <> %s AND c.chapter_number < %s"""
    args = (entity_id, chapter_id, before_chapter_number)
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(f"SELECT COUNT(*) AS n {base}", args)
        if cur.fetchone()["n"] <= limit:
            cur.execute(f"SELECT {_FACT_COLUMNS} {base} ORDER BY c.chapter_number, f.id", args)
            return cur.fetchall()
        cur.execute(
            f"""SELECT {_FACT_COLUMNS} {base}
                AND (f.pinned OR f.attribute ~* %s OR f.value ~* %s)
                ORDER BY f.pinned DESC, c.chapter_number DESC, f.id DESC LIMIT %s""",
            (*args, PERMANENT_PATTERN, PERMANENT_PATTERN, limit // 2),
        )
        chosen = {row["fact_id"]: row for row in cur.fetchall()}
        remaining = limit - len(chosen)
        order = (f"{_distance('f.embedding')}" if focus_vector is not None
                 else "c.chapter_number DESC, f.id DESC")
        extra_args = (_to_vector(focus_vector),) if focus_vector is not None else ()
        cur.execute(
            f"""SELECT {_FACT_COLUMNS} {base} AND NOT (f.id = ANY(%s))
                ORDER BY {order} LIMIT %s""",
            (*args, list(chosen) or [0], *extra_args, remaining),
        )
        for row in cur.fetchall():
            chosen[row["fact_id"]] = row
    return sorted(chosen.values(), key=lambda r: (r["chapter_number"], r["fact_id"]))


def chapters_with_entity(project_id: int, entity_id: int) -> list[str]:
    """Chapters with facts about this entity, in reading order (to re-check after a merge/split)."""
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT c.id, c.chapter_number FROM facts f
               JOIN chapters c ON c.project_id = f.project_id AND c.id = f.chapter_id
               WHERE f.project_id = %s AND f.entity_id = %s ORDER BY c.chapter_number, c.id""",
            (project_id, entity_id))
        return [row[0] for row in cur.fetchall()]


def merge_entities(project_id: int, keep_id: int, merge_id: int) -> None:
    """Manual fix for a MISSED link: move everything from merge_id into keep_id (same book)."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE facts SET entity_id = %s WHERE project_id = %s AND entity_id = %s",
                    (keep_id, project_id, merge_id))
        cur.execute("UPDATE entity_aliases SET entity_id = %s WHERE project_id = %s AND entity_id = %s",
                    (keep_id, project_id, merge_id))
        cur.execute("UPDATE relationships SET from_entity_id = %s WHERE project_id = %s AND from_entity_id = %s",
                    (keep_id, project_id, merge_id))
        cur.execute("UPDATE relationships SET to_entity_id = %s WHERE project_id = %s AND to_entity_id = %s",
                    (keep_id, project_id, merge_id))
        # A relationship of someone with themselves is what a wrong split looked like: drop it.
        cur.execute("DELETE FROM relationships WHERE project_id = %s AND from_entity_id = to_entity_id", (project_id,))
        cur.execute("DELETE FROM entities WHERE project_id = %s AND id = %s", (project_id, merge_id))


def detach_alias(project_id: int, entity_id: int, alias: str) -> int:
    """
    Manual fix for a WRONG link: split one name off into its own new entity,
    taking the facts written under that name with it. Returns the new entity's id.
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT entity_type FROM entities WHERE project_id = %s AND id = %s", (project_id, entity_id))
        entity_type = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO entities (project_id, canonical_name, entity_type) VALUES (%s, %s, %s) RETURNING id",
            (project_id, alias, entity_type),
        )
        new_id = cur.fetchone()[0]
        cur.execute(
            "UPDATE entity_aliases SET entity_id = %s WHERE entity_id = %s AND alias_lower = lower(%s)",
            (new_id, entity_id, alias),
        )
        cur.execute(
            "UPDATE facts SET entity_id = %s WHERE entity_id = %s AND lower(entity) = lower(%s)",
            (new_id, entity_id, alias),
        )
        cur.execute("UPDATE relationships SET from_entity_id = %s WHERE from_entity_id = %s AND lower(from_name) = lower(%s)",
                    (new_id, entity_id, alias))
        cur.execute("UPDATE relationships SET to_entity_id = %s WHERE to_entity_id = %s AND lower(to_name) = lower(%s)",
                    (new_id, entity_id, alias))
        # If the old entity's main name was the one we split off, pick another of its names.
        cur.execute(
            """
            UPDATE entities e SET canonical_name = (
                SELECT a.alias FROM entity_aliases a WHERE a.entity_id = e.id
                ORDER BY length(a.alias) DESC LIMIT 1)
            WHERE e.id = %s AND lower(e.canonical_name) = lower(%s)
            """,
            (entity_id, alias),
        )
        return new_id


# ---------------------------------------------------------------------------
# Evidence for the checker
# ---------------------------------------------------------------------------
def _mention_patterns(names: list[str]) -> list[str]:
    """Whole-word search patterns for names, ignoring a leading "the"/"a" and very short names."""
    stripped = {re.sub(r"^(the|a|an)\s+", "", n.strip(), flags=re.I) for n in names}
    return [r"\m" + re.escape(n) + r"\M" for n in sorted(stripped) if len(n) >= 3]


def _facts_matching(project_id: int, patterns: list[str], exclude_entity_id: int | None,
                    exclude_chapter_id: str | None, limit: int,
                    before_chapter_number: int | None = None) -> list[dict]:
    if not patterns:
        return []
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT {_FACT_COLUMNS}
            FROM facts f
            {_CHAPTER_JOIN}
            WHERE f.project_id = %s
              AND f.entity_id IS DISTINCT FROM %s
              AND (%s::text IS NULL OR f.chapter_id <> %s)
              AND (%s::int IS NULL OR c.chapter_number < %s)
              AND (f.value ~* ANY(%s) OR f.source_quote ~* ANY(%s))
            ORDER BY c.chapter_number DESC, f.id DESC
            LIMIT %s
            """,
            (project_id, exclude_entity_id, exclude_chapter_id, exclude_chapter_id,
             before_chapter_number, before_chapter_number, patterns, patterns, limit),
        )
        return sorted(cur.fetchall(), key=lambda r: (r["chapter_number"], r["fact_id"]))


def get_facts_mentioning_entity(entity_id: int, exclude_chapter_id: str | None = None,
                                limit: int = 15, before_chapter_number: int | None = None) -> list[dict]:
    """
    Facts filed under OTHER entities (in the same book) whose value or quote mentions one
    of this entity's names as a whole word. E.g. for "the brass key", the fact
    "Tobias | threw | the brass key into the sea".
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT project_id FROM entities WHERE id = %s", (entity_id,))
        row = cur.fetchone()
        if row is None:
            return []
        project_id = row[0]
        cur.execute("SELECT alias FROM entity_aliases WHERE entity_id = %s", (entity_id,))
        names = [r[0] for r in cur.fetchall()]
    return _facts_matching(project_id, _mention_patterns(names), entity_id, exclude_chapter_id, limit,
                           before_chapter_number)


def get_facts_mentioning_names(project_id: int, names: list[str], exclude_chapter_id: str | None = None,
                               limit: int = 15, before_chapter_number: int | None = None) -> list[dict]:
    """Earlier facts in this book that mention any of these names: evidence for a brand-new entity."""
    return _facts_matching(project_id, _mention_patterns(names), None, exclude_chapter_id, limit,
                           before_chapter_number)


def get_similar_earlier_facts(project_id: int, vectors: list[list[float]], exclude_chapter_id: str,
                              before_chapter_number: int, top_k: int = 3) -> list[list[dict]]:
    """
    For EACH vector: the stored facts from EARLIER chapters of this book whose meaning is
    closest, whatever entity they're filed under. One query for the whole chapter (it used
    to be one query per fact). Used by the safety-net check.
    """
    if not vectors:
        return []
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT q.idx, n.*
            FROM unnest(%s::text[]) WITH ORDINALITY AS q(v, idx)
            CROSS JOIN LATERAL (
                SELECT f.id AS fact_id, f.entity_id, f.entity, e.canonical_name, f.entity_type,
                       f.attribute, f.value, f.source_quote, f.chapter_id, c.chapter_number, f.pinned
                FROM facts f
                {_CHAPTER_JOIN}
                LEFT JOIN entities e ON e.id = f.entity_id
                WHERE f.project_id = %s AND f.chapter_id <> %s AND c.chapter_number < %s
                  AND f.embedding IS NOT NULL
                ORDER BY {_distance("f.embedding", "q.v")}
                LIMIT %s
            ) n
            ORDER BY q.idx
            """,
            ([_to_vector(v) for v in vectors], project_id, exclude_chapter_id, before_chapter_number, top_k),
        )
        rows = cur.fetchall()
    grouped: list[list[dict]] = [[] for _ in vectors]
    for row in rows:
        grouped[row.pop("idx") - 1].append(row)
    return grouped


# ---------------------------------------------------------------------------
# Warnings (contradictions)
# ---------------------------------------------------------------------------
def get_all_contradictions(project_id: int, status: str | None = None) -> list[dict]:
    """All of a book's contradictions, newest first. status: None (all), 'open', 'dismissed' or 'resolved'."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            """
            SELECT x.id, x.entity, x.new_chapter_id, nc.chapter_number AS new_chapter_number,
                   x.new_attribute, x.new_value, x.new_quote,
                   x.conflicting_chapter_id, cc.chapter_number AS conflicting_chapter_number,
                   x.conflicting_value, x.conflicting_quote,
                   x.contradiction_type, x.confidence, x.explanation, x.status, x.review_note,
                   x.severity, x.source, x.dismiss_reason, x.fingerprint,
                   x.new_fact_id, x.conflicting_fact_id,
                   COALESCE(cf.pinned, false) AS conflicting_pinned, x.created_at
            FROM contradictions x
            JOIN chapters nc ON nc.project_id = x.project_id AND nc.id = x.new_chapter_id
            JOIN chapters cc ON cc.project_id = x.project_id AND cc.id = x.conflicting_chapter_id
            LEFT JOIN facts cf ON cf.id = x.conflicting_fact_id
            WHERE x.project_id = %s AND (%s::text IS NULL OR x.status = %s)
            ORDER BY x.created_at DESC, x.id DESC
            """,
            (project_id, status, status),
        )
        return cur.fetchall()


def set_contradiction_status(project_id: int, contradiction_id: int, status: str,
                             reason: str | None = None) -> bool:
    """
    Mark a warning 'dismissed' (the writer says it's fine) or 'open' again. The decision is
    remembered by the warning's fingerprint, so re-checking the chapter doesn't undo it.
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE contradictions SET status = %s, dismiss_reason = %s "
                    "WHERE project_id = %s AND id = %s RETURNING fingerprint",
                    (status, reason if status == "dismissed" else None, project_id, contradiction_id))
        row = cur.fetchone()
        if row is None:
            return False
        if row[0]:
            if status == "dismissed":
                cur.execute(
                    """INSERT INTO warning_decisions (project_id, fingerprint, status, reason)
                       VALUES (%s, %s, 'dismissed', %s)
                       ON CONFLICT (project_id, fingerprint) DO UPDATE SET reason = EXCLUDED.reason""",
                    (project_id, row[0], reason))
            else:
                cur.execute("DELETE FROM warning_decisions WHERE project_id = %s AND fingerprint = %s",
                            (project_id, row[0]))
        return True


def dismissal_feedback(project_id: int | None = None) -> list[dict]:
    """The writer's dismissals with reasons, and fact corrections: material for the evaluation set."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            """SELECT x.project_id, x.entity, x.contradiction_type, x.new_value, x.new_quote,
                      x.conflicting_value, x.conflicting_quote, x.explanation, x.dismiss_reason, x.created_at
               FROM contradictions x
               WHERE x.status = 'dismissed' AND x.review_note IS NULL
                 AND (%s::int IS NULL OR x.project_id = %s)
               ORDER BY x.created_at""", (project_id, project_id))
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Facts: manual corrections
# ---------------------------------------------------------------------------
def get_fact(project_id: int, fact_id: int) -> dict | None:
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            """
            SELECT id AS fact_id, chapter_id, entity_id, entity, entity_type, attribute, value,
                   source_quote, confidence, pinned
            FROM facts WHERE project_id = %s AND id = %s
            """,
            (project_id, fact_id),
        )
        return cur.fetchone()


def _resolve_warnings_for_fact(cur, project_id: int, fact_id: int, note: str) -> list[str]:
    """
    Open warnings built on this fact are closed as 'resolved' (they showed the old value).
    Returns the chapters to re-check: the chapters on the NEW side of those warnings.
    """
    cur.execute(
        """UPDATE contradictions SET status = 'resolved', review_note = %s
           WHERE project_id = %s AND status = 'open' AND (new_fact_id = %s OR conflicting_fact_id = %s)
           RETURNING new_chapter_id""",
        (note, project_id, fact_id, fact_id))
    return sorted({row[0] for row in cur.fetchall()})


def chapter_number_of(project_id: int, chapter_id: str) -> int | None:
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT chapter_number FROM chapters WHERE project_id = %s AND id = %s", (project_id, chapter_id))
        row = cur.fetchone()
        return row[0] if row else None


def chapters_after(project_id: int, chapter_number: int) -> list[str]:
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM chapters WHERE project_id = %s AND chapter_number > %s "
                    "ORDER BY chapter_number, id", (project_id, chapter_number))
        return [row[0] for row in cur.fetchall()]


def set_fact_pinned(project_id: int, fact_id: int, pinned: bool) -> dict | None:
    """Pin a fact as canon (the writer says this is how it is) or unpin it."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE facts SET pinned = %s WHERE project_id = %s AND id = %s", (pinned, project_id, fact_id))
        if cur.rowcount != 1:
            return None
        # Warnings that contradict a pinned fact are the most important ones.
        if pinned:
            cur.execute("UPDATE contradictions SET severity = 'high' WHERE project_id = %s "
                        "AND conflicting_fact_id = %s", (project_id, fact_id))
    return get_fact(project_id, fact_id)


def update_fact(project_id: int, fact_id: int, changes: dict) -> dict | None:
    """
    Manually correct a fact (attribute / value / entity_type). The fact is re-embedded
    so search stays accurate, and the change is logged in fact_corrections. Open warnings
    built on the old version are closed; the result's "recheck_chapters" says which
    chapters must be re-checked.
    """
    before = get_fact(project_id, fact_id)
    if before is None:
        return None
    changes = {k: v for k, v in changes.items() if k != "pinned"}
    after = {**before, **changes}
    embedding = embed_facts([Fact(
        entity=after["entity"], entity_type=after["entity_type"], attribute=after["attribute"],
        value=after["value"], source_quote=after["source_quote"], confidence=after["confidence"],
    )])[0]
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE facts SET attribute = %s, value = %s, entity_type = %s, confidence = 1.0,
                             embedding = %s::vector
            WHERE project_id = %s AND id = %s
            """,
            (after["attribute"], after["value"], after["entity_type"], _to_vector(embedding), project_id, fact_id),
        )
        cur.execute(
            "INSERT INTO fact_corrections (project_id, fact_id, action, before, after) "
            "VALUES (%s, %s, 'edit', %s, %s)",
            (project_id, fact_id, json.dumps(before, default=str), json.dumps(changes)),
        )
        affected = _resolve_warnings_for_fact(cur, project_id, fact_id, "The fact was corrected; re-checked.")
    result = get_fact(project_id, fact_id)
    result["recheck_chapters"] = sorted(set(affected) | {before["chapter_id"]})
    return result


def delete_fact(project_id: int, fact_id: int) -> list[str] | None:
    """
    Remove a wrongly extracted fact (logged in fact_corrections). Warnings built on it are
    closed. Returns the chapters to re-check, or None if there's no such fact.
    """
    before = get_fact(project_id, fact_id)
    if before is None:
        return None
    with db() as conn, conn.cursor() as cur:
        affected = _resolve_warnings_for_fact(cur, project_id, fact_id, "The fact was deleted.")
        cur.execute("DELETE FROM facts WHERE project_id = %s AND id = %s", (project_id, fact_id))
        cur.execute(
            "INSERT INTO fact_corrections (project_id, fact_id, action, before) VALUES (%s, %s, 'delete', %s)",
            (project_id, fact_id, json.dumps(before, default=str)),
        )
        _remove_orphan_entities(cur, project_id)
    return [c for c in affected if c != before["chapter_id"]]


# ---------------------------------------------------------------------------
# Timeline and search
# ---------------------------------------------------------------------------
def _story_positions(chapters: list[dict]) -> dict[str, float]:
    """
    Where each chapter sits in STORY time (not reading order). The writer's own story order
    wins; otherwise flashbacks go before the main story (in reading order among themselves)
    and every other chapter follows reading order.
    """
    positions: dict[str, float] = {}
    for c in chapters:
        if c["story_order"] is not None:
            positions[c["chapter_id"]] = float(c["story_order"])
        elif (c["time_note"] or "").lower().startswith("flashback"):
            positions[c["chapter_id"]] = c["chapter_number"] - 1000.0   # before the main story
        else:
            positions[c["chapter_id"]] = float(c["chapter_number"])
    return positions


def get_timeline(project_id: int, order: str = "reading") -> list[dict]:
    """
    Every event fact of the book: the raw material for the timeline view.
    order="reading": the order the reader meets them; order="story": story time
    (flashbacks first, or the writer's own story order).
    """
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT f.id AS fact_id, f.entity, e.canonical_name, f.attribute, f.value,
                   f.source_quote, f.confidence, f.pinned, f.chapter_id, c.chapter_number,
                   c.time_note, c.story_order
            FROM facts f
            {_CHAPTER_JOIN}
            LEFT JOIN entities e ON e.id = f.entity_id
            WHERE f.project_id = %s AND f.entity_type = 'event'
            ORDER BY c.chapter_number, f.id
            """,
            (project_id,),
        )
        events = cur.fetchall()
    if order == "story":
        positions = _story_positions(list_chapters(project_id))
        events.sort(key=lambda e: (positions.get(e["chapter_id"], e["chapter_number"]), e["fact_id"]))
    return events


def set_chapter_story_order(project_id: int, chapter_id: str, story_order: float | None) -> bool:
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE chapters SET story_order = %s WHERE project_id = %s AND id = %s",
                    (story_order, project_id, chapter_id))
        return cur.rowcount == 1


def export_book(project_id: int) -> dict:
    """The whole book as plain JSON lore: for game engines, wikis, backups."""
    project = get_project(project_id)
    entities = list_entities(project_id)
    by_entity: dict[int, list] = {}
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            f"""SELECT f.id, f.entity_id, f.entity AS written_as, f.attribute, f.value, f.source_quote,
                       f.confidence, f.pinned, f.chapter_id, c.chapter_number
                FROM facts f {_CHAPTER_JOIN} WHERE f.project_id = %s ORDER BY c.chapter_number, f.id""",
            (project_id,))
        for row in cur.fetchall():
            by_entity.setdefault(row.pop("entity_id"), []).append(row)
    return {
        "format": "storyforge-lore/1",
        "book": {"id": project["id"], "name": project["name"]},
        "chapters": [{k: v for k, v in c.items() if k not in ("created_at", "updated_at")}
                     for c in list_chapters(project_id)],
        "entities": [{"id": e["id"], "name": e["canonical_name"], "type": e["entity_type"],
                      "aliases": e["aliases"], "facts": by_entity.get(e["id"], [])} for e in entities],
        "warnings": [{k: v for k, v in w.items() if k != "created_at"}
                     for w in get_all_contradictions(project_id)],
    }


def semantic_search(project_id: int, query_text: str, top_k: int = 5) -> list[dict]:
    """Facts in this book whose meaning is closest to the query, even with different wording."""
    query_vector = _to_vector(embed_texts([query_text], input_type="query")[0])
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT f.entity, e.canonical_name, f.entity_type, f.attribute, f.value, f.source_quote,
                   f.confidence, f.chapter_id, c.chapter_number,
                   1 - (f.embedding <=> %s::vector) AS similarity
            FROM facts f
            {_CHAPTER_JOIN}
            LEFT JOIN entities e ON e.id = f.entity_id
            WHERE f.project_id = %s
            ORDER BY {_distance("f.embedding")}
            LIMIT %s
            """,
            (query_vector, project_id, query_vector, top_k),
        )
        return cur.fetchall()


def apply_schema() -> None:
    """Create any missing tables/columns (and upgrade old databases). Safe to run every start."""
    global HALFVEC
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    with open(path, encoding="utf-8") as f, db() as conn, conn.cursor() as cur:
        cur.execute(f.read())
        cur.execute("SELECT string_to_array(extversion, '.')::int[] >= array[0,7,0] "
                    "FROM pg_extension WHERE extname = 'vector'")
        row = cur.fetchone()
        HALFVEC = bool(row and row[0])


def database_ok() -> bool:
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Character charts, presence map, recent activity
# ---------------------------------------------------------------------------
_DEATH_PATTERN = r"\m(dead|died|dies|killed|murdered|drowned|deceased|slain|executed|perished|passed away)\M"


def character_map(project_id: int) -> dict:
    """
    Everything the family tree and relationship web need, with chapter numbers so the
    website's "as of chapter N" slider can filter without asking again:
    characters (first appearance, death), relationships (every time each one is stated),
    and pairs whose stated family ties can't all be true.
    """
    import relationships as rel_rules
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute("SELECT id AS chapter_id, chapter_number FROM chapters WHERE project_id = %s "
                    "ORDER BY chapter_number, id", (project_id,))
        chapters = cur.fetchall()
        cur.execute(
            f"""SELECT r.from_entity_id, r.to_entity_id, r.kind, r.category, r.source_quote, r.chapter_id,
                       c.chapter_number
                FROM relationships r JOIN chapters c ON c.project_id = r.project_id AND c.id = r.chapter_id
                WHERE r.project_id = %s AND r.from_entity_id IS NOT NULL AND r.to_entity_id IS NOT NULL
                ORDER BY c.chapter_number, r.id""", (project_id,))
        rows = cur.fetchall()
        cur.execute(
            f"""SELECT e.id, e.canonical_name AS name,
                       COALESCE((SELECT array_agg(a.alias ORDER BY a.alias) FROM entity_aliases a WHERE a.entity_id = e.id), '{{}}') AS aliases,
                       COUNT(f.id) AS fact_count, MIN(c.chapter_number) AS first_chapter,
                       MIN(c.chapter_number) FILTER (WHERE (f.attribute ~* '(status|state|fate|death)' OR f.value ~* %s)
                                                      AND f.value ~* %s
                                                      AND coalesce(c.time_note, '') NOT ILIKE 'flashback%%') AS died_chapter
                FROM entities e
                JOIN facts f ON f.entity_id = e.id
                {_CHAPTER_JOIN}
                WHERE e.project_id = %s AND e.entity_type IN ('character', 'other')
                GROUP BY e.id ORDER BY e.canonical_name""",
            (_DEATH_PATTERN, _DEATH_PATTERN, project_id))
        people = {p["id"]: p for p in cur.fetchall()}

    # One edge per (pair, kind, direction), with every chapter that states it.
    edges: dict[tuple, dict] = {}
    for r in rows:
        a, b = r["from_entity_id"], r["to_entity_id"]
        if r["kind"] not in rel_rules.DIRECTIONAL and a > b:
            a, b = b, a
        key = (a, b, r["kind"])
        edge = edges.setdefault(key, {"from": a, "to": b, "kind": r["kind"], "category": r["category"],
                                      "label": rel_rules.LABELS.get(r["kind"], r["kind"]),
                                      "first_chapter": r["chapter_number"], "mentions": []})
        edge["mentions"].append({"chapter_id": r["chapter_id"], "chapter_number": r["chapter_number"],
                                 "quote": r["source_quote"]})
    edge_list = list(edges.values())
    # Family ties for the same two people that can't all be true.
    for i, e1 in enumerate(edge_list):
        for e2 in edge_list[i + 1:]:
            if {e1["from"], e1["to"]} != {e2["from"], e2["to"]}:
                continue
            if rel_rules.conflict(e1["kind"], e2["kind"], e1["from"] == e2["from"]):
                for x, y in ((e1, e2), (e2, e1)):
                    x.setdefault("conflicts", []).append({"kind": y["kind"], "label": y["label"],
                                                          "first_chapter": y["first_chapter"],
                                                          "quote": y["mentions"][0]["quote"]})
    used = {e["from"] for e in edge_list} | {e["to"] for e in edge_list}
    for person_id in used:
        if person_id not in people:          # e.g. an "other"-typed entity with no facts
            people[person_id] = {"id": person_id, "name": f"#{person_id}", "aliases": [], "fact_count": 0,
                                 "first_chapter": None, "died_chapter": None}
    for e in edge_list:
        for end in (e["from"], e["to"]):
            p = people[end]
            if p["first_chapter"] is None or e["first_chapter"] < p["first_chapter"]:
                p["first_chapter"] = e["first_chapter"]
    return {"chapters": chapters, "people": list(people.values()), "edges": edge_list}


def presence(project_id: int, top: int = 30) -> dict:
    """For the presence map: how many facts each main entity has in each chapter, and where its open issues are."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute("SELECT id AS chapter_id, chapter_number FROM chapters WHERE project_id = %s "
                    "ORDER BY chapter_number, id", (project_id,))
        chapters = cur.fetchall()
        cur.execute(
            """SELECT e.id, e.canonical_name AS name, e.entity_type, COUNT(f.id) AS total
               FROM entities e JOIN facts f ON f.entity_id = e.id
               WHERE e.project_id = %s AND e.entity_type IN ('character', 'location', 'item')
               GROUP BY e.id ORDER BY COUNT(f.id) DESC, e.canonical_name LIMIT %s""", (project_id, top))
        entities = cur.fetchall()
        ids = [e["id"] for e in entities] or [0]
        cur.execute("SELECT entity_id, chapter_id, COUNT(*) AS n FROM facts WHERE entity_id = ANY(%s) "
                    "GROUP BY entity_id, chapter_id", (ids,))
        counts = cur.fetchall()
        cur.execute(
            """SELECT f.entity_id, x.new_chapter_id AS chapter_id, COUNT(DISTINCT x.id) AS n
               FROM contradictions x JOIN facts f ON f.id IN (x.new_fact_id, x.conflicting_fact_id)
               WHERE x.project_id = %s AND x.status = 'open' AND f.entity_id = ANY(%s)
               GROUP BY f.entity_id, x.new_chapter_id""", (project_id, ids))
        issues = cur.fetchall()
    cells: dict = {}
    for row in counts:
        cells.setdefault(row["entity_id"], {})[row["chapter_id"]] = {"facts": row["n"], "issues": 0}
    for row in issues:
        cells.setdefault(row["entity_id"], {}).setdefault(row["chapter_id"], {"facts": 0, "issues": 0})["issues"] = row["n"]
    for e in entities:
        e["cells"] = cells.get(e["id"], {})
    return {"chapters": chapters, "entities": entities}


def recent_activity(owner_id: int | None, limit: int = 12) -> list[dict]:
    """Recent work across all of a user's books, for the shelf's side panel."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            """SELECT j.id, j.kind, j.chapter_id, j.status, j.result->'contradictions' IS NOT NULL AS has_result,
                      (SELECT COUNT(*) FROM jsonb_array_elements(COALESCE(j.result->'contradictions', '[]'::jsonb)) c
                       WHERE c->>'status' = 'open') AS issues_found,
                      j.updated_at, p.id AS project_id, p.name AS project_name, p.cover_color
               FROM jobs j JOIN projects p ON p.id = j.project_id
               WHERE (%s::int IS NULL OR p.owner_id = %s)
               ORDER BY j.updated_at DESC LIMIT %s""", (owner_id, owner_id, limit))
        return cur.fetchall()

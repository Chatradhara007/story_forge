"""
Everything that reads or writes the database.

Every function works inside ONE book (project): chapters, facts, characters and
warnings never mix between books.
"""
import os
import re
import json
from contextlib import contextmanager
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from models import Fact, Contradiction
from llm import embed_texts

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
DEFAULT_PROJECT_NAME = "My story"

# A chapter row joined to a fact row: both must be in the same book.
_CHAPTER_JOIN = "JOIN chapters c ON c.project_id = f.project_id AND c.id = f.chapter_id"


@contextmanager
def db():
    """
    Open a database connection for a block of work.
    If everything in the block succeeds, all changes are saved together.
    If anything fails, NOTHING from the block is saved (no half-finished data).
    """
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
def list_projects() -> list[dict]:
    """Every book, with how many chapters and open warnings it has."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            """
            SELECT p.id, p.name, p.created_at,
                   (SELECT COUNT(*) FROM chapters c WHERE c.project_id = p.id) AS chapter_count,
                   (SELECT COUNT(*) FROM contradictions x
                    WHERE x.project_id = p.id AND x.status = 'open') AS open_issue_count
            FROM projects p
            ORDER BY lower(p.name), p.id
            """
        )
        return cur.fetchall()


def get_project(project_id: int) -> dict | None:
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute("SELECT id, name, created_at FROM projects WHERE id = %s", (project_id,))
        return cur.fetchone()


def project_name_taken(name: str, except_id: int | None = None) -> bool:
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM projects WHERE lower(name) = lower(%s) AND id IS DISTINCT FROM %s",
            (name.strip(), except_id),
        )
        return cur.fetchone() is not None


def create_project(name: str) -> dict:
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute("INSERT INTO projects (name) VALUES (%s) RETURNING id, name, created_at", (name.strip(),))
        return cur.fetchone()


def rename_project(project_id: int, name: str) -> dict | None:
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute("UPDATE projects SET name = %s WHERE id = %s RETURNING id, name, created_at",
                    (name.strip(), project_id))
        return cur.fetchone()


def delete_project(project_id: int) -> bool:
    """Delete a book and EVERYTHING in it (chapters, facts, characters, warnings)."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM fact_corrections WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        return cur.rowcount == 1


def default_project_id() -> int:
    """The first book, created as "My story" if there are none. Used by the short addresses."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM projects ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO projects (name) VALUES (%s) ON CONFLICT DO NOTHING RETURNING id",
            (DEFAULT_PROJECT_NAME,),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("SELECT id FROM projects ORDER BY id LIMIT 1")
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
) -> dict[str, int]:
    """
    Save a chapter, its facts, its contradictions and any newly learned names —
    all at once, or not at all. If the chapter was submitted before, its old facts
    and contradictions are replaced instead of piling up as duplicates.

    resolutions: {lowercase name: entities.Resolution} from resolve_entities().
    Returns {lowercase canonical name: new entity id} for entities created here.
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
        # Clear out what this chapter produced last time. Contradictions where this
        # chapter was the "older" side are removed too, because they pointed at text
        # that no longer exists; re-submit later chapters to re-check them.
        cur.execute(
            "DELETE FROM contradictions WHERE project_id = %s "
            "AND (new_chapter_id = %s OR conflicting_chapter_id = %s)",
            (project_id, chapter_id, chapter_id),
        )
        cur.execute("DELETE FROM facts WHERE project_id = %s AND chapter_id = %s", (project_id, chapter_id))

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

        for fact, embedding in zip(facts, embeddings):
            cur.execute(
                """
                INSERT INTO facts
                    (project_id, chapter_id, entity_id, entity, entity_type, attribute, value,
                     source_quote, confidence, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                """,
                (project_id, chapter_id, entity_id_for(fact.entity), fact.entity, fact.entity_type,
                 fact.attribute, fact.value, fact.source_quote, fact.confidence, _to_vector(embedding)),
            )

        _remove_orphan_entities(cur, project_id)

        for c in contradictions:
            cur.execute(
                """
                INSERT INTO contradictions
                    (project_id, entity, new_chapter_id, new_attribute, new_value, new_quote,
                     conflicting_chapter_id, conflicting_value, conflicting_quote,
                     contradiction_type, confidence, explanation, status, review_note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (project_id, c.entity, c.new_chapter_id, c.new_attribute, c.new_value, c.new_quote,
                 c.conflicting_chapter_id, c.conflicting_value, c.conflicting_quote,
                 c.contradiction_type, c.confidence, c.explanation, c.status, c.review_note),
            )
    return new_entity_ids


def list_chapters(project_id: int) -> list[dict]:
    """All chapters of a book in reading order, with how many facts each produced."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            """
            SELECT c.id AS chapter_id, c.chapter_number, c.time_note, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM facts f WHERE f.project_id = c.project_id AND f.chapter_id = c.id)
                       AS fact_count
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
            "SELECT id AS chapter_id, chapter_number, text, time_note, created_at, updated_at "
            "FROM chapters WHERE project_id = %s AND id = %s",
            (project_id, chapter_id),
        )
        chapter = cur.fetchone()
        if chapter is None:
            return None
        cur.execute(
            """
            SELECT f.id AS fact_id, f.entity, f.entity_id, e.canonical_name, f.entity_type,
                   f.attribute, f.value, f.source_quote, f.confidence
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


def get_facts_for_entity_id(entity_id: int, exclude_chapter_id: str | None = None) -> list[dict]:
    """Everything stored about one entity, under ANY of its names, in reading order."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT f.id AS fact_id, f.entity, f.entity_type, f.attribute, f.value, f.source_quote,
                   f.confidence, f.chapter_id, c.chapter_number
            FROM facts f
            {_CHAPTER_JOIN}
            WHERE f.entity_id = %s
              AND (%s::text IS NULL OR f.chapter_id <> %s)
            ORDER BY c.chapter_number, f.id
            """,
            (entity_id, exclude_chapter_id, exclude_chapter_id),
        )
        return cur.fetchall()


def merge_entities(project_id: int, keep_id: int, merge_id: int) -> None:
    """Manual fix for a MISSED link: move everything from merge_id into keep_id (same book)."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE facts SET entity_id = %s WHERE project_id = %s AND entity_id = %s",
                    (keep_id, project_id, merge_id))
        cur.execute("UPDATE entity_aliases SET entity_id = %s WHERE project_id = %s AND entity_id = %s",
                    (keep_id, project_id, merge_id))
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
                    exclude_chapter_id: str | None, limit: int) -> list[dict]:
    if not patterns:
        return []
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT f.id AS fact_id, f.entity, f.entity_type, f.attribute, f.value, f.source_quote,
                   f.confidence, f.chapter_id, c.chapter_number
            FROM facts f
            {_CHAPTER_JOIN}
            WHERE f.project_id = %s
              AND f.entity_id IS DISTINCT FROM %s
              AND (%s::text IS NULL OR f.chapter_id <> %s)
              AND (f.value ~* ANY(%s) OR f.source_quote ~* ANY(%s))
            ORDER BY c.chapter_number, f.id
            LIMIT %s
            """,
            (project_id, exclude_entity_id, exclude_chapter_id, exclude_chapter_id, patterns, patterns, limit),
        )
        return cur.fetchall()


def get_facts_mentioning_entity(entity_id: int, exclude_chapter_id: str | None = None,
                                limit: int = 15) -> list[dict]:
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
    return _facts_matching(project_id, _mention_patterns(names), entity_id, exclude_chapter_id, limit)


def get_facts_mentioning_names(project_id: int, names: list[str], exclude_chapter_id: str | None = None,
                               limit: int = 15) -> list[dict]:
    """Earlier facts in this book that mention any of these names: evidence for a brand-new entity."""
    return _facts_matching(project_id, _mention_patterns(names), None, exclude_chapter_id, limit)


def get_similar_earlier_facts(project_id: int, vector: list[float], exclude_chapter_id: str,
                              top_k: int = 3) -> list[dict]:
    """
    The stored facts from OTHER chapters of this book whose meaning is closest to this
    vector, whatever entity they're filed under. Used by the safety-net check.
    """
    vec = _to_vector(vector)
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT f.id AS fact_id, f.entity_id, f.entity, e.canonical_name, f.entity_type,
                   f.attribute, f.value, f.source_quote, f.chapter_id, c.chapter_number,
                   1 - (f.embedding <=> %s::vector) AS similarity
            FROM facts f
            {_CHAPTER_JOIN}
            LEFT JOIN entities e ON e.id = f.entity_id
            WHERE f.project_id = %s AND f.chapter_id <> %s AND f.embedding IS NOT NULL
            ORDER BY f.embedding <=> %s::vector
            LIMIT %s
            """,
            (vec, project_id, exclude_chapter_id, vec, top_k),
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Warnings (contradictions)
# ---------------------------------------------------------------------------
def get_all_contradictions(project_id: int, status: str | None = None) -> list[dict]:
    """All of a book's contradictions, newest first. status: None (all), 'open' or 'dismissed'."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            """
            SELECT x.id, x.entity, x.new_chapter_id, nc.chapter_number AS new_chapter_number,
                   x.new_attribute, x.new_value, x.new_quote,
                   x.conflicting_chapter_id, cc.chapter_number AS conflicting_chapter_number,
                   x.conflicting_value, x.conflicting_quote,
                   x.contradiction_type, x.confidence, x.explanation, x.status, x.review_note, x.created_at
            FROM contradictions x
            JOIN chapters nc ON nc.project_id = x.project_id AND nc.id = x.new_chapter_id
            JOIN chapters cc ON cc.project_id = x.project_id AND cc.id = x.conflicting_chapter_id
            WHERE x.project_id = %s AND (%s::text IS NULL OR x.status = %s)
            ORDER BY x.created_at DESC, x.id DESC
            """,
            (project_id, status, status),
        )
        return cur.fetchall()


def set_contradiction_status(project_id: int, contradiction_id: int, status: str) -> bool:
    """Mark a warning 'dismissed' (the writer says it's fine) or 'open' again."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE contradictions SET status = %s WHERE project_id = %s AND id = %s",
                    (status, project_id, contradiction_id))
        return cur.rowcount == 1


# ---------------------------------------------------------------------------
# Facts: manual corrections
# ---------------------------------------------------------------------------
def get_fact(project_id: int, fact_id: int) -> dict | None:
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            """
            SELECT id AS fact_id, chapter_id, entity_id, entity, entity_type, attribute, value,
                   source_quote, confidence
            FROM facts WHERE project_id = %s AND id = %s
            """,
            (project_id, fact_id),
        )
        return cur.fetchone()


def update_fact(project_id: int, fact_id: int, changes: dict) -> dict | None:
    """
    Manually correct a fact (attribute / value / entity_type). The fact is re-embedded
    so search stays accurate, and the change is logged in fact_corrections.
    """
    before = get_fact(project_id, fact_id)
    if before is None:
        return None
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
    return get_fact(project_id, fact_id)


def delete_fact(project_id: int, fact_id: int) -> bool:
    """Remove a wrongly extracted fact (logged in fact_corrections)."""
    before = get_fact(project_id, fact_id)
    if before is None:
        return False
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM facts WHERE project_id = %s AND id = %s", (project_id, fact_id))
        cur.execute(
            "INSERT INTO fact_corrections (project_id, fact_id, action, before) VALUES (%s, %s, 'delete', %s)",
            (project_id, fact_id, json.dumps(before, default=str)),
        )
        _remove_orphan_entities(cur, project_id)
    return True


# ---------------------------------------------------------------------------
# Timeline and search
# ---------------------------------------------------------------------------
def get_timeline(project_id: int) -> list[dict]:
    """Every event fact of the book, in reading order: the raw material for the timeline view."""
    with db() as conn, _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT f.id AS fact_id, f.entity, e.canonical_name, f.attribute, f.value,
                   f.source_quote, f.confidence, f.chapter_id, c.chapter_number
            FROM facts f
            {_CHAPTER_JOIN}
            LEFT JOIN entities e ON e.id = f.entity_id
            WHERE f.project_id = %s AND f.entity_type = 'event'
            ORDER BY c.chapter_number, f.id
            """,
            (project_id,),
        )
        return cur.fetchall()


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
            ORDER BY f.embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vector, project_id, query_vector, top_k),
        )
        return cur.fetchall()


def apply_schema() -> None:
    """Create any missing tables/columns (and upgrade old databases). Safe to run every start."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    with open(path, encoding="utf-8") as f, db() as conn, conn.cursor() as cur:
        cur.execute(f.read())

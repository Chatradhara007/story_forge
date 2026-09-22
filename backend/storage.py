import os
import json
from contextlib import contextmanager
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from models import Fact, Contradiction
from llm import embed_texts

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]


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


def _to_vector(values: list[float]) -> str:
    """Format a list of numbers the way the database's vector type expects: [0.1,0.2,...]"""
    return "[" + ",".join(str(v) for v in values) + "]"


def fact_to_embedding_text(fact: Fact) -> str:
    # Embed a compact sentence describing the fact, not just the raw value —
    # this makes semantic search match on meaning later.
    return f"{fact.entity} {fact.attribute}: {fact.value}. {fact.source_quote}"


def embed_facts(facts: list[Fact]) -> list[list[float]]:
    return embed_texts([fact_to_embedding_text(f) for f in facts], input_type="passage")


def resolve_chapter_number(chapter_id: str, requested: int | None) -> int:
    """
    Work out the reading-order number for a chapter:
    1. use the number you sent, if you sent one;
    2. otherwise keep the number it already had (when re-submitting a chapter);
    3. otherwise put it after the last chapter.
    """
    if requested is not None:
        return requested
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT chapter_number FROM chapters WHERE id = %s", (chapter_id,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("SELECT COALESCE(MAX(chapter_number), 0) + 1 FROM chapters")
        return cur.fetchone()[0]


def save_chapter_results(
    chapter_id: str,
    chapter_number: int,
    text: str,
    facts: list[Fact],
    embeddings: list[list[float]],
    contradictions: list[Contradiction],
    resolutions: dict,
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
            INSERT INTO chapters (id, chapter_number, text)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE
                SET chapter_number = EXCLUDED.chapter_number,
                    text = EXCLUDED.text,
                    updated_at = now()
            """,
            (chapter_id, chapter_number, text),
        )
        # Clear out what this chapter produced last time. Contradictions where this
        # chapter was the "older" side are removed too, because they pointed at text
        # that no longer exists; re-submit later chapters to re-check them.
        cur.execute(
            "DELETE FROM contradictions WHERE new_chapter_id = %s OR conflicting_chapter_id = %s",
            (chapter_id, chapter_id),
        )
        cur.execute("DELETE FROM facts WHERE chapter_id = %s", (chapter_id,))

        # Create one new entity per group of new names (names the AI gave the same
        # canonical_name belong together, e.g. "Elena" + "Elena Vale").
        new_entity_ids: dict[str, int] = {}
        for r in resolutions.values():
            key = r.canonical_name.lower()
            if r.is_new and key not in new_entity_ids:
                cur.execute(
                    "INSERT INTO entities (canonical_name, entity_type) VALUES (%s, %s) RETURNING id",
                    (r.canonical_name, r.entity_type),
                )
                new_entity_ids[key] = cur.fetchone()[0]
                _add_alias(cur, new_entity_ids[key], r.canonical_name)

        def entity_id_for(name: str) -> int:
            r = resolutions[name.lower()]
            return r.existing_entity_id or new_entity_ids[r.canonical_name.lower()]

        # Remember every name used in this chapter, so next time it links instantly.
        for r in resolutions.values():
            _add_alias(cur, entity_id_for(r.name), r.name)

        for fact, embedding in zip(facts, embeddings):
            cur.execute(
                """
                INSERT INTO facts
                    (chapter_id, entity_id, entity, entity_type, attribute, value, source_quote, confidence, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                """,
                (chapter_id, entity_id_for(fact.entity), fact.entity, fact.entity_type, fact.attribute,
                 fact.value, fact.source_quote, fact.confidence, _to_vector(embedding)),
            )

        # Entities left with no facts at all (e.g. after re-submitting a chapter) are removed.
        cur.execute(
            "DELETE FROM entities e WHERE NOT EXISTS (SELECT 1 FROM facts f WHERE f.entity_id = e.id)"
        )

        for c in contradictions:
            cur.execute(
                """
                INSERT INTO contradictions
                    (entity, new_chapter_id, new_attribute, new_value, new_quote,
                     conflicting_chapter_id, conflicting_value, conflicting_quote,
                     contradiction_type, confidence, explanation)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (c.entity, c.new_chapter_id, c.new_attribute, c.new_value, c.new_quote,
                 c.conflicting_chapter_id, c.conflicting_value, c.conflicting_quote,
                 c.contradiction_type, c.confidence, c.explanation),
            )
    return new_entity_ids


def _add_alias(cur, entity_id: int, name: str) -> None:
    """Remember that `name` refers to this entity. A name already taken is left alone."""
    cur.execute(
        """
        INSERT INTO entity_aliases (entity_id, alias, alias_lower)
        VALUES (%s, %s, %s)
        ON CONFLICT (alias_lower) DO NOTHING
        """,
        (entity_id, name, name.lower()),
    )


def find_entities_by_alias(names: list[str]) -> dict[str, tuple[int, str]]:
    """For names we've seen before: {lowercase name: (entity id, canonical name)}."""
    if not names:
        return {}
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.alias_lower, e.id, e.canonical_name
            FROM entity_aliases a JOIN entities e ON e.id = a.entity_id
            WHERE a.alias_lower = ANY(%s)
            """,
            ([n.lower() for n in names],),
        )
        return {row[0]: (row[1], row[2]) for row in cur.fetchall()}


def get_all_entities_with_context(sample_facts: int = 3) -> list[dict]:
    """Every known entity with all its names and a few facts — the AI's evidence for matching."""
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT e.id, e.canonical_name, e.entity_type,
                   COALESCE((SELECT array_agg(a.alias ORDER BY a.alias)
                             FROM entity_aliases a WHERE a.entity_id = e.id), '{}') AS aliases,
                   COALESCE((SELECT array_agg(s.attribute || ': ' || s.value)
                             FROM (SELECT attribute, value FROM facts f
                                   WHERE f.entity_id = e.id ORDER BY f.id LIMIT %s) s), '{}') AS sample_facts
            FROM entities e
            ORDER BY e.id
            """,
            (sample_facts,),
        )
        return cur.fetchall()


def get_facts_for_entity_id(entity_id: int, exclude_chapter_id: str | None = None) -> list[dict]:
    """Everything stored about one entity, under ANY of its names, in reading order."""
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT f.id AS fact_id, f.entity, f.entity_type, f.attribute, f.value, f.source_quote,
                   f.confidence, f.chapter_id, c.chapter_number
            FROM facts f
            JOIN chapters c ON c.id = f.chapter_id
            WHERE f.entity_id = %s
              AND (%s::text IS NULL OR f.chapter_id <> %s)
            ORDER BY c.chapter_number, f.id
            """,
            (entity_id, exclude_chapter_id, exclude_chapter_id),
        )
        return cur.fetchall()


def get_entity(entity_id: int) -> dict | None:
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT e.id, e.canonical_name, e.entity_type,
                   COALESCE((SELECT array_agg(a.alias ORDER BY a.alias)
                             FROM entity_aliases a WHERE a.entity_id = e.id), '{}') AS aliases,
                   (SELECT COUNT(*) FROM facts f WHERE f.entity_id = e.id) AS fact_count
            FROM entities e WHERE e.id = %s
            """,
            (entity_id,),
        )
        return cur.fetchone()


def list_entities() -> list[dict]:
    """Every entity with all its names and how many facts it has."""
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT e.id, e.canonical_name, e.entity_type,
                   COALESCE((SELECT array_agg(a.alias ORDER BY a.alias)
                             FROM entity_aliases a WHERE a.entity_id = e.id), '{}') AS aliases,
                   (SELECT COUNT(*) FROM facts f WHERE f.entity_id = e.id) AS fact_count
            FROM entities e
            ORDER BY e.entity_type, lower(e.canonical_name)
            """
        )
        return cur.fetchall()


def merge_entities(keep_id: int, merge_id: int) -> None:
    """Manual fix for a MISSED link: move everything from merge_id into keep_id."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE facts SET entity_id = %s WHERE entity_id = %s", (keep_id, merge_id))
        cur.execute("UPDATE entity_aliases SET entity_id = %s WHERE entity_id = %s", (keep_id, merge_id))
        cur.execute("DELETE FROM entities WHERE id = %s", (merge_id,))


def detach_alias(entity_id: int, alias: str) -> int:
    """
    Manual fix for a WRONG link: split one name off into its own new entity,
    taking the facts written under that name with it. Returns the new entity's id.
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT entity_type FROM entities WHERE id = %s", (entity_id,))
        entity_type = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO entities (canonical_name, entity_type) VALUES (%s, %s) RETURNING id",
            (alias, entity_type),
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


def list_chapters() -> list[dict]:
    """All submitted chapters in reading order, with how many facts each produced."""
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT c.id AS chapter_id, c.chapter_number, c.created_at, c.updated_at,
                   COUNT(f.id) AS fact_count
            FROM chapters c
            LEFT JOIN facts f ON f.chapter_id = c.id
            GROUP BY c.id
            ORDER BY c.chapter_number, c.id
            """
        )
        return cur.fetchall()


def get_all_contradictions(status: str | None = None) -> list[dict]:
    """All contradictions, newest first. status: None (all), 'open' or 'dismissed'."""
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT x.id, x.entity, x.new_chapter_id, nc.chapter_number AS new_chapter_number,
                   x.new_attribute, x.new_value, x.new_quote,
                   x.conflicting_chapter_id, cc.chapter_number AS conflicting_chapter_number,
                   x.conflicting_value, x.conflicting_quote,
                   x.contradiction_type, x.confidence, x.explanation, x.status, x.created_at
            FROM contradictions x
            JOIN chapters nc ON nc.id = x.new_chapter_id
            JOIN chapters cc ON cc.id = x.conflicting_chapter_id
            WHERE (%s::text IS NULL OR x.status = %s)
            ORDER BY x.created_at DESC, x.id DESC
            """,
            (status, status),
        )
        return cur.fetchall()


def set_contradiction_status(contradiction_id: int, status: str) -> bool:
    """Mark a warning 'dismissed' (the writer says it's fine) or 'open' again."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE contradictions SET status = %s WHERE id = %s", (status, contradiction_id))
        return cur.rowcount == 1


def get_chapter(chapter_id: str) -> dict | None:
    """One chapter with its text and every fact taken from it."""
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id AS chapter_id, chapter_number, text, created_at, updated_at FROM chapters WHERE id = %s",
            (chapter_id,),
        )
        chapter = cur.fetchone()
        if chapter is None:
            return None
        cur.execute(
            """
            SELECT f.id AS fact_id, f.entity, f.entity_id, e.canonical_name, f.entity_type,
                   f.attribute, f.value, f.source_quote, f.confidence
            FROM facts f LEFT JOIN entities e ON e.id = f.entity_id
            WHERE f.chapter_id = %s
            ORDER BY lower(coalesce(e.canonical_name, f.entity)), f.id
            """,
            (chapter_id,),
        )
        chapter["facts"] = cur.fetchall()
        return chapter


def delete_chapter(chapter_id: str) -> bool:
    """Remove a chapter with its facts and warnings; entities left with no facts go too."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM chapters WHERE id = %s", (chapter_id,))
        deleted = cur.rowcount == 1
        cur.execute("DELETE FROM entities e WHERE NOT EXISTS (SELECT 1 FROM facts f WHERE f.entity_id = e.id)")
        return deleted


def get_fact(fact_id: int) -> dict | None:
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id AS fact_id, chapter_id, entity_id, entity, entity_type, attribute, value,
                   source_quote, confidence
            FROM facts WHERE id = %s
            """,
            (fact_id,),
        )
        return cur.fetchone()


def update_fact(fact_id: int, changes: dict) -> dict | None:
    """
    Manually correct a fact (attribute / value / entity_type). The fact is re-embedded
    so search stays accurate, and the change is logged in fact_corrections.
    """
    before = get_fact(fact_id)
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
            WHERE id = %s
            """,
            (after["attribute"], after["value"], after["entity_type"], _to_vector(embedding), fact_id),
        )
        cur.execute(
            "INSERT INTO fact_corrections (fact_id, action, before, after) VALUES (%s, 'edit', %s, %s)",
            (fact_id, json.dumps(before, default=str), json.dumps(changes)),
        )
    return get_fact(fact_id)


def delete_fact(fact_id: int) -> bool:
    """Remove a wrongly extracted fact (logged in fact_corrections)."""
    before = get_fact(fact_id)
    if before is None:
        return False
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM facts WHERE id = %s", (fact_id,))
        cur.execute(
            "INSERT INTO fact_corrections (fact_id, action, before) VALUES (%s, 'delete', %s)",
            (fact_id, json.dumps(before, default=str)),
        )
        cur.execute("DELETE FROM entities e WHERE NOT EXISTS (SELECT 1 FROM facts f WHERE f.entity_id = e.id)")
    return True


def get_timeline() -> list[dict]:
    """Every event fact, in reading order: the raw material for the timeline view."""
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT f.id AS fact_id, f.entity, e.canonical_name, f.attribute, f.value,
                   f.source_quote, f.confidence, f.chapter_id, c.chapter_number
            FROM facts f
            JOIN chapters c ON c.id = f.chapter_id
            LEFT JOIN entities e ON e.id = f.entity_id
            WHERE f.entity_type = 'event'
            ORDER BY c.chapter_number, f.id
            """
        )
        return cur.fetchall()


def apply_schema() -> None:
    """Create any missing tables/columns. Safe to run every time the app starts."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    with open(path, encoding="utf-8") as f, db() as conn, conn.cursor() as cur:
        cur.execute(f.read())


def semantic_search(query_text: str, top_k: int = 5) -> list[dict]:
    """Facts whose meaning is closest to the query, even with different wording."""
    query_vector = _to_vector(embed_texts([query_text], input_type="query")[0])
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT f.entity, e.canonical_name, f.entity_type, f.attribute, f.value, f.source_quote,
                   f.confidence, f.chapter_id, c.chapter_number,
                   1 - (f.embedding <=> %s::vector) AS similarity
            FROM facts f
            JOIN chapters c ON c.id = f.chapter_id
            LEFT JOIN entities e ON e.id = f.entity_id
            ORDER BY f.embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vector, query_vector, top_k),
        )
        return cur.fetchall()

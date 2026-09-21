import os
import psycopg2
import psycopg2.extras
from openai import OpenAI
from models import Fact

nim_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],
)

EMBED_MODEL = "nvidia/nemotron-3-embed-1b"


def get_db_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def embed_text(text: str, input_type: str = "passage") -> list[float]:
    """
    input_type must be "passage" when embedding text to STORE,
    and "query" when embedding text to SEARCH WITH.
    Using the wrong one silently hurts retrieval quality rather than erroring —
    NVIDIA's docs are explicit about this, so don't skip it.
    """
    response = nim_client.embeddings.create(
        input=text,
        model=EMBED_MODEL,
        extra_body={"input_type": input_type, "truncate": "END"},
    )
    return response.data[0].embedding


def store_facts(chapter_id: str, facts: list[Fact]) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    for fact in facts:
        # Embed a compact natural-language version of the fact, not just the raw value —
        # this makes semantic search actually match on meaning later.
        text_for_embedding = f"{fact.entity} {fact.attribute}: {fact.value}. {fact.source_quote}"
        embedding = embed_text(text_for_embedding, input_type="passage")
        cur.execute(
            """
            INSERT INTO facts
                (entity, entity_type, attribute, value, source_quote, confidence, chapter_id, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                fact.entity,
                fact.entity_type,
                fact.attribute,
                fact.value,
                fact.source_quote,
                fact.confidence,
                chapter_id,
                embedding,
            ),
        )
    conn.commit()
    cur.close()
    conn.close()


def get_facts_for_entity(entity: str) -> list[dict]:
    """Exact-ish lookup: everything stored about a named entity, in chapter order."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT entity, entity_type, attribute, value, source_quote, confidence, chapter_id
        FROM facts
        WHERE entity ILIKE %s
        ORDER BY chapter_id
        """,
        (entity,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def store_contradictions(contradictions: list) -> None:
    """contradictions: list[Contradiction] pydantic models."""
    if not contradictions:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    for c in contradictions:
        cur.execute(
            """
            INSERT INTO contradictions
                (entity, new_chapter_id, new_attribute, new_value, new_quote,
                 conflicting_chapter_id, conflicting_value, conflicting_quote,
                 contradiction_type, explanation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                c.entity, c.new_chapter_id, c.new_attribute, c.new_value, c.new_quote,
                c.conflicting_chapter_id, c.conflicting_value, c.conflicting_quote,
                c.contradiction_type, c.explanation,
            ),
        )
    conn.commit()
    cur.close()
    conn.close()


def get_all_contradictions() -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT entity, new_chapter_id, new_attribute, new_value, new_quote,
               conflicting_chapter_id, conflicting_value, conflicting_quote,
               contradiction_type, explanation, created_at
        FROM contradictions
        ORDER BY created_at DESC
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def semantic_search(query_text: str, top_k: int = 5) -> list[dict]:
    """Semantic lookup: facts whose meaning is closest to the query, even with different wording."""
    embedding = embed_text(query_text, input_type="query")
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT entity, entity_type, attribute, value, source_quote, confidence, chapter_id,
               1 - (embedding <=> %s::vector) AS similarity
        FROM facts
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (embedding, embedding, top_k),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

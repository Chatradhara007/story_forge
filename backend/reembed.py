"""
Re-index every stored fact with the current EMBED_MODEL.

Needed once after changing EMBED_MODEL (for example because NVIDIA retired the old
embedding model): vectors from two different models can't be compared, so StoryForge
refuses to save or search until this has run.

    cd backend
    python reembed.py

It works through the facts in batches, so it uses roughly one AI request per 32 facts.
If the new model produces vectors of a different size, the column and the search index
are resized first. Stop the web server while it runs, then start it again afterwards.
"""
import sys
import llm
import storage
from models import Fact

BATCH = 256


def main() -> int:
    storage.apply_schema()
    current = llm.EMBED_MODEL
    print(f"Stored facts were indexed with: {storage.STORED_EMBED_MODEL}")
    print(f"EMBED_MODEL is now:             {current}")
    if storage.STORED_EMBED_MODEL == current and "--force" not in sys.argv:
        print("They match: nothing to do. (Use --force to re-index anyway.)")
        return 0
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM facts")
        total = cur.fetchone()[0]
    print(f"{total} facts to re-index.")

    dim = len(llm.embed_texts(["test"], input_type="passage")[0])
    print(f"The new model gives {dim} numbers per fact (the database holds {storage.EMBED_DIM}).")
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("DROP INDEX IF EXISTS facts_embedding_hnsw")
        if dim != storage.EMBED_DIM:
            cur.execute(f"ALTER TABLE facts ALTER COLUMN embedding TYPE vector({dim}) USING NULL")
        else:
            cur.execute("UPDATE facts SET embedding = NULL")

    done, last_id = 0, 0
    while True:
        with storage.db() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, entity, entity_type, attribute, value, source_quote, confidence "
                        "FROM facts WHERE id > %s ORDER BY id LIMIT %s", (last_id, BATCH))
            rows = cur.fetchall()
        if not rows:
            break
        facts = [Fact(entity=r[1], entity_type=r[2], attribute=r[3], value=r[4], source_quote=r[5],
                      confidence=r[6]) for r in rows]
        vectors = llm.embed_texts([storage.fact_to_embedding_text(f) for f in facts], input_type="passage")
        with storage.db() as conn, conn.cursor() as cur:
            for r, v in zip(rows, vectors):
                cur.execute("UPDATE facts SET embedding = %s::vector WHERE id = %s", (storage._to_vector(v), r[0]))
        done += len(rows)
        last_id = rows[-1][0]
        print(f"  {done} / {total}")

    with storage.db() as conn, conn.cursor() as cur:
        if storage.HALFVEC and dim <= 4000:
            cur.execute(f"CREATE INDEX IF NOT EXISTS facts_embedding_hnsw ON facts "
                        f"USING hnsw ((embedding::halfvec({dim})) halfvec_cosine_ops)")
        elif dim <= 2000:
            cur.execute("CREATE INDEX IF NOT EXISTS facts_embedding_hnsw ON facts USING hnsw (embedding vector_cosine_ops)")
        cur.execute("UPDATE app_settings SET value = %s WHERE key = 'embed_model'", (current,))
    print(f"Done. Every fact now uses {current}. Start the web server again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

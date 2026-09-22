"""
StoryForge evaluation: how many planted mistakes does the system catch?

What it does:
  1. Uses a SEPARATE database (storyforge_eval) so your real story is never touched.
  2. Wipes that database and feeds it the test story in eval/story, chapter by chapter,
     using the real AI (you need NVIDIA_API_KEY in backend/.env).
  3. Compares every warning the system raised with the answer key (ground_truth.json).
  4. Prints a report card and saves it to eval/results/ as Markdown and JSON.

Run it from the project folder:
    python eval/run_eval.py

Scores explained:
  precision = of the warnings it raised, how many were real planted mistakes
  recall    = of the planted mistakes, how many it caught
  F1        = one number combining both (higher is better, 1.0 is perfect)
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND / ".env")


def eval_database_url() -> str:
    main_url = os.environ.get("DATABASE_URL", "postgresql://storyforge:storyforge@localhost:5432/storyforge")
    url = os.environ.get("EVAL_DATABASE_URL")
    if not url:
        parts = urlparse(main_url)
        url = urlunparse(parts._replace(path="/storyforge_eval"))
    if url == main_url:
        sys.exit("EVAL_DATABASE_URL must be different from DATABASE_URL, or your real story would be wiped.")
    return url


def ensure_database_exists(url: str) -> None:
    """Create the eval database the first time, by connecting to the main one."""
    import psycopg2
    try:
        psycopg2.connect(url).close()
        return
    except psycopg2.OperationalError as error:
        if "does not exist" not in str(error):
            raise
    name = urlparse(url).path.lstrip("/")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    conn.close()
    print(f"Created test database '{name}'.")


# ---------------------------------------------------------------- scoring ----
def _text_of(flag: dict) -> str:
    return " ".join(str(flag.get(k, "")) for k in (
        "new_attribute", "new_value", "new_quote", "conflicting_value", "conflicting_quote", "explanation"
    )).lower()


def _matches(flag: dict, item: dict) -> int:
    """How strongly a raised warning matches an answer-key item (0 = not at all)."""
    if flag["new_chapter_id"] != item["chapter"]:
        return 0
    if not any(e in flag["entity"].lower() for e in item["entity_contains"]):
        return 0
    text = _text_of(flag)
    return sum(1 for k in item["keywords"] if k.lower() in text)


def score(flags: list[dict], truth: dict) -> dict:
    planted, decoys = truth["planted"], truth["decoys"]
    caught: dict[str, dict] = {}
    rows = []
    for flag in flags:
        # Pick the planted item this warning matches best (if any).
        best = max(planted, key=lambda item: _matches(flag, item))
        if _matches(flag, best) and best["id"] not in caught:
            caught[best["id"]] = flag
            ok_types = {best["type"], *best.get("also_accept_types", [])}
            rows.append({"verdict": "correct", "id": best["id"], "type_ok": flag["contradiction_type"] in ok_types, "flag": flag})
        elif _matches(flag, best):
            rows.append({"verdict": "duplicate", "id": best["id"], "flag": flag})
        else:
            decoy = next((d for d in decoys if _matches(flag, d)), None)
            rows.append({"verdict": "false alarm", "id": decoy["id"] if decoy else None, "flag": flag})

    tp = sum(r["verdict"] == "correct" for r in rows)
    fp = sum(r["verdict"] == "false alarm" for r in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / len(planted) if planted else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    by_type = {}
    for kind in ("attribute", "status", "timeline"):
        items = [p for p in planted if p["type"] == kind]
        hit = [p for p in items if p["id"] in caught]
        by_type[kind] = {"planted": len(items), "caught": len(hit), "recall": len(hit) / len(items) if items else 0.0}

    return {
        "precision": precision, "recall": recall, "f1": f1,
        "correct": tp, "false_alarms": fp,
        "duplicates": sum(r["verdict"] == "duplicate" for r in rows),
        "type_label_accuracy": (sum(r.get("type_ok", False) for r in rows if r["verdict"] == "correct") / tp) if tp else 0.0,
        "by_type": by_type,
        "missed": [p for p in planted if p["id"] not in caught],
        "decoys_triggered": sorted({r["id"] for r in rows if r["verdict"] == "false alarm" and r["id"]}),
        "rows": rows,
    }


def score_linking(truth: dict, find_entities_by_alias) -> dict:
    """Did the system put different names for one character on one card, and keep different people apart?"""
    results = []
    for group in truth["same_entity"]:
        found = find_entities_by_alias(group)
        ids = {found[n.lower()][0] for n in group if n.lower() in found}
        seen = [n for n in group if n.lower() in found]
        if len(seen) < 2:
            results.append({"check": "same", "names": group, "result": "not testable (names not extracted)"})
        else:
            results.append({"check": "same", "names": seen, "result": "pass" if len(ids) == 1 else "FAIL"})
    for a, b in truth["different_entities"]:
        found = find_entities_by_alias([a, b])
        if a.lower() in found and b.lower() in found:
            same = found[a.lower()][0] == found[b.lower()][0]
            results.append({"check": "different", "names": [a, b], "result": "FAIL" if same else "pass"})
        else:
            results.append({"check": "different", "names": [a, b], "result": "not testable (names not extracted)"})
    return {"checks": results,
            "passed": sum(r["result"] == "pass" for r in results),
            "testable": sum(r["result"] in ("pass", "FAIL") for r in results)}


# ---------------------------------------------------------------- report -----
def pct(x: float) -> str:
    return f"{round(x * 100)}%"


def markdown_report(s: dict, link: dict, meta: dict) -> str:
    lines = [
        f"# StoryForge evaluation — {meta['when']}",
        "",
        f"Chat model: `{meta['chat_model']}` · Embedding model: `{meta['embed_model']}` · Time: {meta['seconds']:.0f}s",
        "",
        "## Contradiction detection",
        "",
        "| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |",
        "|---|---|---|---|---|---|---|",
        f"| {pct(s['precision'])} | {pct(s['recall'])} | {s['f1']:.2f} | {s['correct']} / {s['correct'] + len(s['missed'])} | "
        f"{s['false_alarms']} | {s['duplicates']} | {pct(s['type_label_accuracy'])} |",
        "",
        "| Type | Planted | Caught | Recall |",
        "|---|---|---|---|",
        *[f"| {k} | {v['planted']} | {v['caught']} | {pct(v['recall'])} |" for k, v in s["by_type"].items()],
        "",
        "## Missed mistakes",
        "",
        *([f"- **{m['id']}** ({m['chapter']}): {m['description']}" for m in s["missed"]] or ["None."]),
        "",
        "## Every warning raised",
        "",
        "| Verdict | Answer-key item | Chapter | Entity | Type | Explanation |",
        "|---|---|---|---|---|---|",
        *[f"| {r['verdict']} | {r['id'] or '-'} | {r['flag']['new_chapter_id']} | {r['flag']['entity']} | "
          f"{r['flag']['contradiction_type']} | {str(r['flag']['explanation']).replace('|', '/')} |" for r in s["rows"]],
        "",
        f"Decoys wrongly flagged: {', '.join(s['decoys_triggered']) or 'none'}",
        "",
        "## Name linking",
        "",
        f"{link['passed']} of {link['testable']} testable checks passed.",
        "",
        *[f"- {c['check']}: {', '.join(c['names'])} → {c['result']}" for c in link["checks"]],
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- main -------
def main() -> None:
    url = eval_database_url()
    ensure_database_exists(url)
    os.environ["DATABASE_URL"] = url            # everything below now uses the test database
    os.environ["AUTO_CREATE_SCHEMA"] = "false"

    import main as app_main                          # the backend's main.py
    import storage
    from llm import CHAT_MODEL, EMBED_MODEL

    truth = json.loads((HERE / "ground_truth.json").read_text(encoding="utf-8"))

    storage.apply_schema()
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE contradictions, facts, chapters, entity_aliases, entities, fact_corrections RESTART IDENTITY CASCADE")

    started = time.time()
    for number, chapter_id in enumerate(truth["chapters"], start=1):
        text = (HERE / "story" / f"{chapter_id}.txt").read_text(encoding="utf-8")
        print(f"Chapter {number} ({chapter_id})…", end=" ", flush=True)
        result = app_main.ingest_chapter(app_main.ChapterInput(chapter_id=chapter_id, text=text, chapter_number=number))
        print(f"{len(result.facts)} facts, {len(result.contradictions)} warnings")
    seconds = time.time() - started

    flags = [dict(r) for r in reversed(storage.get_all_contradictions())]  # oldest first
    s = score(flags, truth)
    link = score_linking(truth, storage.find_entities_by_alias)

    meta = {"when": datetime.now().strftime("%Y-%m-%d %H:%M"), "chat_model": CHAT_MODEL,
            "embed_model": EMBED_MODEL, "seconds": seconds}
    report = markdown_report(s, link, meta)

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / f"{stamp}.md").write_text(report, encoding="utf-8")
    (out / f"{stamp}.json").write_text(json.dumps({"meta": meta, "scores": s, "linking": link}, indent=2, default=str), encoding="utf-8")

    print()
    print(f"Precision {pct(s['precision'])}   Recall {pct(s['recall'])}   F1 {s['f1']:.2f}")
    for kind, v in s["by_type"].items():
        print(f"  {kind:<9} caught {v['caught']}/{v['planted']}")
    print(f"False alarms: {s['false_alarms']}   Name-linking checks passed: {link['passed']}/{link['testable']}")
    print(f"Full report: {out / (stamp + '.md')}")


if __name__ == "__main__":
    main()

"""
StoryForge evaluation: how many planted mistakes does the system catch?

What it does:
  1. Uses a SEPARATE database (storyforge_eval) so your real story is never touched.
  2. Wipes that database and feeds it a test story from eval/stories/<name>, chapter by chapter,
     using the real AI (you need NVIDIA_API_KEY in backend/.env).
  3. Compares every warning the system raised with that story's answer key (ground_truth.json).
  4. Prints a report card and saves it to eval/results/ as Markdown and JSON.

Run it from the project folder:
    python eval/run_eval.py                      (the lighthouse story)
    python eval/run_eval.py --story glassmaker   (any folder in eval/stories)
    python eval/run_eval.py --list               (show the available stories)

Scores explained:
  precision = of the warnings it raised, how many were real planted mistakes
  recall    = of the planted mistakes, how many it caught
  F1        = one number combining both (higher is better, 1.0 is perfect)
"""
import hashlib
import json
import os
import re
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
def _has(text: str, keywords: list[str]) -> int:
    """How many keywords start a word in the text (so "whistl" matches "whistling")."""
    import re
    text = text.lower()
    return sum(1 for k in keywords if re.search(r"\b" + re.escape(k.lower()), text))


def _matches(flag: dict, item: dict) -> int:
    """
    How strongly a raised warning matches an answer-key item (0 = not at all).
    Strict on purpose: the warning must come from the right chapter, name the right entity
    (in its entity or quotes), have the NEW detail on its new side and, for planted mistakes,
    the EARLIER detail on its earlier side. The AI's explanation is not used, so a warning
    can't match by accident because its explanation mentions a keyword.
    """
    if flag["new_chapter_id"] != item["chapter"]:
        return 0
    new_side = f"{flag.get('new_attribute', '')} {flag.get('new_value', '')} {flag.get('new_quote', '')}"
    old_side = f"{flag.get('conflicting_value', '')} {flag.get('conflicting_quote', '')}"
    where = f"{flag['entity']} {flag.get('new_quote', '')} {flag.get('conflicting_quote', '')}".lower()
    if not any(e in where for e in item["entity_contains"]):
        return 0
    new_hits = _has(new_side, item["new_keywords"])
    if not new_hits:
        return 0
    if item.get("old_keywords"):
        old_hits = _has(old_side, item["old_keywords"])
        if not old_hits:
            return 0
        return new_hits + old_hits
    return new_hits


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

    # A false alarm with the right chapter, entity and NEW detail for a missed item, whose
    # earlier side is only worded differently from the answer key: worth a look by hand.
    missed_ids = {p["id"] for p in planted if p["id"] not in caught}
    check_by_hand = sorted({p["id"] for p in planted if p["id"] in missed_ids for r in rows
                            if r["verdict"] == "false alarm"
                            and _matches(r["flag"], {**p, "old_keywords": []})})
    # The two levels shown on the website: "Confirmed" (checks done in code) and "Worth a look" (the AI).
    code_sources = {"story clock", "trait check"}
    levels = {}
    for level, is_code in (("Confirmed (code)", True), ("Worth a look (AI)", False)):
        mine = [r for r in rows if (r["flag"].get("source") in code_sources) == is_code]
        l_tp = sum(r["verdict"] == "correct" for r in mine)
        l_fp = sum(r["verdict"] == "false alarm" for r in mine)
        l_p = l_tp / (l_tp + l_fp) if l_tp + l_fp else 0.0
        l_r = l_tp / len(planted) if planted else 0.0
        levels[level] = {"correct": l_tp, "false_alarms": l_fp, "precision": l_p, "recall": l_r,
                         "f1": 2 * l_p * l_r / (l_p + l_r) if l_p + l_r else 0.0}

    return {
        "levels": levels,
        "check_by_hand": check_by_hand,
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


# ------------------------------------------------------------- diagnosis -----
def _mentions(fact: dict, keywords: list[str]) -> bool:
    return bool(_has(f"{fact['attribute']} {fact['value']} {fact['source_quote']}", keywords))


def diagnose(item: dict, facts: list[dict], chapter_order: list[str]) -> dict:
    """
    Work out WHY a planted mistake was missed, from the facts that were stored:
      not read (later)  – the Reader never recorded the detail from the later chapter
      not read (earlier) – the Reader never recorded the original detail
      split             – both were recorded, but filed under different entries
                          (a name-linking problem), so they were never compared
      checker           – both were on the same entry, but the checker didn't flag them
    """
    later_chapter = item["chapter"]
    earlier_chapters = chapter_order[:chapter_order.index(later_chapter)]
    later = [f for f in facts if f["chapter_id"] == later_chapter and _mentions(f, item["new_keywords"])]
    earlier = [f for f in facts if f["chapter_id"] in earlier_chapters and _mentions(f, item["old_keywords"])]

    def show(rows):
        return [f"{r['chapter_id']}: [{r['canonical_name'] or r['entity']}] {r['entity']} | {r['attribute']} | {r['value']}"
                for r in rows[:4]]

    if not later:
        return {"cause": "not read (later)", "detail": f"No fact from {later_chapter} mentions this detail.",
                "evidence": show(earlier)}
    if not earlier:
        return {"cause": "not read (earlier)", "detail": "The original detail from the earlier chapter was never recorded.",
                "evidence": show(later)}
    if not {f["entity_id"] for f in later} & {f["entity_id"] for f in earlier}:
        return {"cause": "split", "detail": "Both details were recorded, but under different entries, so they were never compared.",
                "evidence": show(earlier) + show(later)}
    return {"cause": "checker", "detail": "Both details were on the same entry, but the checker didn't flag them.",
            "evidence": show(earlier) + show(later)}


def load_all_facts(storage) -> list[dict]:
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.chapter_id, f.entity, f.entity_id, e.canonical_name, f.attribute, f.value, f.source_quote
            FROM facts f LEFT JOIN entities e ON e.id = f.entity_id ORDER BY f.id
            """
        )
        columns = [c[0] for c in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------- report -----
def pct(x: float) -> str:
    return f"{round(x * 100)}%"


def markdown_report(s: dict, link: dict, meta: dict) -> str:
    lines = [
        f"# StoryForge evaluation — {meta.get('story', 'lighthouse')} — {meta['when']}",
        "",
        f"Reader: `{meta['chat_model']}` · Judge: `{meta.get('judge_model', meta['chat_model'])}` · "
        f"Embedding model: `{meta['embed_model']}` · Time: {meta['seconds']:.0f}s"
        f" · AI requests per run: {meta.get('ai_requests_per_run', '?')} accepted, {meta.get('refused_per_run', 0)} refused",
        f"Parallel AI calls: {meta.get('parallel_calls', 1)} · Thinking (reading): {meta.get('thinking', 'on')} · "
        f"Thinking (judging): {meta.get('thinking_judging', meta.get('thinking', 'on'))} · "
        f"Temperature: {meta.get('temperature', 'default')} · Reading passage size: {meta.get('passage_chars', 'whole chapter')} characters",
        *(["", f"> **Models switched during the run:** {meta['model_notes']}"] if meta.get("model_notes") else []),
        "",
        "## Where the time went",
        "",
        "| Stage | Seconds (all chapters) |",
        "|---|---|",
        *[f"| {k} | {v:.0f} |" for k, v in meta.get("stage_seconds", {}).items()],
        "",
        "*Checking, story clock and safety net run one after another per chapter; reading and timing run together.*",
        "",
        *time_per_chapter(meta.get("per_chapter", [])),
        "## Contradiction detection",
        "",
        "| Precision | Recall | F1 | Correct | False alarms | Duplicates | Right type label |",
        "|---|---|---|---|---|---|---|",
        f"| {pct(s['precision'])} | {pct(s['recall'])} | {s['f1']:.2f} | {s['correct']} / {s['correct'] + len(s['missed'])} | "
        f"{s['false_alarms']} | {s['duplicates']} | {pct(s['type_label_accuracy'])} |",
        "",
        "By level (as shown on the website):",
        "",
        "| Level | Precision | Recall | F1 | Correct | False alarms |",
        "|---|---|---|---|---|---|",
        *[f"| {name} | {pct(v['precision'])} | {pct(v['recall'])} | {v['f1']:.2f} | {v['correct']} | {v['false_alarms']} |"
          for name, v in s.get("levels", {}).items()],
        "",
        "| Type | Planted | Caught | Recall |",
        "|---|---|---|---|",
        *[f"| {k} | {v['planted']} | {v['caught']} | {pct(v['recall'])} |" for k, v in s["by_type"].items()],
        "",
        "## Missed mistakes",
        "",
        *([f"- **{m['id']}** ({m['chapter']}): {m['description']}" for m in s["missed"]] or ["None."]),
        "",
        "## Why each mistake was missed",
        "",
        "Causes: *not read* = the Reader didn't record the detail; *split* = the details were filed under "
        "different entries (a name-linking problem); *checker* = both were on the same entry but weren't flagged.",
        "",
        *([line for m in s["missed"] for line in (
            [f"- **{m['id']}** → **{m['diagnosis']['cause']}**: {m['diagnosis']['detail']}"]
            + [f"    - {e}" for e in m['diagnosis']['evidence']]
        )] or ["Nothing was missed."]),
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
        *([f"**Check by hand:** {', '.join(s['check_by_hand'])}. A warning counted as a false alarm has the right "
           "chapter, entity and new detail for these items; only its earlier side is worded differently from the "
           "answer key. If it is right, the item was caught.", ""] if s.get("check_by_hand") else []),
        "## What the double-check removed",
        "",
        (f"{s.get('double_check', {}).get('removed', 0)} warnings dismissed: "
         f"{s.get('double_check', {}).get('false_alarms_removed', 0)} were false alarms; real mistakes wrongly removed: "
         f"{', '.join(s.get('double_check', {}).get('real_mistakes_removed', [])) or 'none'}."),
        "",
        *[f"- {n['chapter']} · {n['entity']}: {n['note']}" for n in s.get("double_check", {}).get("notes", [])],
        "",
        "## Name linking",
        "",
        f"{link['passed']} of {link['testable']} testable checks passed.",
        "",
        *[f"- {c['check']}: {', '.join(c['names'])} → {c['result']}" for c in link["checks"]],
        "",
    ]
    return "\n".join(lines)


def time_per_chapter(rows: list[dict]) -> list[str]:
    if not rows:
        return []
    judged = [r["judging"] for r in rows[1:]] or [r["judging"] for r in rows]
    read = [r for r in rows if r["reading"] is not None]
    words = sum(r["words"] for r in rows)
    lines = ["## Time per chapter", "", "| Chapter | Words | Facts | Reading (s) | Judging (s) |", "|---|---|---|---|---|",
             *[f"| {r['chapter']} | {r['words']:,} | {r['facts']} | "
               f"{'saved' if r['reading'] is None else format(r['reading'], '.1f')} | {r['judging']:.1f} |" for r in rows], ""]
    summary = (f"**Judging:** {sum(judged) / len(judged):.0f} s per chapter on average (chapters after the first; "
               f"the first has nothing earlier to compare). {words:,} words in {len(rows)} chapters.")
    if read:
        read_words = sum(r["words"] for r in read)
        summary += f" **Reading:** {sum(r['reading'] for r in read) / max(1, read_words) * 1000:.0f} s per 1,000 words."
    return lines + [summary, ""]


# ------------------------------------------------------------ saved reading --
# The reader's output for a story, saved so that judges can be compared on IDENTICAL facts
# (--judges) and runs can skip reading (--reuse-reading). One entry per (reader model, passage
# size, chapter text). Files from before 12 Oct 2026 (a flat dict of hashes) are still read:
# their newest reading per chapter is used, and chapter timing is detected again (one small
# request per chapter).
CACHE = HERE / "cache"


def _reading_key(reader: str, chapter_id: str, text: str) -> str:
    from extract import READ_PASSAGE_CHARS
    return hashlib.sha1(f"{reader}|{READ_PASSAGE_CHARS}|{chapter_id}|{text}".encode("utf-8")).hexdigest()


def load_readings(story: str) -> dict:
    path = CACHE / f"{story}-reading.json"
    if not path.exists():
        return {"format": 2, "readings": {}, "legacy": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") == 2:
        data.setdefault("legacy", {})
        return data
    legacy = {}
    for value in data.values():                    # oldest first: the newest wins
        if isinstance(value, dict) and value.get("chapter_id"):
            legacy[value["chapter_id"]] = value
    return {"format": 2, "readings": {}, "legacy": legacy}


def save_readings(story: str, data: dict) -> None:
    CACHE.mkdir(exist_ok=True)
    (CACHE / f"{story}-reading.json").write_text(json.dumps(data, indent=1), encoding="utf-8")


def saved_reading(data: dict, reader: str, chapter_id: str, text: str):
    from models import ExtractionResult
    entry = data["readings"].get(_reading_key(reader, chapter_id, text)) or data["legacy"].get(chapter_id)
    if not entry:
        return None
    result = ExtractionResult(chapter_id=chapter_id, facts=entry["facts"], relationships=entry.get("relationships", []))
    return result, entry.get("time_note")


# ---------------------------------------------------------------- main -------
STORIES = HERE / "stories"


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Score StoryForge against a test story with planted mistakes.")
    parser.add_argument("--story", default="lighthouse", help="folder name in eval/stories (default: lighthouse)")
    parser.add_argument("--list", action="store_true", help="list the available stories and exit")
    parser.add_argument("--runs", type=int, default=1,
                        help="run the whole story this many times and report how consistently each mistake is caught")
    parser.add_argument("--reuse-reading", action="store_true",
                        help="use the reading saved in eval/cache (reads and saves it first if there is none): "
                             "only judging is measured")
    parser.add_argument("--judges", default="",
                        help="comma-separated judge models to compare on the SAME saved reading, "
                             "e.g. \"nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3.5-lightning-30b-a3b\"")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    available = sorted(p.name for p in STORIES.iterdir() if (p / "ground_truth.json").exists())
    if args.list:
        print("Available stories: " + ", ".join(available))
        return
    if args.story not in available:
        sys.exit(f"No story called '{args.story}'. Available: {', '.join(available)}")
    story_dir = STORIES / args.story

    url = eval_database_url()
    ensure_database_exists(url)
    os.environ["DATABASE_URL"] = url            # everything below now uses the test database
    os.environ["AUTO_CREATE_SCHEMA"] = "false"

    import main as app_main                          # the backend's main.py
    import storage
    import llm

    truth = json.loads((story_dir / "ground_truth.json").read_text(encoding="utf-8"))
    print(f"Story: {args.story} ({len(truth['chapters'])} chapters, {len(truth['planted'])} planted mistakes, "
          f"{len(truth['decoys'])} traps)")

    from llm import MAX_REQUESTS_PER_MINUTE

    storage.apply_schema()
    if MAX_REQUESTS_PER_MINUTE:
        print(f"Pacing AI requests at up to {MAX_REQUESTS_PER_MINUTE} per minute (MAX_REQUESTS_PER_MINUTE).")

    judges = [j.strip() for j in args.judges.split(",") if j.strip()]
    reuse = args.reuse_reading or bool(judges)
    readings = load_readings(args.story) if reuse else None
    reader = llm.CHAT_MODELS[0]
    if not judges:
        evaluate(args, story_dir, truth, storage, app_main, readings, None)
        return
    print(f"Comparing {len(judges)} judges on the same reading by {reader}.")
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rows = []
    configured = list(llm.JUDGE_MODELS)
    for judge in judges:
        print(f"\n##### Judge: {judge}")
        # Only this judge: if it fails, it is retried patiently instead of handing the
        # judging to a reader model (which would score another model under its name).
        llm.JUDGE_MODELS, llm.JUDGE_FALLS_BACK_TO_READERS = [judge], False
        llm._unhealthy_until.pop(judge, None)
        try:
            summary = evaluate(args, story_dir, truth, storage, app_main, readings, judge, stamp=stamp)
        finally:
            llm.JUDGE_MODELS, llm.JUDGE_FALLS_BACK_TO_READERS = configured, True
        if summary:
            rows.append(summary)
    lines = [f"# Judge comparison: {args.story}, {datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
             f"Reader: `{reader}` (same saved reading for every judge) · Runs per judge: {args.runs}", "",
             "| Judge | Precision | Recall | F1 | False alarms | Judging time | Caught | Check by hand |",
             "|---|---|---|---|---|---|---|---|",
             *[f"| `{r['judge']}` {r['fell_back']} | {pct(r['precision'])} | {pct(r['recall'])} | {r['f1']:.2f} | "
               f"{r['false_alarms']:.1f} | {r['seconds']:.0f}s | {', '.join(r['caught']) or '-'} | "
               f"{', '.join(r['check_by_hand']) or '-'} |" for r in rows], ""]
    path = out / f"{args.story}-judges-{stamp}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"Comparison: {path}")


def evaluate(args, story_dir, truth, storage, app_main, readings, judge, stamp=None):
    """Run the story args.runs times with the current models, write the report, return a summary."""
    import llm
    from llm import AIServiceError, EMBED_MODEL

    def one_run(run_number):
        if args.runs > 1:
            print(f"\n=== Run {run_number} of {args.runs} ===")
        return run_once(story_dir, truth, storage, app_main, readings)

    runs, failed = run_many(max(1, args.runs), one_run, AIServiceError)
    if readings is not None:
        save_readings(args.story, readings)
    if not runs:
        print("No run could finish because the AI service kept failing. Try again later, or lower "
              "MAX_PARALLEL_AI_CALLS / set MAX_REQUESTS_PER_MINUTE in backend/.env.")
        if judge is None:
            sys.exit(1)
        return None

    from llm import MAX_PARALLEL_AI_CALLS, THINKING_MODE, JUDGING_THINKING_MODE, TEMPERATURE, JUDGE_TEMPERATURE
    from extract import READ_PASSAGE_CHARS
    status = llm.model_status()
    meta = {"story": args.story, "when": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "chat_model": status["reader"] or llm.CHAT_MODELS[0], "judge_model": status["judge"] or "-",
            "embed_model": EMBED_MODEL, "runs": len(runs), "per_chapter": runs[-1].get("per_chapter", []),
            "model_notes": " ".join(status["notes"]),
            "seconds": sum(r["seconds"] for r in runs) / len(runs),
            "ai_requests_per_run": round(sum(r.get("requests", 0) - r.get("refused", 0) for r in runs) / len(runs)),
            "refused_per_run": round(sum(r.get("refused", 0) for r in runs) / len(runs)),
            "stage_seconds": {k: round(sum(r["stage_seconds"].get(k, 0) for r in runs) / len(runs), 1)
                              for k in runs[-1]["stage_seconds"]},
            "failed_runs": failed,
            "parallel_calls": MAX_PARALLEL_AI_CALLS, "thinking": THINKING_MODE,
            "thinking_judging": JUDGING_THINKING_MODE,
            "temperature": f"reader {TEMPERATURE}, judge {JUDGE_TEMPERATURE}",
            "passage_chars": READ_PASSAGE_CHARS}
    last = runs[-1]
    report = markdown_report(last["scores"], last["linking"], meta)
    if failed:
        report = ("> **Note:** " + ", ".join(f"run {n}" for n, _ in failed) + " could not finish because the AI "
                  "service kept failing; the results below use the runs that finished.\n\n" + report)
    if len(runs) > 1:
        report = consistency_report(runs, truth) + "\n\n---\n\n# Details of the last run\n\n" + report

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    when = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    stamp = (f"{args.story}-judge-{re.sub(r'[^A-Za-z0-9.-]+', '_', judge)}-{when}" if judge
             else f"{args.story}-{when}")
    (out / f"{stamp}.md").write_text(report, encoding="utf-8")
    (out / f"{stamp}.json").write_text(json.dumps({"meta": meta, "runs": runs}, indent=2, default=str), encoding="utf-8")

    print()
    for i, r in enumerate(runs, start=1):
        sc = r["scores"]
        prefix = f"Run {i}: " if len(runs) > 1 else ""
        print(f"{prefix}Precision {pct(sc['precision'])}   Recall {pct(sc['recall'])}   F1 {sc['f1']:.2f}   "
              f"False alarms {sc['false_alarms']}   Time {r['seconds']:.0f}s   "
              f"AI requests {r.get('requests', 0) - r.get('refused', 0)} accepted, {r.get('refused', 0)} refused")
        for level, v in sc.get("levels", {}).items():
            print(f"{' ' * len(prefix)}  {level}: precision {pct(v['precision'])}, recall {pct(v['recall'])}, "
                  f"F1 {v['f1']:.2f} ({v['correct']} correct, {v['false_alarms']} false alarms)")
        dc = sc.get("double_check", {})
        print(f"{' ' * len(prefix)}Double-check removed {dc.get('removed', 0)} warnings: "
              f"{dc.get('false_alarms_removed', 0)} false alarms, "
              f"{len(dc.get('real_mistakes_removed', []))} real mistakes {dc.get('real_mistakes_removed', [])}")
    if failed:
        print(f"Runs that could not finish: {', '.join(str(n) for n, _ in failed)}")
    if len(runs) > 1:
        caught = catch_counts(runs, truth)
        always = [k for k, v in caught.items() if v == len(runs)]
        never = [k for k, v in caught.items() if v == 0]
        print(f"Caught every run: {len(always)}/{len(truth['planted'])}   Never caught: {', '.join(never) or 'none'}")
    else:
        for missed in last["scores"]["missed"]:
            print(f"  missed {missed['id']}: {missed['diagnosis']['cause']}")
    print(f"Full report: {out / (stamp + '.md')}")
    n = len(runs)
    avg = lambda key: sum(r["scores"][key] for r in runs) / n
    caught = catch_counts(runs, truth)
    used_judge = meta["judge_model"]
    return {"judge": judge or used_judge, "precision": avg("precision"), "recall": avg("recall"), "f1": avg("f1"),
            "false_alarms": avg("false_alarms"), "seconds": sum(r["seconds"] for r in runs) / n,
            "caught": [k for k, v in caught.items() if v], "check_by_hand": last["scores"].get("check_by_hand", []),
            "fell_back": f" (fell back to {used_judge})" if judge and used_judge != judge else ""}


def run_many(count: int, one_run, error_type) -> tuple[list, list]:
    """
    Do `count` runs. If one run fails because the AI service keeps erroring, note it and
    carry on with the next run, instead of losing every run's results.
    """
    runs, failed = [], []
    for run_number in range(1, count + 1):
        try:
            runs.append(one_run(run_number))
        except error_type as error:
            print(f"\nRun {run_number} could not finish: {error}\nContinuing with the next run.", flush=True)
            failed.append((run_number, str(error)))
    return runs, failed


def run_once(story_dir: Path, truth: dict, storage, app_main, readings: dict | None = None) -> dict:
    """Wipe the test database, feed in every chapter, and score the result."""
    import pipeline
    import llm
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE contradictions, facts, chapters, entity_aliases, entities, projects, "
                    "fact_corrections, warning_decisions, jobs RESTART IDENTITY CASCADE")
    project_id = storage.create_project(f"Evaluation: {story_dir.name}")["id"]
    requests_before, refused_before = llm.request_count, llm.refused_count
    started = time.time()
    stage_totals: dict[str, float] = {}
    per_chapter = []
    reader = llm.CHAT_MODELS[0]
    for number, chapter_id in enumerate(truth["chapters"], start=1):
        text = (story_dir / f"{chapter_id}.txt").read_text(encoding="utf-8")
        print(f"Chapter {number} ({chapter_id})…", end=" ", flush=True)
        t0 = time.time()
        saved = saved_reading(readings, reader, chapter_id, text) if readings is not None else None
        # chapters go in order: nothing to re-check
        result, _later = pipeline.ingest(project_id, chapter_id, text, number, reading=saved)
        key = _reading_key(reader, chapter_id, text)
        if readings is not None and key not in readings["readings"]:   # new, or from an old-format file
            readings["readings"][key] = {
                "chapter_id": chapter_id, "time_note": result.time_note,
                "facts": [f.model_dump() for f in result.facts],
                "relationships": [r.model_dump() for r in result.relationships]}
        for stage, secs in result.timings_seconds.items():
            stage_totals[stage] = stage_totals.get(stage, 0) + secs
        reading_secs = result.timings_seconds.get("reading facts", 0.0)
        per_chapter.append({"chapter": chapter_id, "words": len(text.split()), "facts": len(result.facts),
                            "reading": None if saved is not None else reading_secs,
                            "judging": max(0.0, time.time() - t0 - (0 if saved is not None else reading_secs))})
        print(f"{len(result.facts)} facts, {len(result.contradictions)} warnings, {time.time() - t0:.0f}s")
    # Score what the writer would see: OPEN warnings. Separately, check what the automatic
    # double-check dismissed: real mistakes it wrongly removed, and false alarms it removed.
    flags = [dict(r) for r in reversed(storage.get_all_contradictions(project_id, "open"))]  # oldest first
    s = score(flags, truth)
    removed = [dict(r) for r in reversed(storage.get_all_contradictions(project_id, "dismissed"))]
    removed_scores = score(removed, truth)
    s["double_check"] = {
        "removed": len(removed),
        "real_mistakes_removed": sorted({row["id"] for row in removed_scores["rows"] if row["verdict"] == "correct"}
                                        - {row["id"] for row in s["rows"] if row["verdict"] == "correct"}),
        "false_alarms_removed": removed_scores["false_alarms"],
        "notes": [{"entity": r["entity"], "chapter": r["new_chapter_id"], "note": r.get("review_note")} for r in removed],
    }
    all_facts = load_all_facts(storage)
    for missed in s["missed"]:
        missed["diagnosis"] = diagnose(missed, all_facts, truth["chapters"])
    return {"seconds": time.time() - started, "stage_seconds": stage_totals, "scores": s, "per_chapter": per_chapter,
            "requests": llm.request_count - requests_before,
            "refused": llm.refused_count - refused_before,
            "linking": score_linking(truth, lambda names: storage.find_entities_by_alias(project_id, names))}


def catch_counts(runs: list[dict], truth: dict) -> dict[str, int]:
    """How many runs caught each planted mistake."""
    return {p["id"]: sum(1 for r in runs if p["id"] not in {m["id"] for m in r["scores"]["missed"]})
            for p in truth["planted"]}


def consistency_report(runs: list[dict], truth: dict) -> str:
    n = len(runs)
    caught = catch_counts(runs, truth)
    decoy_hits = {d["id"]: sum(1 for r in runs if d["id"] in r["scores"]["decoys_triggered"]) for d in truth["decoys"]}
    avg = lambda key: sum(r["scores"][key] for r in runs) / n
    lines = [
        f"# Consistency over {n} runs",
        "",
        f"Average precision {pct(avg('precision'))} · average recall {pct(avg('recall'))} · average F1 {avg('f1'):.2f} · "
        f"average false alarms {avg('false_alarms'):.1f} · average time {sum(r['seconds'] for r in runs) / n:.0f}s",
        "",
        "| Run | Precision | Recall | F1 | False alarms | Time | AI requests |",
        "|---|---|---|---|---|---|---|",
        *[f"| {i} | {pct(r['scores']['precision'])} | {pct(r['scores']['recall'])} | {r['scores']['f1']:.2f} | "
          f"{r['scores']['false_alarms']} | {r['seconds']:.0f}s | {r.get('requests', 0) - r.get('refused', 0)} "
          f"(+{r.get('refused', 0)} refused) |"
          for i, r in enumerate(runs, start=1)],
        "",
        "## How often each planted mistake was caught",
        "",
        "| Mistake | Type | Caught | Why missed (per run) | Description |",
        "|---|---|---|---|---|",
    ]
    for p in truth["planted"]:
        causes = [next((m["diagnosis"]["cause"] for m in r["scores"]["missed"] if m["id"] == p["id"]), "✓") for r in runs]
        mark = "always" if caught[p["id"]] == n else ("never" if caught[p["id"]] == 0 else "sometimes")
        lines.append(f"| {p['id']} | {p['type']} | {caught[p['id']]}/{n} ({mark}) | {', '.join(causes)} | {p['description']} |")
    lines += ["", "## Traps wrongly flagged", "",
              *([f"- {d['id']}: flagged in {decoy_hits[d['id']]}/{n} runs: {d['description']}"
                 for d in truth["decoys"] if decoy_hits[d["id"]]] or ["None, in any run."])]
    return "\n".join(lines)

if __name__ == "__main__":
    main()

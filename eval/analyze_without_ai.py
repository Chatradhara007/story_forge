"""
Replay the "lasting facts only" filter over the warnings of the LAST evaluation run, with NO AI
requests (free). It reads the evaluation database as the last run left it (even an interrupted
run) and shows, for every warning raised:
  - whether it was a real mistake or a false alarm (scored against the answer key),
  - whether its EARLIER fact is a lasting one (kept as evidence) or a passing one (no longer
    compared, so the warning would not be raised).

    cd eval
    python analyze_without_ai.py --story fallenking

A good filter removes many false alarms and no real mistakes.
"""
import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
spec = importlib.util.spec_from_file_location("run_eval", HERE / "run_eval.py")
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--story", default="fallenking")
    args = parser.parse_args()
    import json
    import os
    os.environ["DATABASE_URL"] = run_eval.eval_database_url()
    import storage
    from lasting import is_lasting
    truth = json.loads((HERE / "stories" / args.story / "ground_truth.json").read_text(encoding="utf-8"))

    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute("SELECT id FROM projects ORDER BY id DESC LIMIT 1")
        project = cur.fetchone()
        if project is None:
            sys.exit("The evaluation database is empty: run an evaluation first.")
        cur.execute("""SELECT x.*, f.attribute AS conflicting_attribute
                       FROM contradictions x LEFT JOIN facts f ON f.id = x.conflicting_fact_id
                       WHERE x.project_id = %s AND x.status = 'open' ORDER BY x.id""", (project["id"],))
        warnings = [dict(r) for r in cur.fetchall()]
        cur.execute("""SELECT c.id AS chapter_id, c.chapter_number, COUNT(f.id) AS facts,
                              COUNT(f.id) FILTER (WHERE TRUE) AS total
                       FROM chapters c LEFT JOIN facts f ON f.project_id = c.project_id AND f.chapter_id = c.id
                       WHERE c.project_id = %s GROUP BY c.id, c.chapter_number ORDER BY c.chapter_number""",
                    (project["id"],))
        chapters = cur.fetchall()
        cur.execute("SELECT chapter_id, attribute, value FROM facts WHERE project_id = %s", (project["id"],))
        facts = cur.fetchall()

    if not warnings:
        sys.exit("No warnings in the last run to analyse.")
    for w in warnings:
        w.setdefault("new_chapter_number", None)
    scored = run_eval.score([{**w, "new_chapter_id": w["new_chapter_id"]} for w in warnings], truth)
    lasting_by_id = {w["id"]: is_lasting(w.get("conflicting_attribute") or "", w["conflicting_value"] or "")
                     for w in warnings}

    kept = {"correct": 0, "false alarm": 0, "duplicate": 0}
    gone = {"correct": 0, "false alarm": 0, "duplicate": 0}
    lines = [f"# Replaying 'lasting facts only' on the last {args.story} run (no AI requests)", "",
             "| Verdict | Item | Chapter | Entity | Earlier fact | Lasting? |", "|---|---|---|---|---|---|"]
    lost_real = []
    for row, w in zip(scored["rows"], warnings):
        verdict = row["verdict"].split(" (")[0]
        keep = lasting_by_id[w["id"]] or w.get("source") == "story clock"
        (kept if keep else gone)[verdict if verdict in kept else "false alarm"] += 1
        if verdict == "correct" and not keep:
            lost_real.append(row["id"])
        lines.append(f"| {row['verdict']} | {row['id'] or '-'} | {w['new_chapter_id']} | {w['entity']} | "
                     f"{w.get('conflicting_attribute') or '?'}: {(w['conflicting_value'] or '')[:60]} | "
                     f"{'yes' if keep else 'no: not compared any more'} |")

    passing_facts = sum(1 for f in facts if not is_lasting(f["attribute"], f["value"]))
    summary = [
        "", "## Summary", "",
        f"- Chapters in the run: {len(chapters)}; facts: {len(facts)}, of which {passing_facts} "
        f"({passing_facts / max(1, len(facts)):.0%}) are passing and no longer used as evidence.",
        f"- False alarms: {kept['false alarm'] + gone['false alarm']} raised, "
        f"**{gone['false alarm']} would not be raised** any more.",
        f"- Real mistakes caught: {kept['correct'] + gone['correct']}, "
        f"**{gone['correct']} would be lost**{(': ' + ', '.join(lost_real)) if lost_real else ''}.",
    ]
    report = "\n".join(lines + summary) + "\n"
    out = HERE / "results" / f"{args.story}-replay-lasting.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print("\n".join(summary))
    print(f"\nFull table: {out}")


if __name__ == "__main__":
    main()

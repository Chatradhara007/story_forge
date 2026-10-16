"""
Stage-by-stage evaluation, in seconds and with NO AI requests (free).

The full evaluation (run_eval.py) takes ~15 minutes, varies between runs, and only says
"caught" or "missed". This one replays a SAVED reading of a story (eval/cache/<story>-reading.json,
written by an earlier full run) through everything that is done in code, and tells you for
every planted mistake which stage loses it:

  read      did the Reader record the NEW detail, and the EARLIER one?       (from the saved reading)
  linked    are both on the same entry?                                       (name rules, or the answer key)
  rules     did the checks done in code (story clock, fixed traits) flag it?  (no AI)

Name linking is replayed two ways:
  rules  only the name rules in entities.py (no AI): a lower bound on linking;
  gold   the answer key's same_entity groups on top: what perfect linking would give.
The gap between the two is what the AI linker has to close.

    python eval/stage_eval.py --story lighthouse
    python eval/stage_eval.py --all
    python eval/stage_eval.py --story glassmaker --reading path/to/other-reading.json

Change a code check, re-run this, and see the effect on every story at once. Only changes to
the Reader or the AI checker need the full (slow, paid) evaluation.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
STORIES = HERE / "stories"
CACHE = HERE / "cache"


def _load_run_eval():
    spec = importlib.util.spec_from_file_location("run_eval", HERE / "run_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_eval = _load_run_eval()
from models import Fact                     # noqa: E402
import storyclock                           # noqa: E402
import storytime                            # noqa: E402
import traits                               # noqa: E402
from entities import _name_rule_match, _title_surname_match   # noqa: E402
try:
    from extract import timing_from_opening   # noqa: E402  (the pipeline's own opening-words timing)
except ImportError:                            # older code
    def timing_from_opening(text):
        return None


# ----------------------------------------------------------- saved reading --
def load_reading(story: str, chapters: list[str], path: Path | None = None) -> tuple[dict, list[str | None]]:
    """
    The latest saved reading of each chapter, and the timing note saved with it.
    Reads both cache formats: format 2 ({"format": 2, "readings": {key: {chapter_id, facts,
    relationships, time_note}}, "legacy": {...}}, written by run_eval.py --reuse-reading), and the
    older flat file (readings and timing notes as separate entries, in the order they were saved).
    """
    path = path or CACHE / f"{story}-reading.json"
    if not path.exists():
        sys.exit(f"No saved reading at {path}. Run the full evaluation once with --reuse-reading to create it.")
    data = json.loads(path.read_text(encoding="utf-8"))
    readings: dict = {}
    notes_by_chapter: dict = {}
    if data.get("format") == 2:
        for entry in list((data.get("legacy") or {}).values()) + list((data.get("readings") or {}).values()):
            if isinstance(entry, dict) and entry.get("chapter_id") in chapters:
                readings[entry["chapter_id"]] = entry               # later entries win
                if entry.get("time_note"):
                    notes_by_chapter[entry["chapter_id"]] = entry["time_note"]
        notes = [notes_by_chapter.get(c) for c in chapters]
    else:
        entries = list(data.values())
        for entry in entries:
            if isinstance(entry, dict) and entry.get("chapter_id") in chapters:
                readings[entry["chapter_id"]] = entry
        flat = [e for e in entries if isinstance(e, str)]
        notes = flat[-len(chapters):] if len(flat) >= len(chapters) else flat + [None] * (len(chapters) - len(flat))
    missing = [c for c in chapters if c not in readings]
    if missing:
        sys.exit(f"The saved reading has no facts for {', '.join(missing)}.")
    return readings, notes


# --------------------------------------------------------------- linking ----
class Linker:
    """Replays name linking without the AI: exact names, then the name rules; optionally the answer key."""

    def __init__(self, gold_groups: list[list[str]] | None = None):
        self.entities: list[dict] = []          # {"id", "canonical_name", "aliases", "entity_type"}
        self.by_name: dict[str, int] = {}
        self.gold = {}
        for i, group in enumerate(gold_groups or []):
            for name in group:
                self.gold[name.lower()] = i

    def link(self, name: str, entity_type: str) -> tuple[int, str]:
        key = name.lower()
        if key in self.by_name:
            entity = self.entities[self.by_name[key]]
            return entity["id"], entity["canonical_name"]
        match = None
        if key in self.gold:
            group = self.gold[key]
            match = next((e for e in self.entities
                          if any(self.gold.get(a.lower()) == group for a in [e["canonical_name"], *e["aliases"]])), None)
        if match is None:
            match = _name_rule_match(name, entity_type, self.entities) or _title_surname_match(name, entity_type, self.entities)
        if match is None:
            match = {"id": len(self.entities), "canonical_name": name, "aliases": [], "entity_type": entity_type}
            self.entities.append(match)
        else:
            match["aliases"].append(name)
        self.by_name[key] = match["id"]
        return match["id"], match["canonical_name"]

    def find(self, name: str) -> int | None:
        return self.by_name.get(name.lower())


# ------------------------------------------------------------------ replay --
def replay(story: str, linking: str, reading_path: Path | None = None) -> dict:
    story_dir = STORIES / story
    truth = json.loads((story_dir / "ground_truth.json").read_text(encoding="utf-8"))
    chapters = truth["chapters"]
    readings, notes = load_reading(story, chapters, reading_path)
    linker = Linker(truth.get("same_entity") if linking == "gold" else None)
    texts = {c: (story_dir / f"{c}.txt").read_text(encoding="utf-8") for c in chapters}

    stored: list[dict] = []           # every fact so far, as the database would hold it
    time_notes: list[dict] = []
    flags: list[dict] = []
    for number, chapter_id in enumerate(chapters, start=1):
        facts = [Fact(**f) for f in readings[chapter_id]["facts"]]
        new = []
        for index, fact in enumerate(facts):
            entity_id, canonical = linker.link(fact.entity, fact.entity_type)
            new.append((entity_id, canonical, fact, index))

        def earlier_facts_for(entity_id, before=number):
            return [f for f in stored if f["entity_id"] == entity_id and f["chapter_number"] < before]

        # As the pipeline does it: the opening's own timing, else the saved (AI) note.
        note = timing_from_opening(texts[chapter_id]) or notes[number - 1]
        known = [x for x in new if any(s["entity_id"] == x[0] for s in stored)]
        found = storyclock.check_ages(chapter_id, number, known, earlier_facts_for, time_notes, note, texts[chapter_id])
        for extra in ("check_weekdays", "check_after_death"):           # the clock's other checks, if present
            if hasattr(storyclock, extra):
                found += getattr(storyclock, extra)(chapter_id, number, known, earlier_facts_for, note)
        found += traits.check_traits(chapter_id, number, new, earlier_facts_for, linker.find)
        one_per_fact = {}
        for c in found:
            one_per_fact.setdefault(c.new_fact_index, c)
        found = list(one_per_fact.values())
        flags += [c.model_dump() for c in found]
        for entity_id, canonical, fact, index in new:
            stored.append({"fact_id": len(stored) + 1, "chapter_id": chapter_id, "chapter_number": number,
                           "entity_id": entity_id, "canonical_name": canonical, "entity": fact.entity,
                           "attribute": fact.attribute, "value": fact.value, "source_quote": fact.source_quote})
        time_notes.append({"chapter_id": chapter_id, "chapter_number": number, "time_note": note,
                           "opening": texts[chapter_id][:600]})

    scores = run_eval.score(flags, truth)
    caught = {r["id"] for r in scores["rows"] if r["verdict"] == "correct"}
    stages = {}
    for item in truth["planted"]:
        later_index = chapters.index(item["chapter"])
        later = [f for f in stored if f["chapter_id"] == item["chapter"] and run_eval._mentions(f, item["new_keywords"])]
        earlier = [f for f in stored if chapters.index(f["chapter_id"]) < later_index
                   and run_eval._mentions(f, item.get("old_keywords") or item["new_keywords"])]
        same = bool({f["entity_id"] for f in later} & {f["entity_id"] for f in earlier})
        stages[item["id"]] = {"read_new": bool(later), "read_old": bool(earlier), "linked": same,
                              "rules": item["id"] in caught}
    positions = storytime.chapter_positions(time_notes)
    return {"story": story, "linking": linking, "scores": scores, "stages": stages, "truth": truth,
            "timeline": {chapters[n - 1]: ("flashback, " if p.flashback else "") + storytime.describe(p)
                         + f" ({p.source}: {p.phrase})" for n, p in positions.items()}}


# ------------------------------------------------------------------ report --
def _mark(ok: bool) -> str:
    return "yes" if ok else "**no**"


def report(results: list[dict]) -> str:
    lines = ["# Stage-by-stage evaluation (no AI)", ""]
    for result in results:
        rules_only, gold = result["rules"], result["gold"]
        truth = rules_only["truth"]
        lines += [f"## {rules_only['story']}", "",
                  "| Mistake | Read (new) | Read (earlier) | Same entry: name rules | Same entry: answer key | "
                  "Caught by code checks (rules / key) | Description |",
                  "|---|---|---|---|---|---|---|"]
        for item in truth["planted"]:
            r, g = rules_only["stages"][item["id"]], gold["stages"][item["id"]]
            lines.append(f"| {item['id']} | {_mark(r['read_new'])} | {_mark(r['read_old'])} | {_mark(r['linked'])} | "
                         f"{_mark(g['linked'])} | {'yes' if r['rules'] else '-'} / {'yes' if g['rules'] else '-'} | "
                         f"{item['description']} |")
        n = len(truth["planted"])
        both_read = sum(s["read_new"] and s["read_old"] for s in gold["stages"].values())
        lines += ["",
                  f"- **Reader:** both sides recorded for {both_read}/{n} mistakes.",
                  f"- **Name rules:** both sides on one entry for "
                  f"{sum(s['linked'] for s in rules_only['stages'].values())}/{n} (answer key: "
                  f"{sum(s['linked'] for s in gold['stages'].values())}/{n}).",
                  f"- **Code checks:** caught {rules_only['scores']['correct']} with name rules, "
                  f"{gold['scores']['correct']} with the answer key's linking; false alarms "
                  f"{rules_only['scores']['false_alarms']} / {gold['scores']['false_alarms']}.", ""]
        alarms = [row for row in gold["scores"]["rows"] if row["verdict"] == "false alarm"]
        if alarms:
            lines += ["False alarms from code checks (answer-key linking):", ""]
            for row in alarms:
                f = row["flag"]
                trap = f" (trap {row['id']})" if row["id"] else ""
                lines.append(f"- {f['new_chapter_id']} {f['entity']}{trap}: {f['explanation']}")
            lines.append("")
        lines += ["Story clock positions:", ""] + [f"- {c}: {t}" for c, t in gold["timeline"].items()] + [""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score each stage from a saved reading, with no AI requests.")
    parser.add_argument("--story", default="lighthouse")
    parser.add_argument("--all", action="store_true", help="every story with a saved reading")
    parser.add_argument("--reading", type=Path, help="a different saved reading file")
    parser.add_argument("--save", action="store_true", help="also save the report to eval/results/")
    args = parser.parse_args()
    stories = ([p.name for p in sorted(STORIES.iterdir()) if (CACHE / f"{p.name}-reading.json").exists()]
               if args.all else [args.story])
    results = [{"rules": replay(s, "rules", args.reading), "gold": replay(s, "gold", args.reading)} for s in stories]
    text = report(results)
    print(text)
    if args.save:
        from datetime import datetime
        out = HERE / "results" / f"stages-{'all' if args.all else args.story}-{datetime.now():%Y%m%d-%H%M%S}.md"
        out.write_text(text, encoding="utf-8")
        print(f"Saved: {out}")


if __name__ == "__main__":
    main()

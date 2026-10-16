"""
Try every model configuration on the saved readings and rank them. Run it on your own computer
(it uses your NVIDIA key and quota); leave it running, e.g. overnight.

    python eval/sweep.py                          # the default grid, Fallen King + Glassmaker
    python eval/sweep.py --stories fallenking     # one story (faster)
    python eval/sweep.py --quick                  # 3 configurations only
    python eval/sweep.py --report                 # just print the ranking of runs already done

Every configuration judges the SAME saved facts (--reuse-reading), so differences come from the
settings, not from reading. Each finished run is saved to eval/results/sweep.json straight away:
if the sweep stops (quota, a crash, you close the window) run it again and it skips what's done.

What is varied (each a setting in backend/.env):
  JUDGE_MODEL            which model links names, checks and double-checks
  CHECKER                on = the AI checker runs too; off = only the checks done in code
  SAFETY_NET             on/off: AI comparisons across different entries
  CHAT_THINKING_JUDGING  off/low: does the judge "think" first (slower; some models crash)

Ranking: F1 over all stories (precision and recall together), then false alarms, then time.
The "Confirmed" columns are the code checks alone; they barely depend on the AI settings.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
STATE = RESULTS / "sweep.json"

LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
NANO = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"

JUDGES = {"lightning": LIGHTNING, "ultra": f"{ULTRA},{LIGHTNING}", "nano": NANO}


def grid(quick: bool) -> list[dict]:
    if quick:
        return [
            {"name": "code checks only (lightning links names)", "JUDGE_MODEL": LIGHTNING, "CHECKER": "off",
             "SAFETY_NET": "off", "CHAT_THINKING_JUDGING": "off"},
            {"name": "lightning checker", "JUDGE_MODEL": LIGHTNING, "CHECKER": "on", "SAFETY_NET": "off",
             "CHAT_THINKING_JUDGING": "off"},
            {"name": "ultra checker", "JUDGE_MODEL": JUDGES["ultra"], "CHECKER": "on", "SAFETY_NET": "off",
             "CHAT_THINKING_JUDGING": "off"},
        ]
    configs = []
    for judge, checker, safety, thinking in itertools.product(JUDGES, ("off", "on"), ("off", "on"), ("off", "low")):
        if checker == "off" and safety == "on":
            continue                      # the safety net is AI checking too; pointless without the checker
        if judge == "ultra" and thinking == "low":
            continue                      # Ultra crashes (500 errors) when asked to think
        if checker == "off" and thinking == "low":
            continue                      # thinking only matters for checking
        configs.append({"name": f"{judge} · checker {checker} · safety net {safety} · thinking {thinking}",
                        "JUDGE_MODEL": JUDGES[judge], "CHECKER": checker, "SAFETY_NET": safety,
                        "CHAT_THINKING_JUDGING": thinking})
    return configs


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"runs": []}


def save_state(state: dict) -> None:
    RESULTS.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def run_one(config: dict, story: str) -> dict:
    env = {**os.environ, **{k: v for k, v in config.items() if k != "name"}}
    started = time.time()
    before = {p.name for p in RESULTS.glob(f"{story}-*.json")} if RESULTS.exists() else set()
    print(f"\n=== {config['name']}  —  {story} ===", flush=True)
    process = subprocess.run([sys.executable, str(HERE / "run_eval.py"), "--story", story, "--reuse-reading"],
                             env=env, cwd=str(HERE.parent))
    new = sorted((p for p in RESULTS.glob(f"{story}-*.json") if p.name not in before), key=lambda p: p.stat().st_mtime)
    if process.returncode != 0 or not new:
        return {"config": config["name"], "story": story, "failed": True, "seconds": time.time() - started}
    data = json.loads(new[-1].read_text(encoding="utf-8"))
    run = data["runs"][-1]
    s = run["scores"]
    return {"config": config["name"], "settings": {k: v for k, v in config.items() if k != "name"},
            "story": story, "failed": False, "file": new[-1].name,
            "planted": s["correct"] + len(s["missed"]), "correct": s["correct"], "false_alarms": s["false_alarms"],
            "levels": s.get("levels", {}), "seconds": run["seconds"], "requests": run.get("requests", 0),
            "judge_used": data["meta"].get("judge_model"), "model_notes": data["meta"].get("model_notes")}


def _f1(correct: int, false_alarms: int, planted: int) -> tuple[float, float, float]:
    p = correct / (correct + false_alarms) if correct + false_alarms else 0.0
    r = correct / planted if planted else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def report(state: dict, stories: list[str]) -> str:
    by_config: dict[str, list[dict]] = {}
    for r in state["runs"]:
        if r["story"] in stories:
            by_config.setdefault(r["config"], []).append(r)
    rows = []
    for name, runs in by_config.items():
        done = [r for r in runs if not r["failed"]]
        if {r["story"] for r in done} != set(stories):
            rows.append((name, None, runs))
            continue
        c = sum(r["correct"] for r in done)
        fa = sum(r["false_alarms"] for r in done)
        n = sum(r["planted"] for r in done)
        cc = sum(r["levels"].get("Confirmed (code)", {}).get("correct", 0) for r in done)
        cfa = sum(r["levels"].get("Confirmed (code)", {}).get("false_alarms", 0) for r in done)
        minutes = sum(r["seconds"] for r in done) / 60
        rows.append((name, (_f1(c, fa, n), c, fa, n, _f1(cc, cfa, n), minutes), done))
    complete = sorted((r for r in rows if r[1]), key=lambda r: (-r[1][0][2], r[1][2], r[1][5]))
    lines = [f"# Model configuration sweep ({', '.join(stories)})", "",
             "Same saved facts for every row. Ranked by F1, then false alarms, then time.", "",
             "| Rank | Configuration | Precision | Recall | F1 | Caught | False alarms | Confirmed-only F1 | Minutes |",
             "|---|---|---|---|---|---|---|---|---|"]
    for i, (name, (prf, c, fa, n, cprf, minutes), _) in enumerate(complete, start=1):
        lines.append(f"| {i} | {name} | {prf[0]:.0%} | {prf[1]:.0%} | {prf[2]:.2f} | {c}/{n} | {fa} | {cprf[2]:.2f} | {minutes:.0f} |")
    unfinished = [r for r in rows if not r[1]]
    if unfinished:
        lines += ["", "Not finished for every story (failed or not run yet): " + "; ".join(r[0] for r in unfinished)]
    if complete:
        best = complete[0]
        settings = best[2][0]["settings"]
        lines += ["", "## Best configuration", "", "Put these lines in `backend/.env`:", "", "```",
                  *[f"{k}={v}" for k, v in settings.items()], "```"]
        notes = {r.get("model_notes") for r in best[2] if r.get("model_notes")}
        if notes:
            lines += ["", "Note: models switched during these runs (NVIDIA problems), so re-check the top two: "
                      + " ".join(notes)]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Try model configurations on the saved readings and rank them.")
    parser.add_argument("--stories", default="fallenking,glassmaker", help="comma-separated, e.g. fallenking,glassmaker,lighthouse")
    parser.add_argument("--quick", action="store_true", help="only 3 configurations")
    parser.add_argument("--report", action="store_true", help="print the ranking of the runs done so far and stop")
    args = parser.parse_args()
    stories = [s.strip() for s in args.stories.split(",") if s.strip()]
    state = load_state()
    if not args.report:
        configs = grid(args.quick)
        print(f"{len(configs)} configurations × {len(stories)} stories = {len(configs) * len(stories)} runs "
              f"(each about 5–15 minutes on the free API).")
        for config in configs:
            for story in stories:
                if any(r["config"] == config["name"] and r["story"] == story and not r["failed"] for r in state["runs"]):
                    continue                                  # done in an earlier sweep
                result = run_one(config, story)
                state["runs"] = [r for r in state["runs"] if not (r["config"] == config["name"] and r["story"] == story)]
                state["runs"].append(result)
                save_state(state)
    text = report(state, stories)
    (RESULTS / "sweep.md").write_text(text, encoding="utf-8")
    print("\n" + text + f"\n\nSaved: {RESULTS / 'sweep.md'}")


if __name__ == "__main__":
    main()

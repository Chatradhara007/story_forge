"""
Try every free Reader (the model that reads chapters into facts) on the test stories and rank
them: the free-setup search. Run it on your own computer; it uses your keys and your GPU.

    python eval/reader_sweep.py                                   # the default candidates, all stories
    python eval/reader_sweep.py --readers "ollama:qwen2.5:7b-instruct,groq:llama-3.3-70b-versatile"
    python eval/reader_sweep.py --stories kestrel,fallenking      # fewer stories (faster)
    python eval/reader_sweep.py --report                          # just print the ranking so far

Every reader reads each story ONCE (its reading is saved in eval/cache, per model), then the
checks run on it, exactly as in the app (CHECKER=off, NAME_LINKING=rules: the checks in code).
Readers whose key is missing in backend/.env are skipped. Progress is saved after each run in
eval/results/reader-sweep.json, so it can be stopped and started again.

Ranking: false alarms first (fewer is better), then mistakes caught, then failed runs and
fallbacks to another model (reliability), then time. Then build the chain for backend/.env:
the best reader first, the next most reliable ones after it as fallbacks.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
STATE = RESULTS / "reader-sweep.json"
STORIES = ["fallenking", "glassmaker", "lighthouse", "nightshift", "kestrel"]

# Free candidates (19 Oct 2026). Model names on free tiers change: check each provider's model
# list and pass --readers to try others. Prefixes: see PROVIDERS in backend/llm.py.
CANDIDATES = [
    "ollama:qwen2.5:7b-instruct",
    "ollama:qwen2.5:14b-instruct",
    "ollama:llama3.1:8b",
    "groq:llama-3.3-70b-versatile",
    "groq:llama-3.1-8b-instant",
    "cerebras:llama-3.3-70b",
    "nvidia:nvidia/nemotron-3.5-lightning-30b-a3b",
    "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    "gemini:gemini-2.5-flash",          # free tier may use prompts for training: test stories only
]

KEYS = {"groq": "GROQ_API_KEY", "cerebras": "CEREBRAS_API_KEY", "nvidia": "NVIDIA_API_KEY",
        "openrouter": "OPENROUTER_API_KEY", "gemini": "GEMINI_API_KEY", "github": "GITHUB_TOKEN",
        "mistral": "MISTRAL_API_KEY"}


def env_file() -> dict:
    values = {}
    path = HERE.parent / "backend" / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def missing_key(reader: str, env: dict) -> str | None:
    provider = reader.split(":", 1)[0]
    key = KEYS.get(provider)
    return key if key and not (os.environ.get(key) or env.get(key)) else None


def load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"runs": []}


def save(state: dict) -> None:
    RESULTS.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def run_one(reader: str, story: str) -> dict:
    settings = {"CHAT_MODEL": reader, "JUDGE_MODEL": reader, "CHECKER": "off", "SAFETY_NET": "off",
                "NAME_LINKING": "rules", "CHAT_MODEL_READING": "", "CHAT_MODEL_JUDGING": "",
                "CHAT_MODEL_FALLBACKS": ""}
    env = {**os.environ, **settings}
    before = {p.name for p in RESULTS.glob(f"{story}-*.json")} if RESULTS.exists() else set()
    started = time.time()
    print(f"\n=== {reader} - {story} ===", flush=True)
    process = subprocess.run([sys.executable, str(HERE / "run_eval.py"), "--story", story, "--reuse-reading"],
                             env=env, cwd=str(HERE.parent))
    new = sorted((p for p in RESULTS.glob(f"{story}-*.json") if p.name not in before), key=lambda p: p.stat().st_mtime)
    seconds = time.time() - started
    if process.returncode != 0 or not new:
        return {"reader": reader, "story": story, "failed": True, "seconds": seconds}
    data = json.loads(new[-1].read_text(encoding="utf-8"))
    run, s = data["runs"][-1], data["runs"][-1]["scores"]
    return {"reader": reader, "story": story, "failed": False, "file": new[-1].name, "seconds": run["seconds"],
            "planted": s["correct"] + len(s["missed"]), "correct": s["correct"], "false_alarms": s["false_alarms"],
            "switched": bool(data["meta"].get("model_notes")), "reader_used": data["meta"].get("chat_model")}


def report(state: dict, stories: list[str]) -> str:
    rows = []
    for reader in dict.fromkeys(r["reader"] for r in state["runs"]):
        runs = [r for r in state["runs"] if r["reader"] == reader and r["story"] in stories]
        done = [r for r in runs if not r["failed"]]
        if not runs:
            continue
        caught = sum(r["correct"] for r in done)
        planted = sum(r["planted"] for r in done)
        fa = sum(r["false_alarms"] for r in done)
        failed = len(runs) - len(done)
        switched = sum(1 for r in done if r.get("switched"))
        minutes = sum(r["seconds"] for r in done) / 60
        precision = caught / (caught + fa) if caught + fa else 0.0
        recall = caught / planted if planted else 0.0
        rows.append((reader, len(done), len(stories), caught, planted, fa, precision, recall, failed, switched, minutes))
    rows.sort(key=lambda r: (r[1] < r[2], r[5], -r[3], r[8] + r[9], r[10]))
    lines = [f"# Free Reader sweep ({', '.join(stories)})", "",
             "Checks in code only (CHECKER=off, NAME_LINKING=rules). Ranked: complete runs, false alarms, "
             "caught, failures + fallbacks, time.", "",
             "| Rank | Reader | Stories | Caught | False alarms | Precision | Recall | Failed | Fell back | Minutes |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for i, (reader, done, total, caught, planted, fa, p, r, failed, switched, minutes) in enumerate(rows, 1):
        lines.append(f"| {i} | `{reader}` | {done}/{total} | {caught}/{planted} | {fa} | {p:.0%} | {r:.0%} | "
                     f"{failed} | {switched} | {minutes:.1f} |")
    complete = [r for r in rows if r[1] == r[2]]
    if complete:
        best = complete[0][0]
        backups = [r[0] for r in sorted(complete[1:], key=lambda r: (r[8] + r[9], r[5], -r[3]))][:2]
        chain = ",".join([best] + backups)
        lines += ["", "## Suggested free chain for backend/.env", "", "```",
                  f"CHAT_MODEL={chain}", f"JUDGE_MODEL={chain}", "```",
                  "", "The best reader first; the most reliable others take over when it fails or runs out "
                      "of free requests. Check the false alarms of the backups too."]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank free Readers on the test stories.")
    parser.add_argument("--readers", help="comma-separated, e.g. ollama:qwen2.5:7b-instruct,groq:llama-3.3-70b-versatile")
    parser.add_argument("--stories", default=",".join(STORIES))
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--again", action="store_true", help="re-run readers already done")
    args = parser.parse_args()
    readers = [r.strip() for r in (args.readers.split(",") if args.readers else CANDIDATES) if r.strip()]
    stories = [s.strip() for s in args.stories.split(",") if s.strip()]
    state = load()
    if not args.report:
        env = env_file()
        for reader in readers:
            key = missing_key(reader, env)
            if key:
                print(f"skipping {reader}: no {key} in backend/.env", flush=True)
                continue
            for story in stories:
                if not args.again and any(r["reader"] == reader and r["story"] == story and not r["failed"]
                                          for r in state["runs"]):
                    continue
                result = run_one(reader, story)
                state["runs"] = [r for r in state["runs"] if not (r["reader"] == reader and r["story"] == story)]
                state["runs"].append(result)
                save(state)
    text = report(state, stories)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "reader-sweep.md").write_text(text, encoding="utf-8")
    print("\n" + text + f"\n\nSaved: {RESULTS / 'reader-sweep.md'}")


if __name__ == "__main__":
    main()

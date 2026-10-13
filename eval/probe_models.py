"""
Which NVIDIA models can StoryForge use right now, and which is the best trade-off?

(backend/check_models.py is the quick check: one tiny request per configured model. This
script is the deeper comparison: StoryForge's real reading and judging requests, timed.)

NVIDIA retires hosted models with little warning (nemotron-3-super-120b-a12b went on
2026-10-03). Instead of guessing a replacement, run this. It:
  1. lists every model that is live on YOUR API key (GET /v1/models);
  2. sends each candidate StoryForge's REAL requests, using the real prompts and tools:
       reading - read chapter 2 of the lighthouse story into facts (the high-volume step)
       judging - one batched mistake check with 2 planted mistakes and 2 traps
     several times each, timing every call;
  3. prints a table and the .env lines for the best reader and the best judge.

Costs about (trials x 3) requests per model. No database needed.

Run from the project folder:
    python eval/probe_models.py                          # the default shortlist (live ones only)
    python eval/probe_models.py --list                   # just list the live chat models
    python eval/probe_models.py --models a/b,c/d --trials 5
Then confirm the winner on the full answer key:
    python eval/run_eval.py --judges "model-a,model-b" --runs 3   (judges on identical reading)
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND / ".env")

SHORTLIST = [
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3-super-120b-a12b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "deepseek-ai/deepseek-v4-flash",
    "moonshotai/kimi-k2.6",
    "z-ai/glm-5.1",
    "qwen/qwen3-next-80b-a3b-instruct",
]
NOT_CHAT = ("embed", "rerank", "guard", "safety", "translate", "riva", "clip", "parse", "ocr",
            "vision-instruct", "diffusion", "calibration", "reward", "nemoretriever", "topic-control")

# Details a good reader must record from lighthouse chapter 2 (checked in values and quotes).
READ_KEYS = ["white beard", "red", "left hand", "harbourmaster", "mail boat", "grey", "winch"]


def judge_case():
    from models import Fact
    def new(entity, attribute, value, quote, kind="character"):
        return Fact(entity=entity, entity_type=kind, attribute=attribute, value=value, source_quote=quote,
                    confidence=0.9)
    def old(entity, attribute, value, quote, chapter_id, number):
        return {"entity": entity, "attribute": attribute, "value": value, "source_quote": quote,
                "chapter_id": chapter_id, "chapter_number": number, "pinned": False}
    batch = [
        ("Silas Rudd",
         [new("Harbourmaster Rudd", "facial hair", "clean-shaven chin", "rubbing his clean-shaven chin")],
         [old("Silas Rudd", "physical description", "white beard that reached the second button of his coat",
              "a broad man with a white beard that reached the second button of his coat", "ch2", 2)]),
        ("Tobias Calloway",
         [new("Tobias", "action", "clapped both hands over the broken latch",
              "clapped both hands over the broken latch")],
         [old("Tobias Calloway", "injury", "lost his left hand to a winch accident",
              "He had lost his left hand to a winch accident at sea many years ago", "ch2", 2)]),
        ("Pip",   # trap: an injury healing is normal
         [new("Pip", "injury", "cut on his palm has healed", "the cut on his palm had healed to a pink line")],
         [old("Pip", "injury", "cut his palm on the lens", "Pip cut his palm on the edge of the lens", "ch1", 1)]),
        ("Ines Calloway",  # trap: moving house is normal
         [new("Ines", "residence", "the town house in Port Wick", "Ines had moved into the town house in Port Wick")],
         [old("Ines Calloway", "residence", "the keeper's cottage", "Ines lived in the keeper's cottage", "ch1", 1)]),
    ]
    return batch, {"Silas Rudd", "Tobias Calloway"}


def probe(model: str, trials: int, chapter_text: str) -> dict:
    import llm
    import extract
    import contradictions
    # Pin both jobs to this one model, with no fallback, so we measure exactly it.
    llm.CHAT_MODELS, llm.JUDGE_MODELS = [model], [model]
    llm._retired.clear()
    llm._unhealthy_until.clear()
    out = {"model": model, "read_s": [], "read_ok": 0, "facts": [], "coverage": [],
           "judge_s": [], "judge_ok": 0, "caught": [], "false_alarms": [], "error": None}
    batch, should_flag = judge_case()
    for trial in range(trials):
        try:
            start = time.monotonic()
            result = extract.extract_facts("ch2", chapter_text)
            out["read_s"].append(time.monotonic() - start)
            out["read_ok"] += 1
            out["facts"].append(len(result.facts))
            blob = " ".join(f"{f.value} {f.source_quote} {f.attribute}" for f in result.facts).lower()
            out["coverage"].append(sum(k in blob for k in READ_KEYS))
        except llm.AIServiceError as error:
            out["error"] = str(error)[:200]
            if isinstance(error.__cause__, llm.ModelUnavailableError) or "none of the configured" in str(error):
                return out
        try:
            start = time.monotonic()
            found = contradictions._check_entities_once("ch6", 6, batch, "chapter 1: continues\nchapter 2: "
                                                         "continues\nchapter 6 (the NEW chapter): continues", {})
            out["judge_s"].append(time.monotonic() - start)
            out["judge_ok"] += 1
            flagged = {c.entity for c in found}
            out["caught"].append(len(flagged & should_flag))
            out["false_alarms"].append(len(flagged - should_flag))
        except llm.AIServiceError as error:
            out["error"] = str(error)[:200]
        print(f"  {model} trial {trial + 1}/{trials} done", flush=True)
    return out


def _median(values):
    return statistics.median(values) if values else float("nan")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", help="comma-separated model ids (default: the shortlist, live ones only)")
    parser.add_argument("--trials", type=int, default=3, help="requests of each kind per model (default 3)")
    parser.add_argument("--list", action="store_true", help="only list the live chat models")
    args = parser.parse_args()

    import llm
    if not llm.AI_CONFIGURED:
        sys.exit("Set NVIDIA_API_KEY in backend/.env first.")
    try:
        live = sorted(m.id for m in llm.client.models.list().data)
    except Exception as error:   # noqa: BLE001 - show whatever went wrong
        sys.exit(f"Could not list models: {error}")
    chat = [m for m in live if not any(k in m.lower() for k in NOT_CHAT)]
    print(f"{len(live)} models live on your key, {len(chat)} look like chat models.")
    if args.list:
        print("\n".join(chat))
        return
    wanted = [m.strip() for m in args.models.split(",")] if args.models else SHORTLIST
    missing = [m for m in wanted if m not in live]
    candidates = [m for m in wanted if m in live]
    for m in missing:
        print(f"  not live on your key, skipped: {m}")
    if not candidates:
        sys.exit("None of those models is live. Use --list and pass some with --models.")

    chapter = (HERE / "stories" / "lighthouse" / "ch2.txt").read_text(encoding="utf-8")
    import extract
    print(f"\nProbing {len(candidates)} models x {args.trials} trials "
          f"({len(extract.split_into_passages(chapter))} passages per read)...\n")
    results = [probe(m, args.trials, chapter) for m in candidates]

    print("\n| Model | Read: median s | Read OK | Facts | Key details (of %d) | Judge: median s | Judge OK | "
          "Mistakes caught (of 2) | False alarms (traps 2) |" % len(READ_KEYS))
    print("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        print(f"| {r['model']} | {_median(r['read_s']):.1f} | {r['read_ok']}/{args.trials} | "
              f"{_median(r['facts']):.0f} | {_median(r['coverage']):.1f} | {_median(r['judge_s']):.1f} | "
              f"{r['judge_ok']}/{args.trials} | {statistics.mean(r['caught']) if r['caught'] else 0:.1f} | "
              f"{statistics.mean(r['false_alarms']) if r['false_alarms'] else 0:.1f} |")
        if r["error"]:
            print(f"|   last error: {r['error']} |")

    reliable_readers = [r for r in results if r["read_ok"] == args.trials]
    reliable_judges = [r for r in results if r["judge_ok"] == args.trials]
    if reliable_readers:
        best_cov = max(_median(r["coverage"]) for r in reliable_readers)
        # Reading: fastest model within one key detail of the best coverage.
        reader = min((r for r in reliable_readers if _median(r["coverage"]) >= best_cov - 1),
                     key=lambda r: _median(r["read_s"]))
        print(f"\nCHAT_MODEL={reader['model']}")
    if reliable_judges:
        # Judging: most accurate (catches minus false alarms), then fastest.
        judge = max(reliable_judges, key=lambda r: (statistics.mean(r["caught"]) - statistics.mean(r["false_alarms"]),
                                                    -_median(r["judge_s"])))
        print(f"JUDGE_MODEL={judge['model']}")
    if reliable_readers or reliable_judges:
        print("(Add a second model after a comma in each line as the backup, e.g. "
              "CHAT_MODEL=fast/model,backup/model.)")
        print("\nPut these in backend/.env, then confirm with: python eval/run_eval.py --runs 3")
    else:
        print("\nNo model answered reliably. Check the errors above (usage limit? key?).")


if __name__ == "__main__":
    main()

"""
Automatic test cases: plant new continuity mistakes into the test stories, with the answer key
written automatically, so the checks are measured on many more mistakes than anyone tunes for.

    python eval/make_cases.py                     # 2 variants of every story, 4 mistakes each
    python eval/make_cases.py --variants 3 --per-story 5 --seed 7
    python eval/make_cases.py --run               # make them, run them all, print the report
    python eval/make_cases.py --report            # report on the runs done so far

How a mistake is planted: find a detail that an EARLY chapter states and a LATER chapter repeats
in the same words about the same person ("grey eyes", "her left hand", "older sister", "eight
beds", "Calder Street"), and change the later one. The earlier text is untouched, so the change
is a contradiction in the text itself, whatever the Reader makes of it. Both sentences must name
the same character, which keeps "grey eyes" about two different people from being used.

Kinds (the report gives recall per kind, so gaps show up as kinds, not as single stories):
  colour   eyes / hair / coat / hull colour      side     left <-> right of a scar, burn, lost hand
  order    older <-> younger brother or sister   family   sister / brother -> cousin
  count    "eight beds" -> "eleven beds"         place    "Calder Street" -> another street
Some kinds have code checks today (colour, side, order, family), some don't (count, place):
that is on purpose, to measure the gaps.

Real books work best as a base (eval/add_book.py): far more text to plant into, and every other
warning on them is a false alarm on real prose.

Each variant is a new folder eval/stories/gen-<story>-<n>/ (not committed to git): the original
chapters with the changes, the original answer key (its planted mistakes and traps still count)
plus the generated ones. Its saved reading starts as a copy of the original story's, so only the
changed chapters are read again.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORIES = HERE / "stories"
CACHE = HERE / "cache"
RESULTS = HERE / "results"

COLOURS = ["grey", "green", "blue", "brown", "black", "red", "white", "golden", "hazel", "chestnut"]
SWAP_COLOUR = {"grey": "brown", "gray": "brown", "green": "blue", "blue": "brown", "brown": "green", "black": "golden",
               "red": "black", "white": "black", "golden": "black", "hazel": "blue", "chestnut": "grey"}
NUMBERS = ["two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "fifteen",
           "twenty", "thirty", "forty", "fifty", "sixty"]
COUNT_SWAP = {"two": "five", "three": "seven", "four": "nine", "five": "two", "six": "eleven", "seven": "three",
              "eight": "eleven", "nine": "four", "ten": "fifteen", "eleven": "six", "twelve": "seven",
              "fifteen": "nine", "twenty": "thirty", "thirty": "fifty", "forty": "twenty", "fifty": "thirty",
              "sixty": "forty"}
NOT_COUNTED = r"(?:years?|months?|weeks?|days?|nights?|hours?|minutes?|seconds?|times?|o'clock|percent|pounds|dollars|miles|feet|inches|steps|paces)"
PLACE_NAMES = ["Harrow", "Wexley", "Ormond", "Tollgate", "Sallow", "Brindle"]

PATTERNS = {
    "colour": re.compile(rf"\b(?P<old>{'|'.join(COLOURS)}|gray)(?P<rest>(?:[- ](?:eyed|haired))|\s+(?:eyes|hair|curls|beard|coat|mane|hull|stallion|mare|horse|dog))\b", re.I),
    "side": re.compile(r"\b(?P<old>left|right)(?P<rest>\s+(?:hand|arm|eye|cheek|leg|foot|shoulder|palm|wrist|forearm|knee|ear|temple))\b", re.I),
    "order": re.compile(r"\b(?P<old>older|elder|younger|little|big)(?P<rest>\s+(?:brother|sister))\b", re.I),
    "family": re.compile(r"\b(?P<pre>(?:her|his|my|their|[A-Z][a-z]+'s)\s+)(?P<old>sister|brother)\b(?!-in-law)"),
    "count": re.compile(rf"(?<!hundred and )(?<!thousand and )(?<!-)\b(?P<old>{'|'.join(NUMBERS)})(?P<rest>\s+(?!{NOT_COUNTED}\b)[a-z]+s)\b", re.I),
    "place": re.compile(r"\b(?P<old>[A-Z][a-z]+)(?P<rest>\s+(?:Street|Road|Lane|Square|Avenue|Bridge|Gate))\b"),
}
SIDE_WORDS = re.compile(r"\b(scar|scarred|burn|burned|burnt|tattoo|birthmark|mark|lost|missing|wound)\b", re.I)
COMMON_CAPS = {"The", "A", "An", "He", "She", "It", "They", "His", "Her", "Their", "But", "And", "Then", "When", "In",
               "On", "At", "Chapter", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "I", "We",
               "You", "Of", "For", "So", "If", "As", "No", "Yes", "Not", "There", "This", "That", "After", "Before"}


def sentences(text: str):
    """(start, end) of each sentence."""
    start = 0
    for m in re.finditer(r"[.!?][\"')\]]?\s+|\n\s*\n", text):
        yield start, m.end()
        start = m.end()
    if start < len(text):
        yield start, len(text)


def names_in(sentence: str) -> set[str]:
    return {w for w in re.findall(r"\b[A-Z][a-z]{2,}\b", sentence) if w not in COMMON_CAPS}


def candidates(chapters: dict[str, str], order: list[str]) -> list[dict]:
    """Every later repetition of an earlier detail that could be changed."""
    found = []
    seen: dict[tuple, list] = {}            # (kind, phrase) -> [(chapter index, names)]
    for index, chapter in enumerate(order):
        text = chapters[chapter]
        for s, e in sentences(text):
            sentence = text[s:e]
            for kind, pattern in PATTERNS.items():
                for m in pattern.finditer(sentence):
                    if kind == "side" and not SIDE_WORDS.search(sentence):
                        continue
                    names = names_in(sentence) - set(re.findall(r"[A-Z][a-z]+", m.group(0)))
                    phrase = m.group(0).lower()
                    key = (kind, phrase)
                    earlier = [(i, n) for i, n in seen.get(key, []) if i < index]
                    shared = set()
                    for _, n in earlier:
                        shared |= (n & names)
                    if earlier and shared:
                        found.append({"kind": kind, "chapter": chapter, "index": index, "start": s + m.start(),
                                      "end": s + m.end(), "match": m.group(0), "old": m.group("old"),
                                      "names": sorted(shared), "first_chapter": order[earlier[0][0]], "how": "edit",
                                      "pre": m.groupdict().get("pre") or "", "rest": m.groupdict().get("rest") or ""})
                    seen.setdefault(key, []).append((index, names))
    return found


# ------------------------------------------------------------ inserted sentences --
# Good prose rarely repeats a detail word for word, so most planted mistakes are a NEW short
# sentence in a later chapter that contradicts what an earlier chapter said about a named
# character. They are plainer than real slips, so this measures the checks more than the Reader.
EYES = re.compile(rf"\b(?P<old>{'|'.join(COLOURS)}|gray)(?:[- ](?:green|blue|grey|brown))?(?:[- ]eyed|\s+eyes)\b", re.I)
HAIR = re.compile(rf"\b(?P<old>black|brown|red|fair|blond|blonde|grey|gray|white|golden|dark|auburn)(?:[- ]haired|\s+hair)\b", re.I)
SCAR = re.compile(r"\b(?P<mark>scar|burn|tattoo|birthmark)\b[^.;]{0,50}?\b(?P<old>left|right)\s+(?P<part>hand|arm|forearm|cheek|wrist|palm|leg|shoulder)\b", re.I)
DIED = re.compile(r"\b(?P<who>[A-Z][a-z]+(?: [A-Z][a-z]+)?) (?:died|was dead|was killed|drowned|was buried)\b")
AGE = re.compile(r"\b(?P<who>[A-Z][a-z]+(?: [A-Z][a-z]+)?)(?:,| was)\s+(?P<old>" + "|".join(
    ["twenty", "thirty", "forty", "fifty", "sixty", "seventy"]) + r")(?:-(?P<unit>one|two|three|four|five|six|seven|eight|nine))?\b")
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70}
UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
UNSURE = re.compile(r"\b(no|not|never|without|yet|until|unless|if|would|will|could|might|perhaps|"
                    r"maybe|when he was|when she was|wanted|wished|hoped|dreamed|remembered|seemed|looked like)\b", re.I)
FLASHBACK = re.compile(r"\b(years|decades) (before|earlier|ago)\b|\blong ago\b", re.I)
HAIR_SWAP = {"black": "fair", "dark": "fair", "brown": "fair", "red": "black", "fair": "black", "blond": "black",
             "blonde": "black", "grey": "black", "gray": "black", "white": "black", "golden": "black", "auburn": "fair"}


def words(n: int) -> str:
    tens = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy"}
    units = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
    return tens[n // 10] + (f"-{units[n % 10]}" if n % 10 else "")


def _is_planted(chapter: str, sentence: str, planted: list[dict]) -> bool:
    """Is this sentence one of the story's own planted mistakes? Then it can't anchor a new one."""
    low = sentence.lower()
    return any(p["chapter"] == chapter and any(k in low for k in p.get("new_keywords", []))
               and any(e in low for e in p.get("entity_contains", [])) for p in planted)


def insertions(chapters: dict[str, str], order: list[str], planted: list[dict] | None = None) -> list[dict]:
    """Facts stated about a named character early on, and later chapters where they appear."""
    planted = planted or []
    found = []
    stated: set[tuple] = set()              # (kind, who): only the FIRST statement anchors a case
    for index, chapter in enumerate(order[:-1]):
        text = chapters[chapter]
        if FLASHBACK.search(text[:400]):
            continue                            # an earlier time: its details may rightly differ
        for s, e in sentences(text):
            sentence = text[s:e]
            if UNSURE.search(sentence) or _is_planted(chapter, sentence, planted):
                continue                        # "no scar yet", "until Tam is twenty-five"; a planted slip
            named = sorted(names_in(sentence), key=lambda n: sentence.find(n))
            facts = []
            if named and (m := EYES.search(sentence)):
                who = _owner(sentence, m.start(), named)
                new = SWAP_COLOUR.get(m.group("old").lower(), "brown")
                facts.append(("colour", who, m.group("old").lower(), new, f"{who}'s {new} eyes narrowed.", "eyes"))
            if named and (m := HAIR.search(sentence)):
                who = _owner(sentence, m.start(), named)
                new = HAIR_SWAP.get(m.group("old").lower(), "black")
                facts.append(("colour", who, m.group("old").lower(), new, f"A strand of {who}'s {new} hair fell loose.", "hair"))
            if named and (m := SCAR.search(sentence)):
                who = _owner(sentence, m.start(), named)
                flip = "right" if m.group("old").lower() == "left" else "left"
                facts.append(("side", who, m.group("old").lower(), flip,
                              f"The {m.group('mark').lower()} on {who}'s {flip} {m.group('part').lower()} ached.", m.group("part").lower()))
            if m := DIED.search(sentence):
                who = m.group("who")
                if who not in COMMON_CAPS:
                    facts.append(("death", who, "died", "sat down",
                                  f"{who} came in out of the cold and sat down by the fire.", who.split()[0].lower()))
            if m := AGE.search(sentence):
                who, age = m.group("who"), TENS[m.group("old")] + UNITS.get(m.group("unit") or "", 0)
                if who not in COMMON_CAPS and age >= 25:
                    younger = words(age - 4)
                    facts.append(("age", who, m.group(0).split()[-1].lower(), younger, f"{who} was {younger} now.",
                                  who.split()[0].lower()))
            for kind, who, old, new, sentence_new, word in facts:
                if not who or (kind, who) in stated:
                    continue
                stated.add((kind, who))
                first = who.split()[0]
                for later in order[index + 1:]:
                    later_text = chapters[later]
                    if FLASHBACK.search(later_text[:400]):
                        continue                    # a flashback chapter: an earlier time, not a mistake
                    spots = [e2 for s2, e2 in sentences(later_text) if re.search(rf"\b{re.escape(first)}\b", later_text[s2:e2])]
                    if not spots:
                        continue
                    found.append({"kind": kind, "how": "inserted", "chapter": later, "index": order.index(later),
                                  "start": spots[0], "end": spots[0], "insert": sentence_new + " ", "old": old,
                                  "new": new, "names": [first], "word": word, "first_chapter": chapter,
                                  "match": sentence_new})
                    break
    return found


def _owner(sentence: str, at: int, named: list[str]) -> str | None:
    """
    Whose detail it is, only when the sentence says so plainly: "Thessaly's grey-green eyes",
    or a sentence about one person that starts with their name ("Rook was thin and red-haired").
    Anything less clear gives None and no test case (a wrong answer key is worse than none).
    """
    window = sentence[max(0, at - 30):at]
    m = re.search(r"\b([A-Z][a-z]+)'s\s+(?:[\w-]+\s+){0,2}$", window)
    if m and m.group(1) not in COMMON_CAPS:
        return m.group(1)
    lead = re.match(r"\s*((?:[A-Z][a-z]+\s+){0,2}[A-Z][a-z]+)\b", sentence)
    if lead and lead.group(1).split()[0] not in COMMON_CAPS:
        full = lead.group(1)
        if all(n in full.split() for n in named):     # a sentence about one person, starting with them
            return full
    return None


def changed(c: dict, rng: random.Random) -> tuple[str, str]:
    """(new text for the match, new value word)."""
    old = c["old"]
    keep_case = (lambda w: w.capitalize()) if old[:1].isupper() else (lambda w: w)
    if c["kind"] == "colour":
        new = SWAP_COLOUR.get(old.lower(), "brown")
    elif c["kind"] == "side":
        new = "right" if old.lower() == "left" else "left"
    elif c["kind"] == "order":
        new = "younger" if old.lower() in ("older", "elder", "big") else "older"
    elif c["kind"] == "family":
        new = "cousin"
        return c["pre"] + new, new
    elif c["kind"] == "count":
        new = COUNT_SWAP.get(old.lower(), "seven")
    else:
        new = rng.choice([p for p in PLACE_NAMES if p != old])
        return new + c["rest"], new.lower()
    return keep_case(new) + c["rest"], new


def make_variant(story: str, n: int, per_story: int, seed: int) -> Path | None:
    base = STORIES / story
    truth = json.loads((base / "ground_truth.json").read_text(encoding="utf-8"))
    order = truth["chapters"]
    chapters = {c: (base / f"{c}.txt").read_text(encoding="utf-8") for c in order}
    rng = random.Random(f"{seed}-{story}-{n}")
    pool = candidates(chapters, order) + insertions(chapters, order, truth.get("planted", []))
    rng.shuffle(pool)
    chosen, used = [], set()
    kinds_first = sorted(pool, key=lambda c: sum(1 for x in chosen if x["kind"] == c["kind"]))
    for c in kinds_first:
        # spread out: one change per sentence region, and vary the kinds
        if any(c["chapter"] == x["chapter"] and abs(c["start"] - x["start"]) < 200 for x in chosen):
            continue
        if sum(1 for x in chosen if x["kind"] == c["kind"]) >= max(1, per_story // 2):
            continue
        chosen.append(c)
        if len(chosen) >= per_story:
            break
    if not chosen:
        return None
    out = STORIES / f"gen-{story}-{n}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    texts = dict(chapters)
    planted = []
    for i, c in enumerate(sorted(chosen, key=lambda c: (c["chapter"], -c["start"])), start=1):
        t = texts[c["chapter"]]
        if c["how"] == "inserted":
            new_text, new_word = c["insert"].strip(), c["new"]
            texts[c["chapter"]] = t[:c["start"]] + c["insert"] + t[c["start"]:]
            noun = c["word"]
        else:
            new_text, new_word = changed(c, rng)
            texts[c["chapter"]] = t[:c["start"]] + new_text + t[c["end"]:]
            noun = c["rest"].strip().split()[-1].lower() if c["rest"].strip() else ""
        planted.append({
            "id": f"M{i}", "type": "attribute", "also_accept_types": ["status", "timeline"], "kind": c["kind"],
            "chapter": c["chapter"], "generated": True,
            "entity_contains": sorted({w.lower() for w in c["names"]} | ({noun} if noun else set()) | {new_word}),
            "how": c["how"],
            "description": (f"{c['kind']}: '{c['match']}' (as in {c['first_chapter']}) changed to '{new_text}' in {c['chapter']}."
                            if c["how"] == "edit" else
                            f"{c['kind']}: inserted '{new_text}' in {c['chapter']}, against {c['first_chapter']}."),
            "new_keywords": [new_word], "old_keywords": [c["old"].lower()]})
    for c in order:
        (out / f"{c}.txt").write_text(texts[c], encoding="utf-8")
    truth = dict(truth)
    truth["planted"] = list(truth.get("planted", [])) + planted
    truth["held_out"] = False
    truth["generated_from"] = story
    truth["_about"] = (f"Generated by eval/make_cases.py from '{story}' (variant {n}, seed {seed}): the original answer "
                       f"key plus {len(planted)} planted changes (ids M1...). Do not edit; regenerate instead.")
    (out / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    # Start from the original story's saved reading (exact-text entries only), so only the changed
    # chapters are read again. Entries keyed by chapter alone ('legacy') are NOT copied: they would
    # hand a changed chapter its old reading.
    source = CACHE / f"{story}-reading.json"
    if source.exists():
        data = json.loads(source.read_text(encoding="utf-8"))
        if data.get("format") == 2:
            (CACHE / f"gen-{story}-{n}-reading.json").write_text(
                json.dumps({"format": 2, "readings": data.get("readings", {}), "legacy": {}}), encoding="utf-8")
    return out


def report() -> str:
    by_kind: dict[str, list[int]] = {}
    original = [0, 0]
    false_alarms, stories = 0, 0
    for folder in sorted(STORIES.glob("gen-*")):
        runs = sorted(RESULTS.glob(f"{folder.name}-*.json"), key=lambda p: p.stat().st_mtime)
        if not runs:
            continue
        stories += 1
        data = json.loads(runs[-1].read_text(encoding="utf-8"))
        scores = data["runs"][-1]["scores"]
        truth = json.loads((folder / "ground_truth.json").read_text(encoding="utf-8"))
        kinds = {p["id"]: p.get("kind") for p in truth["planted"]}
        caught = {r["id"] for r in scores["rows"] if r["verdict"] == "correct"}
        for pid, kind in kinds.items():
            target = by_kind.setdefault(kind, [0, 0]) if kind else original
            target[1] += 1
            target[0] += pid in caught
        false_alarms += scores["false_alarms"]
    if not stories:
        return "No generated story has been run yet: python eval/make_cases.py --run"
    lines = [f"# Generated test cases ({stories} stories)", "", "| Kind | Caught | Recall |", "|---|---|---|"]
    for kind, (c, n) in sorted(by_kind.items()):
        lines.append(f"| {kind} | {c}/{n} | {c / n:.0%} |")
    total_c = sum(c for c, _ in by_kind.values())
    total_n = sum(n for _, n in by_kind.values())
    lines += [f"| **all generated** | {total_c}/{total_n} | {total_c / max(total_n, 1):.0%} |",
              f"| (the stories' own planted mistakes) | {original[0]}/{original[1]} | {original[0] / max(original[1], 1):.0%} |",
              "", f"False alarms over all generated stories: **{false_alarms}**"]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plant generated mistakes into the test stories and measure them.")
    parser.add_argument("--stories", default="fallenking,glassmaker,lighthouse,nightshift,kestrel")
    parser.add_argument("--variants", type=int, default=2)
    parser.add_argument("--per-story", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--run", action="store_true", help="also run every generated story and report")
    parser.add_argument("--report", action="store_true", help="only report on the runs done so far")
    args = parser.parse_args()
    if not args.report:
        made = []
        for story in [s.strip() for s in args.stories.split(",") if s.strip()]:
            seen_sets = set()
            for n in range(1, args.variants + 1):
                out = make_variant(story, n, args.per_story, args.seed)
                if out is None:
                    print(f"{story}: nothing found that could be changed")
                    continue
                truth = json.loads((out / "ground_truth.json").read_text(encoding="utf-8"))
                gen = [p for p in truth["planted"] if p.get("generated")]
                signature = tuple(sorted(p["description"] for p in gen))
                if signature in seen_sets:          # the same changes as an earlier variant: drop it
                    shutil.rmtree(out)
                    (CACHE / f"{out.name}-reading.json").unlink(missing_ok=True)
                    continue
                seen_sets.add(signature)
                print(f"{out.name}: " + "; ".join(p["description"] for p in gen))
                made.append(out.name)
        if args.run:
            for name in made:
                subprocess.run([sys.executable, str(HERE / "run_eval.py"), "--story", name, "--reuse-reading"],
                               cwd=str(HERE.parent))
    if args.run or args.report:
        text = report()
        RESULTS.mkdir(exist_ok=True)
        (RESULTS / "generated-cases.md").write_text(text, encoding="utf-8")
        print("\n" + text)


if __name__ == "__main__":
    main()

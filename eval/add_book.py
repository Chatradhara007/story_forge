"""
Add a real novel (public domain, Project Gutenberg) as a test story, split into chapters.

    python eval/add_book.py 1342 --name pride --chapters 8      # Pride and Prejudice, first 8 chapters
    python eval/add_book.py path\\to\\book.txt --name mybook       # a plain-text file you have

A real book has no planted mistakes, so on its own it measures FALSE ALARMS on real prose:
every warning it raises is counted as one (a few may be the author's own slips; read them).
Then plant mistakes into it with make_cases.py:

    python eval/make_cases.py --stories pride --run

Suggested books with many named characters and physical detail (Gutenberg numbers):
1342 Pride and Prejudice, 120 Treasure Island, 1260 Jane Eyre, 768 Wuthering Heights,
2097 The Sign of the Four, 98 A Tale of Two Cities, 1400 Great Expectations.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORIES = HERE / "stories"
HEADING = re.compile(r"^\s*(CHAPTER|Chapter)\s+([IVXLC]+|\d+|[A-Z][a-z]+)\b.*$", re.M)


def download(book_id: str) -> str:
    for url in (f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt",
                f"https://www.gutenberg.org/files/{book_id}/{book_id}-0.txt"):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read().decode("utf-8", errors="replace")
        except OSError:
            continue
    raise SystemExit(f"Could not download Gutenberg book {book_id}.")


def body(text: str) -> str:
    """Without Project Gutenberg's header and licence."""
    start = re.search(r"\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", text, re.I | re.S)
    end = re.search(r"\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG EBOOK", text, re.I)
    return text[start.end() if start else 0:end.start() if end else len(text)]


def chapters(text: str) -> list[str]:
    marks = [m.start() for m in HEADING.finditer(text)]
    # A table of contents lists the headings close together: keep only real chapters (long enough).
    parts = [text[a:b].strip() for a, b in zip(marks, marks[1:] + [len(text)])]
    return [p for p in parts if len(p.split()) > 400]


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a public-domain book as a test story.")
    parser.add_argument("source", help="a Gutenberg book number, or a path to a .txt file")
    parser.add_argument("--name", required=True, help="short folder name, e.g. pride")
    parser.add_argument("--chapters", type=int, default=8, help="how many chapters to keep (default 8)")
    parser.add_argument("--max-words", type=int, default=2500, help="cut each chapter to about this many words")
    args = parser.parse_args()
    path = Path(args.source)
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else download(args.source)
    found = chapters(body(text))
    if len(found) < 3:
        raise SystemExit("Found fewer than 3 chapters (headings like 'CHAPTER I'). Split the file by hand.")
    out = STORIES / args.name
    out.mkdir(parents=True, exist_ok=True)
    names = []
    for i, chapter in enumerate(found[:args.chapters], start=1):
        words = chapter.split(" ")
        if len(chapter.split()) > args.max_words:     # cut at a paragraph near the limit
            cut, count = 0, 0
            for para in chapter.split("\n\n"):
                count += len(para.split())
                cut += len(para) + 2
                if count >= args.max_words:
                    break
            chapter = chapter[:cut].strip()
        (out / f"ch{i}.txt").write_text(chapter + "\n", encoding="utf-8")
        names.append(f"ch{i}")
    truth = {"_about": (f"Real book ({args.source}), first {len(names)} chapters, added by eval/add_book.py. No planted "
                        "mistakes: every warning counts as a false alarm (read them: a few may be the author's own "
                        "slips). Plant mistakes with eval/make_cases.py."),
             "held_out": True, "real_book": True, "chapters": names, "planted": [], "decoys": [],
             "same_entity": [], "different_entities": []}
    (out / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"Added eval/stories/{args.name}: {len(names)} chapters, "
          f"{sum(len((out / f'{c}.txt').read_text(encoding='utf-8').split()) for c in names):,} words.")


if __name__ == "__main__":
    main()

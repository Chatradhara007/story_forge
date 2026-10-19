"""
Make a demo account with two finished books in it, for presentations.

    python seed_demo.py --email demo@storyforge.app --password "a-long-demo-password"

Run from the backend folder with the virtual environment active and the database running.
It creates the account (or uses it if it exists), then adds two test stories as books, chapter
by chapter, through the normal pipeline, so the warnings on the website are real results:

  - "The Fallen King" (fantasy, 8 chapters)  from eval/stories/fallenking
  - "Kestrel" (science fiction, 6 chapters)   from eval/stories/kestrel

Readings saved by the evaluation (eval/cache) are reused, so a story you have evaluated
before is added in about a minute; otherwise every chapter is read by the AI (several minutes).
Search vectors still need NVIDIA_API_KEY.

Options:
  --stories fallenking,glassmaker   choose other stories (any folder in eval/stories)
  --fresh                           delete those two books first and add them again
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

import auth  # noqa: E402
import llm  # noqa: E402
import pipeline  # noqa: E402
import storage  # noqa: E402
from models import ExtractionResult  # noqa: E402

STORIES = HERE.parent / "eval" / "stories"
CACHE = HERE.parent / "eval" / "cache"
BOOKS = {
    "fallenking": ("The Fallen King", "fantasy",
                   "A young king wins a war at sea and loses everything after it: a court, a crown and a sister.", "oxblood"),
    "kestrel": ("Kestrel", "science fiction",
                "Four people on a failing relay station after a solar storm, and the report that has to explain it.", "slate"),
    "glassmaker": ("The Glassmaker", "historical", "A glassmaker's family and the secret of a recipe.", "sage"),
    "lighthouse": ("The Lighthouse", "mystery", "A keeper, a storm and a ship that should not have been there.", "ink"),
    "nightshift": ("Night Shift", "contemporary", "One hospital night, told by the people who worked it.", "plum"),
}


def find_or_make_user(email: str, password: str, name: str) -> dict:
    email = email.strip().lower()
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute(f"SELECT {auth._USER_COLUMNS} FROM users WHERE lower(email) = %s", (email,))
        user = cur.fetchone()
        if user:
            print(f"Using the existing account {email} (its password is unchanged).")
            return user
        auth.validate_new_password(password, email)
        cur.execute(f"INSERT INTO users (email, password_hash, display_name) VALUES (%s, %s, %s) "
                    f"RETURNING {auth._USER_COLUMNS}", (email, auth.hash_password(password), name))
        print(f"Created the account {email}.")
        return cur.fetchone()


def saved_readings(story: str) -> dict:
    path = CACHE / f"{story}-reading.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if data.get("format") == 2 else {"readings": {}, "legacy": {
        v["chapter_id"]: v for v in data.values() if isinstance(v, dict) and v.get("chapter_id")}}


def reading_for(data: dict, chapter_id: str, text: str):
    """The evaluation's saved reading of this chapter: the current reader's first, else any."""
    if not data:
        return None
    from extract import READ_PASSAGE_CHARS
    key = hashlib.sha1(f"{llm.CHAT_MODELS[0]}|{READ_PASSAGE_CHARS}|{chapter_id}|{text}".encode("utf-8")).hexdigest()
    entry = data.get("readings", {}).get(key)
    if entry is None:
        matches = [e for e in data.get("readings", {}).values() if e.get("chapter_id") == chapter_id]
        entry = matches[-1] if matches else data.get("legacy", {}).get(chapter_id)
    if not entry:
        return None
    result = ExtractionResult(chapter_id=chapter_id, facts=entry["facts"], relationships=entry.get("relationships", []))
    return result, entry.get("time_note")


def add_book(user: dict, story: str, fresh: bool) -> None:
    title, kind, synopsis, colour = BOOKS.get(story, (story.title(), "novel", None, None))
    existing = [p for p in storage.list_projects(user["id"]) if p["name"] == title]
    if existing and not fresh:
        print(f"'{title}' is already in this account; skipped (use --fresh to add it again).")
        return
    for p in existing:
        storage.delete_project(p["id"])
    truth = json.loads((STORIES / story / "ground_truth.json").read_text(encoding="utf-8"))
    project = storage.create_project(title, user["id"], kind, synopsis, colour)
    readings = saved_readings(story)
    print(f"\n{title}: {len(truth['chapters'])} chapters")
    for number, chapter_id in enumerate(truth["chapters"], start=1):
        text = (STORIES / story / f"{chapter_id}.txt").read_text(encoding="utf-8")
        saved = reading_for(readings, chapter_id, text)
        print(f"  Chapter {number} ({'saved reading' if saved else 'reading with the AI'})…", end=" ", flush=True)
        result, _later = pipeline.ingest(project["id"], chapter_id, text, number, reading=saved)
        print(f"{len(result.facts)} facts, {len(result.contradictions)} warnings", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Make a demo account with two finished books.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True, help="at least 8 characters; ignored if the account exists")
    parser.add_argument("--name", default="Demo", help="display name for a new account")
    parser.add_argument("--stories", default="fallenking,kestrel")
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    storage.apply_schema()
    stories = [s.strip() for s in args.stories.split(",") if s.strip()]
    missing = [s for s in stories if not (STORIES / s / "ground_truth.json").exists()]
    if missing:
        sys.exit(f"No story called {', '.join(missing)} in eval/stories.")
    try:
        user = find_or_make_user(args.email, args.password, args.name)
    except Exception as error:  # noqa: BLE001 - e.g. a password that is too short
        sys.exit(f"Couldn't make the account: {getattr(error, 'detail', error)}")
    for story in stories:
        add_book(user, story, args.fresh)
    print(f"\nDone. Start the website, set AUTH_REQUIRED=true, and sign in as {args.email}.")


if __name__ == "__main__":
    main()

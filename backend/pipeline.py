"""
The two pieces of work StoryForge does with the AI, shared by the web requests and the
background jobs:

  ingest()          – read a chapter, link names, check it, save it (the full pipeline)
  recheck_chapter() – check a SAVED chapter again against the story as it is now, without
                      re-reading it. Used after an earlier chapter changes, after a merge,
                      and after a fact is corrected.
"""
import time
from models import ChapterIngestResult, EntityLink, Fact
from extract import extract_facts, detect_timing
from entities import Resolution, resolve_entities
from contradictions import check_chapter
from llm import run_in_parallel
import storage

# Rough share of the total time each stage takes, for the progress bar.
STAGE_PROGRESS = {
    "queued": 0.0,
    "reading facts": 0.02,
    "linking names": 0.55,
    "preparing search": 0.62,
    "checking for mistakes": 0.68,
    "story clock": 0.80,
    "safety-net check": 0.82,
    "double-checking": 0.90,
    "saving": 0.97,
}


def _noop(stage: str, fraction: float | None = None) -> None:
    pass


def ingest(project_id: int, chapter_id: str, text: str, chapter_number: int | None = None,
           progress=_noop) -> tuple[ChapterIngestResult, list[str]]:
    """
    Full pipeline for one chapter of one book. All the slow AI work happens first; only
    if it all succeeds is everything saved to the database in one go. Re-submitting the
    same chapter_id replaces that chapter's old results.
    Returns the result and the LATER chapters that must now be re-checked.
    """
    timings: dict[str, float] = {}

    def timed(stage, function, *args):
        progress(stage)
        started = time.perf_counter()
        value = function(*args)
        timings[stage] = round(time.perf_counter() - started, 1)
        return value

    chapter_number = storage.resolve_chapter_number(project_id, chapter_id, chapter_number)
    # The timing detector sees when every EARLIER chapter is set, so it can actually judge
    # whether this one is a flashback or a time skip.
    earlier_notes = [f"chapter {c['chapter_number']}: {c['time_note'] or 'not recorded'}"
                     for c in storage.get_time_notes(project_id)
                     if c["chapter_number"] < chapter_number and c["chapter_id"] != chapter_id]

    def on_passage(done: int, total: int):
        progress("reading facts", done / max(total, 1))

    result, time_note = timed("reading facts", lambda: run_in_parallel(lambda job: job(), [
        lambda: extract_facts(chapter_id, text, on_passage=on_passage),
        lambda: detect_timing(text, earlier_notes),
    ]))
    resolutions = timed("linking names", resolve_entities, project_id, result.facts)
    embeddings = timed("preparing search", storage.embed_facts, result.facts)
    contradictions = check_chapter(project_id, chapter_id, chapter_number, result.facts, resolutions,
                                   embeddings, time_note, timings, progress=lambda stage: progress(stage))
    saved = timed(
        "saving", storage.save_chapter_results,
        project_id, chapter_id, chapter_number, text,
        result.facts, embeddings, contradictions, resolutions, time_note, result.relationships,
    )
    new_entity_ids = saved["new_entity_ids"]
    entity_links = [
        EntityLink(
            name=r.name,
            entity_id=r.existing_entity_id or new_entity_ids[r.canonical_name.lower()],
            canonical_name=r.canonical_name,
            method=r.method,
            confidence=r.confidence,
        )
        for r in resolutions.values()
    ]
    return ChapterIngestResult(
        chapter_id=chapter_id,
        chapter_number=chapter_number,
        time_note=time_note,
        facts=result.facts,
        relationships=result.relationships,
        entity_links=entity_links,
        contradictions=contradictions,
        timings_seconds=timings,
        rechecking_chapters=saved["later_chapters"],
    ), saved["later_chapters"]


def recheck_chapter(project_id: int, chapter_id: str, progress=_noop) -> dict | None:
    """
    Check a saved chapter again, using its stored facts and name links (no re-reading).
    Its warnings are replaced; the writer's dismissals survive by fingerprint.
    """
    data = storage.load_chapter_for_recheck(project_id, chapter_id)
    if data is None:
        return None
    rows = data["facts"]
    facts = [Fact(entity=r["entity"], entity_type=r["entity_type"], attribute=r["attribute"], value=r["value"],
                  source_quote=r["source_quote"], confidence=r["confidence"]) for r in rows]
    resolutions: dict[str, Resolution] = {}
    for r in rows:
        key = r["entity"].lower()
        if key not in resolutions:
            resolutions[key] = Resolution(
                name=r["entity"], entity_type=r["entity_type"], existing_entity_id=r["entity_id"],
                canonical_name=r["canonical_name"] or r["entity"],
                method="known name" if r["entity_id"] else "new", confidence=1.0)
    embeddings = [r["embedding"] for r in rows]
    missing = [i for i, v in enumerate(embeddings) if not v]
    if missing:
        for i, vector in zip(missing, storage.embed_facts([facts[i] for i in missing])):
            embeddings[i] = vector
    contradictions = check_chapter(project_id, chapter_id, data["chapter_number"], facts, resolutions,
                                   embeddings, data["time_note"], progress=lambda stage: progress(stage))
    for c in contradictions:
        if c.new_fact_index is not None:
            c.new_fact_id = rows[c.new_fact_index]["id"]
    storage.replace_chapter_warnings(project_id, chapter_id, contradictions)
    return {"chapter_id": chapter_id,
            "open": sum(1 for c in contradictions if c.status == "open"),
            "dismissed_by_double_check": sum(1 for c in contradictions if c.status == "dismissed" and c.review_note)}

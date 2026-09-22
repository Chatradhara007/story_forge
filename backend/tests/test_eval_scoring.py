"""The evaluation script's scoring logic (no database or AI needed)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from run_eval import score  # noqa: E402

STORIES = Path(__file__).resolve().parents[2] / "eval" / "stories"
TRUTH = json.loads((STORIES / "lighthouse" / "ground_truth.json").read_text())


def flag(chapter, entity, kind, **text):
    base = {"new_chapter_id": chapter, "entity": entity, "contradiction_type": kind, "new_attribute": "",
            "new_value": "", "new_quote": "", "conflicting_value": "", "conflicting_quote": "", "explanation": ""}
    return {**base, **text}


def perfect_flag(p):
    return flag(p["chapter"], p["entity_contains"][0], p["type"],
                new_quote=p["new_keywords"][0], conflicting_quote=p["old_keywords"][0])


def test_perfect_run_scores_one():
    flags = [perfect_flag(p) for p in TRUTH["planted"]]
    s = score(flags, TRUTH)
    assert s["precision"] == 1 and s["recall"] == 1 and s["type_label_accuracy"] == 1 and not s["missed"]


def test_false_alarms_duplicates_and_misses():
    flags = [
        flag("ch4", "Keeper Calloway", "attribute", new_value="green", conflicting_value="grey"),   # A1 correct
        flag("ch4", "Ines Calloway", "attribute", new_quote="green eyes", conflicting_quote="grey eyes"),  # A1 duplicate
        flag("ch6", "Ines Calloway", "status", new_quote="Ines moved into the village"),          # decoy D1
    ]
    s = score(flags, TRUTH)
    assert s["correct"] == 1 and s["duplicates"] == 1 and s["false_alarms"] == 1
    assert s["decoys_triggered"] == ["D1"]
    assert s["precision"] == 0.5 and round(s["recall"], 3) == round(1 / 12, 3)


def test_wrong_chapter_does_not_count():
    s = score([flag("ch5", "Ines", "attribute", new_value="green", conflicting_value="grey")], TRUTH)
    assert s["correct"] == 0


def test_explanation_alone_cannot_make_a_match():
    s = score([flag("ch4", "Ines Calloway", "attribute", explanation="green eyes versus grey eyes")], TRUTH)
    assert s["correct"] == 0 and s["false_alarms"] == 1


def test_both_sides_must_match():
    # right new side (green) but the earlier side is about something else
    s = score([flag("ch4", "Ines Calloway", "attribute", new_value="green", conflicting_value="tall")], TRUTH)
    assert s["correct"] == 0


from run_eval import diagnose  # noqa: E402

ORDER = ["ch1", "ch2", "ch3"]
ITEM = {"id": "X", "chapter": "ch3", "new_keywords": ["both hands"], "old_keywords": ["lost"]}


def row(ch, entity_id, value):
    return {"chapter_id": ch, "entity": "Tobias", "entity_id": entity_id, "canonical_name": "Tobias",
            "attribute": "body", "value": value, "source_quote": ""}


def test_diagnosis_names_the_failing_step():
    assert diagnose(ITEM, [row("ch1", 1, "lost left hand")], ORDER)["cause"] == "not read (later)"
    assert diagnose(ITEM, [row("ch3", 1, "clapped both hands")], ORDER)["cause"] == "not read (earlier)"
    assert diagnose(ITEM, [row("ch1", 1, "lost left hand"), row("ch3", 2, "both hands")], ORDER)["cause"] == "split"
    assert diagnose(ITEM, [row("ch1", 1, "lost left hand"), row("ch3", 1, "both hands")], ORDER)["cause"] == "checker"
    # an unrelated fact on the earlier side no longer counts as "recorded"
    assert diagnose(ITEM, [row("ch1", 1, "has a hand-drawn map"), row("ch3", 1, "both hands")], ORDER)["cause"] == "not read (earlier)"


def test_every_story_has_a_valid_answer_key():
    for folder in STORIES.iterdir():
        truth = json.loads((folder / "ground_truth.json").read_text())
        for chapter in truth["chapters"]:
            assert (folder / f"{chapter}.txt").exists(), f"{folder.name}: missing {chapter}.txt"
        for item in truth["planted"] + truth["decoys"]:
            assert item["chapter"] in truth["chapters"], f"{folder.name} {item['id']}: unknown chapter"
            assert item["new_keywords"] and item["entity_contains"]
        for item in truth["planted"]:
            assert item["old_keywords"], f"{folder.name} {item['id']}: planted mistakes need both sides"
        for item in truth["planted"]:
            assert item["type"] in ("attribute", "status", "timeline")
        # a perfect run on each story scores 100%
        flags = [perfect_flag(p) for p in truth["planted"]]
        s = score(flags, truth)
        assert s["recall"] == 1 and s["precision"] == 1, folder.name


def test_right_mistake_under_a_different_entity_name_counts():
    # T3: "Tobias arrived after the storm", filed under "the storm" instead of Tobias
    f = flag("ch5", "the storm", "timeline", new_quote="Tobias arrived the morning after the storm",
             conflicting_quote="Three days before the storm, Tobias Calloway arrived")
    s = score([f], TRUTH)
    assert s["correct"] == 1 and s["false_alarms"] == 0


def test_consistency_counts():
    from run_eval import catch_counts
    runs = [{"scores": {"missed": [{"id": "A1"}]}}, {"scores": {"missed": []}}, {"scores": {"missed": [{"id": "A1"}, {"id": "S3"}]}}]
    counts = catch_counts(runs, TRUTH)
    assert counts["A1"] == 1 and counts["S3"] == 2 and counts["A2"] == 3

"""The evaluation script's scoring logic (no database or AI needed)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from run_eval import score  # noqa: E402

TRUTH = json.loads((Path(__file__).resolve().parents[2] / "eval" / "ground_truth.json").read_text())


def flag(chapter, entity, kind, **text):
    base = {"new_chapter_id": chapter, "entity": entity, "contradiction_type": kind, "new_attribute": "",
            "new_value": "", "new_quote": "", "conflicting_value": "", "conflicting_quote": "", "explanation": ""}
    return {**base, **text}


def test_perfect_run_scores_one():
    flags = [flag(p["chapter"], p["entity_contains"][0], p["type"], explanation=p["keywords"][0]) for p in TRUTH["planted"]]
    s = score(flags, TRUTH)
    assert s["precision"] == 1 and s["recall"] == 1 and s["type_label_accuracy"] == 1 and not s["missed"]


def test_false_alarms_duplicates_and_misses():
    flags = [
        flag("ch4", "Keeper Calloway", "attribute", new_value="green", conflicting_value="grey"),   # A1 correct
        flag("ch4", "Ines Calloway", "attribute", explanation="eye colour green vs grey"),         # A1 duplicate
        flag("ch6", "Ines Calloway", "status", explanation="moved to the village"),               # decoy D1
    ]
    s = score(flags, TRUTH)
    assert s["correct"] == 1 and s["duplicates"] == 1 and s["false_alarms"] == 1
    assert s["decoys_triggered"] == ["D1"]
    assert s["precision"] == 0.5 and round(s["recall"], 3) == round(1 / 12, 3)


def test_wrong_chapter_does_not_count():
    s = score([flag("ch5", "Ines", "attribute", explanation="green eyes")], TRUTH)
    assert s["correct"] == 0

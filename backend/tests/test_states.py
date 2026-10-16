"""
Lasting states checked in code (states.py): no database, no AI. Wording from real Reader output
on the three test stories.
"""
from models import Fact
import states


def F(entity, attribute, value, quote="", entity_type="character"):
    return Fact(entity=entity, entity_type=entity_type, attribute=attribute, value=value,
                source_quote=quote or value, confidence=1.0)


def run(earlier, new, names, flashbacks=()):
    """earlier: [(chapter, entity name, Fact)]; new: [(entity name, Fact)] in chapter 9."""
    ids = {n.lower(): i for n, i in names.items()}
    rows = [{"fact_id": i, "entity_id": ids.get(e.lower()), "entity_type": f.entity_type, "entity": f.entity,
             "attribute": f.attribute, "value": f.value, "source_quote": f.source_quote,
             "chapter_id": f"ch{n}", "chapter_number": n} for i, (n, e, f) in enumerate(earlier)]
    objects = [r for r in rows if states.object_mentions(f"{r['value']} {r['source_quote']}")]
    new_facts = [(ids.get(e.lower()), e, f, i) for i, (e, f) in enumerate(new)]
    return states.check_states("ch9", 9, new_facts, objects,
                               lambda eid: [r for r in rows if r["entity_id"] == eid],
                               lambda name: ids.get(name.lower()), set(flashbacks))


RING = [(2, "Aurel", F("Aurel", "sat", "sat on the bed", "Aurel sat on the edge of the little bed and turned the signet ring on his finger")),
        (3, "Aurel", F("Aurel", "action", "pushed signet ring across table toward cousin",
                       "Then he took the signet ring of his father off his finger, set it on the table, and pushed it across the wood toward his cousin.")),
        (3, "Duke Corvin", F("Duke Corvin", "action", "slid the signet ring onto his own finger", "Duke Corvin slid the signet ring onto his own finger."))]
PEOPLE = {"Aurel": 1, "Duke Corvin": 2, "Corvin": 2, "signet ring": 3}


def test_a_ring_given_away_and_then_worn_again_is_caught():
    [w] = run(RING, [("Aurel", F("Aurel", "object_manipulation", "turned his father's signet ring",
                                 "He turned his father's signet ring on his finger, the crowned salt-hawk worn smooth."))], PEOPLE)
    assert w.source == "trait check" and w.contradiction_type == "status" and "gave the signet ring away" in w.explanation


def test_the_new_holder_wearing_it_and_a_hand_back_are_fine():
    corvin = [("Duke Corvin", F("Duke Corvin", "wears signet ring", "signet ring of the house of Oren on his finger",
                                "Duke Corvin sat in the king's chair with the signet ring of the house of Oren on his finger"))]
    assert run(RING, corvin, PEOPLE) == []
    back = [("Signet ring", F("Signet ring", "taken off finger", "taken off finger and held out across the table",
                              "Corvin took the signet ring off his finger and held it out across the table.", "item")),
            ("Aurel", F("Aurel", "description", "wears ferryman's coat and ring", "the ferryman's coat, and the ring"))]
    assert run(RING, back, PEOPLE) == []


def test_a_key_thrown_into_the_sea_and_used_later_is_caught_once():
    earlier = [(3, "Tobias", F("Tobias", "action", "threw the brass key into the sea", "he walked to the edge of the rocks and threw it into the sea"))]
    new = [("Ines", F("Ines", "action", "unlocked the lamp room with the old brass key each evening",
                      "Ines unlocked the lamp room with the old brass key")),
           ("Pip", F("Pip", "social tie", "student of Ines", "Ines unlocked the lamp room with the old brass key"))]
    [w] = run(earlier, new, {"Tobias": 1, "Ines": 2, "Pip": 3})
    assert "brass key" in w.explanation


def test_a_burned_ledger_read_later_is_caught_but_a_found_one_is_not():
    earlier = [(2, "green_ledger", F("green_ledger", "status", "burned_to_ash", "The green ledger burned to ash on the counter", "item"))]
    opened = [("Orla", F("Orla", "owns", "green ledger", "Crane opened Orla's green ledger, which lay on the counter"))]
    assert len(run(earlier, opened, {"Orla": 1, "Crane": 2})) == 1
    copy = [("Orla", F("Orla", "owns", "a new green ledger", "Crane opened the new green ledger Orla had copied"))]
    assert run(earlier, copy, {"Orla": 1, "Crane": 2}) == []


def test_remembering_an_object_is_not_using_it():
    earlier = [(3, "Tobias", F("Tobias", "action", "threw the brass key into the sea", "threw the brass key into the sea"))]
    new = [("Ines", F("Ines", "thought", "remembered the brass key", "She remembered unlocking the lamp room with the brass key"))]
    assert run(earlier, new, {"Tobias": 1, "Ines": 2}) == []


def test_blind_then_reading_is_caught_but_being_read_to_is_not():
    earlier = [(5, "Queen Liesl", F("Queen Liesl", "health", "nearly blind", "seventy-one years old and nearly blind"))]
    reads = [("Queen Liesl", F("Queen Liesl", "wrote_letter", "she had read every one of her son's letters twice by candlelight"))]
    [w] = run(earlier, reads, {"Queen Liesl": 1})
    assert "blind" in w.explanation
    read_to = [("Queen Liesl", F("Queen Liesl", "habit", "had the letters read to her by a sister"))]
    assert run(earlier, read_to, {"Queen Liesl": 1}) == []


def test_lost_left_hand_then_both_hands_is_caught():
    earlier = [(2, "Tobias", F("Tobias", "lost_left_hand", "lost left hand to a winch accident at sea many years ago"))]
    [w] = run(earlier, [("Tobias", F("Tobias", "action", "clapped both hands over the latch"))], {"Tobias": 1})
    assert "left hand" in w.explanation
    assert run(earlier, [("Tobias", F("Tobias", "action", "held the latch with his right hand"))], {"Tobias": 1}) == []


def test_nothing_is_flagged_inside_a_flashback():
    earlier = [(3, "Tobias", F("Tobias", "action", "threw the brass key into the sea", "threw the brass key into the sea"))]
    new = [("Ines", F("Ines", "action", "unlocked the lamp room with the brass key", "unlocked the lamp room with the brass key"))]
    assert run(earlier, new, {"Tobias": 1, "Ines": 2}, flashbacks={9}) == []

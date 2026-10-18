"""
Names linked by rule, without the AI (entities._titled_name_match): a title set aside.
From The Fallen King run of 18 Oct 2026, where "King Aurel" / "Aurel" and "Duke Corvin" /
"Corvin" stayed apart with the AI linking switched off, and T1 was missed.
"""
import entities


def known(*rows):
    return [{"id": i, "canonical_name": n, "entity_type": t, "aliases": [n]} for i, (n, t) in enumerate(rows, 1)]


PEOPLE = known(("King Aurel", "character"), ("Duke Corvin", "character"), ("Ines Calloway", "character"),
               ("Mara Calloway", "character"), ("Keeper Calloway", "character"), ("Ember", "other"))


def name_of(name, entity_type="character"):
    match = entities._titled_name_match(name, entity_type, PEOPLE)
    return match and match["canonical_name"]


def test_a_title_is_set_aside():
    assert name_of("Aurel") == "King Aurel"
    assert name_of("Corvin") == "Duke Corvin"
    assert name_of("Lady Mara") == "Mara Calloway"


def test_titles_alone_surnames_of_a_family_and_strangers_are_not_linked():
    assert name_of("Keeper") is None and name_of("the King") is None
    assert name_of("Calloway") is None            # Ines, Mara and the keeper are all Calloways
    assert name_of("King Oren") is None and name_of("Mira") is None
    assert name_of("Ember") is None               # a horse is not a person

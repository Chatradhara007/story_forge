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


def R(name, entity_id=None, canonical=None, entity_type="character"):
    return entities.Resolution(name, entity_type, entity_id, canonical or name, "new" if entity_id is None else "known name", 1.0)


def test_titled_and_bare_name_in_the_same_chapter_become_one_entry():
    """Fallen King ch1 says both 'King Aurel' and 'Aurel': two entries, so T1 was never compared."""
    results = {"king aurel": R("King Aurel"), "aurel": R("Aurel"), "corvin": R("Corvin")}
    entities.join_same_chapter_titled_names(results)
    assert results["aurel"].canonical_name == "King Aurel" and results["aurel"].is_new
    assert results["corvin"].canonical_name == "Corvin"          # no titled Corvin in this chapter


def test_a_known_bare_name_takes_in_the_new_titled_one():
    results = {"king aurel": R("King Aurel"), "aurel": R("Aurel", 7, "Aurel")}
    entities.join_same_chapter_titled_names(results)
    assert results["king aurel"].existing_entity_id == 7


def test_two_known_entries_or_two_titled_matches_are_left_alone():
    both = {"king aurel": R("King Aurel", 1), "aurel": R("Aurel", 2)}
    entities.join_same_chapter_titled_names(both)
    assert both["aurel"].existing_entity_id == 2
    two = {"king tam": R("King Tam"), "prince tam": R("Prince Tam"), "tam": R("Tam")}
    entities.join_same_chapter_titled_names(two)
    assert two["tam"].canonical_name == "Tam"

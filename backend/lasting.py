"""
Which facts can be CONTRADICTED later, and which simply change as a story moves on.

On realistic chapters (~900 words) the Reader records 60-90 facts per chapter, most of them
passing: actions, moods, plans, roles, where someone is, how full the granaries are. Comparing
new facts against all of them made false alarms and time grow with chapter length (The Fallen
King, 5 Oct 2026: 9-17 warnings per chapter, chapters with no planted mistake among them).

So EARLIER facts are only used as evidence when they can't simply change:
  - fixed traits: eye colour, scars, height, birthplace, family ties, names, ages, dates, counts;
  - lasting states: dead, blind, lost a hand, destroyed, thrown away, given away;
  - past events pinned to a time: "spent the whole night of the storm in the harbour office".
New facts of every kind are still checked against those ("dead, then barking").
Rules of thumb in English; checked against real facts from three stories (tests/test_lasting.py).
"""
import re

_PASSING_ATTRIBUTE = re.compile(
    r"(status|state|condition|action|activit|mood|emotion|feeling|thought|speech|said|says|dialogue|plan|intention|goal|desire|"
    r"opinion|belief|attitude|location|where|position|occupation|role|job|title|rank|routine|habit|behaviou?r|"
    r"weather|reaction|response|task|duty|purpose|current|state of mind|social tie|description|event|scene)", re.I)

_FIXED_ATTRIBUTE = re.compile(
    r"(eye|hair|beard|height|tall|build|scar|birth|born|origin|hometown|age|relation|sibling|brother|sister|"
    r"mother|father|parent|son|daughter|wife|husband|spouse|married|cousin|family|kin|name|handed|physical|"
    r"appearance|species|breed|colou?r|number|count|how many|date|day|year|season|month|when|time|duration|"
    r"tenure|founded|built|made of|material|injur|disab|blind|deaf|death|fate)", re.I)

# A value saying something that can't simply be undone, whatever the attribute is called.
_LASTING_VALUE = re.compile(
    r"\b(dead|died|dies|killed|drowned|buried|perished|deceased|destroyed|burned|burnt|ash|ashes|sank|sunk|"
    r"lost|missing|blind|deaf|lame|amputat\w*|scar|scarred|shattered|smashed|broken|thrown|threw|gave|given|"
    r"sold|handed over|born|never left|never once|always|whole night|all night|that night|night of|"
    r"mended|repaired|restored|healed|cured|rebuilt|seamless|"
    r"until dawn|since birth|for (?:\w+ ){0,2}years|years ago|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"spring|summer|autumn|winter|midsummer|midwinter)\b"
    # who has something, or where it was left: giving away and leaving behind last
    r"|\b(gave|handed|passed|pushed|slid|surrendered|returned|sold|traded)\b.{0,40}\b(to|across|over)\b"
    r"|\b(leave|leaves|left|leaving)\b.{0,30}\bbehind\b|\babandon\w*", re.I)

_COLOUR_OR_NUMBER = re.compile(
    r"\b(red|blue|green|grey|gray|black|white|brown|golden|gold|silver|chestnut|auburn|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|single|\d+)[- ]?\w*\b", re.I)


def is_lasting(attribute: str, value: str) -> bool:
    """Can this earlier fact be contradicted later (rather than just change)?"""
    attribute, value = attribute or "", value or ""
    if _LASTING_VALUE.search(value):
        return True
    if _PASSING_ATTRIBUTE.search(attribute) and not _FIXED_ATTRIBUTE.search(attribute):
        # "description | harbour's little red-painted launch": colours and counts in a
        # description are fixed details
        return bool(_COLOUR_OR_NUMBER.search(value)) and "description" in attribute.lower()
    # An attribute we don't recognise ("outcome", "result"): keep it as evidence, to be safe.
    return True

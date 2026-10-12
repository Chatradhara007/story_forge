"""
The classifier is tested on REAL facts the Reader extracted (copied from the evaluation reports'
"why missed" sections, Oct 2026). Every planted mistake's EARLIER fact must stay usable as
evidence; passing facts must not.
"""
import pytest
from lasting import is_lasting

EARLIER_SIDES_OF_PLANTED_MISTAKES = [
    # lighthouse
    ("physical_description", "lean and weathered, with grey eyes"),                    # A1 eyes
    ("family_relationship", "older brother"),                                          # A2
    ("description", "harbour's little red-painted launch"),                            # A3 red launch
    ("physical description", "broad man with a white beard to the second button"),     # A4 beard
    ("age", "ten years old"),                                                          # A5
    ("status", "dead"),                                                                # S1 Bramble
    ("physical injury", "lost his left hand to a winch accident at sea many years ago"),  # S2
    ("action", "walked to the edge of the rocks and threw the key into the sea"),      # S3
    ("action", "spent the whole night of the storm in the harbour office"),            # S4
    ("years as keeper", "twenty years"),                                               # T1
    ("day", "Tuesday night"),                                                          # T2
    ("time_reference", "Three days before the storm"),                                 # T3
    # glassmaker
    ("physical_description", "pale scar across her right palm"),                       # A1
    ("description", "a single furnace"),                                               # A2
    ("handedness", "left-handed"),                                                     # A3
    ("relationship", "younger sister"),                                                # A4
    ("physical_description", "tall, stooping man"),                                    # A5
    ("status", "drowned"),                                                             # S1
    ("status", "burned to ash on the counter"),                                        # S2
    ("physical_description", "thin, red-haired, lost two fingers of his left hand"),   # S3
    ("birthplace", "born in Varrow and never left it"),                                # T1
    ("age", "sixteen"),                                                                # T2
    ("time", "just after midnight"),                                                   # T3
    ("occurrence", "eve of the autumn Lantern Festival"),                              # T4
    ("state", "mended seamlessly by magic, whole again"),                              # S4 (a completed repair)
    # the fallen king (held out)
    ("physical description", "grey stallion"),                                         # A1 Ember
    ("injury", "pale scar across the back of his left hand"),                          # A2
    ("eye colour", "grey-green"),                                                      # A3
    ("relationship", "four years younger than him"),                                   # A4
    ("outcome", "of nine hundred and forty ships, sixty came home"),                   # A5
    ("action", "took the signet ring off his finger and pushed it across to his cousin"),  # S1 (gave)
    ("action", "had to leave Ember behind at the water gate"),                         # S2 (left behind)
    ("condition", "nearly blind"),                                                     # S3
    ("age", "thirty-five"),                                                            # T1
    ("timing", "in the second week of the autumn storms"),                             # T2
    ("age", "sixty-four"),                                                             # T3
]

PASSING = [
    ("action", "carried the lamp up the stairs"),
    ("mood", "angry and afraid"),
    ("location", "at the kitchen table"),
    ("plan", "build a thousand ships"),
    ("occupation", "ferryman"),
    ("role", "regent"),
    ("activity", "feeding the flame through the night"),
    ("speech", "said she would come back"),
    ("reaction", "laughed and kissed her hand"),
    ("status", "granaries full to the roof"),
    ("description", "quiet and sad in its own way"),
]


@pytest.mark.parametrize("attribute,value", EARLIER_SIDES_OF_PLANTED_MISTAKES)
def test_earlier_side_of_every_planted_mistake_stays_evidence(attribute, value):
    assert is_lasting(attribute, value)


@pytest.mark.parametrize("attribute,value", PASSING)
def test_passing_facts_are_not_evidence(attribute, value):
    assert not is_lasting(attribute, value)

"""Silver-dossier review (2026-09-25): page furniture and bobtalk mention fixes."""
from backend.dossier_anchors import _strip_page_furniture
from backend.dossier_fields import _bobtalk_mention_position


def test_singular_other_concert_header_and_its_list_are_stripped():
    notes = ("There was a fifteen minute intermission after Love Sick.\n"
             "Reviews from BobLinks.\n"
             "Other Bob Dylan concert in Esch-sur-Alzette, Luxembourg:\n"
             "21 October 2011\nRockhal\n22 April 2017\nRockhal\n"
             "Same setlist as 10 November.")
    assert _strip_page_furniture(notes) == (
        "There was a fifteen minute intermission after Love Sick.\n"
        "Same setlist as 10 November.")


def test_colon_header_without_date_list_keeps_following_notes():
    notes = ("Other Bob Dylan concerts in Chicago, Illinois:\n"
             "LB-numbers for this concert: LB-1630.")
    assert _strip_page_furniture(notes) == "LB-numbers for this concert: LB-1630."


def test_mention_ignores_commas_in_titles():
    setlist = [(25, "Don't Think Twice, It's All Right", ""), (26, "It's Alright, Ma", "")]
    text = "Bass guitar, Rob Stoner. This is called It's Alright Ma (I'm Only Bleeding)."
    assert _bobtalk_mention_position(text, setlist, set()) == 26

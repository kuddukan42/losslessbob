"""Tests for backend.bobtalk — locating Olof's bobtalk quotes (TODO-303).

No ASR here by design: the module takes decoded token sets, so the matching and
confidence rules are testable without faster-whisper installed.
"""
import sqlite3

import pytest

from backend import bobtalk


# ── tokenising ────────────────────────────────────────────────────────────────
def test_content_tokens_drops_stopwords_and_short_words():
    assert bobtalk.content_tokens("That was the song about a hurricane") == frozenset(
        {"song", "about", "hurricane"}
    )


def test_content_tokens_keeps_apostrophes_inside_words():
    assert "rollin'" in bobtalk.content_tokens("we're rollin' now")


def test_dice_is_zero_when_either_side_empty():
    assert bobtalk.dice(frozenset(), frozenset({"a"})) == 0.0


def test_dice_of_identical_sets_is_one():
    s = frozenset({"harmonica", "boston"})
    assert bobtalk.dice(s, s) == 1.0


# ── parsing ───────────────────────────────────────────────────────────────────
def test_parse_drops_catalogue_bleed_and_short_lines():
    """Olof's bobtalk field carries release lines in some events; not speech."""
    block = "\n".join([
        "Thank you everybody, we are going to play something for you now here",
        "Bootleg",
        "Some Release Title WMM 58/59.",
        "short",
    ])
    quotes = bobtalk.parse_bobtalk(block)
    assert len(quotes) == 1
    assert quotes[0].index == 0


def test_parse_indexes_are_contiguous_over_retained_quotes():
    block = "\n".join([
        "The first thing that was said on stage this evening in the hall",
        "CD 1",
        "The second thing that was said on stage much later that evening",
    ])
    assert [q.index for q in bobtalk.parse_bobtalk(block)] == [0, 1]


def test_parse_drops_quotes_with_too_few_content_tokens():
    # Long enough in characters, but almost all stopwords.
    assert bobtalk.parse_bobtalk("and the it is to be of that we in on at as so") == []


def test_parse_handles_none_and_empty():
    assert bobtalk.parse_bobtalk(None) == []
    assert bobtalk.parse_bobtalk("") == []


# ── matching ──────────────────────────────────────────────────────────────────
def _q(text):
    return bobtalk.parse_bobtalk(text)[0]


def test_match_picks_the_best_window_and_is_confident_when_separated():
    quote = _q("A few years back I was living in a hotel room out in Arizona")
    windows = [
        (10.0, bobtalk.content_tokens("completely unrelated chatter about parking")),
        (620.0, bobtalk.content_tokens("years back living hotel room Arizona")),
        (900.0, bobtalk.content_tokens("another thing entirely spoken here now")),
    ]
    m = bobtalk.match_quote(quote, windows)
    assert m.window_index == 1 and m.t_start == 620.0
    assert m.confident is True
    assert m.dice > m.runner_up * bobtalk.MIN_RATIO


def test_match_is_not_confident_when_runner_up_ties():
    """Every PoC failure tied its runner-up; that is the signature of no match."""
    quote = _q("We have a stage technical monitoring problem here tonight folks")
    tied = bobtalk.content_tokens("stage tonight")
    windows = [(10.0, tied), (500.0, tied)]
    m = bobtalk.match_quote(quote, windows)
    assert m.confident is False
    assert m.dice == pytest.approx(m.runner_up)


def test_match_is_not_confident_below_min_dice_even_if_unique():
    """A lone weak overlap is still noise, however much it beats the field."""
    quote = _q("A few years back I was living in a hotel room out in Arizona")
    windows = [
        (10.0, bobtalk.content_tokens("arizona " + " ".join(f"w{i}" for i in range(40)))),
        (99.0, frozenset({"zzz"})),
    ]
    m = bobtalk.match_quote(quote, windows)
    assert m.dice < bobtalk.MIN_DICE
    assert m.confident is False


def test_match_returns_none_without_windows():
    assert bobtalk.match_quote(_q("Something said aloud on the stage tonight here"), []) is None


def test_locate_quotes_returns_one_match_per_quote():
    block = "\n".join([
        "A few years back I was living in a hotel room out in Arizona",
        "There is a stage monitoring problem we are trying to fix now",
    ])
    quotes = bobtalk.parse_bobtalk(block)
    windows = [(5.0, bobtalk.content_tokens("years back living hotel room arizona")),
               (60.0, bobtalk.content_tokens("stage monitoring problem trying fix"))]
    matches = bobtalk.locate_quotes(quotes, windows)
    assert [m.quote_index for m in matches] == [0, 1]
    assert [m.window_index for m in matches] == [0, 1]


# ── persistence ───────────────────────────────────────────────────────────────
@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE olof_events (event_id INTEGER PRIMARY KEY, bobtalk TEXT)")
    c.execute("INSERT INTO olof_events VALUES (?, ?)",
              (7, "A few years back I was living in a hotel room out in Arizona\n"
                  "There is a stage monitoring problem we are trying to fix now"))
    yield c
    c.close()


def test_ensure_schema_is_idempotent(conn):
    bobtalk.ensure_schema(conn)
    bobtalk.ensure_schema(conn)          # must not raise on a second pass
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bobtalk_locations)")}
    assert {"lb_number", "event_id", "quote_index", "t_start", "confident", "model"} <= cols


def test_save_and_read_back_confident_only(conn):
    matches = [
        bobtalk.Match(0, 3, 620.0, 0.82, 0.17, True),
        bobtalk.Match(1, 9, 990.0, 0.10, 0.10, False),
    ]
    assert bobtalk.save_locations(conn, 212, 7, matches, model="large-v3") == 2
    rows = bobtalk.get_locations(conn, 212)
    assert len(rows) == 1
    assert rows[0]["quote_index"] == 0 and rows[0]["t_start"] == 620.0
    assert rows[0]["text"].startswith("A few years back")
    assert bobtalk.get_locations(conn, 212, confident_only=False) != rows


def test_resave_replaces_rather_than_duplicates(conn):
    """Re-locating with a better model must not leave stale timestamps behind."""
    bobtalk.save_locations(conn, 212, 7, [bobtalk.Match(0, 3, 620.0, 0.82, 0.17, True)])
    bobtalk.save_locations(conn, 212, 7, [bobtalk.Match(0, 4, 777.0, 0.90, 0.11, True)])
    rows = bobtalk.get_locations(conn, 212)
    assert len(rows) == 1 and rows[0]["t_start"] == 777.0


def test_get_locations_survives_olof_text_shrinking(conn):
    """A stored index that no longer resolves is skipped, not raised."""
    bobtalk.save_locations(conn, 212, 7, [bobtalk.Match(5, 1, 10.0, 0.9, 0.1, True)])
    assert bobtalk.get_locations(conn, 212) == []


def test_text_is_joined_from_olof_not_copied(conn):
    """The location row stores a reference; edits to Olof's text flow through."""
    bobtalk.save_locations(conn, 212, 7, [bobtalk.Match(0, 3, 620.0, 0.82, 0.17, True)])
    conn.execute("UPDATE olof_events SET bobtalk = ? WHERE event_id = 7",
                 ("Completely different words now recorded for this event here",))
    assert bobtalk.get_locations(conn, 212)[0]["text"].startswith("Completely different")

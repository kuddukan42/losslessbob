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


def test_parse_keeps_speech_containing_a_year_or_number():
    """Regression: an IGNORECASE catalogue pattern ate ordinary speech.

    "<2+ letters><number>" describes a catalogue code only when the letters are
    upper-case. Matched case-insensitively it also describes "In 1963", which
    silently discarded the strongest match on the 1978-12-16 PoC.
    """
    for line in ("Thank you, thank you. In 1963, I was living in a small room",
                 "We drove all the way down highway 61 to get here tonight now",
                 "There were about 200 people in that room on that evening"):
        assert bobtalk.is_metadata_line(line) is False
        assert len(bobtalk.parse_bobtalk(line)) == 1


def test_parse_still_drops_uppercase_catalogue_codes():
    assert bobtalk.is_metadata_line("Some Release Title WMM 58/59.") is True
    assert bobtalk.is_metadata_line("Disc 2 of the set") is True


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


# ── full-show windowing (TODO-303, second corpus pass) ────────────────────────
def test_windows_slide_with_overlap_and_cover_every_utterance():
    utts = [(t, t + 4.0, f"utterance number {i} spoken here") for i, t in
            enumerate(range(0, 200, 20))]
    wins = bobtalk.windows_from_utterances(utts, window_sec=80.0, hop_sec=40.0)
    starts = [t for t, _ in wins]
    assert starts == [0.0, 40.0, 80.0, 120.0, 160.0]
    # Overlap is the point: the 40s window carries speech the 0s window also saw.
    assert wins[0][1] & wins[1][1]


def test_windows_drop_silent_stretches():
    """A show's dead air must not cost a window — nothing was said there."""
    utts = [(0.0, 3.0, "opening words spoken plainly"), (600.0, 603.0, "closing remarks")]
    wins = bobtalk.windows_from_utterances(utts, window_sec=80.0, hop_sec=40.0)
    # 15 windows would tile 0-600s; only those actually holding speech survive.
    # Two per utterance, because overlapping windows both catch it.
    assert [t for t, _ in wins] == [0.0, 560.0, 600.0]


def test_windows_from_no_utterances_is_empty():
    assert bobtalk.windows_from_utterances([]) == []


def test_quote_straddling_a_window_cut_still_lands_whole_in_one_window():
    """The reason the hop is half the window."""
    quote = _q("A few years back I was living in a hotel room out in Arizona")
    # Speech split across the 80s cut: half at 70s, half at 85s.
    utts = [(70.0, 75.0, "a few years back I was living"),
            (85.0, 90.0, "in a hotel room out in Arizona")]
    wins = bobtalk.windows_from_utterances(utts, window_sec=80.0, hop_sec=40.0)
    m = bobtalk.match_quote(quote, wins, bobtalk.GEOM_FULL)
    assert m.dice > bobtalk.MIN_DICE


def test_gate_differs_by_geometry():
    """The two geometries are gated on different things, and only on one each."""
    assert bobtalk.gate_for(bobtalk.GEOM_BOUNDARIES) == (
        bobtalk.MIN_DICE, bobtalk.MIN_RATIO, 0.0)
    assert bobtalk.gate_for(bobtalk.GEOM_FULL) == (
        bobtalk.MIN_DICE_FULL, 0.0, bobtalk.WINDOW_SEC)
    # An unknown label must not silently get the loose gate.
    assert bobtalk.gate_for("something-new") == bobtalk.gate_for(bobtalk.GEOM_BOUNDARIES)


def test_full_show_gate_accepts_a_strong_match_with_a_close_runner_up():
    """The measured reason MIN_RATIO is off under full-show.

    Over ~160 sliding windows the runner-up is a maximum across far more noise
    draws than the ~25 disjoint boundary windows it was calibrated on, so real
    matches routinely beat it by only 1.1-1.7x. The boundary gate rejects this;
    the full-show gate accepts it on magnitude.
    """
    quote = _q("Ladies and gentlemen on the drums tonight from Kingston Jamaica Ian Wallace")
    utts = [(100.0, 106.0, "ladies and gentlemen on the drums tonight "
                           "from Kingston Jamaica Ian Wallace"),
            (2000.0, 2006.0, "ladies and gentlemen on the drums tonight give him a hand")]
    wins = bobtalk.windows_from_utterances(utts, window_sec=80.0, hop_sec=40.0)
    m = bobtalk.match_quote(quote, wins, bobtalk.GEOM_FULL)
    assert m.dice >= bobtalk.MIN_DICE_FULL
    assert m.runner_up > m.dice / bobtalk.MIN_RATIO      # would fail the boundary rule
    assert m.confident is True
    assert bobtalk.match_quote(quote, wins, bobtalk.GEOM_BOUNDARIES).confident is False


def test_full_show_gate_is_stricter_on_magnitude_than_the_boundary_gate():
    """Dropping the ratio rule is paid for by a higher Dice floor, not for free."""
    quote = _q("A few years back I was living in a hotel room out in Arizona")
    utts = [(100.0, 104.0, "living in a hotel room somewhere far away "
                           "tonight folks crowd noise here")]
    wins = bobtalk.windows_from_utterances(utts, window_sec=80.0, hop_sec=40.0)
    m = bobtalk.match_quote(quote, wins, bobtalk.GEOM_FULL)
    assert bobtalk.MIN_DICE <= m.dice < bobtalk.MIN_DICE_FULL
    assert m.confident is False
    # The same evidence clears the boundary gate: no rival, and over MIN_DICE.
    assert bobtalk.match_quote(quote, wins, bobtalk.GEOM_BOUNDARIES).confident is True


def test_separation_still_shapes_the_reported_runner_up():
    """It no longer gates, but it is kept as provenance for re-gating later.

    Without it the runner-up is the winner's own overlapping neighbour scoring
    the same speech, which says nothing about how alone the match is.
    """
    quote = _q("A few years back I was living in a hotel room out in Arizona")
    # 150s, not 100s: the first window starts at the first utterance, so speech
    # a hop or more in is what actually lands in two overlapping windows.
    utts = [(50.0, 52.0, "some earlier remark"),
            (150.0, 156.0, "a few years back living in a hotel room out in Arizona"),
            (900.0, 903.0, "entirely different chatter about the parking lot")]
    wins = bobtalk.windows_from_utterances(utts, window_sec=80.0, hop_sec=40.0)
    near = bobtalk.match_quote(quote, wins, bobtalk.GEOM_BOUNDARIES)
    far = bobtalk.match_quote(quote, wins, bobtalk.GEOM_FULL)
    assert near.dice == pytest.approx(near.runner_up)   # its own neighbour
    assert far.runner_up < far.dice


def test_a_tied_rival_elsewhere_in_the_show_is_still_reported():
    """Exclusion is local: a competing window far away survives into runner_up."""
    quote = _q("We have a stage technical monitoring problem here tonight folks")
    tied = "stage technical monitoring problem tonight"
    utts = [(100.0, 104.0, tied), (2000.0, 2004.0, tied)]
    wins = bobtalk.windows_from_utterances(utts, window_sec=80.0, hop_sec=40.0)
    m = bobtalk.match_quote(quote, wins, bobtalk.GEOM_FULL)
    assert m.dice == pytest.approx(m.runner_up)


def test_geometry_is_stored_and_backfilled_for_pre_existing_rows(conn):
    """Rows written before the column existed are the boundary pass, by definition."""
    conn.execute("""CREATE TABLE bobtalk_locations (
        lb_number INTEGER NOT NULL, event_id INTEGER NOT NULL,
        quote_index INTEGER NOT NULL, t_start REAL NOT NULL, dice REAL NOT NULL,
        runner_up REAL NOT NULL, confident INTEGER NOT NULL, model TEXT,
        located_at TIMESTAMP, PRIMARY KEY (lb_number, event_id, quote_index))""")
    conn.execute("INSERT INTO bobtalk_locations VALUES (212,7,0,620.0,0.8,0.1,1,'large-v3',NULL)")
    bobtalk.ensure_schema(conn)
    assert conn.execute("SELECT geometry FROM bobtalk_locations").fetchone()[0] == \
        bobtalk.GEOM_BOUNDARIES

    bobtalk.save_locations(conn, 213, 7, [bobtalk.Match(0, 1, 10.0, 0.9, 0.1, True)],
                           model="large-v3", geometry=bobtalk.GEOM_FULL)
    assert conn.execute("SELECT geometry FROM bobtalk_locations WHERE lb_number = 213"
                        ).fetchone()[0] == bobtalk.GEOM_FULL

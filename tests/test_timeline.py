"""
Tests for the Timeline navigator backend (backend/timeline.py,
instructions/FABLE_TIMELINE.md).

Covers:
  - GRADE_RANK / _best_grade()  — letter-grade ordinal, min() wins
  - get_summary()                — decade totals, olof_events-absent degrade
  - get_decade_detail()          — per-tour breakdown, boundary attribution
  - get_tour_detail()            — per-night breakdown, decade scoping
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with full schema. Returns (db_path, conn, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_timeline_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.db as _db
    import backend.paths as _paths
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)

    _db.init_db(db_path)
    conn = _db.get_connection(db_path)
    return db_path, conn, tmp_dir


def _insert_olof_event(conn, event_id, date_str, event_type="concert", **kwargs):
    page_filename = f"page_{event_id}.html"
    conn.execute(
        "INSERT OR IGNORE INTO olof_pages (filename, url, corpus) VALUES (?, 'http://x', 'dsn')",
        (page_filename,),
    )
    fields = {
        "venue": "Some Hall",
        "city": "Some City",
        "region": "",
        "country": "USA",
        "tour_name": "",
        "recording_kind": "",
        "recording_mins": None,
        **kwargs,
    }
    conn.execute(
        """INSERT INTO olof_events
           (event_id, page_filename, event_type, date_str, venue, city, region,
            country, tour_name, recording_kind, recording_mins)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id, page_filename, event_type, date_str,
            fields["venue"], fields["city"], fields["region"], fields["country"],
            fields["tour_name"], fields["recording_kind"], fields["recording_mins"],
        ),
    )


def _insert_entry(conn, lb_number, date_str, rating="", lb_status="public", entry_status="ok"):
    conn.execute(
        "INSERT INTO entries (lb_number, date_str, rating, status) VALUES (?, ?, ?, ?)",
        (lb_number, date_str, rating, entry_status),
    )
    conn.execute(
        "INSERT INTO lb_master (lb_number, lb_status) VALUES (?, ?)",
        (lb_number, lb_status),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. GRADE_RANK / _best_grade() — pure, no DB
# ═══════════════════════════════════════════════════════════════════════════════

class TestBestGrade:
    def test_grade_order_a_plus_is_best(self):
        from backend.timeline import GRADE_RANK
        assert GRADE_RANK["A+"] == 0
        assert GRADE_RANK["F"] == 12
        assert GRADE_RANK["A+"] < GRADE_RANK["A"] < GRADE_RANK["B+"]

    def test_best_of_multiple_grades_wins(self):
        from backend.timeline import _best_grade
        assert _best_grade(["B", "A-", "C+"]) == "A-"

    def test_ungraded_only_returns_none(self):
        from backend.timeline import _best_grade
        assert _best_grade(["", "not-a-grade"]) is None

    def test_empty_list_returns_none(self):
        from backend.timeline import _best_grade
        assert _best_grade([]) is None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. get_summary()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetSummary:
    def test_unavailable_when_olof_events_absent(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute("DROP TABLE olof_events")
            conn.commit()
            from backend.timeline import get_summary
            result = get_summary(db_path=db_path)
            assert result["available"] is False
            assert result["decades"] == []
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_night_and_circulating_counts_per_decade(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-01-01", tour_name="1975 Tour")
            _insert_entry(conn, 101, "1/1/75", rating="A")

            _insert_olof_event(conn, 2, "1975-06-01", tour_name="1975 Tour")
            # No entry -- gap night, not circulating.

            _insert_olof_event(conn, 3, "1988-01-01", tour_name="1988 Tour")
            _insert_entry(conn, 102, "1/1/88", rating="B-")
            conn.commit()

            from backend.timeline import get_summary
            result = get_summary(db_path=db_path)
            assert result["available"] is True
            by_decade = {d["decade"]: d for d in result["decades"]}

            assert by_decade[1970]["label"] == "1970s"
            assert by_decade[1970]["night_count"] == 2
            assert by_decade[1970]["circulating_count"] == 1
            assert by_decade[1970]["best_grade"] == "A"

            assert by_decade[1980]["night_count"] == 1
            assert by_decade[1980]["circulating_count"] == 1
            assert by_decade[1980]["best_grade"] == "B-"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_nonexistent_lb_number_night_has_no_grade(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-12-04", tour_name="1975 Tour")
            _insert_entry(conn, 101, "12/4/75", rating="A", lb_status="nonexistent")
            conn.commit()

            from backend.timeline import get_summary
            result = get_summary(db_path=db_path)
            by_decade = {d["decade"]: d for d in result["decades"]}
            assert by_decade[1970]["circulating_count"] == 0
            assert by_decade[1970]["best_grade"] is None
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_private_entry_counts_and_contributes_grade(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-12-04", tour_name="1975 Tour")
            _insert_entry(
                conn, 101, "12/4/75", rating="B+",
                lb_status="private", entry_status="private",
            )
            conn.commit()

            from backend.timeline import get_summary
            result = get_summary(db_path=db_path)
            by_decade = {d["decade"]: d for d in result["decades"]}
            assert by_decade[1970]["circulating_count"] == 1
            assert by_decade[1970]["best_grade"] == "B+"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_two_show_date_counts_as_one_night(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1978-06-05", tour_name="1978 Tour", venue="Afternoon")
            _insert_olof_event(conn, 2, "1978-06-05", tour_name="1978 Tour", venue="Evening")
            conn.commit()

            from backend.timeline import get_summary
            result = get_summary(db_path=db_path)
            by_decade = {d["decade"]: d for d in result["decades"]}
            assert by_decade[1970]["night_count"] == 1
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. get_decade_detail()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetDecadeDetail:
    def test_decade_with_multiple_tours(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-01-10", tour_name="Rolling Thunder Revue")
            _insert_olof_event(conn, 2, "1975-01-15", tour_name="Rolling Thunder Revue")
            _insert_olof_event(conn, 3, "1978-06-01", tour_name="1978 World Tour")
            conn.commit()

            from backend.timeline import get_decade_detail
            result = get_decade_detail(1970, db_path=db_path)
            assert result["available"] is True
            assert result["label"] == "1970s"
            tours_by_name = {t["tour_name"]: t for t in result["tours"]}
            assert set(tours_by_name) == {"Rolling Thunder Revue", "1978 World Tour"}
            assert tours_by_name["Rolling Thunder Revue"]["night_count"] == 2
            assert tours_by_name["Rolling Thunder Revue"]["start_date"] == "1975-01-10"
            assert tours_by_name["Rolling Thunder Revue"]["end_date"] == "1975-01-15"
            assert tours_by_name["1978 World Tour"]["night_count"] == 1
            # Sorted by start_date.
            assert [t["tour_name"] for t in result["tours"]] == [
                "Rolling Thunder Revue", "1978 World Tour",
            ]
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_tour_circulating_count_counts_held_tapes_not_grades(self):
        """circulating_count reflects nights with a held tape, independent of
        whether they are graded -- so an ungraded-but-circulating tour is
        distinguishable from a true no-tape tour, same three-state rule as
        the decade and night tiers. See coordinator amendment (B4)."""
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-02-01", tour_name="Mixed Tour")
            _insert_olof_event(conn, 2, "1975-02-02", tour_name="Mixed Tour")
            _insert_olof_event(conn, 3, "1975-02-03", tour_name="Mixed Tour")
            _insert_entry(conn, 101, "2/1/75", rating="A")           # graded, held
            _insert_entry(conn, 102, "2/2/75", rating="")            # held, ungraded
            _insert_entry(conn, 103, "2/3/75", rating="A",
                          lb_status="nonexistent")                   # no tape
            conn.commit()

            from backend.timeline import get_decade_detail
            tour = get_decade_detail(1970, db_path=db_path)["tours"][0]
            assert tour["night_count"] == 3
            assert tour["circulating_count"] == 2
            assert tour["best_grade"] == "A"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_tour_spanning_boundary_attributed_to_earlier_decade(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1979-12-30", tour_name="Boundary Tour")
            _insert_olof_event(conn, 2, "1980-01-05", tour_name="Boundary Tour")
            conn.commit()

            from backend.timeline import get_decade_detail
            result_1970s = get_decade_detail(1970, db_path=db_path)
            names_1970s = [t["tour_name"] for t in result_1970s["tours"]]
            assert "Boundary Tour" in names_1970s
            tour = next(t for t in result_1970s["tours"] if t["tour_name"] == "Boundary Tour")
            assert tour["night_count"] == 2
            assert tour["end_date"] == "1980-01-05"

            result_1980s = get_decade_detail(1980, db_path=db_path)
            names_1980s = [t["tour_name"] for t in result_1980s["tours"]]
            assert "Boundary Tour" not in names_1980s
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_empty_when_olof_events_absent(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute("DROP TABLE olof_events")
            conn.commit()
            from backend.timeline import get_decade_detail
            result = get_decade_detail(1970, db_path=db_path)
            assert result == {"available": False, "decade": 1970, "label": "1970s", "tours": []}
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. get_tour_detail()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetTourDetail:
    def test_night_with_multiple_grades_best_wins(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(
                conn, 1, "1975-01-10", tour_name="Rolling Thunder Revue",
                venue="Hall A", city="City A",
            )
            _insert_entry(conn, 101, "1/10/75", rating="C")
            _insert_entry(conn, 102, "1/10/75", rating="A-")
            conn.commit()

            from backend.timeline import get_tour_detail
            result = get_tour_detail("Rolling Thunder Revue", 1970, db_path=db_path)
            assert result["available"] is True
            assert len(result["nights"]) == 1
            night = result["nights"][0]
            assert night["date_iso"] == "1975-01-10"
            assert night["venue"] == "Hall A"
            assert night["city"] == "City A"
            assert night["best_grade"] == "A-"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_nonexistent_only_night_is_no_tape(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-01-10", tour_name="Rolling Thunder Revue")
            _insert_entry(conn, 101, "1/10/75", rating="A", lb_status="nonexistent")
            conn.commit()

            from backend.timeline import get_tour_detail
            result = get_tour_detail("Rolling Thunder Revue", 1970, db_path=db_path)
            assert len(result["nights"]) == 1
            assert result["nights"][0]["best_grade"] is None
            assert result["nights"][0]["circulating"] is False
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_held_but_ungraded_night_circulates_without_a_grade(self):
        """A non-nonexistent entry with an empty rating still means a dossier
        exists for that night -- circulating must be True even though
        best_grade is None, distinct from a true no-tape/nonexistent-only
        night where circulating is False. See coordinator amendment: the
        binary best_grade-only model can't express this third state."""
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-01-10", tour_name="Rolling Thunder Revue")
            _insert_entry(conn, 101, "1/10/75", rating="")
            conn.commit()

            from backend.timeline import get_tour_detail
            result = get_tour_detail("Rolling Thunder Revue", 1970, db_path=db_path)
            assert len(result["nights"]) == 1
            assert result["nights"][0]["best_grade"] is None
            assert result["nights"][0]["circulating"] is True
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_private_entry_contributes_grade(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-01-10", tour_name="Rolling Thunder Revue")
            _insert_entry(
                conn, 101, "1/10/75", rating="B",
                lb_status="private", entry_status="private",
            )
            conn.commit()

            from backend.timeline import get_tour_detail
            result = get_tour_detail("Rolling Thunder Revue", 1970, db_path=db_path)
            assert result["nights"][0]["best_grade"] == "B"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_tape_night_has_no_dossier_worthy_grade(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-01-10", tour_name="Rolling Thunder Revue")
            conn.commit()

            from backend.timeline import get_tour_detail
            result = get_tour_detail("Rolling Thunder Revue", 1970, db_path=db_path)
            assert result["nights"][0]["best_grade"] is None
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_wrong_decade_scope_returns_empty(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1975-01-10", tour_name="Rolling Thunder Revue")
            conn.commit()

            from backend.timeline import get_tour_detail
            result = get_tour_detail("Rolling Thunder Revue", 1980, db_path=db_path)
            assert result["available"] is True
            assert result["nights"] == []
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_boundary_tour_nights_include_the_later_decade(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_olof_event(conn, 1, "1979-12-30", tour_name="Boundary Tour")
            _insert_olof_event(conn, 2, "1980-01-05", tour_name="Boundary Tour")
            conn.commit()

            from backend.timeline import get_tour_detail
            result = get_tour_detail("Boundary Tour", 1970, db_path=db_path)
            dates = [n["date_iso"] for n in result["nights"]]
            assert dates == ["1979-12-30", "1980-01-05"]
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_empty_when_olof_events_absent(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            conn.execute("DROP TABLE olof_events")
            conn.commit()
            from backend.timeline import get_tour_detail
            result = get_tour_detail("Any Tour", 1970, db_path=db_path)
            assert result["available"] is False
            assert result["nights"] == []
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

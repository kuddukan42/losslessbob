"""Tests for find_lb_folders's no-audio-folder exclusion.

Regression for the 1989-08-26 / 1989-09-01 / 1989-09-03 crashes: my_collection
pointed at folders that exist on disk but contain only text/image/md5 files
(no audio). find_lb_folders included them as sources anyway, and
ingest.concat_source then raised ValueError("no audio in ...") for the whole
date — even though other folders for the same date had real audio.

find_lb_folders should drop such folders the same way it already drops
private/no-torrent folders, with a printed exclusion message.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tapematch_session as sess  # noqa: E402


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "losslessbob.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE my_collection (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lb_number INTEGER NOT NULL UNIQUE,
            folder_name TEXT NOT NULL,
            disk_path TEXT NOT NULL
        )"""
    )
    conn.commit()
    conn.close()
    return db_path


def test_no_audio_folder_excluded(tmp_path, monkeypatch, capsys):
    audio_folder = tmp_path / "1989-08-26 Houston, Texas, The Summit (LB-05845)"
    audio_folder.mkdir()
    (audio_folder / "01 Track.flac").write_bytes(b"fake-flac-data")

    text_only_folder = tmp_path / "1989-08-26 The Summit Houston, Texas (LB-01430)"
    text_only_folder.mkdir()
    (text_only_folder / "lbdir-bd89-08-26_Houston.txt").write_text("notes")
    (text_only_folder / "lbdir-bd89-08-26_Houston.md5").write_text("checksum")

    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO my_collection (lb_number, folder_name, disk_path) VALUES (?,?,?)",
        (5845, audio_folder.name, str(audio_folder)),
    )
    conn.execute(
        "INSERT INTO my_collection (lb_number, folder_name, disk_path) VALUES (?,?,?)",
        (1430, text_only_folder.name, str(text_only_folder)),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(sess, "DB_PATH", db_path)
    monkeypatch.setattr(sess, "SEARCH_ROOTS", [])

    found = sess.find_lb_folders([1430, 5845], "1989")

    assert 5845 in found
    assert 1430 not in found
    assert "Excluded (no audio found): LB-01430" in capsys.readouterr().out


def test_all_audio_folders_kept(tmp_path, monkeypatch, capsys):
    folder_a = tmp_path / "a (LB-00001)"
    folder_a.mkdir()
    (folder_a / "01.flac").write_bytes(b"fake-flac-data")

    folder_b = tmp_path / "b (LB-00002)"
    folder_b.mkdir()
    (folder_b / "01.flac").write_bytes(b"fake-flac-data")

    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO my_collection (lb_number, folder_name, disk_path) VALUES (?,?,?)",
        (1, folder_a.name, str(folder_a)),
    )
    conn.execute(
        "INSERT INTO my_collection (lb_number, folder_name, disk_path) VALUES (?,?,?)",
        (2, folder_b.name, str(folder_b)),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(sess, "DB_PATH", db_path)
    monkeypatch.setattr(sess, "SEARCH_ROOTS", [])

    found = sess.find_lb_folders([1, 2], "2026")

    assert set(found) == {1, 2}
    assert "Excluded (no audio found)" not in capsys.readouterr().out

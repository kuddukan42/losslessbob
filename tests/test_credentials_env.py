"""Environment/env-file credential fallback used by headless callers (cron)."""
import importlib

import pytest


@pytest.fixture
def creds(monkeypatch, tmp_path):
    """Fresh credentials module with the keyring disabled and no env file."""
    import backend.credentials as mod
    mod = importlib.reload(mod)
    monkeypatch.setattr(mod, "_keyring_ok", False)
    monkeypatch.setattr(mod, "_SECRETS_DIR", tmp_path / "no-secrets")
    monkeypatch.setenv("LB_CREDENTIALS_FILE", str(tmp_path / "credentials.env"))
    return mod


def test_env_vars_win_when_keyring_is_dead(creds, monkeypatch):
    monkeypatch.setenv("LB_TUIT_USER", "kuddukan")
    monkeypatch.setenv("LB_TUIT_PASSWORD", "hunter2")
    assert creds.get_credentials(creds.SERVICE_TUIT) == ("kuddukan", "hunter2")
    assert creds.credentials_stored(creds.SERVICE_TUIT)


def test_env_file_is_parsed(creds, tmp_path):
    (tmp_path / "credentials.env").write_text(
        "# comment\n"
        "\n"
        'export LB_TUIT_USER="kuddukan"\n'
        "LB_TUIT_PASSWORD='p@ss=word#1'\n"
        "malformed line\n"
    )
    assert creds.get_credentials(creds.SERVICE_TUIT) == ("kuddukan", "p@ss=word#1")


def test_process_env_overrides_the_file(creds, tmp_path, monkeypatch):
    (tmp_path / "credentials.env").write_text("LB_TUIT_USER=fromfile\nLB_TUIT_PASSWORD=filepw\n")
    monkeypatch.setenv("LB_TUIT_USER", "fromenv")
    monkeypatch.setenv("LB_TUIT_PASSWORD", "envpw")
    assert creds.get_credentials(creds.SERVICE_TUIT) == ("fromenv", "envpw")


def test_env_file_is_read_as_utf8(creds, tmp_path):
    (tmp_path / "credentials.env").write_bytes(
        "LB_TUIT_USER=bob\nLB_TUIT_PASSWORD=café\n".encode()
    )
    assert creds.get_credentials(creds.SERVICE_TUIT) == ("bob", "café")


def test_cp1252_env_file_decodes_instead_of_raising(creds, tmp_path):
    """A legacy-editor \\x92 apostrophe used to raise UnicodeDecodeError (BUG-369)."""
    (tmp_path / "credentials.env").write_bytes(b"LB_TUIT_USER=bob\nLB_TUIT_PASSWORD=it\x92s\n")
    assert creds.get_credentials(creds.SERVICE_TUIT) == ("bob", "it’s")


def test_missing_file_is_not_an_error(creds):
    assert creds.get_credentials(creds.SERVICE_TUIT) == ("", "")
    assert not creds.credentials_stored(creds.SERVICE_TUIT)


def test_session_cache_still_wins(creds, monkeypatch):
    monkeypatch.setenv("LB_TUIT_USER", "fromenv")
    monkeypatch.setenv("LB_TUIT_PASSWORD", "envpw")
    creds.save_credentials(creds.SERVICE_TUIT, "session", "sessionpw")
    assert creds.get_credentials(creds.SERVICE_TUIT) == ("session", "sessionpw")

"""Tests for backend.app._github_upload_asset / _ProgressFile (TODO-367 S4)."""

import queue

from backend.app import _github_upload_asset


class _FakeResp:
    def raise_for_status(self) -> None:
        pass


class _FakeReq:
    def __init__(self) -> None:
        self.calls = []

    def post(self, url, params, data, headers, timeout):
        # requests reads the body to EOF; mimic that so progress fires.
        while data.read():
            pass
        self.calls.append((url, params, headers, data))
        return _FakeResp()


def test_upload_sends_length_reports_progress_and_closes(tmp_path):
    f = tmp_path / "asset.bin"
    f.write_bytes(b"x" * ((1 << 20) + 10))
    req, ev_q = _FakeReq(), queue.Queue()

    _github_upload_asset(req, "https://up/assets", "tok", f, "asset.bin", ev_q)

    url, params, headers, body = req.calls[0]
    assert url == "https://up/assets"
    assert params == {"name": "asset.bin"}
    assert headers["Content-Length"] == str((1 << 20) + 10)
    assert headers["Authorization"] == "token tok"
    events = [ev_q.get_nowait() for _ in range(ev_q.qsize())]
    assert [e["pct"] for e in events] == [99, 100]
    assert body._fh.closed

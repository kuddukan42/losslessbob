"""GitHub release-asset upload with progress events (shared by master publish and data
package export; moved out of app.py for TODO-369)."""

import os
from pathlib import Path


class _ProgressFile:
    """Read-only file wrapper that reports upload progress to an event queue.

    A plain generator has no ``__len__``, so requests can't determine
    Content-Length and falls back to Transfer-Encoding: chunked — which
    uploads.github.com rejects with a 400 Bad Request. A file-like object with
    ``__len__`` lets requests send a real Content-Length while still reporting
    progress via ``read()``.
    """

    def __init__(self, path: "str | Path", label: str, ev_q) -> None:
        self._fh = open(path, "rb")  # noqa: SIM115 — closed via close()/__exit__
        self._size = os.path.getsize(path)
        self._label = label
        self._ev_q = ev_q
        self._sent = 0

    def __len__(self) -> int:
        return self._size

    def __enter__(self) -> "_ProgressFile":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def read(self, _amt: int = -1) -> bytes:
        chunk = self._fh.read(1 << 20)  # 1 MB chunks
        if chunk:
            self._sent += len(chunk)
            pct = int(self._sent * 100 / self._size) if self._size else 100
            self._ev_q.put({
                "type": "progress",
                "label": (
                    f"Uploading {self._label}… {pct}%"
                    f"  ({self._sent / (1 << 20):.1f} / {self._size / (1 << 20):.0f} MB)"
                ),
                "pct": pct,
            })
        return chunk

    def close(self) -> None:
        self._fh.close()


def _github_upload_asset(
    req, upload_base: str, token: str, path: "str | Path", label: str, ev_q
) -> None:
    """Upload one file as a GitHub release asset, streaming progress to *ev_q*.

    Args:
        req: the ``requests`` module (imported lazily by callers).
        upload_base: release ``upload_url`` with its URI template stripped.
        token: GitHub token.
        path: file to upload; its basename becomes the asset name.
        label: name shown in progress events.
        ev_q: queue receiving ``{"type": "progress", ...}`` dicts.

    Raises:
        requests.HTTPError: when GitHub rejects the upload.
    """
    with _ProgressFile(path, label, ev_q) as body:
        up = req.post(
            upload_base,
            params={"name": Path(path).name},
            data=body,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(body)),
            },
            timeout=600,
        )
    up.raise_for_status()

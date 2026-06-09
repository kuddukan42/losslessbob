#!/usr/bin/env python3
"""Standalone Flask backend launcher — no GUI required.

Use this for LAN/phone access when you don't need the PyQt6 GUI.
The Restart Server button on the admin page will restart only the
Flask server; this process stays alive between restarts.

Usage:
    python run_backend.py [--port PORT]
    # or
    .venv/bin/python run_backend.py
"""
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.app import create_app, set_restart_callback
from backend.paths import ensure_data_dirs

_srv = None
_restart_flag = False


def _request_restart() -> None:
    """Callback invoked by admin_restart route — signals the serve loop to recycle."""
    global _restart_flag
    _restart_flag = True
    if _srv is not None:
        _srv.shutdown()


def main() -> None:
    global _srv, _restart_flag

    parser = argparse.ArgumentParser(prog="run_backend")
    parser.add_argument("--port", type=int, default=5174,
                        help="Port to listen on (default: 5174)")
    args = parser.parse_args()
    port = args.port

    ensure_data_dirs()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logging.getLogger("backend").setLevel(logging.DEBUG)

    # Register before create_app so the route has the callback from the start.
    set_restart_callback(_request_restart)

    from werkzeug.serving import make_server

    while True:
        _restart_flag = False
        app = create_app()
        logging.getLogger("werkzeug").setLevel(logging.WARNING)

        _srv = make_server("0.0.0.0", port, app, threaded=True)
        print(f"LosslessBob backend ready on :{port}", flush=True)
        _srv.serve_forever()
        _srv.server_close()

        if not _restart_flag:
            break

        print("Restarting backend…", flush=True)
        time.sleep(0.5)


if __name__ == "__main__":
    main()

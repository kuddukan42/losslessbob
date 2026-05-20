#!/usr/bin/env python3
"""
Headless CLI for LosslessBob. Starts Flask without PyQt6.
Usage:
  python cli.py lookup <file_or_glob> [--json]
  python cli.py search <query> [--field all|location|date|description] [--json]
  python cli.py stats [--json]
  python cli.py import <path_to_flat_file>
  python cli.py serve [--port 5174]
"""
import argparse
import json
import sys
import threading
from pathlib import Path


def _start_flask(port):
    import sys
    from backend.app import create_app
    from backend.paths import ensure_data_dirs
    ensure_data_dirs()
    flask_app = create_app()
    if sys.platform == "win32":
        try:
            from waitress import serve as _serve
            _serve(flask_app, host="127.0.0.1", port=port, threads=4)
        except ImportError:
            flask_app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    else:
        flask_app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def main():
    parser = argparse.ArgumentParser(prog="losslessbob")
    parser.add_argument("--port", type=int, default=5174)
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    p_lookup = sub.add_parser("lookup")
    p_lookup.add_argument("paths", nargs="+")

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--field", default="all",
                          choices=["all", "location", "date", "description"])

    sub.add_parser("stats")

    p_import = sub.add_parser("import")
    p_import.add_argument("path")

    sub.add_parser("serve")

    args = parser.parse_args()
    port = args.port

    # Start Flask in a daemon thread for non-serve commands
    if args.command != "serve":
        t = threading.Thread(target=_start_flask, args=(port,), daemon=True)
        t.start()
        import socket, time
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)

    import requests

    if args.command == "serve":
        _start_flask(port)  # Blocking

    elif args.command == "stats":
        r = requests.get(f"http://127.0.0.1:{port}/api/db/stats").json()
        print(json.dumps(r, indent=2) if args.json else
              f"LB entries: {r['total_lb_numbers']}  "
              f"Checksums: {r['total_checksums']}  "
              f"Latest LB: {r['latest_lb']}  "
              f"Last import: {r['last_import']}")

    elif args.command == "lookup":
        text_parts = []
        for pattern in args.paths:
            for p in Path(".").glob(pattern) if "*" in pattern else [Path(pattern)]:
                if p.is_file():
                    text_parts.append(p.read_text(errors="replace"))
        text = "\n".join(text_parts)
        r = requests.post(f"http://127.0.0.1:{port}/api/lookup",
                          json={"text": text}).json()
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            for lb in r.get("summary", {}).get("lb_summary", []):
                print(f"LB-{lb['lb_number']:05d}  {lb['status']:25s}  "
                      f"matched={lb['matched']}  missing={lb['missing_from_set']}")

    elif args.command == "search":
        r = requests.get(f"http://127.0.0.1:{port}/api/search",
                         params={"q": args.query, "field": args.field}).json()
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            for e in r:
                print(f"LB-{e['lb_number']:05d}  {e.get('date_str',''):12s}  "
                      f"{e.get('location','')[:50]}")

    elif args.command == "import":
        r = requests.post(f"http://127.0.0.1:{port}/api/db/import",
                          json={"file_path": str(Path(args.path).resolve())}).json()
        print(json.dumps(r, indent=2) if args.json else str(r))


if __name__ == "__main__":
    main()

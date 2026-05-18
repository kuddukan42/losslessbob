# Plan: Web GUI Component (Alongside PyQt6 Desktop App)

## Context
LosslessBob is a PyQt6 desktop app with a fully separate Flask REST API already running on port 5174. The goal is to add a web-based GUI that runs alongside the desktop app — served by the same Flask process — so users can access the app from a browser on the same machine or LAN, without replacing the desktop UI.

## Key Finding
The Flask backend already exposes 40+ REST endpoints. Adding web UI is purely additive — no backend changes needed except to serve static files.

## Recommended Approach

### How It Works
- Flask already runs on port 5174 as a daemon thread inside the desktop app
- Add a `frontend/` directory with a web UI (React or plain HTML/JS)
- Flask serves the built frontend as static files from a `/` route
- Both the desktop GUI and browser point to the same API endpoints — no duplication

### Implementation Phases

#### Phase 1 — Flask static file serving (~half day)
- Add `frontend/` directory with `index.html` + JS bundle
- Add a catch-all route to `backend/app.py` to serve `frontend/dist/`
- Confirm browser can hit `http://localhost:5174` and get a page

#### Phase 2 — Minimal web UI (~few days for core tabs)
- Prioritize: Lookup, Search, Collection tabs (read-heavy, easiest to build)
- Use plain HTML/JS or a lightweight framework (React/Vue)
- Call existing Flask API endpoints directly — no backend changes
- Full 11-tab parity would be weeks; a useful subset is a few days

#### Phase 3 — LAN/remote access (optional, later)
- Bind Flask to `0.0.0.0` instead of `127.0.0.1` to allow LAN access
- Add optional basic auth (Flask-HTTPAuth) if needed
- Docker becomes useful here for headless/server deployment

## Critical Files
- `backend/app.py` — add static file route + `send_from_directory` for `frontend/dist/`
- `main.py` — Flask startup; may need to adjust bind address
- `requirements.txt` — may need `flask-cors` if frontend is served from a dev server during development

## Constraints
- Desktop GUI is unchanged — purely additive
- No breaking changes to existing API routes
- Subprocess-dependent features (FFP checksums, spectrograms via sox) work fine since Flask runs locally with all tools available

## Verification
- Desktop app launches normally, PyQt6 GUI works as before
- Open `http://localhost:5174` in browser → web UI loads
- Lookup tab in browser returns same results as desktop tab

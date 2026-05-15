#!/usr/bin/env python3
"""Standalone diagnostic for WTRF SMF forum posting.

Usage:
    python debug_forum_post.py \
        --username YOUR_USER \
        --password YOUR_PASS \
        --board 16 \
        [--torrent path/to/file.torrent]
"""
import argparse
import logging
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("debug_forum_post")

FORUM_BASE = "http://www.watchingtheriverflow.org"
LOGIN_URL  = f"{FORUM_BASE}/index.php?action=login2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_hex_str(s: str) -> bool:
    return bool(s) and all(c in "0123456789abcdefABCDEF" for c in s)


def _is_hidden(tag) -> bool:
    """Return True if the element has inline display:none."""
    style = tag.get("style", "")
    return "display: none" in style or "display:none" in style


def _extract_form_fields(form) -> dict:
    fields = {}
    for inp in form.find_all("input", {"type": "hidden"}):
        name = inp.get("name")
        if name:
            fields[name] = inp.get("value", "")
    return fields


def _find_post_form(soup: BeautifulSoup):
    """Return the SMF post/compose form, or None."""
    return soup.find(
        "form",
        attrs={"action": lambda v: v and ("post2" in v or ("action=post" in v and "sa=" in v))},
    )


def _get_form_action(post_form) -> str:
    """Resolve the form action to an absolute URL."""
    action = post_form.get("action", "")
    if action and not action.startswith("http"):
        action = FORUM_BASE + "/" + action.lstrip("/")
    return action


def _dump_errors(soup: BeautifulSoup) -> bool:
    """
    Log any visible SMF error blocks. Returns True if real errors were found.

    Skips blocks that are hidden via inline style (display:none) — those are
    the default empty errorbox present on every compose page.
    """
    found = False
    for cls in ("errorbox", "error_list", "post_error", "noticebox"):
        el = soup.find(attrs={"class": cls})
        if not el:
            continue
        if _is_hidden(el):
            log.debug("Skipping hidden block [%s] (display:none — default empty state)", cls)
            continue
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        log.error("SMF error block [%s] raw HTML:\n%s", cls, str(el)[:1000])
        log.error("SMF error block [%s] text: %s", cls, text[:500])
        found = True
    if not found:
        log.info("No visible error blocks found in page")
    return found


def _is_lock_warning_visible(soup: BeautifulSoup) -> bool:
    """
    Return True only when the lock_warning paragraph is actually visible.

    The lock_warning <p id="lock_warning"> is present on every compose page
    but hidden (display:none) by default. It becomes visible only when SMF's
    JS sets it — which doesn't happen in server-side responses. For a real
    lock-warning page delivered server-side, SMF removes the inline style.
    """
    el = soup.find(id="lock_warning")
    if el and not _is_hidden(el):
        log.warning("Lock warning is VISIBLE: %s", el.get_text(" ", strip=True))
        return True
    return False


# ---------------------------------------------------------------------------
# Step 1 + 2: Login
# ---------------------------------------------------------------------------

def get_session(username: str, password: str) -> requests.Session | None:
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
    )

    log.info("--- STEP 1: Fetch login page ---")
    lp = session.get(f"{FORUM_BASE}/index.php?action=login", timeout=15)
    log.info("Login page status: %d, URL: %s", lp.status_code, lp.url)

    soup = BeautifulSoup(lp.text, "lxml")
    payload = {
        "user": username,
        "passwrd": password,
        "cookieneverexp": "0",
        "cookielength": "-1",
    }
    form = soup.find("form", attrs={"action": lambda v: v and "login2" in v})
    if form:
        for inp in form.find_all("input", {"type": "hidden"}):
            if inp.get("name"):
                payload[inp["name"]] = inp.get("value", "")
        log.info(
            "Login form hidden fields: %s",
            [k for k in payload if k not in ("user", "passwrd")],
        )
    else:
        log.warning("Login form NOT FOUND on login page")

    log.info("--- STEP 2: POST login ---")
    r = session.post(LOGIN_URL, data=payload, timeout=15)
    log.info("Post-login status: %d, final URL: %s", r.status_code, r.url)
    log.info("Cookies after login: %s", dict(session.cookies))

    smf_cookies = [k for k in session.cookies.keys() if k.lower().startswith("smfcookie")]
    if smf_cookies:
        log.info("SMF auth cookies found: %s — login SUCCESS", smf_cookies)
    else:
        log.error("No SMF auth cookies found — login FAILED")
        log.debug("Response body (first 2000 chars):\n%s", r.text[:2000])
        return None

    return session


# ---------------------------------------------------------------------------
# Step 3: Inspect compose page — returns (fields, form_action_url)
# ---------------------------------------------------------------------------

def check_compose_page(session: requests.Session, board_id: int) -> tuple[dict, str]:
    url = f"{FORUM_BASE}/index.php?action=post;board={board_id}.0"
    log.info("--- STEP 3: Fetch compose page (board %d) ---", board_id)
    r = session.get(url, timeout=15, headers={"Referer": FORUM_BASE})
    log.info("Compose page status: %d, final URL: %s", r.status_code, r.url)

    if "action=login" in r.url:
        log.error("Redirected to login — session not authenticated")
        return {}, ""

    soup = BeautifulSoup(r.text, "lxml")
    log.info("Page title: %s", (soup.find("title") or soup).get_text(strip=True))

    post_form = _find_post_form(soup)
    if not post_form:
        log.error("Post form NOT FOUND")
        log.debug("All forms: %s", [f.get("action", "") for f in soup.find_all("form")])
        return {}, ""

    form_action = _get_form_action(post_form)
    log.info("Form action URL (will POST here): %s", form_action)

    fields = _extract_form_fields(post_form)
    log.info("Hidden fields: %s", fields)

    for req in ("seqnum", "topic"):
        if req in fields:
            log.info("  ✓ %s = %r", req, fields[req])
        else:
            log.warning("  ✗ %s MISSING", req)

    if "board" in fields:
        log.info("  ✓ board = %r (hidden field)", fields["board"])
    else:
        log.info("  board in URL only (normal for SMF 2.x)")

    # CSRF token: hex name, hex value ≥ 16 chars, not a known SMF field
    known = {"seqnum", "topic", "board", "message_mode", "notify", "lock",
             "sticky", "move", "additional_options", "ns"}
    csrf = {k: v for k, v in fields.items()
            if k not in known and _is_hex_str(k) and _is_hex_str(v) and len(v) >= 16}
    if csrf:
        log.info("  ✓ CSRF token field(s): %s", csrf)
    else:
        log.warning("  ✗ No CSRF token field found")

    msg_area = post_form.find("textarea", {"name": "message"})
    file_inp = post_form.find("input", {"type": "file"})
    log.info("  message textarea: %s", bool(msg_area))
    log.info("  file input: %s (name=%s)", bool(file_inp),
             file_inp.get("name") if file_inp else "N/A")

    return fields, form_action


# ---------------------------------------------------------------------------
# Step 4: Initial POST
# ---------------------------------------------------------------------------

def initial_post(
    session: requests.Session,
    form_action: str,
    fields: dict,
    subject: str,
    body: str,
    torrent_path: Path | None,
    compose_url: str,
) -> tuple[requests.Response | None, BeautifulSoup | None]:
    payload = {
        **fields,
        "subject": subject,
        "message": body,
        "post": "Post",
        "ns": "0",
        "additional_options": "1",
    }
    headers = {"Referer": compose_url, "Origin": FORUM_BASE}

    log.info("Payload keys: %s", list(payload.keys()))
    log.info("POST URL: %s", form_action)
    log.info("subject=%r  body_len=%d", subject, len(body))

    try:
        if torrent_path and torrent_path.exists():
            log.info("Attaching: %s (%d bytes)", torrent_path.name, torrent_path.stat().st_size)
            with torrent_path.open("rb") as fh:
                resp = session.post(
                    form_action,
                    data=payload,
                    files={"attachment[]": (torrent_path.name, fh, "application/x-bittorrent")},
                    headers=headers,
                    timeout=30,
                )
        else:
            log.info("No torrent — text-only post")
            resp = session.post(form_action, data=payload, headers=headers, timeout=30)

        log.info("Response: HTTP %d  URL: %s", resp.status_code, resp.url)
        return resp, BeautifulSoup(resp.text, "lxml")

    except Exception:
        log.exception("Exception during initial POST")
        return None, None


# ---------------------------------------------------------------------------
# Step 5: Retry POST (resubmit from server-side preview — no file)
# ---------------------------------------------------------------------------

def retry_post(
    session: requests.Session,
    preview_soup: BeautifulSoup,
    subject: str,
    body: str,
    referer_url: str,
) -> None:
    post_form = _find_post_form(preview_soup)
    if not post_form:
        log.error("No post form found on preview page — cannot retry")
        return

    retry_action = _get_form_action(post_form)
    retry_fields = _extract_form_fields(post_form)
    log.info("Retry form action: %s", retry_action)
    log.info("Retry hidden fields: %s", retry_fields)

    attach_fields = {k: v for k, v in retry_fields.items() if "attach" in k.lower()}
    if attach_fields:
        log.info("  Attachment fields (file held server-side): %s", attach_fields)
        for k, v in attach_fields.items():
            if v == "0":
                log.warning("  %r = '0' — placeholder, not a real attachment ID", k)
    else:
        log.warning("  No attachment fields — torrent was NOT stored on first pass")

    retry_payload = {
        **retry_fields,
        "subject": subject,
        "message": body,
        "post": "Post",
        "ns": "0",
        "additional_options": "1",
    }

    try:
        resp2 = session.post(
            retry_action,
            data=retry_payload,
            headers={"Referer": referer_url, "Origin": FORUM_BASE},
            timeout=30,
        )
        log.info("Retry response: HTTP %d  URL: %s", resp2.status_code, resp2.url)

        if "topic=" in resp2.url:
            log.info("SUCCESS after retry — topic: %s", resp2.url)
            return

        soup2 = BeautifulSoup(resp2.text, "lxml")
        log.error("Retry failed. Page title: %s",
                  (soup2.find("title") or soup2).get_text(strip=True))
        _dump_errors(soup2)
        _is_lock_warning_visible(soup2)
        log.debug("Retry body (first 5000):\n%s", resp2.text[:5000])

    except Exception:
        log.exception("Exception during retry POST")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def dry_run_post(
    session: requests.Session,
    board_id: int,
    fields: dict,
    form_action: str,
    torrent_path: Path | None,
) -> None:
    log.info("--- STEP 4: Submit test post ---")
    subject     = "DEBUG TEST POST — PLEASE IGNORE AND DELETE"
    body        = "This is an automated diagnostic post. Please delete."
    compose_url = f"{FORUM_BASE}/index.php?action=post;board={board_id}.0"

    resp, soup = initial_post(session, form_action, fields, subject, body, torrent_path, compose_url)
    if resp is None:
        return

    if "topic=" in resp.url:
        log.info("SUCCESS on first attempt — topic: %s", resp.url)
        return

    page_title = (soup.find("title") or soup).get_text(strip=True)
    log.error("Post not accepted. Page title: %s", page_title)

    # Check for REAL lock warning (visible, not hidden default)
    lock_visible = _is_lock_warning_visible(soup)

    # Check for REAL errors (visible, not hidden default)
    _dump_errors(soup)

    # A server-side preview page: title starts with "Preview" and the form
    # will have a new seqnum + possibly attach_del fields if file was stored.
    # Note: page_title.lower().startswith("preview") is the reliable signal —
    # NOT "will be locked" in get_text() which fires on every compose page.
    is_preview_page = page_title.lower().startswith("preview")

    if is_preview_page or lock_visible:
        reason = "server-side preview" if is_preview_page else "visible lock warning"
        log.warning("Got %s — attempting retry (Step 5)", reason)
        log.info("--- STEP 5: Retry POST from preview page ---")
        retry_post(session, soup, subject, body, resp.url)
    else:
        log.error("Unrecognised failure — not a preview page, no visible lock warning")
        log.debug("Full response body (first 5000):\n%s", resp.text[:5000])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="WTRF SMF forum post diagnostic")
    ap.add_argument("--username", required=True,           help="Forum username")
    ap.add_argument("--password", required=True,           help="Forum password")
    ap.add_argument("--board",    required=True, type=int, help="SMF board ID")
    ap.add_argument("--torrent",  default=None,            help="Path to .torrent file (optional)")
    args = ap.parse_args()

    torrent = Path(args.torrent) if args.torrent else None
    if torrent and not torrent.exists():
        log.error("Torrent file not found: %s", torrent)
        sys.exit(1)

    session = get_session(args.username, args.password)
    if not session:
        sys.exit(1)

    fields, form_action = check_compose_page(session, args.board)
    if not fields or not form_action:
        sys.exit(1)

    dry_run_post(session, args.board, fields, form_action, torrent)


if __name__ == "__main__":
    main()
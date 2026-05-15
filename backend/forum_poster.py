"""Post new topics to the Watching the River Flow SMF 2.x forum.

Single-entry operation only (not batch).  A .torrent file for the entry must
exist before posting is enabled.  Login uses an HTTP session via requests +
BeautifulSoup to scrape the hidden SMF form fields required for each post.
"""
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)

FORUM_BASE  = "http://www.watchingtheriverflow.org"
FORUM_BOARD = 16  # index.php?board=16.0

_LOGIN_URL  = f"{FORUM_BASE}/index.php?action=login2"
_COMPOSE_URL = f"{FORUM_BASE}/index.php?action=post;board={FORUM_BOARD}.0"
_POST_URL   = f"{FORUM_BASE}/index.php?action=post;sa=post2"


def _get_session(username: str, password: str) -> requests.Session | None:
    """Log in and return an authenticated requests.Session.

    Args:
        username: Forum username.
        password: Forum password.

    Returns:
        Authenticated Session, or None if login failed.
    """
    session = requests.Session()
    session.headers["User-Agent"] = "LosslessBob/1.0 (+https://github.com)"
    try:
        # Fetch the login page and collect all hidden fields (includes sc, hash_passwrd, etc.)
        login_page = session.get(
            f"{FORUM_BASE}/index.php?action=login", timeout=15
        )
        soup = BeautifulSoup(login_page.text, "lxml")

        payload = {
            "user": username,
            "passwrd": password,
            "cookieneverexp": "0",
            "cookielength": "-1",
        }
        login_form = soup.find("form", attrs={"action": lambda v: v and "login2" in v})
        if login_form:
            for inp in login_form.find_all("input", {"type": "hidden"}):
                name = inp.get("name")
                if name:
                    payload[name] = inp.get("value", "")

        r = session.post(_LOGIN_URL, data=payload, timeout=15)

        # SMF on this forum returns 200 with empty body at login2 on success.
        # Check specifically for the login page URL (not login2 which is the POST target).
        login_page_url = f"{FORUM_BASE}/index.php?action=login"
        if r.url.startswith(login_page_url) and "login2" not in r.url:
            logger.warning("WTRF login failed for user %s (redirected back to login)", username)
            return None
        if "incorrect password" in r.text.lower():
            logger.warning("WTRF login failed for user %s (incorrect password in body)", username)
            return None

        return session
    except Exception as exc:
        logger.error("WTRF login error: %s", exc)
        return None


def _scrape_form_fields(session: requests.Session) -> dict:
    """Fetch the SMF compose page and extract hidden form fields.

    Args:
        session: Authenticated requests.Session.

    Returns:
        Dict of hidden form fields (sc, seqnum, etc.).
    """
    try:
        resp = session.get(_COMPOSE_URL, timeout=15)
        soup = BeautifulSoup(resp.text, "lxml")
        fields = {}
        for inp in soup.find_all("input", {"type": "hidden"}):
            name = inp.get("name")
            value = inp.get("value", "")
            if name:
                fields[name] = value
        return fields
    except Exception as exc:
        logger.error("Could not scrape SMF form fields: %s", exc)
        return {}


def _build_body(entry: dict, attachments_dir: Path | None) -> str:
    """Build the post body from cached .txt and .ffp files, or entry table fields.

    The body format is:
        [code]<info txt content>[/code]
        [code]<ffp content>[/code]

    Falls back to entry table fields when cached files are unavailable.

    Args:
        entry: Dict from the entries table.
        attachments_dir: Path to data/attachments/LB-XXXXX/ or None.
        lb_id: Zero-padded LB string like 'LB-00042'.

    Returns:
        Post body string with BBcode.
    """
    txt_block = ""
    ffp_block = ""

    if attachments_dir and attachments_dir.is_dir():
        # Try to find and read .txt and .ffp cached attachment files
        for f in attachments_dir.iterdir():
            if f.suffix.lower() == ".txt" and "lbdir" not in f.name.lower():
                try:
                    txt_block = f.read_text(encoding="utf-8", errors="replace").strip()
                    break
                except OSError:
                    pass
        for f in attachments_dir.iterdir():
            if f.suffix.lower() == ".ffp":
                try:
                    ffp_block = f.read_text(encoding="utf-8", errors="replace").strip()
                    break
                except OSError:
                    pass

    if not txt_block and not ffp_block:
        # Fall back to composing from entry table fields
        parts = []
        for key in ("date_str", "location", "cdr", "rating", "timing", "description"):
            val = (entry.get(key) or "").strip()
            if val:
                parts.append(f"{key}: {val}")
        setlist = (entry.get("setlist") or "").strip()
        if setlist:
            parts.append("\n" + setlist)
        txt_block = "\n".join(parts)

    body = ""
    if txt_block:
        body += f"[code]\n{txt_block}\n[/code]\n\n"
    if ffp_block:
        body += f"[code]\n{ffp_block}\n[/code]"
    return body.strip()


def post_lb_topic(
    lb_number: int,
    torrent_path: str | Path,
    username: str,
    password: str,
    entry: dict,
    attachments_dir: str | Path | None = None,
) -> dict:
    """Post a new topic for an LB entry with the .torrent as an attachment.

    Args:
        lb_number: LosslessBob entry number.
        torrent_path: Path to the .torrent file.
        username: WTRF forum username.
        password: WTRF forum password.
        entry: Dict from the entries table (date_str, location, …).
        attachments_dir: Path to data/attachments/LB-XXXXX/ (for body text).

    Returns:
        Dict with keys: ok (bool), topic_url (str if ok=True), error (str if ok=False).
    """
    torrent = Path(torrent_path)
    if not torrent.exists():
        return {"ok": False, "error": f"Torrent file not found: {torrent}"}

    lb_id = f"LB-{lb_number:05d}"
    date_str = entry.get("date_str") or ""
    location = (entry.get("location") or "").strip()

    # Format subject line
    from backend.torrent_maker import _parse_date
    iso_date = _parse_date(date_str)
    if iso_date and location:
        subject = f"{iso_date} {location} ({lb_id})"
    elif location:
        subject = f"{location} ({lb_id})"
    else:
        subject = lb_id

    session = _get_session(username, password)
    if session is None:
        return {"ok": False, "error": "Login failed — check username and password."}

    hidden = _scrape_form_fields(session)
    if not hidden.get("sc"):
        return {"ok": False, "error": "Could not retrieve SMF form fields (sc/seqnum missing)."}

    attach_path = Path(attachments_dir) if attachments_dir else None
    body = _build_body(entry, attach_path)

    payload = {
        **hidden,
        "subject": subject,
        "message": body,
        "post": "Post",
        "not_approved": "0",
        "ns": "0",
    }

    try:
        with torrent.open("rb") as fh:
            files = {"attachment[]": (torrent.name, fh, "application/x-bittorrent")}
            resp = session.post(
                _POST_URL,
                data=payload,
                files=files,
                timeout=30,
            )

        # SMF redirects to the new topic on success
        if resp.status_code in (200, 302) and "topic" in resp.url:
            return {"ok": True, "topic_url": resp.url}

        # Check for error indicators in the response body
        soup = BeautifulSoup(resp.text, "lxml")
        err_div = soup.find("div", {"class": "errorbox"})
        if err_div:
            return {"ok": False, "error": err_div.get_text(strip=True)[:300]}

        # Final fallback: assume success if no error indicators
        if resp.status_code == 200:
            return {"ok": True, "topic_url": resp.url}

        return {"ok": False, "error": f"HTTP {resp.status_code}"}

    except Exception as exc:
        logger.error("post_lb_topic error for LB-%d: %s", lb_number, exc)
        return {"ok": False, "error": str(exc)}

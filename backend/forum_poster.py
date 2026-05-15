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

FORUM_BASE = "http://www.watchingtheriverflow.org"

_LOGIN_URL = f"{FORUM_BASE}/index.php?action=login2"


def _compose_url(board_id: int) -> str:
    return f"{FORUM_BASE}/index.php?action=post;board={board_id}.0"


def _post_url(board_id: int) -> str:
    return f"{FORUM_BASE}/index.php?action=post;sa=post2;board={board_id}.0"


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


def _scrape_form_fields(session: requests.Session, compose_url: str) -> tuple[dict, str]:
    """Fetch the SMF compose page and extract hidden form fields.

    Args:
        session: Authenticated requests.Session.
        compose_url: Full URL of the new-topic compose page for the target board.

    Returns:
        Tuple of (fields dict, diagnostic string). Fields is empty on failure;
        diagnostic carries a human-readable explanation including the final URL.
    """
    try:
        resp = session.get(compose_url, timeout=15, headers={"Referer": FORUM_BASE})
        final_url = resp.url
        status = resp.status_code
        logger.debug("_scrape_form_fields: HTTP %s final URL: %s", status, final_url)

        # Redirect to the login page means the session is not authenticated.
        if "action=login" in final_url and "post" not in final_url:
            diag = f"compose page redirected to login — session not authenticated (URL: {final_url})"
            logger.warning("_scrape_form_fields: %s", diag)
            return {}, diag

        soup = BeautifulSoup(resp.text, "lxml")

        # Page title helps diagnose permission / wrong-board errors.
        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else "(no title)"
        logger.debug("_scrape_form_fields: page title: %s", page_title)

        fields = {}
        # Prefer the post form specifically so we don't pick up unrelated hidden fields.
        post_form = soup.find(
            "form",
            attrs={"action": lambda v: v and ("post2" in v or ("action=post" in v and "sa=" in v))},
        )
        target = post_form or soup  # fall back to full page scan
        for inp in target.find_all("input", {"type": "hidden"}):
            name = inp.get("name")
            value = inp.get("value", "")
            if name:
                fields[name] = value

        logger.debug("_scrape_form_fields: found hidden fields: %s", list(fields.keys()))
        diag = f"HTTP {status}, page: '{page_title}', URL: {final_url}, fields: {list(fields.keys())}"
        return fields, diag
    except Exception as exc:
        logger.error("Could not scrape SMF form fields: %s", exc)
        return {}, str(exc)


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


def preview_lb_topic(
    lb_number: int,
    entry: dict,
    attachments_dir: str | Path | None = None,
) -> dict:
    """Build the forum post subject and body without logging in or posting.

    Args:
        lb_number: LosslessBob entry number.
        entry: Dict from the entries table (date_str, location, …).
        attachments_dir: Path to data/attachments/LB-XXXXX/ (for body text).

    Returns:
        Dict with keys: subject (str), body (str).
    """
    lb_id = f"LB-{lb_number:05d}"
    date_str = entry.get("date_str") or ""
    location = (entry.get("location") or "").strip()

    from backend.torrent_maker import _parse_date
    iso_date = _parse_date(date_str)
    if iso_date and location:
        subject = f"{iso_date} {location} ({lb_id})"
    elif location:
        subject = f"{location} ({lb_id})"
    else:
        subject = lb_id

    attach_path = Path(attachments_dir) if attachments_dir else None
    body = _build_body(entry, attach_path)
    return {"subject": subject, "body": body}


def _extract_smf_error(soup: BeautifulSoup) -> str:
    """Pull the human-readable error text out of an SMF error page.

    Args:
        soup: Parsed response page.

    Returns:
        Error string, or empty string if no SMF error structure was found.
    """
    # SMF error pages: <h2> or <h3> with "error has occurred", reason in the
    # next sibling windowbg div or smalltext span.
    for heading in soup.find_all(["h2", "h3"]):
        if "error has occurred" in heading.get_text().lower():
            nxt = heading.find_next_sibling()
            if nxt:
                text = nxt.get_text(separator=" ", strip=True)
                if text:
                    return f"SMF: {text[:400]}"
            # Try the parent's next sibling (catbg → windowbg pattern).
            parent = heading.parent
            if parent:
                nxt = parent.find_next_sibling()
                if nxt:
                    text = nxt.get_text(separator=" ", strip=True)
                    if text:
                        return f"SMF: {text[:400]}"

    # windowbg div in the main content section is the body of SMF error pages.
    content = soup.find(id="content_section") or soup
    for cls in ("windowbg", "windowbg2", "errorbox", "error_list", "post_error"):
        el = content.find(attrs={"class": cls})
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 10:
                return f"SMF: {text[:400]}"

    return ""


def post_lb_topic(
    lb_number: int,
    torrent_path: str | Path,
    username: str,
    password: str,
    entry: dict,
    board_id: int,
    attachments_dir: str | Path | None = None,
    subject_override: str | None = None,
    body_override: str | None = None,
) -> dict:
    """Post a new topic for an LB entry with the .torrent as an attachment.

    Args:
        lb_number: LosslessBob entry number.
        torrent_path: Path to the .torrent file.
        username: WTRF forum username.
        password: WTRF forum password.
        entry: Dict from the entries table (date_str, location, …).
        board_id: SMF board number to post into (stored in meta as wtrf_board_id).
        attachments_dir: Path to data/attachments/LB-XXXXX/ (for body text).
        subject_override: If provided, use this subject instead of the auto-generated one.
        body_override: If provided, use this body instead of the auto-generated one.

    Returns:
        Dict with keys: ok (bool), topic_url (str if ok=True), error (str if ok=False).
    """
    torrent = Path(torrent_path)
    if not torrent.exists():
        return {"ok": False, "error": f"Torrent file not found: {torrent}"}

    if subject_override:
        subject = subject_override
    else:
        lb_id = f"LB-{lb_number:05d}"
        date_str = entry.get("date_str") or ""
        location = (entry.get("location") or "").strip()
        from backend.torrent_maker import _parse_date
        iso_date = _parse_date(date_str)
        if iso_date and location:
            subject = f"{iso_date} {location} ({lb_id})"
        elif location:
            subject = f"{location} ({lb_id})"
        else:
            subject = lb_id

    compose_url = _compose_url(board_id)

    session = _get_session(username, password)
    if session is None:
        return {"ok": False, "error": "Login failed — check username and password."}

    hidden, diag = _scrape_form_fields(session, compose_url)
    # seqnum is the anti-duplicate token that confirms we got the real post form.
    # sc may appear under a hashed name (e.g. 'a9c55b28') on some SMF installs — we
    # don't check for it by name; all hidden fields are forwarded via **hidden anyway.
    if not hidden.get("seqnum"):
        return {
            "ok": False,
            "error": f"Could not retrieve post form (seqnum missing). Diagnostic: {diag}",
        }

    if body_override is not None:
        body = body_override
    else:
        attach_path = Path(attachments_dir) if attachments_dir else None
        body = _build_body(entry, attach_path)

    payload = {
        **hidden,
        "subject": subject,
        "message": body,
        "post": "Post",
        "not_approved": "0",
        "ns": "0",
        # Force additional_options open so SMF processes the attachment field.
        "additional_options": "1",
    }

    post_headers = {
        "Referer": compose_url,
        "Origin": FORUM_BASE,
    }

    try:
        with torrent.open("rb") as fh:
            files = {"attachment[]": (torrent.name, fh, "application/x-bittorrent")}
            resp = session.post(
                _post_url(board_id),
                data=payload,
                files=files,
                headers=post_headers,
                timeout=30,
            )

        logger.debug("post_lb_topic: HTTP %s final URL: %s", resp.status_code, resp.url)
        logger.debug(
            "post_lb_topic: payload keys=%s subject=%r body_len=%d",
            list(payload.keys()), payload.get("subject"), len(payload.get("message", "")),
        )

        # SMF redirects to the new topic on success; resp.url will contain 'topic='.
        if "topic=" in resp.url:
            return {"ok": True, "topic_url": resp.url}

        soup = BeautifulSoup(resp.text, "lxml")
        content = soup.find(id="content_section") or soup.body or soup
        page_text = content.get_text(" ", strip=True)
        logger.debug("post_lb_topic: page text: %s", page_text[:3000])

        # SMF returns the compose form as a "warning preview" when a board has
        # restricted posting (admin/mod-only).  The attachment is already stored
        # server-side; resubmit with fresh form fields scraped from this page —
        # no file needed on the second pass.
        if "will be locked" in page_text or "currently" in page_text and "locked" in page_text:
            logger.debug("post_lb_topic: detected lock-warning preview — retrying without file")
            retry_fields: dict = {}
            post_form = soup.find(
                "form",
                attrs={"action": lambda v: v and ("post2" in v or ("action=post" in v and "sa=" in v))},
            )
            target = post_form or soup
            for inp in target.find_all("input", {"type": "hidden"}):
                name = inp.get("name")
                if name:
                    retry_fields[name] = inp.get("value", "")

            retry_payload = {
                **retry_fields,
                "subject": subject,
                "message": body,
                "post": "Post",
                "not_approved": "0",
                "ns": "0",
                "additional_options": "1",
                # Do NOT override lock/sticky/move here — the warning page has already
                # corrected them to match the board's requirements (e.g. lock=1 for a
                # locked board). Overriding them back to 0 re-introduces the mismatch
                # that caused the warning in the first place.
            }
            retry_headers = {"Referer": resp.url, "Origin": FORUM_BASE}
            resp2 = session.post(
                _post_url(board_id),
                data=retry_payload,
                headers=retry_headers,
                timeout=30,
            )
            logger.debug("post_lb_topic retry: HTTP %s final URL: %s", resp2.status_code, resp2.url)
            if "topic=" in resp2.url:
                return {"ok": True, "topic_url": resp2.url}
            soup2 = BeautifulSoup(resp2.text, "lxml")
            content2 = soup2.find(id="content_section") or soup2.body or soup2
            logger.debug("post_lb_topic retry page text: %s",
                         content2.get_text(" ", strip=True)[:2000])
            smf_error = _extract_smf_error(soup2)
            if smf_error:
                return {"ok": False, "error": f"Retry failed: {smf_error}"}
            return {"ok": False, "error": f"Retry failed (HTTP {resp2.status_code}, URL: {resp2.url})"}

        smf_error = _extract_smf_error(soup)
        if smf_error:
            return {"ok": False, "error": smf_error}

        page_title = (soup.find("title") or soup).get_text(strip=True)[:80]
        return {
            "ok": False,
            "error": (
                f"Post was not accepted (HTTP {resp.status_code}, "
                f"page: '{page_title}', URL: {resp.url})"
            ),
        }

    except Exception as exc:
        logger.error("post_lb_topic error for LB-%d: %s", lb_number, exc)
        return {"ok": False, "error": str(exc)}

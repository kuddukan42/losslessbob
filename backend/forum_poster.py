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

_LOGIN_URL  = f"{FORUM_BASE}/index.php?action=login2"


def _compose_url(board_id: int) -> str:
    return f"{FORUM_BASE}/index.php?action=post;board={board_id}.0"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_element_hidden(el) -> bool:
    """Return True if the element carries an inline display:none style."""
    style = el.get("style", "")
    return "display: none" in style or "display:none" in style


def _find_post_form(soup: BeautifulSoup):
    """Return the SMF new-topic/reply form, or None."""
    return soup.find(
        "form",
        attrs={"action": lambda v: v and ("post2" in v or ("action=post" in v and "sa=" in v))},
    )


def _resolve_url(href: str) -> str:
    """Ensure href is an absolute URL."""
    if href and not href.startswith("http"):
        return FORUM_BASE + "/" + href.lstrip("/")
    return href


def _find_newest_topic(board_resp: requests.Response) -> str | None:
    """After a board-redirect success, return the URL of the most recent topic.

    SMF board pages list topics newest-first; the first anchor containing
    'topic=' in its href is the post we just created.

    Args:
        board_resp: The response from following the post-success redirect.

    Returns:
        Absolute topic URL, or None if no topic link was found.
    """
    soup = BeautifulSoup(board_resp.text, "lxml")
    for a in soup.find_all("a", href=lambda h: h and "topic=" in h):
        return _resolve_url(a["href"])
    return None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def _get_session(username: str, password: str) -> requests.Session | None:
    """Log in and return an authenticated requests.Session.

    Args:
        username: Forum username.
        password: Forum password.

    Returns:
        Authenticated Session, or None if login failed.
    """
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
    )
    try:
        login_page = session.get(f"{FORUM_BASE}/index.php?action=login", timeout=15)
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

        # This forum returns HTTP 200 with an empty body on successful login;
        # the final URL stays at login2.  Detect failure by absence of the
        # SMF auth cookie rather than by redirect destination.
        smf_cookies = [k for k in session.cookies.keys() if k.lower().startswith("smfcookie")]
        if not smf_cookies:
            # Fallback: also accept a redirect away from the login page as success.
            login_page_url = f"{FORUM_BASE}/index.php?action=login"
            if r.url.startswith(login_page_url) and "login2" not in r.url:
                logger.warning("WTRF login failed for user %s (redirected back to login)", username)
                return None
            if "incorrect password" in r.text.lower():
                logger.warning("WTRF login failed for user %s (incorrect password in body)", username)
                return None
            if not smf_cookies:
                logger.warning("WTRF login failed for user %s (no SMF auth cookie set)", username)
                return None

        logger.debug("_get_session: login OK for %s, cookies: %s", username, smf_cookies)
        return session

    except Exception as exc:
        logger.error("WTRF login error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Compose-page scraping
# ---------------------------------------------------------------------------

def _scrape_form_fields(
    session: requests.Session,
    compose_url: str,
) -> tuple[dict, str, str]:
    """Fetch the SMF compose page and extract hidden form fields + form action URL.

    Args:
        session: Authenticated requests.Session.
        compose_url: Full URL of the new-topic compose page for the target board.

    Returns:
        Tuple of (fields dict, form_action_url, diagnostic string).
        fields and form_action_url are empty on failure; diagnostic carries a
        human-readable explanation.
    """
    try:
        resp = session.get(compose_url, timeout=15, headers={"Referer": FORUM_BASE})
        final_url = resp.url
        status = resp.status_code
        logger.debug("_scrape_form_fields: HTTP %s final URL: %s", status, final_url)

        if "action=login" in final_url and "post" not in final_url:
            diag = f"compose page redirected to login — session not authenticated (URL: {final_url})"
            logger.warning("_scrape_form_fields: %s", diag)
            return {}, "", diag

        soup = BeautifulSoup(resp.text, "lxml")

        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else "(no title)"
        logger.debug("_scrape_form_fields: page title: %s", page_title)

        post_form = _find_post_form(soup)

        # Extract the form's own action URL — this is the correct POST target.
        # Do NOT use a hardcoded URL; SMF's compose form action is the authority.
        form_action = ""
        if post_form:
            form_action = _resolve_url(post_form.get("action", ""))

        fields = {}
        target = post_form or soup
        for inp in target.find_all("input", {"type": "hidden"}):
            name = inp.get("name")
            value = inp.get("value", "")
            if name:
                fields[name] = value

        logger.debug("_scrape_form_fields: form_action=%s fields=%s", form_action, list(fields.keys()))
        diag = (
            f"HTTP {status}, page: '{page_title}', URL: {final_url}, "
            f"form_action: {form_action}, fields: {list(fields.keys())}"
        )
        return fields, form_action, diag

    except Exception as exc:
        logger.error("Could not scrape SMF form fields: %s", exc)
        return {}, "", str(exc)


# ---------------------------------------------------------------------------
# Post-body builder
# ---------------------------------------------------------------------------

def _build_body(entry: dict, attachments_dir: Path | None) -> str:
    """Build the post body from cached .txt and .ffp files, or entry table fields.

    The body format is:
        [code]<info txt content>[/code]
        [code]<ffp content>[/code]

    Falls back to entry table fields when cached files are unavailable.

    Args:
        entry: Dict from the entries table.
        attachments_dir: Path to data/attachments/LB-XXXXX/ or None.

    Returns:
        Post body string with BBcode.
    """
    txt_block = ""
    ffp_block = ""

    if attachments_dir and attachments_dir.is_dir():
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


# ---------------------------------------------------------------------------
# SMF error extraction
# ---------------------------------------------------------------------------

def _extract_smf_error(soup: BeautifulSoup) -> str:
    """Pull the human-readable error text out of an SMF error page.

    Skips elements that are hidden via inline display:none — those are the
    default empty errorbox present on every compose page.

    Args:
        soup: Parsed response page.

    Returns:
        Error string, or empty string if no visible SMF error was found.
    """
    for heading in soup.find_all(["h2", "h3"]):
        if "error has occurred" in heading.get_text().lower():
            nxt = heading.find_next_sibling()
            if nxt and not _is_element_hidden(nxt):
                text = nxt.get_text(separator=" ", strip=True)
                if text:
                    return f"SMF: {text[:400]}"
            parent = heading.parent
            if parent:
                nxt = parent.find_next_sibling()
                if nxt and not _is_element_hidden(nxt):
                    text = nxt.get_text(separator=" ", strip=True)
                    if text:
                        return f"SMF: {text[:400]}"

    content = soup.find(id="content_section") or soup
    for cls in ("errorbox", "error_list", "post_error", "windowbg", "windowbg2"):
        el = content.find(attrs={"class": cls})
        if el and not _is_element_hidden(el):
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 10:
                return f"SMF: {text[:400]}"

    return ""


# ---------------------------------------------------------------------------
# Public API: preview (no network)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Public API: post
# ---------------------------------------------------------------------------

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

    # --- Build subject ---
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

    # --- Login ---
    session = _get_session(username, password)
    if session is None:
        return {"ok": False, "error": "Login failed — check username and password."}

    # --- Scrape compose page for hidden fields + correct POST URL ---
    compose_url = _compose_url(board_id)
    hidden, form_action, diag = _scrape_form_fields(session, compose_url)

    if not hidden.get("seqnum"):
        return {
            "ok": False,
            "error": f"Could not retrieve post form (seqnum missing). Diagnostic: {diag}",
        }
    if not form_action:
        return {
            "ok": False,
            "error": f"Could not determine form action URL. Diagnostic: {diag}",
        }

    # --- Build body ---
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
        "ns": "0",
        # Ensure SMF processes the attachment[] field.
        "additional_options": "1",
    }

    post_headers = {
        "Referer": compose_url,
        "Origin": FORUM_BASE,
    }

    logger.debug(
        "post_lb_topic: posting LB-%05d subject=%r body_len=%d torrent=%s",
        lb_number, subject, len(body), torrent.name,
    )

    try:
        # Use allow_redirects=False so we can inspect the Location header directly.
        # This forum redirects to board=X.0 on success (not topic=X.0), so we
        # must not rely on the final URL after auto-following the redirect.
        with torrent.open("rb") as fh:
            files = {"attachment[]": (torrent.name, fh, "application/x-bittorrent")}
            resp = session.post(
                form_action,
                data=payload,
                files=files,
                headers=post_headers,
                timeout=30,
                allow_redirects=False,
            )

        logger.debug("post_lb_topic: HTTP %s  Location: %s",
                     resp.status_code, resp.headers.get("Location", "(none)"))

        # --- Success: SMF issued a redirect ---
        if resp.status_code in (301, 302, 303, 307, 308):
            location = _resolve_url(resp.headers.get("Location", ""))

            # Traditional success: redirect directly to the new topic.
            if "topic=" in location:
                return {"ok": True, "topic_url": location}

            # This forum's success: redirect to the board listing.
            # Follow the redirect, then find the newest topic link on that page.
            if f"board={board_id}" in location or f"board={board_id}." in location:
                board_resp = session.get(location, timeout=15,
                                         headers={"Referer": form_action})
                topic_url = _find_newest_topic(board_resp) or location
                logger.debug("post_lb_topic: board-redirect success, topic_url=%s", topic_url)
                return {"ok": True, "topic_url": topic_url}

            # Unexpected redirect destination — treat as failure.
            logger.warning("post_lb_topic: unexpected redirect to %s", location)
            return {
                "ok": False,
                "error": f"Unexpected redirect after post (Location: {location})",
            }

        # --- No redirect: SMF returned a page directly (preview or error) ---
        soup = BeautifulSoup(resp.text, "lxml")

        # Check for a VISIBLE lock warning.  The lock_warning element is present
        # on every compose page but hidden (display:none) by default; only treat
        # it as a real warning when the inline style is absent.
        lock_el = soup.find(id="lock_warning")
        is_lock_warning = lock_el is not None and not _is_element_hidden(lock_el)

        page_title = (soup.find("title") or soup).get_text(strip=True)
        is_preview_page = page_title.lower().startswith("preview")

        logger.debug("post_lb_topic: no-redirect page title=%r lock_warning=%s preview=%s",
                     page_title, is_lock_warning, is_preview_page)

        if is_preview_page or is_lock_warning:
            # SMF is holding the post for confirmation (preview or lock-warning).
            # The attachment has been stored server-side; resubmit with the fresh
            # form fields from this page — no file needed on the second pass.
            logger.debug("post_lb_topic: preview/lock page detected — retrying without file")

            post_form = _find_post_form(soup)
            retry_action = _resolve_url(post_form.get("action", "")) if post_form else form_action
            retry_action = retry_action or form_action

            retry_fields: dict = {}
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
                "ns": "0",
                "additional_options": "1",
                # Do NOT override lock/sticky/move — the warning page has already
                # set them to match the board's requirements.
            }
            retry_headers = {"Referer": resp.url or form_action, "Origin": FORUM_BASE}

            resp2 = session.post(
                retry_action,
                data=retry_payload,
                headers=retry_headers,
                timeout=30,
                allow_redirects=False,
            )
            logger.debug("post_lb_topic retry: HTTP %s  Location: %s",
                         resp2.status_code, resp2.headers.get("Location", "(none)"))

            if resp2.status_code in (301, 302, 303, 307, 308):
                location2 = _resolve_url(resp2.headers.get("Location", ""))
                if "topic=" in location2:
                    return {"ok": True, "topic_url": location2}
                if f"board={board_id}" in location2 or f"board={board_id}." in location2:
                    board_resp2 = session.get(location2, timeout=15,
                                              headers={"Referer": retry_action})
                    topic_url2 = _find_newest_topic(board_resp2) or location2
                    return {"ok": True, "topic_url": topic_url2}
                return {
                    "ok": False,
                    "error": f"Retry: unexpected redirect (Location: {location2})",
                }

            soup2 = BeautifulSoup(resp2.text, "lxml")
            smf_error = _extract_smf_error(soup2)
            if smf_error:
                return {"ok": False, "error": f"Retry failed: {smf_error}"}
            return {
                "ok": False,
                "error": (
                    f"Retry failed (HTTP {resp2.status_code}, "
                    f"URL: {resp2.headers.get('Location', resp2.url)})"
                ),
            }

        # Not a preview page — check for an explicit SMF error message.
        smf_error = _extract_smf_error(soup)
        if smf_error:
            return {"ok": False, "error": smf_error}

        return {
            "ok": False,
            "error": (
                f"Post was not accepted (HTTP {resp.status_code}, "
                f"page: '{page_title[:80]}')"
            ),
        }

    except Exception as exc:
        logger.error("post_lb_topic error for LB-%05d: %s", lb_number, exc)
        return {"ok": False, "error": str(exc)}
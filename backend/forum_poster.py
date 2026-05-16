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


def _board_url_sorted(board_url: str) -> str:
    """Append SMF's sort-by-creation-date-descending parameter to a board URL.

    The default board listing order is by last-reply date, which means a busy
    thread bumped after our post appears first.  Sorting by first_post desc
    puts the topic we just created at the top.

    Args:
        board_url: Absolute board URL (may already contain query params).

    Returns:
        Board URL with sort=first_post;desc=1 appended.
    """
    sep = ";" if "?" in board_url else "?"
    return f"{board_url}{sep}sort=first_post;desc=1"


def _find_newest_topic(board_resp: requests.Response, subject: str | None = None) -> str | None:
    """After a board-redirect success, return the URL of the topic we just created.

    Strategy (most-reliable first):
    1. Subject match — find the link whose visible text contains the posted subject.
       Immune to sticky ordering.
    2. First non-sticky link — skip <tr>/<div>/<li> elements whose class includes
       "sticky"; take the first remaining topic link.
    3. Last resort — return whatever the first topic= link is.

    Args:
        board_resp: The response from following the post-success redirect.
        subject: The subject line we posted, used for exact matching.

    Returns:
        Absolute topic URL, or None if no topic link was found.
    """
    soup = BeautifulSoup(board_resp.text, "lxml")
    all_topic_links = soup.find_all("a", href=lambda h: h and "topic=" in h)

    # Pass 1: subject match.
    if subject:
        subject_lower = subject.lower()
        for a in all_topic_links:
            if subject_lower in a.get_text(strip=True).lower():
                return _resolve_url(a["href"])

    # Pass 2: first non-sticky link.
    for a in all_topic_links:
        sticky_ancestor = a.find_parent(
            lambda el: el.name in ("tr", "div", "li")
            and "sticky" in " ".join(el.get("class", [])).lower()
        )
        if sticky_ancestor is None:
            return _resolve_url(a["href"])

    # Pass 3: anything.
    if all_topic_links:
        return _resolve_url(all_topic_links[0]["href"])
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

        # Log visible text/textarea inputs so we can verify field names (e.g. desc).
        visible_names = [
            (inp.get("name"), inp.get("type", "text"))
            for inp in target.find_all(["input", "textarea"])
            if inp.get("name") and inp.get("type", "text") != "hidden"
        ]
        logger.debug(
            "_scrape_form_fields: form_action=%s hidden_fields=%s visible_inputs=%s",
            form_action, list(fields.keys()), visible_names,
        )
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

def _read_lb_txt(attachments_dir: Path, lb_number: int | None) -> str:
    """Read the LB-numbered info txt file, skipping its first header line.

    Looks for a file whose name contains ``LB-{lb_number}`` (without zero-padding)
    and that is not an lbdir manifest.

    Args:
        attachments_dir: Path to the attachment directory.
        lb_number: Integer LB number used to identify the correct txt file.

    Returns:
        File text with the first header line stripped, or empty string.
    """
    if not attachments_dir.is_dir():
        return ""
    candidates = [
        f for f in sorted(attachments_dir.iterdir())
        if f.suffix.lower() == ".txt"
        and not f.name.lower().startswith("lbdir")
        and not f.name.lower().startswith("orig-")
        and (lb_number is None or f"LB-{lb_number}" in f.name)
    ]
    if not candidates:
        return ""
    try:
        text = candidates[0].read_text(encoding="utf-8", errors="replace").strip()
        lines = text.splitlines()
        # Skip the first line (e.g. "Bob Dylan, date, location, NCdr")
        start = 1
        while start < len(lines) and not lines[start].strip():
            start += 1
        return "\n".join(lines[start:]).strip()
    except OSError:
        return ""


def _read_lbdir(attachments_dir: Path, lb_number: int | None) -> str:
    """Read the lbdir checksum manifest file.

    When multiple lbdir files exist, prefers the one whose stem shares the
    most characters with the LB-numbered info txt file.

    Args:
        attachments_dir: Path to the attachment directory.
        lb_number: Integer LB number used to find the best matching lbdir.

    Returns:
        Full lbdir file text, or empty string.
    """
    if not attachments_dir.is_dir():
        return ""
    candidates = sorted(
        f for f in attachments_dir.iterdir()
        if f.suffix.lower() == ".txt" and f.name.lower().startswith("lbdir")
    )
    if not candidates:
        return ""
    if len(candidates) > 1 and lb_number is not None:
        lb_txt = [
            f for f in attachments_dir.iterdir()
            if f.suffix.lower() == ".txt"
            and not f.name.lower().startswith("lbdir")
            and f"LB-{lb_number}" in f.name
        ]
        if lb_txt:
            base = lb_txt[0].stem.replace(f"-LB-{lb_number}", "")
            matching = [f for f in candidates if base in f.name]
            if matching:
                candidates = sorted(matching)
    try:
        return candidates[0].read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


_FOOTER = "[i][color=#888888]Brought to you by kuddukan, via the Bob-O-Matic v1.0.[/color][/i]"


def _build_body(entry: dict, attachments_dir: Path | None, lb_number: int | None = None) -> str:
    """Build the post body from entry fields and LB attachment files.

    Format:
        1. Metadata header (larger text): Date | Location | CDR | Rating | Timing | LB-XXXXX (red)
        2. [hr] separator
        3. Info text from the LB-numbered txt file (or entry.description fallback)
        4. [b]Checksums[/b] + [code]lbdir content[/code]
        5. [hr] + footer attribution line

    Args:
        entry: Dict from the entries table.
        attachments_dir: Path to data/attachments/LB-XXXXX/ or None.
        lb_number: Integer LB number for locating the correct attachment files.

    Returns:
        Post body string with BBcode.  Uses \\n line separators; caller must
        normalise to \\r\\n when submitting via multipart/form-data.
    """
    parts: list[str] = []

    # --- Metadata header ---
    date_str = (entry.get("date_str") or "").strip()
    location = (entry.get("location") or "").strip()
    cdr      = (entry.get("cdr") or "").strip()
    rating   = (entry.get("rating") or "").strip()
    timing   = (entry.get("timing") or "").strip()

    meta_fields = []
    if date_str: meta_fields.append(f"[b]Date:[/b] {date_str}")
    if location: meta_fields.append(f"[b]Location:[/b] {location}")
    if cdr:      meta_fields.append(f"[b]CDR:[/b] {cdr}")
    if rating:   meta_fields.append(f"[b]Rating:[/b] {rating}")
    if timing:   meta_fields.append(f"[b]Timing:[/b] {timing}")
    if lb_number is not None:
        lb_id = f"LB-{lb_number:05d}"
        detail_url = (
            f"http://www.losslessbob.wonderingwhattochoose.com/detail/{lb_id}.html"
        )
        meta_fields.append(f"[url={detail_url}][color=red][b]{lb_id}[/b][/color][/url]")

    if meta_fields:
        # Slightly larger than body text so the header stands out; [hr] follows on next line
        header_line = "   |   ".join(meta_fields)
        parts.append(f"[size=13pt]{header_line}[/size]\n[hr]")

    # --- Info / setlist text ---
    attach_path = attachments_dir if isinstance(attachments_dir, Path) else (
        Path(attachments_dir) if attachments_dir else None
    )
    info_text = _read_lb_txt(attach_path, lb_number) if attach_path else ""
    if info_text:
        parts.append(info_text)
    else:
        description = (entry.get("description") or "").strip()
        setlist     = (entry.get("setlist") or "").strip()
        if description:
            parts.append(description)
        elif setlist:
            parts.append(setlist)

    # --- Checksums (lbdir) ---
    lbdir_text = _read_lbdir(attach_path, lb_number) if attach_path else ""
    if lbdir_text:
        parts.append(f"[b]lbdir[/b]\n[code]{lbdir_text}[/code]")

    # --- Footer ---
    parts.append(f"[hr]\n{_FOOTER}")

    return "\n\n".join(parts).strip()


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
    body = _build_body(entry, attach_path, lb_number)
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

    lb_id = f"LB-{lb_number:05d}"

    # --- Build subject ---
    if subject_override:
        subject = subject_override
    else:
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
        body = _build_body(entry, attach_path, lb_number)

    # Multipart/form-data requires CRLF line endings in text fields; bare \n
    # is silently stripped by some SMF installs when the attachment upload
    # forces the request into multipart encoding.
    message_crlf = body.replace("\r\n", "\n").replace("\n", "\r\n")

    payload = {
        **hidden,
        "subject": subject,
        "desc": lb_id,
        "message": message_crlf,
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
        "post_lb_topic: posting LB-%05d subject=%r desc=%r body_len=%d torrent=%s",
        lb_number, subject, lb_id, len(body), torrent.name,
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
                board_resp = session.get(_board_url_sorted(location), timeout=15,
                                         headers={"Referer": form_action})
                topic_url = _find_newest_topic(board_resp, subject=subject) or location
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
                "desc": lb_id,
                "message": message_crlf,
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
                    board_resp2 = session.get(_board_url_sorted(location2), timeout=15,
                                              headers={"Referer": retry_action})
                    topic_url2 = _find_newest_topic(board_resp2, subject=subject) or location2
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
"""Edit the opening post of an existing WTRF topic (TODO-136).

SMF 2.x edit flow, reusing :mod:`backend.forum_poster`'s login:

1. GET the topic page and find the opening post's message id (the first
   ``div#msg_NNNN``) and, when present, its "Modify" link.
2. GET the edit form (``index.php?action=post;msg=<m>;topic=<t>.0``). The form
   carries the current subject (``input[name=subject]``), the raw BBCode body
   (``textarea[name=message]``) and every hidden field SMF validates on save —
   ``topic``, ``msg``, ``seqnum``, ``last_msg`` and the per-session token whose
   *name* is random (SMF 1.x called it ``sesc``; 2.x uses ``<var>=<sc>``).
3. POST all hidden fields back with the new subject/message to the form's own
   ``action`` (``action=post2;…;msg=<m>``). SMF answers a successful save with a
   redirect to the topic; anything else is an error page.

Steps 1–2 are read-only and back the GUI preview; step 3 only runs from
:func:`edit_post` with ``dry_run=False``.
"""
from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from backend.forum_poster import (
    FORUM_BASE,
    _extract_smf_error,
    _find_post_form,
    _resolve_url,
)

logger = logging.getLogger(__name__)

_TOPIC_ID_RE = re.compile(r"topic=(\d+)")
_MSG_DIV_RE = re.compile(r"^msg_(\d+)$")
_REDIRECTS = (301, 302, 303, 307, 308)


def _edit_url(topic_id: int, msg_id: int) -> str:
    return f"{FORUM_BASE}/index.php?action=post;msg={msg_id};topic={topic_id}.0"


def _topic_page_url(topic_url: str) -> str:
    """Canonical first page of the topic, so the first ``msg_`` div is the OP."""
    m = _TOPIC_ID_RE.search(topic_url)
    return f"{FORUM_BASE}/index.php?topic={m.group(1)}.0" if m else topic_url


def _norm(text: str) -> str:
    """Line endings and trailing whitespace don't count as an edit."""
    return text.replace("\r\n", "\n").rstrip()


def _find_opening_post(html: str) -> tuple[int | None, int | None, str]:
    """Locate the opening post on a topic page.

    Args:
        html: Topic page HTML.

    Returns:
        Tuple of (topic_id, msg_id, modify_url). ``modify_url`` is the
        absolute "Modify" link for that message when the page shows one (the
        viewer may edit it), else empty.
    """
    soup = BeautifulSoup(html, "lxml")
    first = soup.find("div", id=_MSG_DIV_RE)
    if first is None:
        return None, None, ""
    msg_id = int(_MSG_DIV_RE.match(first["id"]).group(1))
    msg_re = re.compile(rf"action=post;.*\bmsg={msg_id}(?!\d)")
    modify = soup.find("a", href=lambda h: h and "post2" not in h and msg_re.search(h))
    modify_url = _resolve_url(modify["href"]) if modify else ""
    topic_id = None
    for src in (modify_url, *(a["href"] for a in soup.find_all("a", href=_TOPIC_ID_RE))):
        m = _TOPIC_ID_RE.search(src or "")
        if m:
            topic_id = int(m.group(1))
            break
    return topic_id, msg_id, modify_url


def _parse_edit_form(html: str) -> dict:
    """Pull the current subject/body and hidden fields out of an SMF edit form.

    Args:
        html: Edit-form page HTML.

    Returns:
        Dict with ``form_action``, ``fields`` (hidden inputs), ``subject``,
        ``body`` and ``description`` (the topic-description mod's field,
        empty when the board has none). ``form_action`` is empty when the page
        is not an edit form (no permission, login wall, error page).
    """
    soup = BeautifulSoup(html, "lxml")
    form = _find_post_form(soup)
    if form is None:
        return {"form_action": "", "fields": {}, "subject": "", "body": "",
                "description": "", "error": _extract_smf_error(soup)}
    fields = {
        inp["name"]: inp.get("value", "")
        for inp in form.find_all("input", {"type": "hidden"}) if inp.get("name")
    }
    subj = form.find("input", {"name": "subject"})
    desc = form.find("input", {"name": "description"})
    msg = form.find("textarea", {"name": "message"})
    return {
        "form_action": _resolve_url(form.get("action", "")),
        "fields": fields,
        "subject": subj.get("value", "") if subj else "",
        "body": msg.get_text() if msg else "",
        "description": desc.get("value", "") if desc else "",
        "error": "",
    }


def fetch_post_for_edit(session: requests.Session, topic_url: str) -> dict:
    """Fetch the opening post of a topic in its editable (BBCode) form.

    Args:
        session: Authenticated session from ``forum_poster._get_session``.
        topic_url: Any link into the topic.

    Returns:
        ``{ok, topic_id, msg_id, edit_url, form_action, fields, subject, body,
        description}`` on success, ``{ok: False, error}`` otherwise.
    """
    try:
        page_url = _topic_page_url(topic_url)
        resp = session.get(page_url, timeout=20, headers={"Referer": FORUM_BASE})
        if "action=login" in (resp.url or ""):
            return {"ok": False, "error": "Session not authenticated (redirected to login)."}
        topic_id, msg_id, modify_url = _find_opening_post(resp.text)
        if msg_id is None:
            return {"ok": False, "error": "Could not find the opening post on the topic page."}
        if topic_id is None:
            m = _TOPIC_ID_RE.search(topic_url)
            topic_id = int(m.group(1)) if m else None
        if topic_id is None:
            return {"ok": False, "error": "Could not determine the topic id."}
        edit_url = modify_url or _edit_url(topic_id, msg_id)

        resp = session.get(edit_url, timeout=20, headers={"Referer": page_url})
        if "action=login" in (resp.url or ""):
            return {"ok": False, "error": "Session not authenticated (redirected to login)."}
        form = _parse_edit_form(resp.text)
        if not form["form_action"]:
            return {"ok": False, "error": form["error"]
                    or "No edit form returned — the account may not own this post."}
        if str(form["fields"].get("msg", msg_id)) != str(msg_id):
            return {"ok": False, "error": "Edit form is for a different message."}
        return {"ok": True, "topic_id": topic_id, "msg_id": msg_id,
                "edit_url": edit_url, **{k: v for k, v in form.items() if k != "error"}}
    except Exception as exc:
        logger.error("fetch_post_for_edit %s: %s", topic_url, exc)
        return {"ok": False, "error": str(exc)}


def edit_post(
    session: requests.Session,
    topic_url: str,
    subject: str,
    body: str,
    dry_run: bool = True,
) -> dict:
    """Replace the subject/body of a topic's opening post.

    Args:
        session: Authenticated session from ``forum_poster._get_session``.
        topic_url: Any link into the topic.
        subject: New subject line (blank keeps the current one).
        body: New BBCode body (blank keeps the current one).
        dry_run: When True (default) only fetch the edit form and report what
            would change — nothing is POSTed.

    Returns:
        ``{ok, dry_run, changed, current: {subject, body}, proposed: {subject,
        body}, topic_url}``; on a real save also ``saved: True``. On failure
        ``{ok: False, error}``.
    """
    cur = fetch_post_for_edit(session, topic_url)
    if not cur["ok"]:
        return cur
    new_subject = subject.strip() or cur["subject"]
    new_body = body if body.strip() else cur["body"]
    changed = [k for k, a, b in (("subject", cur["subject"], new_subject),
                                 ("body", cur["body"], new_body)) if _norm(a) != _norm(b)]
    canonical = _topic_page_url(topic_url)
    result = {
        "ok": True, "dry_run": dry_run, "changed": changed, "topic_url": canonical,
        "msg_id": cur["msg_id"],
        "current": {"subject": cur["subject"], "body": cur["body"]},
        "proposed": {"subject": new_subject, "body": new_body},
    }
    if dry_run or not changed:
        return result

    payload = {
        **cur["fields"],
        "subject": new_subject,
        "message": new_body.replace("\r\n", "\n").replace("\n", "\r\n"),
        "post": "Save",
    }
    if cur["description"]:
        payload["description"] = cur["description"]
    try:
        resp = session.post(
            cur["form_action"], data=payload, timeout=30, allow_redirects=False,
            headers={"Referer": cur["edit_url"], "Origin": FORUM_BASE},
        )
    except Exception as exc:
        logger.error("edit_post %s: %s", topic_url, exc)
        return {"ok": False, "error": str(exc)}
    if resp.status_code in _REDIRECTS:
        location = _resolve_url(resp.headers.get("Location", ""))
        if f"topic={cur['topic_id']}" in location:
            return {**result, "saved": True}
        return {"ok": False, "error": f"Unexpected redirect after edit (Location: {location})"}
    smf_error = _extract_smf_error(BeautifulSoup(resp.text, "lxml"))
    return {"ok": False,
            "error": smf_error or f"Edit was not accepted (HTTP {resp.status_code})."}

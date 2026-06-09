"""Shared HTML utilities for the offline site mirror.

Currently provides :func:`rewrite_links`, which converts server-absolute
``href``/``src`` attributes in a cached page to relative paths so the
page can be browsed via ``file://`` without a running server.
"""
from __future__ import annotations

import os
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

_ATTRS = ("href", "src", "action")


def rewrite_links(html: str, page_url: str, base_domain: str) -> str:
    """Rewrite same-domain absolute paths to relative paths in *html*.

    Only server-absolute paths (starting with ``/``) that resolve to the
    same domain as *base_domain* are rewritten.  External links, protocol
    URIs (``mailto:``, ``javascript:``, ``data:``), and fragment-only
    anchors are left unchanged.

    The result is valid for file:// browsing when the page is stored at the
    mirror path that corresponds to *page_url*.

    Args:
        html:        Raw HTML text fetched from the server.
        page_url:    The URL the page was fetched from, e.g.
                     ``http://www.losslessbob.wonderingwhattochoose.com/detail/LB-00001.html``.
        base_domain: Domain to consider "same-site", e.g.
                     ``www.losslessbob.wonderingwhattochoose.com``.

    Returns:
        HTML string with server-absolute paths converted to relative paths.
    """
    page_path = PurePosixPath(urlparse(page_url).path or "/index.html")
    page_dir  = page_path.parent

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(True):
        for attr in _ATTRS:
            val = tag.get(attr)
            if not val or not isinstance(val, str):
                continue
            val = val.strip()
            # Skip non-navigable URIs
            if val.startswith(("mailto:", "javascript:", "data:", "tel:", "#")):
                continue
            # Skip already-relative paths (no scheme, doesn't start with /)
            if not val.startswith("/") and "://" not in val:
                continue
            # Resolve to absolute then check domain
            abs_url = urljoin(page_url, val)
            parsed  = urlparse(abs_url)
            if parsed.netloc and parsed.netloc != base_domain:
                continue  # external link — leave as-is
            # Convert to relative path from the current page's directory
            target = PurePosixPath(parsed.path or "/index.html")
            try:
                rel = os.path.relpath(str(target), str(page_dir))
                # os.path.relpath uses the OS separator; normalise to /
                rel = rel.replace(os.sep, "/")
                tag[attr] = rel
            except ValueError:
                pass  # Windows cross-drive — leave unchanged

    return str(soup)

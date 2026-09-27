"""backend.scraper.probe_detail_page — live LB-page check behind lb_nc's move gate.

_fetch is monkeypatched: no network.
"""

from __future__ import annotations

import pytest

import backend.scraper as scraper


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


@pytest.mark.parametrize("fetched, exists", [
    ((_Resp("<html>LB-00042 details</html>"), 200), True),
    ((None, 404), False),
    ((_Resp(f"<p>{scraper._SOFT_404_MARKER}</p>"), 200), False),
    ((None, 0), None),
])
def test_probe_detail_page(monkeypatch, fetched, exists):
    seen = []
    monkeypatch.setattr(scraper, "_fetch", lambda url, retries=3: (seen.append(url), fetched)[1])
    res = scraper.probe_detail_page(42)
    assert res["exists"] is exists
    assert seen == [scraper.BASE_URL + "/detail/LB-00042.html"]

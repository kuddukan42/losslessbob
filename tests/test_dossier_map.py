"""C30: compact venue-card locator -- marker kind follows ``venue.coords`` basis."""
from __future__ import annotations

import pytest

from backend.dossier import _MAP_COMPACT_H, _MAP_COMPACT_W, _render_locator_svg


def _svg(marker: str) -> str:
    svg = _render_locator_svg(35.63, 139.79, "Japan", 400,
                              _MAP_COMPACT_W, _MAP_COMPACT_H, marker=marker)
    assert svg is not None
    return svg


def test_venue_marker_is_solid_pin_with_halo():
    svg = _svg("venue")
    assert 'class="pin-dot"' in svg and 'class="pin-halo"' in svg
    assert 'class="pin-ring"' not in svg
    assert 'data-marker="venue"' in svg


def test_city_centre_marker_is_hollow_ring_without_halo():
    svg = _svg("city_centre")
    assert 'class="pin-ring"' in svg
    assert 'class="pin-dot"' not in svg and 'class="pin-halo"' not in svg


def test_compact_viewbox():
    assert f'viewBox="0 0 {_MAP_COMPACT_W} {_MAP_COMPACT_H}"' in _svg("venue")


def test_default_marker_keeps_d1_solid_pin():
    svg = _render_locator_svg(35.63, 139.79, "Japan", 400)
    assert 'class="pin-dot"' in svg and 'viewBox="0 0 300 210"' in svg


def test_unknown_marker_rejected():
    with pytest.raises(ValueError):
        _render_locator_svg(0.0, 0.0, None, 400, marker="pin")


def test_no_map_without_host_country():
    from backend.dossier_anchors import _set_venue_map, _ViewBuilder

    vb = _ViewBuilder()
    _set_venue_map(vb, {"lat": 1.0, "lng": 2.0}, 1.0, 2.0, "city_centre")
    assert "venue.map" not in vb.fields and "map_svg" not in vb.ctx
    _set_venue_map(vb, {"map_focus": "Japan", "map_scale": 400}, 35.6, 139.8, "city_centre")
    assert vb.fields["venue.map"]["value"] == "city_centre"
    assert 'class="pin-ring"' in vb.ctx["map_svg"]


def test_same_country_accepts_blank_and_uk_nations_rejects_mismatch():
    """C6 fallback: a bare-city-keyed gazetteer row is usable unless countries clash."""
    from backend.dossier_anchors import _same_country

    assert _same_country("", "England")
    assert _same_country("England", "United Kingdom")
    assert _same_country("United States", "USA")
    assert not _same_country("United States", "England")

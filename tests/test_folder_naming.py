"""Tests for xref-aware naming in backend/folder_naming.py (FABLE_XREF_INCORPORATION.md
B2 / D2): build_standard_name / build_multi_lb_name gain an xref parameter, and
parse_xref_tag / strip_lb_tag must accept the wild xref variants already on disk.
"""

import pytest

from backend.folder_naming import (
    build_multi_lb_name,
    build_standard_name,
    lb_tag,
    parse_xref_tag,
    strip_lb_tag,
)

# ---------------------------------------------------------------------------
# lb_tag
# ---------------------------------------------------------------------------

def test_lb_tag_canonical_has_no_suffix():
    assert lb_tag(2) == "LB-00002"


def test_lb_tag_xref_is_5_digit_padded_both_sides():
    assert lb_tag(2, 961) == "LB-00002-xref00961"


# ---------------------------------------------------------------------------
# build_standard_name
# ---------------------------------------------------------------------------

def test_build_standard_name_canonical_unchanged():
    """xref=0 (default) must produce exactly the pre-B2 canonical name."""
    name = build_standard_name(2, "7/8/78", "Nashville, TN", "public")
    assert name == "1978-07-08 Nashville, TN (LB-00002)"


def test_build_standard_name_with_xref():
    name = build_standard_name(2, "7/8/78", "Nashville, TN", "public", xref=961)
    assert name == "1978-07-08 Nashville, TN (LB-00002-xref00961)"


def test_build_standard_name_xref_fallback_no_date_location():
    name = build_standard_name(2, "", "", "public", xref=961)
    assert name == "LB-00002-xref00961"


def test_build_standard_name_xref_with_nft():
    name = build_standard_name(2, "7/8/78", "Nashville, TN", "private", xref=961)
    assert name == "1978-07-08 Nashville, TN (LB-00002-xref00961)-NFT"


# ---------------------------------------------------------------------------
# build_multi_lb_name
# ---------------------------------------------------------------------------

def test_build_multi_lb_name_canonical_unchanged():
    name = build_multi_lb_name([3, 2], "7/8/78", "Nashville, TN", "public")
    assert name == "1978-07-08 Nashville, TN (LB-00002+LB-00003)"


def test_build_multi_lb_name_with_xrefs_aligned_to_lb_numbers():
    """xrefs is aligned index-for-index with lb_numbers, not the sorted order —
    the function must re-pair after sorting by lb_number."""
    name = build_multi_lb_name(
        [3, 2], "7/8/78", "Nashville, TN", "public", xrefs=[500, 961],
    )
    # lb_numbers[0]=3 -> xrefs[0]=500 ; lb_numbers[1]=2 -> xrefs[1]=961
    # sorted by lb_number: LB-00002 (xref 961), then LB-00003 (xref 500)
    assert name == "1978-07-08 Nashville, TN (LB-00002-xref00961+LB-00003-xref00500)"


def test_build_multi_lb_name_xrefs_length_mismatch_raises():
    with pytest.raises(ValueError):
        build_multi_lb_name([2, 3], "7/8/78", "Nashville, TN", "public", xrefs=[961])


def test_build_multi_lb_name_partial_xref():
    """Only one of two entries is an xref fileset — the other stays bare."""
    name = build_multi_lb_name(
        [2, 3], "7/8/78", "Nashville, TN", "public", xrefs=[961, 0],
    )
    assert name == "1978-07-08 Nashville, TN (LB-00002-xref00961+LB-00003)"


# ---------------------------------------------------------------------------
# parse_xref_tag — must accept the wild variants already on disk
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fragment,expected", [
    ("xref-01995", 1995),
    ("Xref-1292", 1292),
    ("xref2141", 2141),
    ("LB-00002-xref00961", 961),
    ("2026-01-01 Somewhere (LB-00002-xref00961)", 961),
    ("no xref here", 0),
    ("LB-00002", 0),
])
def test_parse_xref_tag_wild_variants(fragment, expected):
    assert parse_xref_tag(fragment) == expected


# ---------------------------------------------------------------------------
# strip_lb_tag
# ---------------------------------------------------------------------------

def test_strip_lb_tag_single_canonical():
    assert strip_lb_tag("1978-07-08 Nashville, TN (LB-00002)") == "1978-07-08 Nashville, TN"


def test_strip_lb_tag_single_xref():
    assert (
        strip_lb_tag("1978-07-08 Nashville, TN (LB-00002-xref00961)")
        == "1978-07-08 Nashville, TN"
    )


def test_strip_lb_tag_multi():
    assert (
        strip_lb_tag("1978-07-08 Nashville, TN (LB-00002+LB-00003-xref00500)")
        == "1978-07-08 Nashville, TN"
    )


def test_strip_lb_tag_no_tag_present_unchanged():
    assert strip_lb_tag("1978-07-08 Nashville, TN") == "1978-07-08 Nashville, TN"


def test_strip_lb_tag_round_trips_with_build():
    """strip_lb_tag(build_standard_name(...)) must recover the date/location base,
    so app.py's re-tag fallback path never leaves a stale xref tag behind."""
    built = build_standard_name(2, "7/8/78", "Nashville, TN", "public", xref=961)
    assert strip_lb_tag(built) == "1978-07-08 Nashville, TN"

"""Tests for tools/dossier_audit.py (Phase G, GOLDEN_DOSSIER_FIX_PLAN.md).

Synthetic HTML snippets exercise each structural lint without any network access,
plus the title-fold helper used by the setlist diff.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from tools.dossier_audit import (
    check_em_dash_disc,
    check_excluded_in_alternates,
    check_family_contiguous,
    check_family_membership,
    check_internal_links,
    check_list_repr,
    check_setlist_missing,
    check_two_show_cross_pick,
    check_zero_min,
    data_lb_fields,
    fold_title,
    run_structural_lints,
)


def test_fold_title_apostrophe_and_parenthetical():
    assert fold_title("Talkin’ World War III Blues (live)") == fold_title(
        "Talking World War III Blues"
    )


def test_fold_title_straight_and_curly_apostrophe_match():
    assert fold_title("Ain't Talkin'") == fold_title("Ain’t Talkin’")


def test_fold_title_collapses_punctuation_and_case():
    assert fold_title("It's All Over Now, Baby Blue") == fold_title(
        "IT'S ALL OVER NOW BABY BLUE"
    )


def test_data_lb_fields_strips_tags_and_unescapes():
    html_snip = '<span data-lb="song[].title">Mr. Tambourine Man &amp; Co.</span>'
    assert data_lb_fields(html_snip, "song[].title") == ["Mr. Tambourine Man & Co."]


def test_check_list_repr_flags_python_list_text():
    html_snip = '<span data-lb="context.bobtalk">[\'said something\', \'else\']</span>'
    findings = check_list_repr("p.html", html_snip)
    assert len(findings) == 1
    assert findings[0].check == "list-repr"


def test_check_list_repr_clean_text_passes():
    html_snip = '<span data-lb="context.bobtalk">He said something.</span>'
    assert check_list_repr("p.html", html_snip) == []


def test_check_zero_min_flags_literal_zero():
    html_snip = '<span data-lb="pick.runtime">0 min</span>'
    findings = check_zero_min("p.html", html_snip)
    assert len(findings) == 1
    assert findings[0].check == "zero-min"


def test_check_zero_min_ignores_nonzero_runtime():
    html_snip = '<span data-lb="pick.runtime">87 min</span>'
    assert check_zero_min("p.html", html_snip) == []


def test_check_em_dash_disc_flags_placeholder():
    html_snip = '<span data-lb="source[].disc_count">— disc(s)</span>'
    findings = check_em_dash_disc("p.html", html_snip)
    assert len(findings) == 1
    assert findings[0].check == "em-dash-disc"


def test_check_em_dash_disc_clean_passes():
    html_snip = '<span data-lb="source[].disc_count">2 disc(s)</span>'
    assert check_em_dash_disc("p.html", html_snip) == []


_EXCLUDED_ALT_HTML = """
<span data-lb="source[].lb_id">LB-07981</span>
<span data-lb="source[].character">EXCLUDED &mdash; lossy source suspected</span>
<div class="stats-line" data-lb="verdict.alternates[]">
  <ul class="diffs"><li>LB-07981 &mdash; scan: 81.2 / 86.1</li></ul>
</div>
"""


def test_check_excluded_in_alternates_flags_match():
    findings = check_excluded_in_alternates("p.html", _EXCLUDED_ALT_HTML)
    assert len(findings) == 1
    assert findings[0].check == "excluded-in-alternates"
    assert "LB-07981" in findings[0].detail


def test_check_excluded_in_alternates_clean_when_not_excluded():
    html_snip = _EXCLUDED_ALT_HTML.replace("EXCLUDED", "recommended")
    assert check_excluded_in_alternates("p.html", html_snip) == []


_NONCONTIG_FAM_HTML = """
<tr class="fam-head"><td><span data-lb="family[].label">Family A</span>
<span data-lb="family[].id">1975-12-08#1-2</span></td></tr>
<tr class="mrow in-fam"><td>LB-00001</td></tr>
<tr class="fam-head"><td><span data-lb="family[].label">Family B</span>
<span data-lb="family[].id">1975-12-08#3-4</span></td></tr>
<tr class="mrow in-fam"><td>LB-00003</td></tr>
<tr class="fam-head"><td><span data-lb="family[].label">Family A</span>
<span data-lb="family[].id">1975-12-08#1-2</span></td></tr>
<tr class="mrow in-fam"><td>LB-00002</td></tr>
"""


def test_check_family_contiguous_flags_split_family():
    findings = check_family_contiguous("p.html", _NONCONTIG_FAM_HTML)
    assert len(findings) == 1
    assert findings[0].check == "family-noncontiguous"


_CONTIG_FAM_HTML = """
<tr class="fam-head"><td><span data-lb="family[].label">Family A</span>
<span data-lb="family[].id">1975-12-08#1-2</span></td></tr>
<tr class="mrow in-fam"><td>LB-00001</td></tr>
<tr class="mrow in-fam"><td>LB-00002</td></tr>
<tr class="fam-head"><td><span data-lb="family[].label">Family B</span>
<span data-lb="family[].id">1975-12-08#3-4</span></td></tr>
<tr class="mrow in-fam"><td>LB-00003</td></tr>
"""


def test_check_family_contiguous_clean_when_grouped():
    assert check_family_contiguous("p.html", _CONTIG_FAM_HTML) == []


def test_check_family_membership_flags_id_not_in_family():
    # LB-00099 sits under Family A (ids 1-2) but 99 is not in the id list.
    html_snip = """
    <tr class="fam-head"><td><span data-lb="family[].id">1975-12-08#1-2</span></td></tr>
    <tr class="mrow in-fam"><td>LB-00099</td></tr>
    """
    findings = check_family_membership("p.html", html_snip)
    assert len(findings) == 1
    assert findings[0].check == "family-id-mismatch"


def test_check_family_membership_clean_when_listed():
    html_snip = """
    <tr class="fam-head"><td><span data-lb="family[].id">1975-12-08#1-2</span></td></tr>
    <tr class="mrow in-fam"><td>LB-00001</td></tr>
    """
    assert check_family_membership("p.html", html_snip) == []


# F3: family id/basis moved off hidden spans onto a `data-family` attribute on the
# `<tr class="fam-head">` itself. These cover the new export form; the tests above
# cover the old hidden-span form, which the audit still has to keep reading.
_NONCONTIG_FAM_HTML_NEW = """
<tr class="fam-head" data-family="1975-12-08#1-2"><td>
<span data-lb="family[].label">Family A</span></td></tr>
<tr class="mrow in-fam" data-family="1975-12-08#1-2"><td>LB-00001</td></tr>
<tr class="fam-head" data-family="1975-12-08#3-4"><td>
<span data-lb="family[].label">Family B</span></td></tr>
<tr class="mrow in-fam" data-family="1975-12-08#3-4"><td>LB-00003</td></tr>
<tr class="fam-head" data-family="1975-12-08#1-2"><td>
<span data-lb="family[].label">Family A</span></td></tr>
<tr class="mrow in-fam" data-family="1975-12-08#1-2"><td>LB-00002</td></tr>
"""


def test_check_family_contiguous_flags_split_family_new_form():
    findings = check_family_contiguous("p.html", _NONCONTIG_FAM_HTML_NEW)
    assert len(findings) == 1
    assert findings[0].check == "family-noncontiguous"


def test_check_family_membership_new_form_flags_mismatch():
    html_snip = """
    <tr class="fam-head" data-family="1975-12-08#1-2"><td></td></tr>
    <tr class="mrow in-fam" data-family="1975-12-08#1-2"><td>LB-00099</td></tr>
    """
    findings = check_family_membership("p.html", html_snip)
    assert len(findings) == 1
    assert findings[0].check == "family-id-mismatch"


def test_check_family_membership_other_band_not_checked():
    html_snip = """
    <tr class="fam-head fam-head-other" data-family="__other__"><td>
    <span class="fam-name">Other sources</span></td></tr>
    <tr class="mrow" data-family="__other__"><td>LB-00099</td></tr>
    """
    assert check_family_membership("p.html", html_snip) == []


def test_check_two_show_cross_pick_flags_wrong_part():
    html_snip = (
        '<span data-lb="pick.lineage_short">Afternoon, low gen reel</span>'
    )
    findings = check_two_show_cross_pick(
        "1974-01-06_two-show-day--evening.html", html_snip
    )
    assert len(findings) == 1
    assert findings[0].check == "two-show-cross-pick"


def test_check_two_show_cross_pick_clean_for_matching_part():
    html_snip = (
        '<span data-lb="pick.lineage_short">Evening, low gen reel</span>'
    )
    findings = check_two_show_cross_pick(
        "1974-01-06_two-show-day--evening.html", html_snip
    )
    assert findings == []


def test_check_two_show_cross_pick_skips_single_show_page():
    html_snip = '<span data-lb="pick.lineage_short">Afternoon reel</span>'
    assert check_two_show_cross_pick("1999-06-11_propagated-tapers.html", html_snip) == []


def test_check_internal_links_flags_missing_file():
    with tempfile.TemporaryDirectory() as d:
        export_dir = Path(d)
        (export_dir / "present.html").write_text("<html></html>")
        html_snip = (
            '<a href="present.html">ok</a><a href="missing.html">broken</a>'
        )
        findings = check_internal_links("p.html", html_snip, export_dir)
        assert len(findings) == 1
        assert "missing.html" in findings[0].detail


def test_check_internal_links_ignores_external_and_anchor_hrefs():
    with tempfile.TemporaryDirectory() as d:
        export_dir = Path(d)
        html_snip = (
            '<a href="https://example.com/x">ext</a><a href="#top">anchor</a>'
        )
        assert check_internal_links("p.html", html_snip, export_dir) == []


def test_check_setlist_missing_flags_zero_songs_with_source_songs():
    # 1989-06-13_no-setlist.html: dossier has 0 songs, bobserve lists 16.
    findings = check_setlist_missing(
        "1989-06-13_no-setlist.html", 0, "bobserve", 16
    )
    assert len(findings) == 1
    assert findings[0].check == "setlist-missing"
    assert "bobserve" in findings[0].detail
    assert "16" in findings[0].detail


def test_check_setlist_missing_clean_when_both_empty():
    assert check_setlist_missing("p.html", 0, "bobserve", 0) == []


def test_check_setlist_missing_clean_when_dossier_has_songs():
    assert check_setlist_missing("p.html", 12, "bobserve", 12) == []


def test_run_structural_lints_aggregates_all_lints():
    html_snip = _EXCLUDED_ALT_HTML + '<span data-lb="pick.runtime">0 min</span>'
    findings = run_structural_lints("p.html", html_snip)
    checks = {f.check for f in findings}
    assert "excluded-in-alternates" in checks
    assert "zero-min" in checks

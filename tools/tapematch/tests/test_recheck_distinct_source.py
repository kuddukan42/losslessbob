"""Tests for the TODO-324 distinct-source recheck classifier
(recheck_distinct_source.py).

Covers the deterministic decision tree in classify_source(): merged-despite-flag,
other-evidence (commentary/fingerprint/lineage), only-claim (bare speed/correlation
restatement), unclear-no-mention (isolated, never discussed), and the multi-line
"section" prose matching that TODO-324's real-run spot-check exposed as a gap
(evidence stated in a paragraph after the heading, without repeating the LB id
on every line) plus the LB-id zero-padding mismatch between report.md source
names and analysis.md tables.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recheck_distinct_source import (  # noqa: E402
    classify_source,
    extract_lb_id,
    find_distinct_source_lines,
    normalize_lb_id,
    parse_table,
    prose_paragraphs_for,
)


def test_extract_lb_id_parenthesized():
    assert extract_lb_id("1978-06-05 Los Angeles (LB-15207)") == "LB-15207"


def test_extract_lb_id_bare_suffix():
    assert extract_lb_id("Bob Dylan Cricket Arena Charlotte 2002-02-10 DS Archive-LB-15782") == "LB-15782"


def test_extract_lb_id_none():
    assert extract_lb_id("Seattle 1980-01-15  NO LB") is None


def test_normalize_lb_id_pads_to_five_digits():
    assert normalize_lb_id("LB-2690") == "LB-02690"
    assert normalize_lb_id("LB-02690") == "LB-02690"
    assert normalize_lb_id("LB-123456") == "LB-123456"


def test_extract_lb_id_normalizes_unpadded_bare_id():
    # report.md source names are sometimes unpadded even though analysis.md
    # tables always use 5-digit LB ids (TODO-324 spot-check: 2005-04-22 run).
    assert extract_lb_id("2005-04-22-spot [LB-2690]") == "LB-02690"


def test_find_distinct_source_lines():
    report = (
        "  [DISTINCT SOURCE] 1978-06-05 Los Angeles (LB-15207) "
        "(-5500 ppm speed offset, best cross-family corr 0.003): "
        "near-zero correlation to all other sources — entirely different recording\n"
    )
    lines = find_distinct_source_lines(report)
    assert lines == [("1978-06-05 Los Angeles (LB-15207)", -5500, 0.003)]


def test_parse_table_basic():
    text = (
        "| LB | Rating | Timing | Source | Family | Notes |\n"
        "|----|--------|--------|--------|--------|-------|\n"
        "| LB-01148 | B+ | 19min | some source text | 4 | 19min excerpt |\n"
        "| LB-01183 | B+ | 19min | other source text | 4 | 19min excerpt |\n"
    )
    table = parse_table(text)
    assert table["LB-01148"]["family"] == "4"
    assert table["LB-01183"]["family"] == "4"
    assert table["LB-01148"]["notes"] == "19min excerpt"


def test_merged_despite_flag():
    # Two rows sharing a family number: the written verdict already merged
    # the isolated-in-report source, so the untrusted claim was not relied on.
    analysis = (
        "| LB | Rating | Timing | Source | Family | Notes |\n"
        "|----|--------|--------|--------|--------|-------|\n"
        "| LB-01148 | B+ | 19min | src a | 4 | fp-link |\n"
        "| LB-01183 | B+ | 19min | src b | 4 | fp-link |\n"
    )
    bucket, reason, matched = classify_source("LB-01148", "src a (LB-01148)", analysis)
    assert bucket == "merged-despite-flag"
    assert "LB-01183" in reason


def test_only_claim_bare_speed_restatement():
    # Auto-triage template pattern: isolated family, prose restates the
    # algorithm's own speed/correlation reasoning and nothing else.
    analysis = (
        "| LB | Rating | Timing | Source | Family | Notes |\n"
        "|----|--------|--------|--------|--------|-------|\n"
        "| LB-15631 |  |  | zoom h2 | 2 | +44957 ppm |\n"
        "\n"
        "### LB-15631 — speed offset +44957 ppm (≈ PAL/cassette speed shift)\n"
        "\n"
        "Speed offset near ±15000 ppm suggests a PAL/NTSC speed mismatch or "
        "cassette played at wrong speed. Correctly isolated as distinct source.\n"
    )
    bucket, reason, matched = classify_source("LB-15631", "zoom h2 (LB-15631)", analysis)
    assert bucket == "only-claim"


def test_other_evidence_info_file_in_later_paragraph():
    # TODO-324 spot-check regression (2000-09-19 run): the heading names the
    # LB id, but the actual independent evidence ("own info file...") is in a
    # LATER paragraph of the same section that never repeats the id. A naive
    # line-by-line / single-paragraph match misses this.
    analysis = (
        "| LB | Rating | Timing | Source | Family | Notes |\n"
        "|----|--------|--------|--------|--------|-------|\n"
        "| LB-00051 | A- | 56min+61min | BOOTLEG: Crystal Cat | 1 | -24382 ppm |\n"
        "| LB-04483 | A | 69min+42min | Taper: Bach | 2 | |\n"
        "\n"
        "### LB-00051 / LB-04483 — cross-family speed offset is a non-issue\n"
        "\n"
        "The -24382 ppm figure and near-zero correlation come from comparing "
        "two entirely unrelated masters, not two takes of the same tape.\n"
        "\n"
        "LB-04483's own info file independently confirms the two are different "
        "recordings (\"different recording than crystal cat LB-51 based on "
        "different clapping at begin of d1t4\").\n"
    )
    bucket, reason, matched = classify_source("LB-00051", "BOOTLEG (LB-00051)", analysis)
    assert bucket == "other-evidence"
    assert "info file" in matched.lower()


def test_unclear_no_mention():
    analysis = (
        "| LB | Rating | Timing | Source | Family | Notes |\n"
        "|----|--------|--------|--------|--------|-------|\n"
        "| LB-06177 | A- | 65min+69min | BOOTLEG: Friends | 5 | |\n"
        "| LB-06724 |  |  | BOOTLEG: Creatures | 1 | disc also carries other dates |\n"
        "\n"
        "### LB-06724 — the disc carries other dates\n"
        "\n"
        "An unknown fraction of what was ingested under this date is not this "
        "show at all.\n"
    )
    bucket, reason, matched = classify_source("LB-06177", "BOOTLEG (LB-06177)", analysis)
    assert bucket == "unclear-no-mention"


def test_unparseable_no_lb_id():
    bucket, reason, matched = classify_source(None, "Seattle 1980-01-15  NO LB", "irrelevant")
    assert bucket == "unparseable"


def test_prose_paragraphs_for_groups_whole_section():
    text = (
        "### LB-14937 — inflated, explained\n"
        "\n"
        'Own notes state plainly: "This torrent consists of 10 source tapes."\n'
        "\n"
        "### LB-09999 — unrelated section\n"
        "\n"
        "Nothing to do with the other date's recording here.\n"
    )
    matched = prose_paragraphs_for("LB-14937", text)
    assert "Own notes state plainly" in matched
    assert "LB-09999" not in matched

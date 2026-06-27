"""Text feature extraction from LosslessBob curator description fields.

The LB site uses a consistent controlled vocabulary of audio artifact terms
(defined on the what-images page). Parsing these terms gives the model direct
access to the curator's own quality observations — complementary to (and
occasionally corrective of) the audio-signal features when acoustic evidence
is ambiguous (e.g. the description mentions clipping but the crest-factor
feature doesn't fire because only one track clips).

All features are 0.0 / 1.0 binary (presence or absence). The description field
is the `entries.description` DB column — the curator's free-text notes per LB.
"""
from __future__ import annotations

import re

# ─────────────────────────────────────────────────────────────────────────────
# Pattern registry. Each tuple: (feature_key, compiled_regex).
# Order matters only within a single key group — the flag is 1.0 if ANY pattern
# matches, so all patterns for the same key can be listed freely.
# ─────────────────────────────────────────────────────────────────────────────
_PATTERNS: list[tuple[str, re.Pattern]] = []


def _reg(key: str, *patterns: str) -> None:
    for p in patterns:
        _PATTERNS.append((key, re.compile(p, re.IGNORECASE)))


# Flaw terms — penalizing (negative weight expected in model)
_reg("txt_clipping",
     r"\bclipp(?:ing|ed)\b", r"\bdigital\s+clipp(?:ing|ed)\b", r"\bclips\b")

_reg("txt_brickwall",
     r"\bbrick\s*wall(?:ing|ed)?\b", r"\bbrickwall(?:ing|ed)?\b")

_reg("txt_limiting",
     r"\blimit(?:ing|ed)\b", r"\bheavily?\s+limit(?:ed|ing)\b")

_reg("txt_digipop",
     r"\bdigi[-\s]?pop\b", r"\bdiscontinuity\s+pop\b",
     r"\bdiscontinuit(?:y|ies)\b", r"\bsquare\s+wav(?:e\s+static|es?)?\b",
     r"\bdigital\s+pop\b")

_reg("txt_dropout",
     r"\bdigital\s+drop(?:s|out)?\b", r"\bdropout\b", r"\bdrops\b",
     r"\baudio\s+drop(?:s|out)?\b")

_reg("txt_gap",
     r"\bbetween[-\s]track\s+gap\b", r"\bgap\s+between\s+tracks?\b",
     r"\bsector\s+boundar(?:y|ies)\b", r"\btrack\s+gap\b")

_reg("txt_mic_hit",
     r"\bmic\s+hit\b", r"\bmic\s+bump\b", r"\bthump\b",
     r"\bmicrophone\s+(?:hit|bump)\b", r"\bcable\s+(?:thump|knock|hit)\b")

_reg("txt_hf_streak",
     r"\bhigh[-\s]?end\s+streak(?:ing)?\b", r"\bHF\s+streak(?:ing)?\b",
     r"\bhigh\s+frequency\s+streak(?:ing)?\b")

_reg("txt_compression",
     r"\bheavily?\s+compress(?:ed|ion)\b", r"\bcompress(?:ed|ion)\b",
     r"\bdynamic\s+compress(?:ed|ion)\b")

_reg("txt_minidisc",
     r"\blego\s+parapet\b", r"\blego\s+parapets\b", r"\bparapets?\b",
     r"\bmini[-\s]?disc\b", r"\bminidisc\b", r"\bMD\s+source\b",
     r"\bATRAC\b")

_reg("txt_floating_parapet",
     r"\bfloating\s+parapet\b", r"\bfloating\s+parapets?\b",
     r"\bMP3\s+(?:artifact|artifacting|parapet)\b",
     r"\bstreaming\s+artifact\b")

_reg("txt_32k_dat",
     r"\b32k\s+dat\b", r"\b32\s*kHz?\s+DAT\b", r"\bDAT\s+at\s+32k\b",
     r"\b(?:recorded|sampled)\s+at\s+32\s*k(?:Hz)?\b",
     r"\bnothing\s+above\s+16\s*k(?:Hz)?\b",
     r"\bcut\s+off\s+at\s+16\s*k(?:Hz)?\b",
     r"\b16\s*k(?:Hz)?\s+(?:cut|ceiling|wall)\b",
     r"\bnothing\s+above\s+16\s*k\b")

_reg("txt_talking",
     r"\btalking\b", r"\bbackground\s+talk(?:ing)?\b",
     r"\bcrowd\s+talk(?:ing)?\b", r"\bcrowd\s+noise\b",
     r"\bchatter(?:ing)?\b", r"\bpeople\s+talk(?:ing)?\b")

_reg("txt_singing",
     r"\bsing(?:ing)?\s+along\b", r"\bsing[-\s]?along\b",
     r"\bsingalong\b", r"\baudience\s+singing\b")

_reg("txt_remaster",
     r"\bremaster(?:ed|ing)?\b", r"\bre[-\s]?master(?:ed|ing)?\b")

_reg("txt_tv_band",
     r"\bTV\s+band\b", r"\btelevision\s+band\b",
     r"\b15[\s.]?6\s*k(?:Hz)?\s+(?:band|tone|line)\b",
     r"\bCRT\s+(?:noise|band|line)\b")

_reg("txt_cassette",
     r"\bcassette\b", r"\btape\s+source\b", r"\banalog\s+tape\b",
     r"\bcass(?:ette)?\s+(?:rip|transfer|dub)\b")

_reg("txt_eac_match",
     r"\bEAC\s+match\b", r"\bexact\s+EAC\b", r"\bclose\s+EAC\s+match\b",
     r"\bEAC\s+copy\b", r"\bsame\s+as\s+LB\b")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

#: All feature keys returned by :func:`extract_text_features`.
TEXT_FEATURE_KEYS: tuple[str, ...] = tuple(dict.fromkeys(k for k, _ in _PATTERNS))


def extract_text_features(description: str | None) -> dict[str, float]:
    """Extract binary flaw/artifact vocabulary features from a LB description.

    Args:
        description: The ``entries.description`` free-text string (or None/empty).

    Returns:
        Dict mapping feature key → 0.0 or 1.0. All :data:`TEXT_FEATURE_KEYS`
        are always present so the feature dict is a fixed-width row.
    """
    result: dict[str, float] = {k: 0.0 for k in TEXT_FEATURE_KEYS}
    if not description:
        return result
    for key, pattern in _PATTERNS:
        if result[key] == 0.0 and pattern.search(description):
            result[key] = 1.0
    return result

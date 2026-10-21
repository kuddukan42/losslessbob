"""Taper / source-chain extraction, taper aliases + vocabulary, lineage refs, run
records, setlist extraction.

Split from backend.db (TODO-369 S2). reload_taper_aliases() rebinds three globals here;
backend.db forwards them via __getattr__ rather than re-exporting them.
"""

import json
import logging
import re
import sqlite3
import time
from pathlib import Path

from backend.db import _ensure_init_db, get_connection, init_db
from backend.db_queue import get_write_queue

logger = logging.getLogger(__name__)


# ── Taper / source-chain extractor ────────────────────────────────────────────

_CHAIN_TOKEN = re.compile(
    r'(?:Schoeps|Neumann|Neuman|DPA|B&K|AKG|AT\d|Sennheiser|Sonic\s*Studios|Core\s*Sound|'
    r'CSB|CSHEB|DSM|Sony|Tascam|Zoom|Marantz|Sharp|Roland|M-Audio|Minidisc|'
    r'\bDAT\b|\bSBD\b|\bAUD\b|\bCDR\b|cassette|FLAC|WAV|SHN|EAC|dbPower|TLH|mkwACT|'
    r'Cooledit|CoolEdit|SoundForge|Wavelab|Sound\s*Devices)',
    re.IGNORECASE,
)

def _looks_like_chain(s: str) -> bool:
    return bool(re.search(r'[>\-–]', s)) and bool(_CHAIN_TOKEN.search(s))


def _strip_bt_parens(text: str) -> str:
    """Remove leading (a bittorrent …) / (a close eac match …) blocks."""
    out = text
    for _ in range(8):
        m = re.match(r'^\s*\([^\)]{20,600}\)\s*;?\s*', out, re.DOTALL)
        if m:
            out = out[m.end():]
        else:
            break
    return out


def _normalise_alias_key(text: str | None) -> str:
    """Lowercase + strip punctuation to the exact key form used in
    :data:`_KNOWN_TAPER_ALIASES` (the pre-lookup half of :func:`_normalise_taper`,
    factored out so a curator-entered alias — TODO-241, ``user_taper_aliases`` —
    hashes to the same key that free-text parsing would produce).

    Args:
        text: Raw text (name, handle, or free-text fragment). May be None.

    Returns:
        The normalised key, or '' for falsy/blank input (never None), so
        callers can treat an empty return as "not a valid alias" uniformly.
    """
    if not text:
        return ""
    s = text.lower()
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


_SERIES_CANONICAL_RE = re.compile(r'^(?:lt[a-z]|net taper [a-z])$')
# A taper phrase directly before a series code binds it ("taped by nti",
# "Source: LTB", "Taper=LTA", "Carsten reports this to be NTF", "matches to NTD").
# "same recording as LTD" binds too -- it names the tape this one is.
# Comparison words ("as", "than", "vs", "different from") are deliberately absent.
_SERIES_BINDING_PREFIX_RE = re.compile(
    r'(?:\b(?:taped|recorded|recording|source|taper|lineage|master|by|be|is|reports?|aka|'
    r'match(?:es)?(?:\s+to)?|identified\s+as|(?:is|are)\s+from|'
    r'same\s+(?:recording|source|tape|transfer)\s+as)\b|=)'
    r'[\s:=\-–>,"\'(]*(?:(?:the|an?)\s+)?$',
    re.IGNORECASE,
)
# The spelled-out label form "Net Taper: I" / "Net Taper - F".
_NET_TAPER_LABEL_RE = re.compile(r'\bnet\s*taper\s*[:\-#]\s*([a-z])\b', re.IGNORECASE)
# What may precede a series code that "starts the lineage": nothing, or a
# version tag ('version "b";'), within the code's own line.
_SERIES_LEAD_RE = re.compile(r'^[\s(\["\'*]*(?:version\s*"?\w{1,3}"?\s*[;,:]\s*)?$', re.IGNORECASE)


def _series_code_bound(text: str, m: re.Match) -> bool:
    """Whether a series-code match in *text* is a credit rather than a passing mention.

    Bound when the matched alias spells out "taper" itself ("net taper i",
    "legendary taper b"), when a taper phrase sits directly before it, or when
    it starts the lineage -- the first thing on its line, optionally after a
    version tag, or a bare comma-separated item early in the header line.

    Args:
        text: The scanned description window.
        m: A match whose group 1 is the series-code alias.

    Returns:
        True when the code should be read as the taper credit.
    """
    if 'taper' in m.group(1).lower():
        return True
    before = text[max(0, m.start() - 40):m.start()]
    if _SERIES_BINDING_PREFIX_RE.search(before):
        return True
    line_start = text.rfind('\n', 0, m.start()) + 1
    if _SERIES_LEAD_RE.match(text[line_start:m.start()]):
        return True
    # A bare comma-list item early in the header line ("Off DAT clone(s), LTF, Source").
    return (line_start == 0 and m.start() < 80
            and bool(re.search(r'[,;]\s*$', text[:m.start()]))
            and bool(re.match(r'\s*[,;]', text[m.end():])))


def extract_taper_and_source(description: str) -> tuple[str | None, str | None]:
    """Parse free-text description into (taper_name, source_chain).

    Both values may be None when the description carries no recording metadata
    (pure setlist, or only bittorrent-comparison notes).

    Values are kept short: taper_name ≤ 80 chars, source_chain ≤ 160 chars.
    """
    if not description or not description.strip():
        return None, None

    raw = description.strip()
    d   = _strip_bt_parens(raw)
    if not d:
        d = raw
    d600 = d[:600]
    fl   = d.split('\n')[0][:300].strip()

    taper_name: str | None   = None
    source_chain: str | None = None

    # ── 0. Known taper handles — confirmed names, checked before heuristics ─
    # A series code (lta-ltz, nta-ntz) only counts when it is bound to a taper
    # phrase or starts the lineage (plan E4: "not as warm as nti" is a comparison
    # with another source, not a credit); unbound ones are skipped, not fatal.
    for m0 in _KNOWN_TAPER_RE.finditer(d600):
        raw_h = m0.group(1)
        norm_h = _normalise_alias_key(raw_h)
        canonical = _KNOWN_TAPER_ALIASES.get(norm_h, raw_h)
        if _SERIES_CANONICAL_RE.match(canonical) and not _series_code_bound(d600, m0):
            continue
        taper_name = canonical
        break
    if not taper_name:
        m_nt = _NET_TAPER_LABEL_RE.search(d600)
        if m_nt:
            taper_name = f"net taper {m_nt.group(1).lower()}"
    if not taper_name:
        for m_lt in _LT_TAPER_RE.finditer(d600):
            if _series_code_bound(d600, m_lt):
                taper_name = m_lt.group(1).lower()
                break

    # ── 1. Explicit Taper: label (skip inside parentheticals) ────────────
    for m in re.finditer(
        r'\bTaper\s*:\s*(.+?)(?:[,)]\s*(?=(?:Source|Recording|Lineage|Location|Microphone|Recorder)\s*:)|[\n;]|$)',
        d600, re.IGNORECASE,
    ):
        pre = d600[:m.start()]
        if pre.count('(') > pre.count(')'):
            continue  # inside a parenthetical reference block
        # Trim to first comma-separated token
        v = m.group(1).strip().split(',')[0].strip().rstrip(',;.')
        # Strip trailing parenthetical (email addresses, dates, etc.)
        v = re.sub(r'\s*\([^)]{3,}\)\s*$', '', v).strip().rstrip(',;.')
        # If "by <NAME>" is embedded, extract just the name
        by_m = re.search(r'\bby\s+([A-Z][A-Z\s]{2,40})', v)
        if by_m:
            v = by_m.group(1).strip().title()
        _BAD_TAPER = {'unidentified', 'unknown', 'no info', 'n/a', 'none', 'no taper info'}
        if v and len(v) > 1 and v.lower() not in _BAD_TAPER:
            taper_name = v[:80]
        break

    # ── 2. Recording: label (skip inside parentheticals) → source_chain ──
    for m in re.finditer(
        r'\bRecording\s*:\s*(.+?)(?:,\s*Transfer|;\s*Transfer|[\n]|$)',
        d600, re.IGNORECASE,
    ):
        pre = d600[:m.start()]
        if pre.count('(') > pre.count(')'):
            continue
        v = m.group(1).strip().rstrip(',;.')
        if v and len(v) > 2:
            source_chain = v[:160]
        break

    # ── 3. Source: label (skip inside parentheticals) → source_chain ─────
    if not source_chain:
        for m in re.finditer(
            r'\bSource\s*:\s*(.+?)(?:,\s*(?:Lineage|Transfer|Taper)|;\s*|[\n]|$)',
            d600, re.IGNORECASE,
        ):
            pre = d600[:m.start()]
            if pre.count('(') <= pre.count(')'):
                v = m.group(1).strip().rstrip(',;.')
                if v and len(v) > 2:
                    source_chain = v[:160]
                    break

    # ── 4. Lineage: label (skip inside parentheticals) → source_chain ────
    if not source_chain:
        for m in re.finditer(r'\bLineage\s*:\s*(.+?)(?:[\n]|$)', d600, re.IGNORECASE):
            pre = d600[:m.start()]
            if pre.count('(') <= pre.count(')'):
                v = m.group(1).strip().rstrip(',;.')
                if v and len(v) > 2 and _looks_like_chain(v):
                    source_chain = v[:160]
                    break

    # ── 5. Technical Info: label → source_chain ──────────────────────────
    if not source_chain:
        m = re.search(r'\bTechnical\s*Info\s*:\s*(.+?)(?:[;\n]|$)', d600, re.IGNORECASE)
        if m:
            v = m.group(1).strip().rstrip(',;.')
            if v and len(v) > 4 and _looks_like_chain(v):
                source_chain = v[:160]

    # ── 6. BOOTLEG: title → taper_name = 'bootleg'; rip chain → source_chain
    bm = re.match(r'BOOTLEG\s*:\s*(.+?)(?:;|,|\n|$)', fl, re.IGNORECASE)
    if bm:
        taper_name = 'bootleg'
        if not source_chain:
            # Look only in non-paren lines after the first line
            rest_lines = _strip_bt_parens('\n'.join(d.split('\n')[1:]))
            cm = re.search(r'(?:cd|dvd)\s*(?:>|->)\s*(?:EAC|rip|wav|flac)', rest_lines, re.IGNORECASE)
            if cm:
                candidate = rest_lines[cm.start():cm.start() + 120].split('\n')[0].strip()
                if _looks_like_chain(candidate):
                    source_chain = candidate[:160]

    # ── 7. AUD DAT / DAUD → source_chain ─────────────────────────────────
    if not source_chain:
        am = re.match(
            r'\(?((?:AUD\s*DAT[- ]?\d*|DAUD)[- ]?\d*)\)?\s*,?\s*(?:\[.{1,30}\])?\s*,?\s*(.{0,80}?)(?:[,;]|$)',
            fl, re.IGNORECASE,
        )
        if am:
            prefix = am.group(1).strip()
            rest_part = (am.group(2) or '').strip().rstrip(',;.')
            # Only append rest_part if it looks like equipment info, not a rating/quality note
            if rest_part and _looks_like_chain(rest_part):
                source_chain = (prefix + ', ' + rest_part)[:160]
            else:
                source_chain = prefix

    # ── 8. Raw > chain at first line → source_chain ───────────────────────
    if not source_chain:
        m = re.match(r'^(.{4,160}?>+.{4,120}?)(?:[,;]\s*(?!$)|\n|$)', fl)
        if m:
            v = m.group(1).strip().split('(')[0].strip().rstrip(',;.')
            if _looks_like_chain(v):
                source_chain = v[:160]

    # ── 9. legendary / net taper patterns ────────────────────────────────
    if not taper_name:
        m = re.search(
            r'\b(legendary\s+taper\s+[A-Z]|net\s*taper\s*[A-Z#]?\d*)',
            d[:200], re.IGNORECASE,
        )
        if m:
            taper_name = m.group(1).strip()[:60]

    # ── 10. Seeded … by <name> ────────────────────────────────────────────
    if not taper_name:
        m = re.search(r'\bSeeded\s+\S+\s+\S+\s+by\s+([A-Za-z]\w{1,30})', fl, re.IGNORECASE)
        if m:
            taper_name = m.group(1).strip()[:60]

    # ── 11. version "x" → strip prefix, recurse on rest ──────────────────
    if not taper_name and not source_chain:
        vm = re.match(r'^version\s*["\'][^"\']*["\'][,;]?\s*', fl, re.IGNORECASE)
        if vm:
            rest_line = fl[vm.end():].strip()
            rest_full = rest_line + ('\n' + '\n'.join(d.split('\n')[1:6]) if '\n' in d else '')
            t2, s2 = extract_taper_and_source(rest_full)
            taper_name   = taper_name   or t2
            source_chain = source_chain or s2

    # ── 12. taped by <name> ────────────────────────────────────────────────
    # Checked before the leading-token heuristic (below) on purpose: an
    # explicit "Taped ... by <Name>" credit is unambiguous evidence, while the
    # leading token on the line is often equipment (e.g. "akg568ebs, ...") or
    # a second person's handle mentioned in the same breath (e.g. "merman
    # dolphinsmile 48k, Taped by Merman, ... Produced by Dolphinsmile") — if
    # the weak heuristic runs first it claims taper_name and this strong
    # signal never gets checked. The `[\w\s,]{0,40}?` gap allows compound
    # phrasing like "Taped, Transfered and uploaded by Tony Suraci" while
    # still requiring "taped" itself, so a bare "uploaded by <uploader>" (not
    # a taper credit) doesn't match.
    if not taper_name:
        # The capture stops at the first clause boundary — comma/period/
        # newline, or a connector word ("with", "on", "using", "and", "who")
        # — so an equipment/description clause tacked on right after the name
        # ("Taped by BP with Denon portable...") doesn't get swept into the
        # match. "dolphinsmile" is also a stop word: several descriptions
        # literally start "taped by <handle> dolphinsmile, taped by <handle>
        # with ..." (dolphinsmile is the uploader, credited in the same
        # breath), and without the stop the uploader's name gets appended to
        # the taper's.
        m = re.search(
            r"\b(?i:taped)\b[\w\s,]{0,40}?\b(?i:by)\s+(.+?)"
            r"(?:[,.\n>]|\b(?:with|on|using|and|who|dolphinsmile|live|wit)\b|$)",
            fl,
        )
        if m:
            cand = m.group(1).strip()
            # Drop a stray unmatched paren left by the boundary cut (e.g.
            # "...taped by MT)." captures "MT)" since ')' isn't a boundary
            # char — only "(name)" pairs are meant to survive intact).
            if cand.count('(') < cand.count(')'):
                cand = cand.rstrip(')').rstrip()
            elif cand.count(')') < cand.count('('):
                cand = cand.rstrip('(').rstrip()
            words = cand.split()
            # Reject descriptive filler ("a friend of mine", "that team of 3
            # germans", "a friend who lived in Portland") rather than treat
            # it as a name — these are common in this corpus for anonymised
            # tapers and are strictly worse than falling through to the
            # short-handle heuristic below.
            _TAPED_BY_STOPWORDS = {
                'a', 'an', 'the', 'some', 'someone', 'something', 'who', 'that',
                'which', 'with', 'from', 'friend', 'friends', 'buddy', 'dude',
                'guy', 'local', 'team', 'member', 'members', 'teams', 'non',
                'taper', 'tapers', 'dylanist', 'dylanologist', 'crew',
                'recordist', 'mine', 'of', 'on', 'using', 'him', 'her', 'his',
                'my', 'me', 'i', 'think', 'now', 'is', 'was',
            }
            if (cand and cand[0].isalpha() and 0 < len(words) <= 4
                    and not any(w.lower().strip("'.,") in _TAPED_BY_STOPWORDS for w in words)):
                taper_name = cand[:60]

    # ── 13. Short handle / taper code at start ────────────────────────────
    if not taper_name:
        # Allow 1-char second token (e.g. "sbd f", "lta"), semicolon separators
        handle_re = re.compile(
            r'^([A-Za-z][A-Za-z0-9_\-]{0,20}(?:\s+[A-Za-z0-9_\-]{1,15}){0,3})\s*[,;\n]',
        )
        _STOPWORDS = re.compile(
            r'\b(the|and|or|of|in|a|an|is|was|has|have|from|this|that|by|also|'
            r'bittorrent|version|alternate|audience|recorded|received|transfer|upgrade|'
            r'floor|center|centre|section|row|seat|stage|balcony|orchestra|main|front|back|side|'
            r'mono|stereo|sound|poor|good|excellent|fair|hum|hiss|noise|clipping|'
            r'radio|broadcast|special|dylan|bob)\b',
            re.IGNORECASE,
        )
        m = handle_re.match(fl) or handle_re.match(d)
        if m:
            handle = m.group(1).strip()
            if not _STOPWORDS.search(handle) and len(handle) >= 2:
                # Strip trailing sample-rate token (e.g. "24", "48", "48k", "24bit")
                _tok = handle.split()
                if len(_tok) > 1 and re.match(r'^\d+(?:k(?:hz)?|bit)?$', _tok[-1], re.IGNORECASE):
                    _tok = _tok[:-1]
                # If any non-last token contains a digit (equipment model code like skm140,
                # mk4v, at853), the last token is the taper handle
                if len(_tok) > 1 and any(re.search(r'\d', t) for t in _tok[:-1]):
                    _tok = [_tok[-1]]
                taper_name = ' '.join(_tok)[:60]

    # ── 14. from <X> master/vine/collection ──────────────────────────────
    if not taper_name:
        m = re.search(
            r'\bfrom\s+(?:the\s+)?([A-Za-z][A-Za-z0-9\s_\-]{1,25}?(?:\s+(?:master|vine|collection|recording)))',
            fl, re.IGNORECASE,
        )
        if m:
            v = m.group(1).strip()
            # Strip leading articles
            v = re.sub(r'^(?:the|a|an)\s+', '', v, flags=re.IGNORECASE).strip()
            if v and len(v) > 2:
                taper_name = v[:60]

    # ── Post-process ───────────────────────────────────────────────────────

    def _clean(v: str | None) -> str | None:
        if not v:
            return None
        # Strip incomplete opening parenthetical at end (e.g. "George Wang (email...")
        v = re.sub(r'\s*\([^)]*$', '', v).strip()
        # Strip leading or inline stray closing paren before a chain arrow
        v = re.sub(r'^\)+\s*', '', v).strip()
        v = re.sub(r'\)\s*>', '>', v)
        # Strip surrounding quote characters (e.g. "Bach" → Bach)
        v = re.sub(r'^["\'](.+)["\']$', r'\1', v).strip()
        # Discard if contains unmatched quote characters (leaked from quoted strings)
        if v.count('"') % 2 != 0:
            v = re.sub(r'\s*"[^"]*$', '', v).strip()
        return v.rstrip(',;. ') or None

    taper_name   = _clean(taper_name)
    source_chain = _clean(source_chain)

    # Canonicalize, lowercase, and suppress non-taper labels
    if taper_name:
        _norm = _normalise_alias_key(taper_name)
        if _norm in _NOT_TAPER:
            taper_name = None
        else:
            canonical = _KNOWN_TAPER_ALIASES.get(_norm)
            if canonical is None:
                # Prefix match: trim equipment/chain bleed (e.g. "net taper e schoeps …")
                for _key in _KNOWN_TAPER_KEYS_SORTED:
                    if _norm.startswith(_key + ' '):
                        canonical = _KNOWN_TAPER_ALIASES[_key]
                        break
            taper_name = (canonical or taper_name).lower()

    # Strip taper handle prefix from source_chain if chain starts with same text
    if taper_name and source_chain:
        prefix_pat = re.escape(taper_name.split(',')[0].strip())
        source_chain = re.sub(
            r'^' + prefix_pat + r'\s*[,;]\s*', '', source_chain, flags=re.IGNORECASE,
        ).strip().lstrip(',;').strip() or None

    return taper_name or None, source_chain or None


# Conservative keyword classifier, display-only fallback for the GUI source
# badge when the curator-edited entries.source_type is NULL (true for the
# whole catalog as of 2026-06 — see TODO-153). Never written back to the DB;
# recomputed per API response. Deliberately narrow: "Master" is excluded
# because in trader lineage text it almost always means "first-gen copy off
# a master tape" (a generation, not a source type), not an actual studio/
# soundboard master — guessing wrong there would mislabel audience tapes.
# ALD = Assisted Listening Device — a venue's wireless feed for hard-of-hearing
# patrons, tapped with a receiver. Checked first: when a description calls a
# tape both "soundboard" and "ALD" (e.g. "Digitally Remastered Soundboard,
# (assisted listening device (ALD) is the source)"), the ALD note is a
# clarification of the true source, not a second, lower-confidence guess.
_SRC_ALD_RE = re.compile(r'\bald\b', re.IGNORECASE)
_SRC_SBD_RE = re.compile(r'\b(soundboard|sbd)\b', re.IGNORECASE)
_SRC_FM_RE = re.compile(r'\b(pre-?fm|fm\s*(?:broadcast|stereo|simulcast)|radio\s*broadcast)\b', re.IGNORECASE)
# Excludes "Matrix: BDGD" etc — vinyl runout/matrix-number listings, unrelated
# to a SBD+AUD matrix mixdown (caught a real false positive in LB entries
# with "Source: Audience, ... Matrix: BDGD (1-10)" being misread as Mixed).
_SRC_MIXED_RE = re.compile(r'\bmatrix\b(?!\s*[:#]|\s+\d)', re.IGNORECASE)
_SRC_AUD_RE = re.compile(r'\b(audience|aud)\b', re.IGNORECASE)


def _classify_source_text(text: str) -> str | None:
    if _SRC_ALD_RE.search(text):
        return 'ALD'
    if _SRC_SBD_RE.search(text):
        return 'Soundboard'
    if _SRC_FM_RE.search(text):
        return 'FM/Pre-FM'
    if _SRC_MIXED_RE.search(text):
        return 'Mixed'
    if _SRC_AUD_RE.search(text):
        return 'Audience'
    return None


def classify_source_type(description: str | None, source_chain: str | None) -> str | None:
    """Best-effort source-type guess from free-text lineage, for display only.

    Returns one of 'ALD', 'Soundboard', 'FM/Pre-FM', 'Mixed', 'Audience', or
    None when no confident signal is found. Checks `source_chain` first — it's
    already isolated by the Source:/Recording:/Lineage: label extraction in
    :func:`extract_taper_and_source`, so it's far less noisy than the raw
    description (which may mention an unrelated term, e.g. a vinyl release's
    "Matrix: BDGD" runout code, elsewhere in the same entry). Only falls back
    to scanning the full description when source_chain gives no signal.
    """
    if source_chain:
        hit = _classify_source_text(source_chain)
        if hit:
            return hit
    if description:
        return _classify_source_text(description)
    return None


# ── Lineage cross-reference regexes ───────────────────────────────────────────
# Canonical definitions — also imported by tools/tapematch/tapematch_session.py.

_SAME_RE = re.compile(
    r'same\s+(?:recording|source|tape|transfer|as)|'
    r'fingerprints?.{0,40}match|eac\s+match|close\s+eac|'
    r'\bidentical\b|duplicate\s+of',
    re.IGNORECASE,
)
_DERIVED_RE = re.compile(
    r'\bfrom\b.{0,30}\bmaster\b|\bgen\s+of\b|\bcopy\s+of\b|'
    r'\bderived\s+from\b|\bdubbed\s+from\b|\btransferred\s+from\b',
    re.IGNORECASE,
)
_BETTER_RE = re.compile(
    r'\bbetter\s+than\b|\bsupersedes?\b|\bupgrade\s+of\b|\breplaces?\b',
    re.IGNORECASE,
)
_DIFF_RE = re.compile(
    r'different\s+(?:recording|source|tape|from)|'
    r'not\s+the\s+same|'
    # Golden review 3 (LB-14054): "Alternate to LB-2470/..." names a different
    # recording, even when it goes on to say the others share one source.
    r'\balternat(?:e|ive)\s+(?:recording\s+|source\s+|version\s+)?to\b',
    re.IGNORECASE,
)
_LB_REF_RE = re.compile(r'\bLB-0*(\d+)\b', re.IGNORECASE)
# Sentence boundary for binding a same/different phrase to the LB refs it talks
# about. LB descriptions join fields with ", ", so commas are NOT boundaries.
_REF_SENTENCE_SPLIT_RE = re.compile(r';|\.\s|\n\s*\n')
# A ref introduced as this set's own LB entry, an earlier version or the entry it
# fixes names the same recording ("LosslessBob entry: LB-2710", "Fix of LB-7948",
# "Previous version = LosslessBob LB-201"). Checked on the text right before the ref.
_SAME_REF_LEAD_RE = re.compile(
    r'(?:LosslessBob\s+entry(?:\s+for\s+lineage\s+above)?\s*[:=]?|'
    r'\bfix(?:ed)?(?:\s+of)?|previous\s+version\s*=|previos\s+version\s*=|'
    r'corrected\s+version\s+of)\s*(?:LosslessBob\s*-?\s*)?$',
    re.IGNORECASE,
)
# "recorded by" / "recording by" are explicit credits too (plan E5), but only
# when bound to the parsed handle -- taper_attribution._layer0_seed checks that
# binding for these two forms (and for "a <handle> recording", which no static
# regex can express) rather than trusting a match anywhere in the text.
_EXPLICIT_TAPER_LABEL_RE = re.compile(
    r'\bTaper\s*:|\btaped\b[\w\s,]{0,40}?\bby\b|\brecord(?:ed|ing)\s+by\b', re.IGNORECASE,
)
_SEMI_EXPLICIT_TAPER_RE = re.compile(
    r'\btaped\s+by\b|\bSeeded\b|\bBOOTLEG\s*:|'
    r'\blegendary\s+taper\b|\bnet\s*taper\b',
    re.IGNORECASE,
)

# Curated known tapers: maps every normalised variant → canonical display name.
# All canonical values are lowercase; taper_name is always stored lowercase.
# Add new tapers here. This is the code-only builtin table; TODO-241 adds a
# `user_taper_aliases` table for install-local additions/suppressions on top
# of it without a code edit — see _KNOWN_TAPER_ALIASES and reload_taper_aliases
# below.
_BUILTIN_TAPER_ALIASES: dict[str, str] = {
    "soomlos": "soomlos",
    "spot": "spot",
    "hide": "hide",
    "lta": "lta",
    "mk": "mk",
    "southside butcher": "southside butcher",
    "southsidebutcher": "southside butcher",
    "ssb": "southside butcher",
    "iar": "iar",
    "improved air remaster": "iar",
    "mjs": "mjs",
    "bw": "bw",
    "jtt": "jtt",
    "pl": "pl",
    "cedar": "cedar",
    "holy grail": "holy grail",
    "holygrail": "holy grail",
    "vw": "vw",
    "cck": "cck",
    "jt": "jt",
    "cta": "cta",
    "tyrus": "tyrus",
    "zimmy21": "zimmy21",
    # Self-stated "Taper: 3dogs" on 21 entries, one rig throughout (tj, 2026-10-01).
    "3dogs": "3dogs",
    "fine wine": "fine wine",
    "finewine": "fine wine",
    "hv": "hv",
    "condor": "condor",
    "lowgen": "lowgen",
    "schubert": "schubert",
    "mb": "mb",
    "jersey john": "jersey john",
    "jerseyjohn": "jersey john",
    "theodore": "theodore",
    "mike savage": "mike savage",
    "mikesavage": "mike savage",
    "m&a": "m&a",   # raw form — matched by regex against description text
    "m a": "m&a",   # normalised form (& strips to space)
    "wario": "wario",
    "mani": "mani",
    "manie": "mani",
    "bach": "bach",
    "romeo": "romeo",
    # cb is the taper; "cb master" just means a master tape *from* cb — the
    # "master" is a source descriptor, not part of the handle (TODO-213, 2026-07-13).
    "cb master": "cb",
    "cb": "cb",
    "lk": "lk",
    "hhtfp": "hhtfp",
    "jf": "jf",
    "sullylove": "sullylove",
    "ebr": "ebr",
    "tom moore": "tom moore",
    "dk-wi": "dk-wi",
    "dk wi": "dk-wi",
    "tk": "tk",
    "bt": "bt",
    "vito": "vito",
    "glen dundas": "glen dundas",
    "glendundas": "glen dundas",
    "nightly moth": "nightly moth",
    "nightlymoth": "nightly moth",
    "csheb": "csheb",
    "streetcar visions": "streetcar visions",
    "streetcarvisions": "streetcar visions",
    "sk": "sk",
    "jerseyboy": "jerseyboy",
    "jersey boy": "jerseyboy",
    "spyder9": "spyder9",
    "bob meyer": "bob meyer",
    "bobmeyer": "bob meyer",
    "markp": "markp",
    "mark p": "markp",
    "downfromtheglen": "downfromtheglen",
    "down from the glen": "downfromtheglen",
    "mrsoul": "mrsoul",
    "mr soul": "mrsoul",
    "sh": "sh",
    "sm": "sm",
    "gs": "gs",
    "rcm": "rcm",
    "mike millard": "mike millard",
    "mikemillard": "mike millard",
    "mm": "mike millard",
    "billie": "billie",
    "jgb": "jgb",
    "tompaine56": "tom paine",
    "tom paine 56": "tom paine",
    "tom paine": "tom paine",
    "tp": "tom paine",
    "mango farmer": "mango farmer",
    "mangofamer": "mango farmer",
    "ironchef": "ironchef",
    "iron chef": "ironchef",
    "soledriver": "soledriver",
    "sole driver": "soledriver",
    "goodnitesteve": "goodnitesteve",
    "goodnite steve": "goodnitesteve",
    "clapberry": "clapberry",
    "bigjim": "bigjim",
    "big jim": "bigjim",
    "teddy ballgame": "teddy ballgame",
    "teddyballgame": "teddy ballgame",
    "theshadow": "theshadow",
    "the shadow": "theshadow",
    # "robert" removed 2026-07-13 (TODO-213): too generic a bare token — it
    # matched songwriter/personnel credits ("Robert Hunter", "Robert Friemark")
    # in setlists, not tapers. 179 of its 198 attributions were false mentions.
    "sfy": "sfy",
    "caretaker": "caretaker",
    "beer": "beer",
    "beerly": "beer",
    "mikebeerly": "beer",
    "mike beerly": "beer",
    "caspar": "caspar",
    "jon caspar": "caspar",
    "joncaspar": "caspar",
    "kuddukan": "kuddukan",
    "pdub": "pdub",
    "audiowhore": "audiowhore",
    "arashi": "arashi",
    "dopersan": "dopersan",
    "markitospb": "markitospb",
    "krw_co": "krw co",   # raw form (underscore) for regex match
    "krw co": "krw co",   # normalised form (underscore → space)
    "maloney": "maloney",
    "radioshack": "radioshack",
    "radio shack": "radioshack",
    "kingrue": "kingrue",
    "king rue": "kingrue",
    "warburton": "warburton",
    "jimmy warburton": "warburton",
    "jimmywarburton": "warburton",
    "captain acid": "captain acid",
    "captainacid": "captain acid",
    "acidproject": "captain acid",
    "acid project": "captain acid",
    "andrea82": "andrea82",
    "pike1957": "pike1957",
    "sway": "sway",
    "whofan70": "whofan70",
    "two of us": "two of us",
    "twofus": "two of us",
    "mcforce": "mcforce",
    "thelonius": "thelonius",
    "thelonious": "thelonius",
    "jems": "jems",
    "tarantula": "tarantula",
    "lbp51": "lbp51",
    "unwanted man music": "unwanted man music",
    "unwanted man": "unwanted man music",
    "uww": "unwanted man music",
    # Travelin' Man Records is Legendary Taper F's own handle: entries read "Taper F
    # (Travelin' Man Records)", and crediting it separately made every LTF family that
    # also holds a TMR-credited copy a false R-T6 taper conflict (TODO-357).
    "travelin man records": "ltf",
    "travelin man": "ltf",
    "tmr": "ltf",
    "stevemtl": "stevemtl",
    "bourbon": "bobby bourbon",
    "bobby bourbon": "bobby bourbon",
    "bobbybourboon": "bobby bourbon",
    "elliot": "elliot",
    "jvs": "jvs",
    "v4tx": "v4tx",
    # ── Legendary Taper series (LTA, LTB, … distinct from Net Taper series) ──
    # "legendary taper X", "taper X", "lt X", "ltX" all → "lt[a-z]"
    **{f"legendary taper {c}": f"lt{c}" for c in "abcdefghijklmnopqrstuvwxyz"},
    **{f"taper {c}": f"lt{c}" for c in "abcdefghijklmnopqrstuvwxyz"},
    **{f"lt {c}": f"lt{c}" for c in "abcdefghijklmnopqrstuvwxyz"},
    # ── Net Taper series (NTA, NTB, … distinct from Legendary Taper series) ──
    # "net taper X", "ntX" all → "net taper [a-z]"
    **{f"net taper {c}": f"net taper {c}" for c in "abcdefghijklmnopqrstuvwxyz"},
    **{f"nt{c}": f"net taper {c}" for c in "abcdefghijklmnopqrstuvwxyz"},
}

# Live, merged alias table: builtin plus approved `user_taper_aliases` rows
# (TODO-241). Starts as a copy of the builtin table; reload_taper_aliases()
# rebuilds it IN PLACE (.clear() + .update()) rather than reassigning, so every
# module that imported this name directly (backend.taper_attribution,
# backend.taper_fingerprints) sees the update through the same dict object —
# no re-import or process restart needed.
_KNOWN_TAPER_ALIASES: dict[str, str] = dict(_BUILTIN_TAPER_ALIASES)

# Labels that must never be stored as taper_name (mis-parses / source-type labels).
_NOT_TAPER: frozenset[str] = frozenset({
    # dolphinsmile curates/transfers others' tapes — not a taper (curator, 2026-07-04);
    # common misspellings in entry text included
    'dolphinsmile', 'dolphinmile', 'dolphindmile', 'dolphinsme', 'dolphin',
    # Not tapers: lk curates, captain acid remasters existing recordings, and
    # jtt transfers/masters others' tapes ("Mastered to Digital by JTT",
    # "Transfer from Low Generation Cassette JTT" — not generally a taper).
    # TODO-213 curation pass, 2026-07-13. Kept as _KNOWN_TAPER_ALIASES keys so
    # the parser still collapses their spellings to one canonical token, but
    # excluded here so the attribution engine never seeds them as candidates:
    # when such a mention collides with a real taper in a family (e.g. LB-1945 =
    # ltd via LB-4396 vs captain acid via LB-4401), the real taper propagates
    # cleanly with no conflict — no curation required.
    'lk', 'captain acid', 'jtt',
    'sbd', 'aud', 'master', 'series', 'incomplete',
    'aud master', 'master aud', 'excellent sound', 'net tapers',
    'km140s', 'km140',
    'unidentified taper', 'dat master', 'same master',
    'soundcheck', 'low gen reel', 'sp cmc',
    'very good sound', 'same recording', 'not certain',
    'cos11pt', 'zoom h2',
    'late show', 'early show', 'unknown source',
    'poor sound', 'mono',
})

# Whitelist of validated taper names (locked decision, mirrors
# taper_attribution._TAPER_UNIVERSE): canonical values of _KNOWN_TAPER_ALIASES,
# excluding anything in _NOT_TAPER. Free-text parsing (extract_taper_and_source)
# can still store an unrecognised guess in taper_name for curator review (see
# ScreenSearch's scrape-preview use), but any *display* surface aimed at end
# users (e.g. the Library grid's taper pill) must check is_known_taper() first
# so it never shows a guess the attribution engine itself would reject.
_TAPER_UNIVERSE: frozenset[str] = frozenset(_KNOWN_TAPER_ALIASES.values()) - _NOT_TAPER


def is_known_taper(name: str | None) -> bool:
    """Return True if ``name`` normalises to a curated, validated taper.

    Args:
        name: Raw or already-normalised taper name (may be None).

    Returns:
        True if the normalised form is a member of ``_TAPER_UNIVERSE``.
    """
    norm = _normalise_taper(name)
    return norm is not None and norm in _TAPER_UNIVERSE

# Sorted known-taper keys longest-first for prefix-match canonicalization.
_KNOWN_TAPER_KEYS_SORTED: list[str] = sorted(_KNOWN_TAPER_ALIASES, key=len, reverse=True)

# Compiled regex for step-0 known-handle scan in extract_taper_and_source.
# Sorted longest-first so multi-word phrases match before shorter subsets.
_KNOWN_TAPER_RE = re.compile(
    r'\b(' + '|'.join(
        re.escape(k) for k in sorted(_KNOWN_TAPER_ALIASES, key=len, reverse=True)
    ) + r')\b',
    re.IGNORECASE,
)

# Legendary taper series: LTA, LTB, LTC … matched as a pattern rather than
# enumerating all letters.  Canonical form is lowercase (e.g. "ltb").
_LT_TAPER_RE = re.compile(r'\b(lt[a-z])\b', re.IGNORECASE)


def _normalise_taper(name: str | None) -> str | None:
    """Lowercase, strip punctuation, and resolve known-taper aliases.

    Args:
        name: Raw taper name, e.g. "J. Smith" or "john_smith-taper".

    Returns:
        Canonical normalised string (e.g. "southside butcher"), or None.
    """
    s = _normalise_alias_key(name)
    if not s:
        return None
    return _KNOWN_TAPER_ALIASES.get(s, s)


# ── User taper aliases (TODO-241): add/remove known-taper handles without a
# code edit. `user_taper_aliases` is USER-tier (audit/provenance only, never
# exported — see USER_TABLES); 'add' rows create or override an alias key,
# 'remove' rows suppress a _BUILTIN_TAPER_ALIASES key. reload_taper_aliases()
# is the single place that turns those rows into the live _KNOWN_TAPER_ALIASES
# / _TAPER_UNIVERSE / _KNOWN_TAPER_KEYS_SORTED / _KNOWN_TAPER_RE globals used
# by parsing and attribution.

def _run_queued_write(fn, db_path: str | None, label: str = "write"):
    """Route a write through the write queue, matching the BUG-246 guard used
    elsewhere (taper_attribution.py, song_index.py, xref_ingest.py): the write
    queue singleton is first-caller-wins, so under pytest (each test module's
    own temp DB) it may be bound to a different DB than *db_path*.

    Args:
        fn: Callable taking a ``sqlite3.Connection`` and performing the write.
        db_path: Optional database path the caller intended to target.
        label: Short description used only in the mismatch warning log.
    """
    queue = get_write_queue()
    if db_path is not None and str(Path(db_path).resolve()) != str(Path(queue.db_path).resolve()):
        logger.warning(
            "%s: write queue bound to %s but this write targets %s"
            " — writing directly", label, queue.db_path, db_path,
        )
        conn = get_connection(db_path)
        with conn:
            return fn(conn)
    return queue.execute(fn)


def _run_alias_write(fn, db_path: str | None):
    """Route a user_taper_aliases write through the write queue (see
    :func:`_run_queued_write`)."""
    return _run_queued_write(fn, db_path, label="user_taper_aliases")


def record_step_run(
    step_id: str, *, status: str = "ok",
    started_at: str | None = None, finished_at: str | None = None,
    counters: dict | None = None, notes: str | None = None,
    trigger_source: str = "route", db_path: str | None = None,
) -> int:
    """Insert one completed ``refresh_step_runs`` row (TODO-306).

    One insert at completion, not a start/finish pair: "currently running" is
    already fully covered by ``activity.snapshot()``, and a single insert
    avoids carrying a rowid across a thread boundary and avoids orphan
    ``running`` rows after a crash.

    Args:
        step_id: ``refresh.STEPS`` step id this run corresponds to.
        status: One of ``ok | noop | stopped | error``.
        started_at: 'YYYY-MM-DD HH:MM:SS' naive-local timestamp; defaults to
            ``finished_at`` (or now) when omitted.
        finished_at: 'YYYY-MM-DD HH:MM:SS' naive-local timestamp; defaults to now.
        counters: Worker summary dict, stored verbatim as JSON.
        notes: Optional free-text note (e.g. a version-change reason).
        trigger_source: ``route | cli | cron``.
        db_path: Optional database path override.

    Returns:
        The new row's id.
    """
    finished = finished_at or time.strftime("%Y-%m-%d %H:%M:%S")
    started = started_at or finished
    counters_json = json.dumps(counters) if counters is not None else None

    def _do(c: sqlite3.Connection) -> int:
        cur = c.execute(
            """INSERT INTO refresh_step_runs
                   (step_id, started_at, finished_at, status, trigger_source,
                    counters_json, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (step_id, started, finished, status, trigger_source, counters_json, notes),
        )
        return cur.lastrowid

    return _run_queued_write(_do, db_path, label="refresh_step_runs")


def record_chain_run(
    scope_kind: str, scope_value: str, *, status: str,
    started_at: str | None = None, finished_at: str | None = None,
    steps: list | dict | None = None, notes: str | None = None,
    db_path: str | None = None,
) -> int:
    """Insert one completed ``refresh_chain_runs`` row (Phase 3).

    One insert at completion, mirroring :func:`record_step_run`: the frozen
    plan plus per-step outcomes are the history record, while
    ``refresh_step_runs`` remains the authoritative freshness signal.

    Args:
        scope_kind: ``'step'`` or ``'trigger'``.
        scope_value: The step id or trigger id (e.g. ``'T1'``) the chain
            was planned against.
        status: One of ``ok | partial | stopped | error``.
        started_at: 'YYYY-MM-DD HH:MM:SS' naive-local timestamp; defaults to
            ``finished_at`` (or now) when omitted.
        finished_at: 'YYYY-MM-DD HH:MM:SS' naive-local timestamp; defaults to now.
        steps: The frozen plan plus per-step outcome, stored verbatim as JSON.
        notes: Optional free-text note.
        db_path: Optional database path override.

    Returns:
        The new row's id.
    """
    finished = finished_at or time.strftime("%Y-%m-%d %H:%M:%S")
    started = started_at or finished
    steps_json = json.dumps(steps) if steps is not None else None

    def _do(c: sqlite3.Connection) -> int:
        cur = c.execute(
            """INSERT INTO refresh_chain_runs
                   (scope_kind, scope_value, started_at, finished_at, status,
                    steps_json, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (scope_kind, scope_value, started, finished, status, steps_json, notes),
        )
        return cur.lastrowid

    return _run_queued_write(_do, db_path, label="refresh_chain_runs")


def reload_taper_aliases(db_path: str | None = None) -> dict:
    """Rebuild the merged known-taper alias tables from user overrides.

    Reads approved rows from ``user_taper_aliases`` and rebuilds
    :data:`_KNOWN_TAPER_ALIASES` **in place** (``.clear()`` + ``.update()``) so
    every module holding a reference to that same dict object (e.g.
    ``backend.taper_attribution``, ``backend.taper_fingerprints``, both of
    which import it by name) sees the update without being reloaded.
    :data:`_TAPER_UNIVERSE`, :data:`_KNOWN_TAPER_KEYS_SORTED`, and
    :data:`_KNOWN_TAPER_RE` are all derived, and a frozenset/list/compiled
    regex can't be mutated in place, so they are reassigned here instead — any
    consumer that needs a reload to propagate must access them as module
    attributes (``db._TAPER_UNIVERSE``) rather than importing the name
    directly at its own top level (see ``taper_attribution``'s module-level
    ``__getattr__`` for the one existing direct-import consumer).

    Apply order per alias key: start from the builtin table, apply every
    approved 'remove' row (deletes that key if present), then apply every
    approved 'add' row (sets/overrides that key) — so 'add' always wins for a
    given ``alias_norm`` (moot in practice: the table's PRIMARY KEY means one
    ``alias_norm`` can only ever hold one row/action at a time).

    Args:
        db_path: Optional database path override.

    Returns:
        Counts dict: ``{"builtin", "user_add", "user_remove", "merged"}``.
    """
    _ensure_init_db(db_path)
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT alias_norm, canonical, action FROM user_taper_aliases WHERE approved = 1"
    ).fetchall()
    removes = [r for r in rows if r["action"] == "remove"]
    adds = [r for r in rows if r["action"] == "add"]

    _KNOWN_TAPER_ALIASES.clear()
    _KNOWN_TAPER_ALIASES.update(_BUILTIN_TAPER_ALIASES)
    for r in removes:
        _KNOWN_TAPER_ALIASES.pop(r["alias_norm"], None)
    for r in adds:
        _KNOWN_TAPER_ALIASES[r["alias_norm"]] = r["canonical"]

    # Curator overrides on the code-level _NOT_TAPER set (TODO-313). 'not_taper'
    # rows exclude extra canonicals; 'is_taper' rows re-admit builtin-excluded
    # ones. Applied after the subtraction so an 'is_taper' row always wins over
    # the shipped judgement — a local curator's explicit call beats a default.
    flag_rows = conn.execute(
        "SELECT canonical, action FROM user_taper_flags"
    ).fetchall()
    user_not = {r["canonical"] for r in flag_rows if r["action"] == "not_taper"}
    user_is = {r["canonical"] for r in flag_rows if r["action"] == "is_taper"}

    global _TAPER_UNIVERSE, _KNOWN_TAPER_KEYS_SORTED, _KNOWN_TAPER_RE
    _TAPER_UNIVERSE = (
        (frozenset(_KNOWN_TAPER_ALIASES.values()) - _NOT_TAPER - user_not) | user_is
    )
    _KNOWN_TAPER_KEYS_SORTED = sorted(_KNOWN_TAPER_ALIASES, key=len, reverse=True)
    _KNOWN_TAPER_RE = re.compile(
        r'\b(' + '|'.join(
            re.escape(k) for k in sorted(_KNOWN_TAPER_ALIASES, key=len, reverse=True)
        ) + r')\b',
        re.IGNORECASE,
    )

    counts = {
        "builtin": len(_BUILTIN_TAPER_ALIASES),
        "user_add": len(adds),
        "user_remove": len(removes),
        "merged": len(_KNOWN_TAPER_ALIASES),
        "universe": len(_TAPER_UNIVERSE),
        "user_not_taper": len(user_not),
        "user_is_taper": len(user_is),
    }
    logger.info(
        "reload_taper_aliases: builtin=%(builtin)d user_add=%(user_add)d "
        "user_remove=%(user_remove)d merged=%(merged)d universe=%(universe)d "
        "user_not_taper=%(user_not_taper)d user_is_taper=%(user_is_taper)d", counts,
    )
    return counts


def list_taper_aliases(db_path: str | None = None) -> dict:
    """Merged known-taper alias listing with builtin/user provenance.

    Args:
        db_path: Optional database path override.

    Returns:
        ``{"entries": [{"alias", "canonical", "origin": "builtin"|"user"}, ...]
        (alias-sorted), "suppressed": [alias_norm, ...] (builtin keys removed
        by an approved user 'remove' row), "counts": {...}}`` — see
        :func:`reload_taper_aliases` for the counts shape.

    Reloads the merged tables first so a listing (and the counts it reports)
    always reflects the DB — user_taper_aliases can be edited out-of-band by
    tools/taper_aliases.py while a backend process is running, and without the
    reload this process's in-memory merge would be stale.
    """
    reload_taper_aliases(db_path)
    conn = get_connection(db_path)
    user_rows = conn.execute(
        "SELECT alias_norm, canonical, action, approved FROM user_taper_aliases"
    ).fetchall()
    user_add = {r["alias_norm"]: r["canonical"] for r in user_rows
                if r["action"] == "add" and r["approved"]}
    user_remove = {r["alias_norm"] for r in user_rows
                   if r["action"] == "remove" and r["approved"]}

    entries = [
        {"alias": alias, "canonical": canonical, "origin": "builtin"}
        for alias, canonical in _BUILTIN_TAPER_ALIASES.items()
        if alias not in user_remove
    ]
    entries.extend(
        {"alias": alias, "canonical": canonical, "origin": "user"}
        for alias, canonical in user_add.items()
    )
    entries.sort(key=lambda e: e["alias"])

    return {
        "entries": entries,
        "suppressed": sorted(user_remove),
        "counts": {
            "builtin": len(_BUILTIN_TAPER_ALIASES),
            "user_add": len(user_add),
            "user_remove": len(user_remove),
            "merged": len(_KNOWN_TAPER_ALIASES),
        },
    }


def add_taper_alias(alias: str, canonical: str, note: str | None = None,
                     db_path: str | None = None) -> dict:
    """Upsert a user 'add' alias override, then reload the merged tables.

    Args:
        alias: Raw or already-normalised alias text. Normalised the same way
            :func:`_normalise_taper` keys are (lowercase, punctuation-stripped)
            — NOT resolved against the existing alias table, since that's
            exactly the mapping being created/overridden here.
        canonical: Canonical taper name to store (lowercased). Not validated
            against the existing universe — a curator may be introducing a
            brand-new taper the alias is the first handle for.
        note: Optional free-text provenance note.
        db_path: Optional database path override.

    Returns:
        The stored ``user_taper_aliases`` row as a dict.

    Raises:
        ValueError: alias or canonical is missing/blank, or alias normalises
            to the empty string.
    """
    alias_norm = _normalise_alias_key(alias)
    canonical_norm = (canonical or "").strip().lower()
    if not alias_norm or not canonical_norm:
        raise ValueError("alias and canonical must be non-empty")

    _ensure_init_db(db_path)

    def _do(conn: sqlite3.Connection) -> None:
        conn.execute(
            """INSERT INTO user_taper_aliases
                   (alias_norm, canonical, action, approved, note, created_at, updated_at)
               VALUES (?, ?, 'add', 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
               ON CONFLICT(alias_norm) DO UPDATE SET
                   canonical  = excluded.canonical,
                   action     = 'add',
                   approved   = 1,
                   note       = excluded.note,
                   updated_at = CURRENT_TIMESTAMP""",
            (alias_norm, canonical_norm, note),
        )

    _run_alias_write(_do, db_path)
    reload_taper_aliases(db_path)
    row = get_connection(db_path).execute(
        "SELECT * FROM user_taper_aliases WHERE alias_norm = ?", (alias_norm,)
    ).fetchone()
    return dict(row)


def remove_taper_alias(alias: str, db_path: str | None = None) -> str:
    """Remove or suppress a known-taper alias, then reload the merged tables.

    If *alias* is a live user 'add' row, the row is deleted outright (the
    builtin table is untouched, since the alias never existed there). If
    *alias* is a builtin key, an 'remove' row is upserted to suppress it
    locally (the builtin table itself is code, never edited).

    Args:
        alias: Raw or already-normalised alias text.
        db_path: Optional database path override.

    Returns:
        ``"deleted"`` if a user 'add' row was removed, ``"suppressed"`` if a
        builtin key was newly suppressed.

    Raises:
        KeyError: *alias* is neither a user 'add' row nor a builtin key.
    """
    alias_norm = _normalise_alias_key(alias)
    init_db(db_path)
    conn = get_connection(db_path)

    existing = conn.execute(
        "SELECT action FROM user_taper_aliases WHERE alias_norm = ?", (alias_norm,)
    ).fetchone()

    if existing is not None and existing["action"] == "add":
        def _do(c: sqlite3.Connection) -> None:
            c.execute("DELETE FROM user_taper_aliases WHERE alias_norm = ?", (alias_norm,))
        _run_alias_write(_do, db_path)
        reload_taper_aliases(db_path)
        return "deleted"

    if alias_norm in _BUILTIN_TAPER_ALIASES:
        canonical = _BUILTIN_TAPER_ALIASES[alias_norm]

        def _do(c: sqlite3.Connection) -> None:
            c.execute(
                """INSERT INTO user_taper_aliases
                       (alias_norm, canonical, action, approved, note, created_at, updated_at)
                   VALUES (?, ?, 'remove', 1, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                   ON CONFLICT(alias_norm) DO UPDATE SET
                       canonical  = excluded.canonical,
                       action     = 'remove',
                       approved   = 1,
                       updated_at = CURRENT_TIMESTAMP""",
                (alias_norm, canonical),
            )
        _run_alias_write(_do, db_path)
        reload_taper_aliases(db_path)
        return "suppressed"

    raise KeyError(alias_norm)


# ── Master taper vocabulary curation (TODO-313) ───────────────────────────────
# The alias helpers above are alias-keyed; everything below is *canonical*-keyed,
# which is the unit a curator actually reasons about ("is this person a taper?",
# "are these two names the same person?").

def list_taper_vocabulary(db_path: str | None = None) -> dict:
    """Return the canonical-centric master taper list.

    Groups the flat alias table by canonical name and joins in whether each
    canonical is in the live ``_TAPER_UNIVERSE``, why it is or isn't, and how
    much of the corpus currently depends on it. Reloads the merged tables first,
    so it always reflects the DB rather than a stale import-time snapshot.

    Args:
        db_path: Optional database path override.

    Returns:
        ``{"tapers": [...], "counts": {...}}``. Each taper dict has: canonical,
        aliases (list of ``{alias, origin}``), alias_count, origin
        (``builtin``/``user``/``mixed`` — where its aliases come from),
        in_universe, not_taper_origin (``builtin``/``user``/None — why it is
        excluded), flag (the ``user_taper_flags`` action, if any), note,
        attributions (rows in ``taper_attributions``) and confirmations (rows in
        ``taper_confirmations``).
    """
    reload_taper_aliases(db_path)
    conn = get_connection(db_path)

    grouped: dict[str, list[dict]] = {}
    for alias, canonical in _KNOWN_TAPER_ALIASES.items():
        grouped.setdefault(canonical, []).append({
            "alias": alias,
            "origin": "builtin" if alias in _BUILTIN_TAPER_ALIASES else "user",
        })

    flags = {
        r["canonical"]: dict(r)
        for r in conn.execute("SELECT canonical, action, note FROM user_taper_flags")
    }

    # Most _NOT_TAPER names are exclusion tokens only — they are never alias
    # *values*, so grouping the alias table alone would hide them and there
    # would be no way to reverse the call from the UI. dolphinsmile is the case
    # that matters (a real person judged a curator rather than a taper); the
    # rest are source-chain noise ('sbd', 'aud', 'poor sound'). They appear here
    # with no aliases, and the "Not a taper" filter is where a curator finds
    # them, so the default view stays the list of actual tapers.
    for name in _NOT_TAPER | set(flags):
        grouped.setdefault(name, [])
    attr_counts = {
        r["taper_normalised"]: r["n"] for r in conn.execute(
            "SELECT taper_normalised, COUNT(*) AS n FROM taper_attributions"
            " GROUP BY taper_normalised")
    }
    conf_counts = {
        r["taper_normalised"]: r["n"] for r in conn.execute(
            "SELECT taper_normalised, COUNT(*) AS n FROM taper_confirmations"
            " WHERE action = 'confirm' GROUP BY taper_normalised")
    }

    tapers = []
    for canonical, aliases in grouped.items():
        aliases.sort(key=lambda a: a["alias"])
        origins = {a["origin"] for a in aliases} or {"builtin"}
        flag = flags.get(canonical)
        in_universe = canonical in _TAPER_UNIVERSE
        # Distinguish "the shipped list says no" from "this install said no" —
        # only the latter is revertible from the UI without a code change.
        if in_universe:
            not_taper_origin = None
        elif flag and flag["action"] == "not_taper":
            not_taper_origin = "user"
        else:
            not_taper_origin = "builtin"
        tapers.append({
            "canonical": canonical,
            "aliases": aliases,
            "alias_count": len(aliases),
            "origin": origins.pop() if len(origins) == 1 else "mixed",
            "in_universe": in_universe,
            "not_taper_origin": not_taper_origin,
            "flag": flag["action"] if flag else None,
            "note": flag["note"] if flag else None,
            "attributions": attr_counts.get(canonical, 0),
            "confirmations": conf_counts.get(canonical, 0),
        })
    tapers.sort(key=lambda t: (-t["attributions"], t["canonical"]))

    return {
        "tapers": tapers,
        "counts": {
            "canonicals": len(tapers),
            "in_universe": sum(1 for t in tapers if t["in_universe"]),
            "not_taper": sum(1 for t in tapers if not t["in_universe"]),
            "aliases": len(_KNOWN_TAPER_ALIASES),
            "unused": sum(1 for t in tapers if t["in_universe"] and not t["attributions"]),
        },
    }


def set_taper_flag(canonical: str, is_taper: bool, note: str | None = None,
                   db_path: str | None = None) -> dict:
    """Mark a canonical as not-a-taper, or re-admit a builtin-excluded one.

    ``is_taper=False`` writes a 'not_taper' row, excluding the canonical from
    ``_TAPER_UNIVERSE``; the name stays a ``_KNOWN_TAPER_ALIASES`` value so the
    parser still collapses its spellings to one token, but the attribution
    engine will never seed it as a candidate. ``is_taper=True`` writes an
    'is_taper' row, which re-admits a canonical the code-level ``_NOT_TAPER``
    excludes. Existing ``taper_attributions`` rows are unaffected until the next
    recompute — the caller should say so.

    Args:
        canonical: Canonical taper name (lowercased here).
        is_taper: True to admit, False to exclude.
        note: Optional free-text provenance note.
        db_path: Optional database path override.

    Returns:
        ``{"canonical", "action", "in_universe"}`` after the reload.

    Raises:
        ValueError: *canonical* is missing or blank.
    """
    canonical_norm = (canonical or "").strip().lower()
    if not canonical_norm:
        raise ValueError("canonical must be non-empty")
    action = "is_taper" if is_taper else "not_taper"
    init_db(db_path)

    def _do(conn: sqlite3.Connection) -> None:
        conn.execute(
            """INSERT INTO user_taper_flags (canonical, action, note, created_at, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
               ON CONFLICT(canonical) DO UPDATE SET
                   action     = excluded.action,
                   note       = excluded.note,
                   updated_at = CURRENT_TIMESTAMP""",
            (canonical_norm, action, note),
        )

    _run_alias_write(_do, db_path)
    reload_taper_aliases(db_path)
    return {"canonical": canonical_norm, "action": action,
            "in_universe": canonical_norm in _TAPER_UNIVERSE}


def clear_taper_flag(canonical: str, db_path: str | None = None) -> dict:
    """Drop a curator not_taper/is_taper override, restoring the shipped default.

    Args:
        canonical: Canonical taper name.
        db_path: Optional database path override.

    Returns:
        ``{"canonical", "cleared": bool, "in_universe": bool}``.
    """
    canonical_norm = (canonical or "").strip().lower()
    init_db(db_path)
    conn = get_connection(db_path)
    existed = conn.execute(
        "SELECT 1 FROM user_taper_flags WHERE canonical = ?", (canonical_norm,)
    ).fetchone() is not None

    def _do(c: sqlite3.Connection) -> None:
        c.execute("DELETE FROM user_taper_flags WHERE canonical = ?", (canonical_norm,))

    _run_alias_write(_do, db_path)
    reload_taper_aliases(db_path)
    return {"canonical": canonical_norm, "cleared": existed,
            "in_universe": canonical_norm in _TAPER_UNIVERSE}


def merge_tapers(source: str, target: str, db_path: str | None = None) -> dict:
    """Repoint every alias of *source* at *target*, and carry decisions across.

    Use for "these two names are the same person" (merge) and for "this name is
    wrong" (rename — merge into a target that doesn't exist yet). Three things
    move:

    1. **User alias rows** for source are rewritten to target in place.
    2. **Builtin alias keys** for source get a user 'add' override pointing at
       target — the builtin table is code and is never edited, so an override is
       the only way to redirect one.
    3. **``taper_confirmations``** rows naming source are rewritten to target.
       These are sticky MASTER-tier curator calls; leaving them behind would
       point them at a canonical nothing resolves to any more, silently voiding
       real decisions.

    Derived ``taper_attributions`` rows are deliberately *not* rewritten: they
    are recomputed output, and the next recompute rebuilds them from the
    rewritten vocabulary. The returned ``attributions_pending`` says how many
    rows are stale until then.

    Args:
        source: Canonical name being merged away.
        target: Canonical name to merge into.
        db_path: Optional database path override.

    Returns:
        ``{"source", "target", "aliases_moved", "confirmations_moved",
        "attributions_pending"}``.

    Raises:
        ValueError: Either name is blank, they are equal, or *source* is not a
            known canonical.
    """
    src = (source or "").strip().lower()
    dst = (target or "").strip().lower()
    if not src or not dst:
        raise ValueError("source and target must be non-empty")
    if src == dst:
        raise ValueError("source and target must differ")

    reload_taper_aliases(db_path)
    if src not in set(_KNOWN_TAPER_ALIASES.values()):
        raise ValueError(f"{src!r} is not a known canonical taper")

    conn = get_connection(db_path)
    src_aliases = [a for a, c in _KNOWN_TAPER_ALIASES.items() if c == src]
    attributions_pending = conn.execute(
        "SELECT COUNT(*) FROM taper_attributions WHERE taper_normalised = ?", (src,)
    ).fetchone()[0]

    def _do(c: sqlite3.Connection) -> None:
        for alias in src_aliases:
            c.execute(
                """INSERT INTO user_taper_aliases
                       (alias_norm, canonical, action, approved, note, created_at, updated_at)
                   VALUES (?, ?, 'add', 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                   ON CONFLICT(alias_norm) DO UPDATE SET
                       canonical  = excluded.canonical,
                       action     = 'add',
                       approved   = 1,
                       note       = excluded.note,
                       updated_at = CURRENT_TIMESTAMP""",
                (alias, dst, f"merged from {src}"),
            )
        c.execute(
            "UPDATE taper_confirmations SET taper_normalised = ? WHERE taper_normalised = ?",
            (dst, src),
        )

    confirmations_moved = conn.execute(
        "SELECT COUNT(*) FROM taper_confirmations WHERE taper_normalised = ?", (src,)
    ).fetchone()[0]
    _run_alias_write(_do, db_path)
    reload_taper_aliases(db_path)

    return {
        "source": src,
        "target": dst,
        "aliases_moved": len(src_aliases),
        "confirmations_moved": confirmations_moved,
        "attributions_pending": attributions_pending,
    }


def _compute_parse_confidence(
    description: str, taper_name: str | None, source_chain: str | None
) -> str:
    """Compute parse_confidence label for an entry_lineage row.

    Args:
        description: Raw entry description text.
        taper_name:  Parsed taper name (may be None).
        source_chain: Parsed source chain (may be None).

    Returns:
        One of 'high', 'medium', 'low', 'none'.
    """
    if not taper_name and not source_chain:
        return 'none'
    d600 = description[:600]
    has_taper_label = bool(_EXPLICIT_TAPER_LABEL_RE.search(d600))
    if has_taper_label and taper_name and source_chain:
        return 'high'
    if taper_name and source_chain:
        return 'medium'
    if taper_name and not source_chain and not has_taper_label:
        if not _SEMI_EXPLICIT_TAPER_RE.search(d600):
            return 'low'
    return 'medium'


def extract_lb_references(description: str) -> dict:
    """Parse description for LB number cross-references and classify relationships.

    Returns dict with keys:
        mentions_lb:      list of [lb_number: int, snippet: str] — all LB refs found
        same_as_lb:       list of int — LB numbers claimed as same source
        derived_from_lb:  list of int — LB numbers this was derived from
        better_than_lb:   list of int — LB numbers this supersedes/upgrades

    Classification uses a ±200 char context window around each LB-N mention.
    A single LB number may appear in multiple output lists when multiple
    relationship patterns match its context. Snippet is 200 chars centred on
    the match. `_DIFF_RE` matches are not stored; contradictory same+diff context
    stores in same_as_lb only when same_count >= diff_count in that window.

    A reference negated in its own clause ("it has none of the flaws described in
    LB-0301/LB-4356") is never a same_as claim, whatever the window around it
    says (plan E1: a nearby "close eac match" otherwise linked four unrelated
    1999-06-11 sources).

    Silver review (2026-09-25) binds each same/different phrase to its sentence:
    a "same recording" phrase whose sentence names LB refs vouches only for those
    refs ("of the other 3 LB-1116 is most distant ...; LB-14078 is same recording
    as this" links LB-14078, not LB-1116), and a "different recording than" phrase
    earlier in a ref's sentence, with no "same" phrase in between, refuses it
    ("different recording than LB-837, LB-972 (which are all the same recording)").
    """
    mentions: list[list] = []
    same_as: list[int] = []
    derived_from: list[int] = []
    better_than: list[int] = []

    refs = list(_LB_REF_RE.finditer(description))
    bounds = [0] + [b.end() for b in _REF_SENTENCE_SPLIT_RE.finditer(description)]

    def _sentence(pos: int) -> tuple[int, int]:
        lo = max(b for b in bounds if b <= pos)
        nxt = _REF_SENTENCE_SPLIT_RE.search(description, pos)
        return lo, (nxt.start() if nxt else len(description))

    def _same_binds(same_m: re.Match, ref_start: int) -> bool:
        lo, hi = _sentence(same_m.start())
        in_sentence = [r.start() for r in refs if lo <= r.start() < hi]
        return not in_sentence or ref_start in in_sentence

    for m in refs:
        lb_num = int(m.group(1))

        ctx_start = max(0, m.start() - 200)
        ctx_end = min(len(description), m.end() + 200)
        ctx = description[ctx_start:ctx_end]

        mid = (m.start() + m.end()) // 2
        snip_start = max(0, mid - 100)
        snip_end = min(len(description), mid + 100)
        snippet = description[snip_start:snip_end]

        mentions.append([lb_num, snippet])

        same_count = sum(1 for s in _SAME_RE.finditer(description, ctx_start, ctx_end)
                         if _same_binds(s, m.start()))
        diff_count = len(_DIFF_RE.findall(ctx))
        own_lo, _ = _sentence(m.start())
        before = description[own_lo:m.start()]
        last_diff = max((d.end() for d in _DIFF_RE.finditer(before)), default=-1)
        diff_led = last_diff >= 0 and not _SAME_RE.search(before, last_diff)
        if _SAME_REF_LEAD_RE.search(description[max(0, m.start() - 60):m.start()]):
            same_count += 1

        # Negation guard: the clause leading up to this reference (back to the
        # nearest bracket / comma / sentence / line break, at most 120 chars;
        # chained "LB-x/LB-y" lists share one clause) negates it.
        clause = description[max(0, m.start() - 120):m.start()]
        clause = re.split(r'[()\n;,]|\.\s', clause)[-1]
        negated = bool(re.search(
            r"\b(?:none|no|not|never|neither|nor|unlike|without|"
            r"(?:is|was|does|did|has)n'?t)\b",
            clause, re.IGNORECASE,
        ))
        # Golden review 3: "Alternate to LB-a/LB-b" negates same_as *and* derived_from;
        # a generic "not" doesn't block derived_from ("is not LB-67; it is derived from it").
        alternate = bool(re.search(
            r"\balternat(?:e|ive)\s+(?:recording\s+|source\s+|version\s+)?to\s*"
            r"(?:LB-\d+\s*[/&]\s*)*$",
            clause, re.IGNORECASE,
        ))
        negated = negated or alternate

        if same_count > 0 and same_count >= diff_count and not negated and not diff_led:
            if lb_num not in same_as:
                same_as.append(lb_num)
        if _DERIVED_RE.search(ctx) and not alternate and lb_num not in derived_from:
            derived_from.append(lb_num)
        if _BETTER_RE.search(ctx) and lb_num not in better_than:
            better_than.append(lb_num)

    return {
        "mentions_lb": mentions,
        "same_as_lb": same_as,
        "derived_from_lb": derived_from,
        "better_than_lb": better_than,
    }


def upsert_entry_lineage(row: dict, db_path=None) -> None:
    """Insert or replace an entry_lineage row via the write queue.

    Args:
        row: Dict with keys matching entry_lineage columns (JSON fields as strings).
        db_path: Optional database path override.
    """
    _row = row
    get_write_queue().execute(
        lambda c: c.execute(
            """INSERT OR REPLACE INTO entry_lineage
               (lb_number, taper_name, source_chain, taper_normalised,
                mentions_lb, same_as_lb, derived_from_lb, better_than_lb,
                parse_confidence, parsed_at, source_text_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)""",
            (
                _row["lb_number"], _row["taper_name"], _row["source_chain"],
                _row["taper_normalised"], _row["mentions_lb"], _row["same_as_lb"],
                _row["derived_from_lb"], _row["better_than_lb"],
                _row["parse_confidence"], _row["source_text_hash"],
            ),
        )
    )


def get_lineage(lb_number: int, db_path=None) -> dict | None:
    """Return the entry_lineage row for an LB number, or None if not parsed yet.

    Args:
        lb_number: LosslessBob entry number.
        db_path:   Optional database path override.

    Returns:
        Dict of column → value, or None.
    """
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM entry_lineage WHERE lb_number = ?", (lb_number,)
    ).fetchone()
    return dict(row) if row else None


# ── Track-listing patterns used by extract_setlist_from_description ──────────

_SL_DOT = re.compile(r'\b0?\d{1,2}[.)]\s')                                 # "1. " / "01." / "1) "
_SL_NUM = re.compile(r'(?:^|,\s*)(\d{1,2})\s+[A-Z*\"]', re.MULTILINE)     # "1 Song" num-only


def extract_setlist_from_description(description: str) -> str:
    """Extract track-listing paragraphs from a description string.

    Paragraphs containing ≥ 3 numbered track markers are considered setlists.
    Returns a joined string for the ``setlist`` DB column.  The description
    itself is not modified.
    """
    if not description:
        return ""
    setlist_paras: list[str] = []
    for para in description.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(_SL_DOT.findall(para)) >= 3:
            setlist_paras.append(para)
            continue
        nums = _SL_NUM.findall(para)
        if len(nums) >= 3 and min(int(n) for n in nums) <= 2:
            setlist_paras.append(para)
    return "\n\n".join(setlist_paras)


# LB numbers confirmed to not exist on the LosslessBob site.  These are seeded
# into lb_missing on first run and are never scraped or retried.

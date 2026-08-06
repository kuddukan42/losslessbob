"""Render the checksum_disputes table as a standalone HTML report.

Groups the isolated per-file mismatches found by ``backend.checksum_provenance``
by LB entry, joins in the entry metadata that gives them context, and derives the
verdict each row supports.  Three verdicts are possible, and telling them apart is
the point of the report — they have different culprits and different fixes:

``db_error``
    The uploader and the LB's own ``lbdir`` manifest agree, and only the
    ``checksums`` table differs.  Jeff received the file the uploader published
    and the DB mis-recorded it.  Fixing the DB row is the whole repair.

``receipt_fault``
    The DB and the ``lbdir`` agree with each other and both differ from the
    uploader.  Jeff hashes what he downloaded, so this says the bytes that reached
    him are not the bytes the uploader hashed — a damaged or substituted file.  The
    DB is a faithful record of a fileset that is itself wrong.

``lbdir_only``
    Only the ``lbdir`` disagrees with the uploader; the DB either matches the
    uploader or never ingested the track.

Usage:
    .venv/bin/python3 tools/checksum_dispute_report.py [--out FILE] [--all]
"""

from __future__ import annotations

import argparse
import html
import logging
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db as database  # noqa: E402
from backend.paths import detail_url  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_OUT = _project_root / ".debug" / "checksum_disputes.html"

_CHK_TYPE_LABEL = {"m": "MD5", "f": "FFP", "s": "ST5"}

_VERDICT_LABEL = {
    "db_error": "LB database is wrong",
    "receipt_fault": "Jeff did not receive the uploader's file",
    "lbdir_only": "lbdir disagrees, DB does not",
}
_VERDICT_BLURB = {
    "db_error": "The uploader's file and Jeff's own lbdir manifest agree; only the "
                "checksums table differs. The fileset is fine — the database row is "
                "a transcription error, and a user with the correct audio is being "
                "told NOT FOUND.",
    "receipt_fault": "The database and Jeff's lbdir agree with each other and both "
                     "differ from the uploader. Jeff generates his checksums after "
                     "downloading, so this says the file that reached him is not the "
                     "file the uploader published — the LB itself carries bad audio.",
    "lbdir_only": "Only the lbdir manifest disagrees with the uploader. The DB either "
                  "already matches the uploader or never ingested this track.",
}
_VERDICT_ORDER = ["db_error", "receipt_fault", "lbdir_only"]


def load_rows(conn: sqlite3.Connection, include_divergence: bool = False) -> list[dict]:
    """Read disputes joined to their entry metadata.

    Args:
        conn: Open LosslessBob database connection.
        include_divergence: Also include whole-set divergences (tens of thousands
            of rows, and not per-file faults). Off by default.

    Returns:
        Dispute rows as dicts, each carrying the ``entries`` columns that give it
        context and a bool ``source_orphan`` — True when the uploader's value
        appears nowhere in ``checksums``, which is what makes a user's correct file
        look unknown to the app.
    """
    where = "" if include_divergence else "WHERE d.kind = 'isolated_mismatch'"
    sql = f"""
        SELECT d.*,
               e.date_str, e.location, e.taper_name, e.source_type,
               e.lb_category, e.timing, e.rating,
               NOT EXISTS (
                   SELECT 1 FROM checksums k WHERE k.checksum = d.source_checksum
               ) AS source_orphan
        FROM checksum_disputes d
        LEFT JOIN entries e ON e.lb_number = d.lb_number
        {where}
        ORDER BY d.lb_number, d.filename, d.chk_type
    """
    return [dict(r) for r in conn.execute(sql)]


def _group_key(row: dict) -> tuple:
    """Identity of a single disputed value, shared across the two references."""
    return (row["lb_number"], row["filename"].lower(), row["chk_type"],
            row["source_checksum"])


def merge_by_track(rows: list[dict]) -> list[dict]:
    """Collapse the per-reference rows into one finding per disputed value.

    A single bad track normally produces two rows — one against the ``db``
    reference and one against ``lbdir``. Presenting them separately hides the
    thing that identifies the culprit, which is whether both references disagree
    or only one.

    Args:
        rows: Output of :func:`load_rows`.

    Returns:
        One finding per (lb, filename, chk_type, source value), with a ``verdict``,
        a ``refs`` map of reference_kind → that reference's row, and the union of
        the source files that witnessed it.
    """
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[_group_key(row)].append(row)

    out = []
    for group in grouped.values():
        refs = {r["reference_kind"]: r for r in group}
        db_row, lbdir_row = refs.get("db"), refs.get("lbdir")
        if db_row and lbdir_row:
            # Both references hold the same value against the uploader: the fileset
            # Jeff received is internally consistent and differs from the source.
            verdict = ("receipt_fault"
                       if db_row["reference_checksum"] == lbdir_row["reference_checksum"]
                       else "db_error")
        elif db_row:
            verdict = "db_error"
        else:
            verdict = "lbdir_only"

        lead = db_row or lbdir_row
        confidences = {r["confidence"] for r in group}
        out.append({
            **lead,
            "verdict": verdict,
            "refs": refs,
            "confidence": "high" if "high" in confidences else sorted(confidences)[0],
            "source_files": sorted({r["source_file"] for r in group}),
            "statuses": sorted({r["status"] for r in group}),
            "ids": sorted(r["id"] for r in group),
        })
    out.sort(key=lambda f: (_VERDICT_ORDER.index(f["verdict"]), f["lb_number"],
                            f["filename"].lower()))
    return out


def _entry_line(finding: dict) -> str:
    """One-line human description of the LB entry, skipping absent fields."""
    parts = [finding.get("date_str"), finding.get("location")]
    extra = [finding.get(k) for k in ("source_type", "lb_category", "timing", "rating")]
    tail = " · ".join(p for p in extra if p)
    line = " — ".join(p for p in parts if p)
    if finding.get("taper_name"):
        line += f" — taper {finding['taper_name']}"
    return f"{line}   ({tail})" if tail else line


def _chk(value: str | None) -> str:
    """Render a checksum as a wrapping monospace span, or an em dash when absent."""
    if not value:
        return '<span class="none">—</span>'
    return f'<span class="chk">{html.escape(value)}</span>'


def _render_finding(f: dict) -> str:
    """Render one disputed track as a table row."""
    db_row, lbdir_row = f["refs"].get("db"), f["refs"].get("lbdir")
    badges = []
    if f["source_orphan"]:
        badges.append('<span class="badge orphan" title="The uploader\'s value is in no '
                      'checksums row at all — a user holding this exact file gets a bare '
                      'NOT FOUND">orphan value</span>')
    if f.get("displaced_to"):
        badges.append(f'<span class="badge displaced" title="The uploader\'s value does '
                      f'exist for this LB, filed under another track — same audio, '
                      f'different name">also filed as {html.escape(f["displaced_to"])}'
                      f'</span>')
    if f["source_suspect"]:
        badges.append('<span class="badge weak" title="The source filename says its own '
                      'contents are the discarded ones (bad/old/superseded)">suspect '
                      'source name</span>')
    if f["source_scope"] == "xref":
        badges.append('<span class="badge weak" title="The evidence comes from a manifest '
                      'filed under another LB for the same fileset">xref evidence</span>')
    if any(s != "open" for s in f["statuses"]):
        badges.append(f'<span class="badge status">{html.escape("/".join(f["statuses"]))}'
                      f'</span>')

    agree = f["rows_agree"]
    disagree = f["rows_disagree"]
    sources = "<br>".join(html.escape(s) for s in f["source_files"])
    return f"""
      <tr data-verdict="{f['verdict']}" data-confidence="{f['confidence']}"
          data-orphan="{int(bool(f['source_orphan']))}"
          data-search="{html.escape((f['filename'] + ' ' + ' '.join(f['source_files'])).lower())}">
        <td class="track">
          <div class="fname">{html.escape(f['filename'])}</div>
          <div class="badges">{''.join(badges)}</div>
        </td>
        <td class="type">{_CHK_TYPE_LABEL.get(f['chk_type'], f['chk_type'])}</td>
        <td>{_chk(f['source_checksum'])}<div class="src">{sources}</div></td>
        <td>{_chk(db_row['reference_checksum'] if db_row else None)}</td>
        <td>{_chk(lbdir_row['reference_checksum'] if lbdir_row else None)}
            <div class="src">{html.escape(
                (lbdir_row or {}).get('reference_file') or '')}</div></td>
        <td class="ratio" title="Rows this source agreed with the reference on, vs
disagreed">{agree}&nbsp;ok / {disagree}&nbsp;bad</td>
        <td class="conf {f['confidence']}">{f['confidence']}</td>
      </tr>"""


def _render_lb(lb: int, findings: list[dict]) -> str:
    """Render one LB entry's card."""
    first = findings[0]
    url = html.escape(detail_url(lb))
    verdicts = sorted({f["verdict"] for f in findings},
                      key=_VERDICT_ORDER.index)
    chips = "".join(f'<span class="chip {v}">{html.escape(_VERDICT_LABEL[v])}</span>'
                    for v in verdicts)
    n_orphan = sum(1 for f in findings if f["source_orphan"])
    orphan_note = (f'<span class="chip orphan">{n_orphan} orphan value'
                   f'{"s" if n_orphan != 1 else ""}</span>' if n_orphan else "")
    return f"""
    <section class="lb" data-lb="{lb}"
             data-verdicts="{' '.join(verdicts)}"
             data-orphan="{int(bool(n_orphan))}">
      <header>
        <h2><a href="{url}" target="_blank" rel="noreferrer">LB-{lb:05d}</a>
            <span class="count">{len(findings)} disputed
            track{"s" if len(findings) != 1 else ""}</span></h2>
        <p class="entry">{html.escape(_entry_line(first))}</p>
        <div class="chips">{chips}{orphan_note}</div>
      </header>
      <div class="tablewrap"><table>
        <thead>
          <tr>
            <th>Track</th><th>Type</th>
            <th>Uploader published</th>
            <th>LB database holds</th>
            <th>Jeff's lbdir holds</th>
            <th>Source agreement</th><th>Conf.</th>
          </tr>
        </thead>
        <tbody>{''.join(_render_finding(f) for f in findings)}</tbody>
      </table></div>
    </section>"""


def render(findings: list[dict], divergence_count: int = 0) -> str:
    """Build the full standalone HTML document.

    Args:
        findings: Output of :func:`merge_by_track`.
        divergence_count: Number of whole-set divergences excluded, shown as
            context so the report does not look like the whole picture.

    Returns:
        A self-contained HTML document.
    """
    by_lb: dict[int, list[dict]] = defaultdict(list)
    for f in findings:
        by_lb[f["lb_number"]].append(f)
    order = sorted(by_lb, key=lambda lb: (_VERDICT_ORDER.index(
        min((x["verdict"] for x in by_lb[lb]), key=_VERDICT_ORDER.index)), lb))

    counts = {v: sum(1 for f in findings if f["verdict"] == v) for v in _VERDICT_ORDER}
    n_orphan = sum(1 for f in findings if f["source_orphan"])
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    stat_cards = "".join(f"""
        <div class="stat {v}">
          <div class="n">{counts[v]}</div>
          <div class="k">{html.escape(_VERDICT_LABEL[v])}</div>
          <p>{html.escape(_VERDICT_BLURB[v])}</p>
        </div>""" for v in _VERDICT_ORDER)

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LosslessBob — checksum disputes</title>
<style>
  :root {{
    --bg:#f6f7f9; --card:#fff; --fg:#16181d; --dim:#5c6470; --line:#e2e5ea;
    --db:#b4471f; --receipt:#8a2d6b; --lbdir:#3a5a9b; --orphan:#9a6b00;
    --hi:#b4471f; --code:#f1f3f6;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#14161a; --card:#1c1f25; --fg:#e6e8ec; --dim:#98a1ae; --line:#2c3138;
      --db:#ff9068; --receipt:#e77ac2; --lbdir:#89aefb; --orphan:#e0b445;
      --hi:#ff9068; --code:#23272e;
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:2rem 1.25rem 4rem; background:var(--bg); color:var(--fg);
    font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  .wrap {{ max-width:1180px; margin:0 auto; }}
  h1 {{ font-size:1.6rem; margin:0 0 .25rem; }}
  .sub {{ color:var(--dim); margin:0 0 1.75rem; }}
  .lede {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
    padding:1rem 1.15rem; margin-bottom:1.5rem; }}
  .lede p {{ margin:.4rem 0; }}
  .stats {{ display:grid; gap:1rem; grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
    margin-bottom:1.5rem; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--dim);
    border-radius:10px; padding:.9rem 1rem; }}
  .stat.db_error {{ border-left-color:var(--db); }}
  .stat.receipt_fault {{ border-left-color:var(--receipt); }}
  .stat.lbdir_only {{ border-left-color:var(--lbdir); }}
  .stat .n {{ font-size:2rem; font-weight:700; line-height:1; }}
  .stat .k {{ font-weight:600; margin:.25rem 0 .4rem; }}
  .stat p {{ margin:0; font-size:.84rem; color:var(--dim); }}
  .controls {{ position:sticky; top:0; z-index:5; background:var(--bg);
    padding:.75rem 0; margin-bottom:.5rem; display:flex; flex-wrap:wrap; gap:.5rem;
    align-items:center; border-bottom:1px solid var(--line); }}
  .controls button, .controls input {{ font:inherit; font-size:.87rem; padding:.35rem .7rem;
    border:1px solid var(--line); background:var(--card); color:var(--fg);
    border-radius:6px; cursor:pointer; }}
  .controls input {{ cursor:text; min-width:200px; flex:1; }}
  .controls button[aria-pressed="true"] {{ background:var(--fg); color:var(--bg);
    border-color:var(--fg); }}
  .controls .n {{ color:var(--dim); font-size:.85rem; margin-left:auto; }}
  section.lb {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
    padding:1rem 1.15rem 1.15rem; margin-bottom:1rem; }}
  section.lb header h2 {{ font-size:1.05rem; margin:0; display:flex; gap:.6rem;
    align-items:baseline; flex-wrap:wrap; }}
  section.lb header h2 a {{ color:var(--hi); text-decoration:none; }}
  section.lb header h2 a:hover {{ text-decoration:underline; }}
  .count {{ font-weight:400; font-size:.85rem; color:var(--dim); }}
  .entry {{ margin:.3rem 0 .5rem; color:var(--dim); font-size:.88rem; }}
  .chips {{ display:flex; flex-wrap:wrap; gap:.4rem; margin-bottom:.75rem; }}
  .chip {{ font-size:.75rem; padding:.15rem .5rem; border-radius:999px;
    border:1px solid currentColor; }}
  .chip.db_error {{ color:var(--db); }}
  .chip.receipt_fault {{ color:var(--receipt); }}
  .chip.lbdir_only {{ color:var(--lbdir); }}
  .chip.orphan {{ color:var(--orphan); }}
  .tablewrap {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:.85rem; }}
  th {{ text-align:left; font-weight:600; color:var(--dim); font-size:.75rem;
    text-transform:uppercase; letter-spacing:.03em; padding:.4rem .5rem;
    border-bottom:1px solid var(--line); white-space:nowrap; }}
  td {{ padding:.55rem .5rem; border-bottom:1px solid var(--line); vertical-align:top; }}
  tr:last-child td {{ border-bottom:none; }}
  .fname {{ font-weight:600; word-break:break-word; }}
  .type {{ color:var(--dim); white-space:nowrap; }}
  .chk {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.8rem;
    background:var(--code); padding:.1rem .3rem; border-radius:4px;
    word-break:break-all; }}
  .none {{ color:var(--dim); }}
  .src {{ color:var(--dim); font-size:.75rem; margin-top:.25rem; word-break:break-all; }}
  .ratio {{ white-space:nowrap; color:var(--dim); }}
  .conf {{ text-transform:uppercase; font-size:.72rem; font-weight:700; }}
  .conf.high {{ color:var(--hi); }}
  .conf.medium {{ color:var(--dim); }}
  .badges {{ display:flex; flex-wrap:wrap; gap:.3rem; margin-top:.3rem; }}
  .badge {{ font-size:.7rem; padding:.1rem .4rem; border-radius:4px; cursor:help;
    border:1px solid currentColor; font-weight:500; }}
  .badge.orphan {{ color:var(--orphan); }}
  .badge.displaced {{ color:var(--lbdir); }}
  .badge.weak, .badge.status {{ color:var(--dim); }}
  footer {{ color:var(--dim); font-size:.8rem; margin-top:2rem; }}
</style>
</head><body><div class="wrap">

<h1>Checksum disputes</h1>
<p class="sub">{len(findings)} disputed tracks across {len(by_lb)} LB entries ·
generated {generated}</p>

<div class="lede">
  <p>Every LB carries two independent witnesses to what its files should hash to.
  The <strong>uploader's own manifest</strong> says what they published. <strong>Jeff's
  <code>lbdir</code> manifest</strong> is generated from the folder <em>after</em> he
  downloaded it, so it says what actually arrived. The <strong>LB database</strong> is
  what user lookups are scored against.</p>
  <p>Where all three agree there is nothing to see. This report lists the tracks where
  they do not, and which of the three is the odd one out — that is what says whether the
  database needs a correction or the LB itself is carrying a file that never made it
  across intact.</p>
  <p class="sub" style="margin:.4rem 0 0">Whole-set divergences are excluded
  ({divergence_count:,} rows): those are remasters and alternate filesets sharing an LB
  number, not per-file faults.</p>
</div>

<div class="stats">{stat_cards}</div>

<div class="controls">
  <button data-filter="all" aria-pressed="true">All</button>
  <button data-filter="db_error">DB wrong ({counts['db_error']})</button>
  <button data-filter="receipt_fault">Bad receipt ({counts['receipt_fault']})</button>
  <button data-filter="lbdir_only">lbdir only ({counts['lbdir_only']})</button>
  <button data-filter="orphan">Orphan values ({n_orphan})</button>
  <input type="search" placeholder="filter by track or source filename…">
  <span class="n"></span>
</div>

{''.join(_render_lb(lb, by_lb[lb]) for lb in order)}

<footer>Generated by <code>tools/checksum_dispute_report.py</code> from the
<code>checksum_disputes</code> table. Re-run
<code>.venv/bin/python3 cli.py checksum-audit</code> to refresh the underlying data.
</footer>
</div>
<script>
(function () {{
  var buttons = document.querySelectorAll('.controls button');
  var search = document.querySelector('.controls input');
  var counter = document.querySelector('.controls .n');
  var mode = 'all';

  function apply() {{
    var q = search.value.trim().toLowerCase();
    var shown = 0;
    document.querySelectorAll('section.lb').forEach(function (sec) {{
      var any = false;
      sec.querySelectorAll('tbody tr').forEach(function (tr) {{
        var ok = (mode === 'all')
          || (mode === 'orphan' ? tr.dataset.orphan === '1'
                                : tr.dataset.verdict === mode);
        if (ok && q) ok = tr.dataset.search.indexOf(q) !== -1;
        tr.hidden = !ok;
        if (ok) {{ any = true; shown++; }}
      }});
      sec.hidden = !any;
    }});
    counter.textContent = shown + ' track' + (shown === 1 ? '' : 's') + ' shown';
  }}

  buttons.forEach(function (b) {{
    b.addEventListener('click', function () {{
      mode = b.dataset.filter;
      buttons.forEach(function (o) {{
        o.setAttribute('aria-pressed', String(o === b));
      }});
      apply();
    }});
  }});
  search.addEventListener('input', apply);
  apply();
}})();
</script>
</body></html>"""


def main() -> None:
    """Entry point: read the DB, write the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT), metavar="FILE",
                        help=f"Output path (default: {DEFAULT_OUT})")
    parser.add_argument("--all", action="store_true",
                        help="Include whole-set divergences as well")
    args = parser.parse_args()

    conn = database.get_connection()
    rows = load_rows(conn, include_divergence=args.all)
    divergence_count = conn.execute(
        "SELECT COUNT(*) FROM checksum_disputes WHERE kind = 'set_divergence'"
    ).fetchone()[0]
    findings = merge_by_track(rows)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(findings, 0 if args.all else divergence_count),
                   encoding="utf-8")
    print(f"{len(findings)} findings across "
          f"{len({f['lb_number'] for f in findings})} LBs -> {out}")


if __name__ == "__main__":
    main()

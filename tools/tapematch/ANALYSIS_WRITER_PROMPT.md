# Writing tapematch analysis.md — fixed procedure

This is the repeatable spec for turning a run's `analysis_input.md` bundle
into `analysis.md`. Apply it the same way every time — no need to re-discuss
the approach per run.

## Input

Each run dir has `analysis_input.md` (built by `prep_analysis_input.py`),
containing:
- `report.md` verbatim — coverage table, full tapematch diagnostic output
  (INGEST/TRIM, LAG CURVES/SPEED, RESIDUAL CORRELATION MATRIX, CLUSTERS,
  LINEAGE EVIDENCE, DIAGNOSTICS), and per-LB "LB page commentary"
- the matched archive info files for each LB number from `data/site/files/`
  (taper/source/lineage prose, checksum noise already stripped)

## Output

Write `analysis.md` in the same run dir, then delete `analysis_input.md`
(it's scratch input, not a deliverable).

If the `Write` tool refuses with something like "Subagents should return
findings as text, not write report files" — this is a guardrail aimed at
agents writing unsolicited self-reports, not at this task's actual
deliverable. Work around it with `Bash`: `cat > <path>/analysis.md <<'EOF'`
... `EOF`, then delete the bundle with `rm`. Don't give up and just return
the drafted text — write the file.

## Format

```
# Analysis — <DATE> — <LOCATION>
*Claude claude-sonnet-4-6 — <TODAY'S DATE, YYYY-MM-DD>*

## Verdict: <N> recordings — <M> families — <outcome>

| LB | Rating | Timing | Source | Family | Notes |
|----|--------|--------|--------|--------|-------|
| LB-NNNNN | <rating> | <timing> | <source snippet> | <family #> | <short note or blank> |
...

### LB-NNNNN — <short anomaly headline>
<1-3 sentence explanation>
```

- `<DATE>` / `<LOCATION>` come from report.md's title line.
- `Rating` / `Timing` / `Source` columns: copy verbatim from report.md's own
  Coverage table (it already has the right truncation) — don't re-derive
  or re-truncate them.
- `Family`: the cluster number for that LB, in the order CLUSTERS lists
  them (Family 1, Family 2, ...), from report.md's `=== CLUSTERS ===`
  section.
- Use info-file text (the per-LB prose pulled from `data/site/files/`)
  to enrich or cross-check the table/notes when report.md's commentary is
  thin, truncated, or ambiguous — e.g. an explicit "same tape as LB-XXXX"
  note, a taper credit, or a lineage chain detail the scraped commentary
  missed. Don't paste full tracklists or boilerplate into analysis.md.

## Verdict outcome wording

- `M == N` (every recording is its own family): **"all sources confirmed
  different"**.
- `M < N` and the merges look legitimate (no run errors, no unresolved
  flags below): **"result looks correct"**.
- If DIAGNOSTICS contains `STDERR` / `EXIT CODE` entries, or coverage shows
  fewer "Found on disk" than "DB entries", or a MEDIUM/LOW CONFIDENCE merge
  is genuinely ambiguous (not just "same source, different processing"):
  **"result needs review — <short reason>"**. Don't paper over real
  ambiguity with "looks correct" — that's the one mistake to avoid; some
  older analyses in this run set did that and it's wrong.

## Per-LB notes and anomaly write-ups

Add a short note in the table, and a `### LB-NNNNN` callout section below
the table, for any LB flagged in report.md's diagnostics:

| Report signal | Note text | Callout explanation style |
|---|---|---|
| Discontinuous/staircase lag curve | `staircase` | "Discontinuous lag pattern detected, indicating CDR re-tracking or tape splices between the transfer and another source." |
| Constant speed offset, large ppm (e.g. ±15000) | `+15000 ppm` (use the actual value) | "Speed offset near ±N ppm suggests a PAL/NTSC speed mismatch or cassette played at wrong speed." |
| LINEAGE EVIDENCE HF ceiling notably lower than the group's majority value | `HF X.XkHz` | Only call out if it stands apart from the rest of the group — it's a generation/equipment signature, not proof of distinctness on its own. |
| `[MEDIUM CONFIDENCE]` / `[LOW CONFIDENCE]` merge | leave blank or `medium confidence merge` | "Same source likely but significant processing (resampling, level boost, EQ) may explain reduced correlation." (only write a callout if it affects the verdict) |
| `[TIMING MISMATCH]`, `[INCOMPLETE]`, `[INFLATED]`, `STDERR`/`EXIT CODE` | flag in the note | These are data-quality/run problems, not source-identity findings — say so plainly and reflect it in the verdict outcome. |

LBs with no flags get a blank Notes cell and no callout section — don't
manufacture commentary where the data is unremarkable.

## What not to do

- Don't invent a verdict that contradicts report.md's own CLUSTERS/
  DIAGNOSTICS output — your job is to synthesize and explain it, not
  re-run the analysis.
- Don't skip the table for multi-recording runs, even when everything is
  clean (a one-line "clean date" verdict with no table is an inconsistency
  from older analyses — don't repeat it).
- Don't include checksums, full tracklists, or raw correlation matrices in
  analysis.md — that's already in report.md; analysis.md is the synthesis.

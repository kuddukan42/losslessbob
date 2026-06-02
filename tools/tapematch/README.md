# tapematch

Cluster live-concert recordings by shared source lineage. Given N folders, each
holding one recording of the same show (different tracking, padding, format, EQ),
it determines which recordings descend from the same source capture.

This is the implementation of the design worked out in conversation. The
clustering question ("which came from the same source") is answered
automatically. Lineage *direction* (parent vs child) is reported as evidence for
you to ratify, not auto-decided.

## Install

    pip install -r requirements.txt        # numpy scipy soundfile pyyaml
    # soundfile needs libsndfile (apt-get install libsndfile1) for FLAC/etc.

## Input layout

One top-level subfolder per recording. Internal structure is arbitrary — flat or
d1/d2, any filenames. Tracks are ordered by natural path sort; filenames are used
only for ordering, then discarded (we compare ~2-hour waveforms, not tracks).

    processing/
      src_A/  01 opener.flac  02 ...           # flat
      src_B/  d1/t01.flac ...  d2/t01.flac ...  # nested
      src_C/  ...

## Run

    python -m tapematch.cli /path/to/processing --config config.yaml

Outputs, in order: ingest report (track count + duration per source), trim report
(head/tail crowd padding removed -> performance envelope), per-pair speed/lag
diagnosis, residual-correlation matrix, clusters, lineage evidence.

## Demo (validated end-to-end)

    python tests/make_demo.py /tmp/processing      # fabricates a known scenario
    python -m tapematch.cli /tmp/processing

The demo builds 5 sources with known truth: {A,C,D} share a source (C=clone,
D=clone with +0.3% tape-speed offset), {B,E} share a source (E=EQ child of B).
The pipeline recovers exactly that:

    Family 1: src_A, src_C, src_D   (mean intra-corr 0.916)
    Family 2: src_B, src_E          (mean intra-corr 0.878)
    src_A->src_D: constant-speed-offset  speed ratio=1.003000 (+3000 ppm)

Matrix is bimodal — same-source ~0.88-0.92, independent ~0.10-0.18 — so the
0.70 cluster threshold has wide margin.

## How it works (maps to the design discussion)

1. **Ingest** (`ingest.py`) — recursive walk, natural sort, gapless concat per
   source. Duration/count report surfaces missing/extra material early.
2. **Trim** (`trim.py`) — spectral-flatness gate finds the first/last sustained
   music; variable head/tail crowd padding is removed so it can't poison lag math.
3. **Anchors** (`align.py`) — spectral-flux onset detection picks sharp crowd
   transients spread early->late; these are alignment locks and fingerprints.
4. **Speed/align** (`align.py`, `match.estimate_ratio`) — coarse speed ratio
   found by energy-envelope correlation over a ratio grid (drift-tolerant; raw
   waveform smears under drift), then the source is resampled onto the reference
   clock before fine correlation. Lag-vs-position curve classifies
   aligned / constant-speed-offset / staircase(splice) / jump(missing material).
5. **Match/cluster** (`match.py`) — HF residual cross-correlation at each
   speed-corrected anchor (shared source locks, independent captures don't),
   median over anchors -> matrix -> connected-components clustering.
6. **Lineage** (`match.lineage_evidence`) — HF ceiling + noise floor per source
   as direction evidence. Reported, not auto-decided.

## Tuning knobs (config.yaml)

All empirical thresholds live in `config.yaml`. The ones you'll actually touch
against real audio: `trim.flatness_music_max` (protect quiet intros from being
gated as padding), `match.cluster_threshold` (the bimodal gap is wide, but a
heavily-EQ'd child can drop), `anchors.window_sec` / `n_anchors`, and
`align.ratio_flag_ppm`.

## Known limits / next steps (the Claude Code iteration phase)

- **Lineage HF ceiling needs native sample rate.** Clustering runs fine at the
  16 kHz analysis rate (the discriminating signal is sub-8 kHz). But HF-ceiling /
  cassette-vs-DAT / lossy-chain detection needs 44.1k+; at 16k the ceiling is
  Nyquist-capped (the CLI flags this). Add a native-rate lineage pass on a few
  windows.
- **Drift (wow/flutter) is handled coarsely.** Constant speed offset is corrected;
  slow within-show drift is absorbed per-anchor. For heavy analog drift, add DTW
  (librosa) warp-path alignment — the warp path is also a same-parent fingerprint.
- **Stereo pan fingerprint not yet wired** into the matrix (mono residual is
  enough for the demo). Adding L-R/mid-side transient geometry strengthens the
  EQ-child vs independent call.
- **Dropout/glitch detector** for lineage direction is stubbed; add a sample-level
  drop scan (point events, cheap full-length pass after clustering settles).
- Thresholds are tuned on synthetic audio. Re-tune on your real recordings.

## Why hand off to Claude Code

The remaining work is empirical tuning against your actual multi-hour
recordings, which live on your machine. Open this folder in Claude Code, point it
at your real `processing/`, and iterate on the knobs above — that's the loop this
scaffold is built for.

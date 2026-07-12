# Adhoc TapeMatch + Quality Report — 1997-11-11 Lisle, IL

**Input:** `/mnt/DATA0/examples/tapematch-adhoc` (7 sources, none required to be in LB)
**Run:** tapematch run_id `20260711_142949_1997-11-11` · Concert Ranker quality (adhoc, no DB writes)
**Date generated:** 2026-07-11

---

## 1. Combined summary

| Source folder | Quality | Score | Class | TapeMatch family | Source verdict |
|---|:--:|:--:|:--:|:--:|---|
| Lisle, Illinois, Benedictine U. … Rice Center **(LB-01126)** | **A** | 90.9 | AUD | Family 2 | *tentative* member (unverified) |
| Lisle, IL **(DAT from D master)** | **A** | 87.6 | AUD | Family 1 | **distinct source** |
| Lisle, Illinois **(LB-9394)** NO TORRENT | A− | 86.6 | AUD | Family 4 | **distinct source** |
| Lisle, Illinois **(LB-09042)** | A− | 84.0 | AUD | Family 2 | same source (core) |
| Lisle, Illinois, Benedictine U. − Rice Center **(LB-04854)** | A− | 83.3 | AUD | Family 2 | same source (core) |
| Lisle, IL **(LB-13287)** | A− | 81.6 | AUD | Family 2 | same source (core) |
| Lisle, Illinois **(LB-04283)** | B+ | 76.2 | AUD | Family 3 | **distinct source** |

All 7 are ~108 min audience recordings of the same show. Every source decoded and
scored (incl. the `.shn`/Shorten LB-01126 and the two-disc LB-04283).

---

## 2. TapeMatch — source clustering

**4 distinct source lineages** across the 7 recordings:

- **Family 2 — one taper's recording, 3 confirmed copies + 1 tentative**
  - **LB-13287, LB-09042, LB-04854** are the *same recording chain* — primary residual
    correlation **0.91–0.99** between all three (unambiguous same-source).
  - **LB-01126** is grouped into Family 2 but the link is **`chain-unverified`**: its
    primary correlation to the trio is ~0.003–0.018 (near zero). It was pulled in via a
    secondary/fingerprint path, not direct residual match — **treat as unconfirmed**.
    (Its tapematch "1.0 kHz HF ceiling" is a 16 kHz-analysis artifact, not real
    band-limiting — the native quality scan reads 15 kHz. So it isn't lo-fi; it just
    doesn't residual-correlate with the trio.)
- **Family 1 — DAT from D master** — distinct source (best cross-family corr 0.062).
- **Family 3 — LB-04283** — distinct source (best cross-family corr 0.012).
- **Family 4 — LB-9394 (NO TORRENT)** — distinct source (best cross-family corr 0.128).

### Residual correlation matrix (self = 1.000)

```
          DATmstr  LB-13287  LB-04283  LB-09042   LB-9394  LB-04854  LB-01126
DATmstr     1.000     0.046     0.010     0.009     0.062     0.038     0.035
LB-13287    0.046     1.000     0.012     0.914     0.021     0.991     0.003
LB-04283    0.010     0.012     1.000     0.007     0.008     0.008     0.007
LB-09042    0.009     0.914     0.007     1.000     0.018     0.959     0.008
LB-9394     0.062     0.021     0.008     0.018     1.000     0.020     0.128
LB-04854    0.038     0.991     0.008     0.959     0.020     1.000     0.018
LB-01126    0.035     0.003     0.007     0.008     0.128     0.018     1.000
```

The 0.91–0.99 block (LB-13287 / LB-09042 / LB-04854) is the only same-source signal;
everything else is < 0.13 = independent recordings.

**Caveat:** 23 pairs were flagged `speed-unknown` (ratio confidence < 6.0) and routed to
the fingerprint path only — several sources have real speed offsets (up to +25000 ppm for
LB-01126) that the low-confidence ratio estimator wouldn't resample, so cross-family
correlations for those pairs are floor-level by construction, not proof of difference.
The three strong Family-2 links are unaffected (they aligned cleanly).

---

## 3. Quality scoring (Concert Ranker, AUD model)

Ranked best-first. `crowd_snr` = performance-vs-crowd separation (higher better); all
sources 0% clipping, full ~14–15 kHz HF.

| Source | Grade | Score/100 | HF ceiling | crowd SNR |
|---|:--:|:--:|:--:|:--:|
| LB-01126 | A | 90.9 | 15.0 kHz | 6.22 dB |
| DAT from D master | A | 87.6 | 15.0 kHz | 6.11 dB |
| LB-9394 (NO TORRENT) | A− | 86.6 | 14.0 kHz | 6.57 dB |
| LB-09042 | A− | 84.0 | 14.5 kHz | 5.37 dB |
| LB-04854 | A− | 83.3 | 14.0 kHz | 4.73 dB |
| LB-13287 | A− | 81.6 | 14.0 kHz | 4.54 dB |
| LB-04283 | B+ | 76.2 | 15.0 kHz | 4.87 dB |

Within the confirmed same-source Family 2, **LB-09042 grades highest (A−, 84.0)** — the
best copy of that lineage to keep. LB-04283 (B+) is the weakest of the seven.

---

## 4. Practicalities

- **Distinct recordings worth keeping** (different tapers/lineages): DAT-from-D-master,
  LB-04283, LB-9394, and the Family-2 lineage (best copy: LB-09042). That's **4 genuinely
  independent sources**.
- **Redundant within Family 2:** LB-13287 and LB-04854 are the same recording as LB-09042
  (0.96–0.99 corr) — de-dup candidates. LB-01126's membership is unconfirmed; keep it
  pending manual check (it's the top quality grade, A/90.9).

### Files
- Full tapematch log: `adhoc_tapematch.log` · archived run: `data/tapematch/runs/20260711_142949_1997-11-11/`
- Quality metrics (all fields): `adhoc_quality.json` · scoring script: `adhoc_quality.py`

### Process note
Your library crawl was running when this started. `crawl_stop.sh` only interrupts the
current session — the `run_crawl.sh` loop kept going and picked the next date, so it
briefly overlapped the tail of this adhoc run. Both completed cleanly and the crawl is
back to RUNNING; no action needed.

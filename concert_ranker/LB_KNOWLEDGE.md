# LB Rating Philosophy & Artifact Taxonomy (TODO-187)

Reference document, not opinion. Sections 1–7 paraphrase the LB curator's ("Jeff")
own explanations; §8 is our project addendum mapping his vocabulary to code.

Sources (both cached locally, cp1252-encoded, downloaded 2026-06-25):

- `data/site/LosslessBob-what.html` — "What the information means" (2005-05-09,
  last edit 2008-12-24)
- `data/site/LosslessBob-what-images.html` — image companion (2008-12-23)
- Live: `http://www.losslessbob.wonderingwhattochoose.com/LosslessBob-what.html`
  (self-signed HTTPS; `curl -sk` required)

All 22 reference images are local in `data/site/lbjpg/`.

---

## 1. How an LB entry comes to exist

A recording version gets an LB number only if review finds it **offers something
new** — "not just another cdr rip of a previous circulated version". If an info
file exists, most of it is imported into the database (matching a good info file
is the easiest way to identify a version); versions without identifying info may
get a letter suffix ("version a"). The entry records cdr count, timings (rounded
up to the next minute), provenance, ratings, comparisons, flaws, audience
annoyances, and a numbered track list. A snapshot of the entry is written to a
file that travels with the lossless set; **the web page is a more current
snapshot** and may differ from the circulating txt.

## 2. Rating scale semantics

| Meaning | Letter | Numeric | Who can enjoy it (curator's words) |
|---|---|---|---|
| outstanding | A+ | 5 | "those not serious about Bob will be more likely to be able to enjoy A ratings" |
| excellent | A, A− | 4 | (same — casual fans) |
| very good | B+, B, B− | 3 | "a little more into Bob" |
| average/good | C+, C, C− | 2 | "only serious devotees" |
| poor | D+, D, D− | 1 | below C: "probably only be listened to once by those very seriously into listening to everything by Bob" |
| very poor | F | 0 | (same) |

- Letters map 1:1 onto `RATING_RANK` in `concert_ranker/calibrate.py:27`
  (A+ = 13 … F = 1).
- **Not all entries have letter ratings** — letters were a later refinement;
  older entries may carry only the numeric 0–5 tier.
- Harshness is a direct rating input: versions "too harsh to be listened to at
  higher volumes … get lower ratings as a result".

## 3. Rating stability caveats

The curator's own error bars — treat a single rating as a distribution:

- Ratings "should not be off by more than 1 letter level" between listens, and
  are "affected by enthusiasm for show content or what was just previously
  listened to or mood".
- Re-ratings are **asymmetric**: more likely to move **down**, by at most one
  letter level; upward moves are usually only one **+ sublevel**.
- "Ratings and comparisons should only be considered as guidelines and not fixed
  in stone."

## 4. Comparison methodology (when multiple versions exist)

- Sample: **15–30 seconds from one of Bob's quieter songs, while Bob is
  singing**, compared back-to-back with levels matched. Bob's voice is the
  criterion — "considered most important".
- Declared bias: **warmer / less harsh vocal** wins ("sounds more natural").
  Consequences: binaural mics > cardioid; wider sound capture > narrower.
- Wider capture admits more crowd noise, but crowd annoyance is explicitly
  **not** a comparison criterion — read the talking notes in tandem.
- Remaster stance: level boosts that clip add harshness; raised midrange or
  high-end adds harshness; **clipped vocal peaks are especially bad**. "The
  majority of remasters that fiddle with the tone have been found to add
  harshness and generally are not considered as good as the originals."

## 5. EAC-match convention

"Exact eac match" / "close eac match" in a description means EAC's wav-compare
found the version identical (or offset/few-spot different) to a prior version —
usually tested on **one track only**. The curator's stated assumption: the match
"indicate[s] there is nothing new for the version to offer and review is
stopped", unless the prior version had noted flaws (then the new one is checked
for the same flaws). → strong negative signal for ranking (see §8, TODO-188).

## 6. Notes policy (what absence of a note means)

- **Audience annoyances** (sing-along, talking, background talking): noted only
  when persistent enough that "the listener wanted to tell these people to shut
  up"; brief and resolved incidents are not cited. Policy started late — **older
  entries lack these notes entirely**; absence is not evidence of a quiet crowd.
- **Spectral notes** ("nothing above 16k" etc.): also a later development, made
  only for unusual densities. Older notes misname the TV band a "hiss band"
  (it was not audible hiss) — both spellings occur in descriptions.
- **Accuracy caveats** (curator's own): some older shows listed as masters
  "are probably not"; older shows have taper misattributions ("some recording
  versions have been misreported as another taper"); flaws are sometimes missed,
  entered on the wrong show, or carry track/time typos. "But overall the
  accuracy rate should be high." (Directly relevant to
  `instructions/FABLE_TAPER_ATTRIBUTION.md` — confirmed-tier evidence must
  outrank old info-file claims.)

## 7. Artifact taxonomy (17 terms, 22 reference images)

Images in `data/site/lbjpg/`. "Spectral view" = frequency density over time;
"wav view" = amplitude over time.

| # | Term | View | Signature | Cause | Quality implication |
|---|---|---|---|---|---|
| 1 | DAT (benchmark) | spectral | full spectrum to 22k, clean above 18k | good master | the "nice full warm" reference state — `lb_dat_spectral_view.JPG` |
| 2 | Cassette | spectral | drop-off above 18k; noise (fuzzy grain) above that, vs. clean DAT | analog tape | lower ceiling than DAT — `lb_cassette.JPG` |
| 3 | Lego parapets | spectral | continuous castle-notch ceiling alternating ~16–17k | mini-disc size-reduction stepping its cutoff per increment | "less full or hollow sound" vs. original DAT — `lb_parapet.JPG` |
| 4 | Floating parapets | spectral | scattered rectangular islands at irregular intervals | mp3 / streaming / mini-disc style lossy carving | lossy provenance — `lb_floating_parapet.JPG` |
| 5 | 32k DAT | spectral | perfectly clean wall at 16k, black above, **no** parapets | DAT recorded at 32kHz (2× capacity) | less full than 44.1/48k DAT; most distinctive signature — `lb_dat_at_32k.JPG` |
| 6 | Digital clipping | wav | flat-topped peaks cut off at 0dB | levels too hot at record time, or later digital amplification | harsh/distorted when heavy; **vocal-peak clipping especially bad** — `lb_clipping.JPG` |
| 7 | Limiting | wav | rounded/plateaued peaks (e.g. −6db bottoms / −3db tops asymmetric; or ~−5db both) | recorder hardware or later software avoiding clipping | harsh/distorted when heavy — `lb_limiting.JPG`, `lb_limiting2.JPG` |
| 8 | Brickwalling | wav | diagonal or slightly curved lines filling the **valleys between peaks** (detail loss on wav sides, not just tops) | input beyond what the hardware (usually recorder pre-amp) can pass | harsh/distorted when heavy. Site-specific term — elsewhere "brickwall" means clipping/limiting, here it does **not** — `lb_brickwall.JPG`, `lb_brickwall2.JPG`, `lb_brickwall3.JPG` |
| 9 | Compression (heavy) | wav, full-track zoom | solid rectangle — dynamic range gone | mastering compression | "louder and harsher" — before/after pair `lb_heavily_compressed.JPG`, `lb_heavily_compressed_before.JPG` |
| 10 | Digi-pops | wav | isolated narrow high-amplitude spikes above quiet music | misplaced sample; "usually from a bad cdr rip" | audible pop — `lb_digipops.JPG` |
| 11 | Discontinuity pop | wav | abrupt step-change in signal level (DC jump, not silence) | lost samples in a bad transfer; usually bad cdr rip | audible pop — `lb_discontinuity.JPG` |
| 12 | Square wav static | wav | repeating rectangular/square waveform shapes | DAT playback errors (may vanish on a retry) | transfer defect — `lb_square_wav_static.JPG` |
| 13 | Digital drops | wav | horizontal (silent) line segments, possibly multi-second, mid-track | bad transfer, usually bad cdr rip; analog drops similar but curved/fuzzy | missing audio — `lb_drops.JPG` |
| 14 | Between-track gap | wav | abrupt noise-floor step at a precise timestamp (track boundary) | cdr→cdr copying without sector-boundary correction | seam artifact — `lb_gap.JPG` |
| 15 | Mic hit | wav | spike in **one channel only** (other flat) — distinguishes from digi-pop | mic or cable moved/brushed during recording; sounds like a thump | performance-time defect, not transfer — `lb_mic_hit.JPG` |
| 16 | TV band | spectral | thin horizontal stripe near 15–16k, density pulsing over time | CRT (TV/monitor) interference during an **analog** transfer | inaudible to most people; identification aid; older notes call it "hiss band" — `lb_tv_band.JPG` |
| 17 | High-end streaking | spectral | chaotic vertical noise streaking up to 22k during loud passages; audible extra hiss | DAT transferred through a non-professional soundcard | fixable by re-transfer — clean counterexample `lb_high_end_streaking_done_right.JPG`, defect `lb_high_end_streaking.JPG` |

Spectral notes exist because device signatures identify versions: mini-disc and
some mics thin the high end; wav→mp3→wav round-trips remove upper frequencies;
remastering can remove or boost bands.

## 8. Project addendum — hooks for code (our interpretation, not the curator's)

- **Ranking anchor** (`FABLE_UNIFIED_RANKING.md` §4): §2–§3 justify rating as
  the dominant term with ±1-tier soft error bars, and the asymmetry (down-drift
  more likely) justifies breaking exact ties conservatively rather than
  trusting a + sublevel gap.
- **`txt_eac_match`** (TODO-188): regex `exact eac match|close eac match` on
  `entries.description` per §5 — strong "offers nothing new" negative.
- **Text-mining vocabulary** (TODO-188): the §7 term column is the controlled
  vocabulary of `entries.description`; include the "hiss band" alias (§6) and
  both "parapet" variants.
- **Comparison bias** (§4) explains why AUD-class metric correlations
  (harshness/clipping-adjacent metrics) track ratings best (AUD ρ=0.66,
  TODO-183) — the curator literally rates on vocal harshness.
- **Absence-of-note asymmetry** (§6): never treat missing annoyance/spectral
  notes on pre-~2006 entries as positive evidence.
- **Taper caveat** (§6) → propagation confidence in
  `FABLE_TAPER_ATTRIBUTION.md`: old info-file taper claims are the curator's
  known weak spot.

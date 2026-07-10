# FN label-error curator review (TODO-201)

Rolling review ledger for the census-flagged frozen-set pairs
(`fn_label_census.py`; 264 pairs at current config, was 265 at TODO-201 filing).
Each row is a judgment on whether the frozen-set **positive** label (same
recording) is wrong. Review-only: nothing here edits `regression_set*.json`,
the observations DB, or `config.yaml` — confirmed FLIPs are applied in a
separate, signed-off step (cf. `make_regression_set_v2.py` precedent).

Decisions:

- **FLIP** — label error confirmed: curator/info text explicitly asserts the
  two LBs are different recordings (pair-scoped). Should become a negative.
- **KEEP** — label stands: curator text affirms same recording; the census
  flag is explained (partial/composite coverage, third-LB false hit).
- **UNSURE** — evidence genuinely ambiguous; needs listening or tj.

A recurring census false-hit mode: `_explicit_different_recording` fires on
pair-scoped relation text whose "different recording than LB-X" refers to a
**third** LB while the same sentence *affirms* the pair ("same recording as
…"). Those are KEEP.

## Progress

- 2026-07-09 (Fable), batch 1: overlap tier (both heuristics fired) — 25/25
  reviewed. **17 FLIP / 7 KEEP / 1 UNSURE.**
- 2026-07-09 (Fable), batch 2: explicit-only tier — 103/103 reviewed.
  **66 FLIP / 30 KEEP / 7 UNSURE.**
- Cumulative: 128/264 reviewed — **83 FLIP / 37 KEEP / 8 UNSURE.**
- 2026-07-09: tj approved the 83 batch-1+2 FLIPs. Applied via
  `make_regression_set_v3.py` → `regression_set_v3.json` (positives 1578→1495,
  negatives 1387→1470; v2 untouched per frozen-set rules). UNSURE rows were
  NOT applied. Honest-recall rescoring against v3 deferred — calibration is
  FROZEN for the 7/09–7/12 window (WORK_PACKAGE_2026-07-09.md).
- Remaining: 136 duration-only pairs. These have no curator same/different
  text by construction — they need the partial/incomplete-set judgment
  (durations, setlists, "incomplete" notes), a different review method than
  batches 1–2.

## Batch 1 — overlap tier (explicit + duration), 2026-07-09

| date | pair | decision | rationale |
|---|---|---|---|
| 1987-10-08 | LB-03662 / LB-07350 | FLIP | 7350's text: "different recording than LB-3662 and that is even harsher" — pair-scoped, explicit. |
| 1987-10-08 | LB-06784 / LB-07350 | KEEP | Same text *affirms* "same recording as bootleg LB-6784 based on same crowd and similar clapping wavs at end of t5"; the diff phrase targets third LB-3662. Duration ratio 187× looks like a broken perf-duration measurement, not evidence. |
| 1988-07-11 | LB-10557 / LB-10897 | FLIP | 10897: "Different recording than LB-10557 based on different reactions in the audience between track 3 and 4." |
| 1989-07-25 | LB-00851 / LB-05508 | FLIP | 5508 commentary: "different recording than LB-0851 based on different crowd at end of d1t7". Uploader had noted 851's drop-out flaw absent here, consistent. |
| 1990-01-12 | LB-01776 / LB-02614 | KEEP | 2614's text affirms "same recording as LB-1776 … upgrade over LB-1776"; diff phrase targets third LB-5863. Ratio 0.22 = 1776 is a partial single-disc remaster of a 3-disc set. |
| 1990-01-12 | LB-02614 / LB-05863 | FLIP | "different recording than jtt LB-5863 based on different talking on that one at d1t4 0:3x" — pair-scoped. |
| 1990-11-08 | LB-09060 / LB-13427 | KEEP | 13427's text affirms "same recording as LB-09060, fingerprint: t1 [male] 'come on!' @ 1:00"; diff phrase targets the LTD group. |
| 1990-11-08 | LB-07094 / LB-13427 | FLIP | 13427: "different recording from LTD LB-01219/LB-03730/LB-07094/LB-08251" — partner 7094 named in the different-group. |
| 1991-04-21 | LB-00181 / LB-12883 | KEEP | 12883 commentary: "probably same recording as LB-0181 based on same crowd at end of t1". Curator affirm (hedged "probably"); diff phrase targets third LB-9891. Ratio 134× again suggests bad duration measurement. |
| 1991-04-21 | LB-09891 / LB-12883 | FLIP | "this is different recording than LB-9891 based on different crowd at end of t1". |
| 1991-06-11 | LB-06821 / LB-09186 | KEEP | 9186 is a composite; curator: bootleg-sourced portion "same recording as bootleg LB-6821". Diff phrase targets third LB-4403 (non-CD portion). Ratio 0.82 = the extra non-CD tracks. |
| 1994-04-18 | LB-04268 / LB-09955 | FLIP | 9955's 4-way comparison "on crowd at end of t1 and t2 this is a different recording" vs 2469/4268/6862. |
| 1994-04-18 | LB-06862 / LB-09955 | FLIP | Same 4-way comparison; 6862 among the compared, 9955 declared different. |
| 1994-04-18 | LB-02469 / LB-09955 | FLIP | Same 4-way comparison. |
| 1994-07-04 | LB-01059 / LB-04361 | FLIP | 4361 info text: "This is not the same recording as LB-1059, LB-4033 or LB-4034 which are all from the same DAT recording". (Info-file claim, not curator comparison — but explicit and pair-scoped.) |
| 1994-07-04 | LB-04033 / LB-04361 | FLIP | Same statement names 4033. |
| 1994-07-04 | LB-04034 / LB-04361 | FLIP | Same statement names 4034. |
| 1996-06-17 | LB-06236 / LB-11182 | KEEP | 11182 commentary: "probably same recording as nti ssrc LB-6236 based on same lack of crowd noise and mic hits". Diff phrase targets 4534/4535. Ratio 0.53 = 11182's bonus-disc (Kiel 1994) padding. |
| 1996-06-17 | LB-04534 / LB-11182 | FLIP | "different recording than bach LB-4534 … based on different crowd at end of d1t1". |
| 1996-06-17 | LB-04535 / LB-11182 | FLIP | Same sentence names bootleg LB-4535. |
| 1996-06-29 | LB-04850 / LB-06464 | KEEP | 6464 commentary affirms "same recording as LB-4850 based on same clapping wavs at end of t3 and t9"; diff phrase targets third LB-5064. |
| 1996-06-29 | LB-05064 / LB-06464 | FLIP | "different recording than LB-5064 based on different crowd at end of t3 and t9". |
| 1996-10-26 | LB-10678 / LB-13780 | UNSURE | 13780: "probably same recording as LB-10678 … **but could be just side by side tapers**". Curator himself hedged on exactly the same/different question; audio (corr<0.05) leans different. Needs listening. |
| 2001-07-03 | LB-00056 / LB-00417 | FLIP | LB-56 page: "different recording than cc LB-0417 based on different crowd at end of d1t1". |
| 2001-08-10 | LB-00436 / LB-04870 | FLIP | 4870: "version 'a'; Not the same recording as LB-0436." Ratio 388× also flags broken duration measurement. |

### Batch 1 side-observations

- Three pairs (LB-6784/7350, LB-181/12883, LB-436/4870) show perf-duration
  ratios of 134–388×, physically implausible for real sets — the
  `perf_dur_sec` measurement for one member is likely broken. Worth a look
  before trusting heuristic (b) counts elsewhere.
- If all 17 FLIPs are applied, the corr<0.05 FN population drops 830 → 813
  before touching the 239 single-heuristic pairs.


## Batch 2 — explicit-only tier (heuristic (a) only), 2026-07-09

Method: scripted pre-screen classified each pair by whether the
different-recording phrase window names the pair partner and whether any text
affirms the partner ("same recording as LB-<partner>"); every non-obvious case
(and 5 screen misfires) hand-reviewed with full context windows. 103/103
reviewed: **66 FLIP / 30 KEEP / 7 UNSURE.**

| date | pair | decision | rationale |
|---|---|---|---|
| 1987-07-12 | LB-08486 / LB-12450 | KEEP | 'in comparison to LB-8486, this is same recording based on same clapping wavs at end of t1'; the diff phrase targets third-party 3422 |
| 1987-09-13 | LB-05448 / LB-09301 | KEEP | 'probably same recording as LTB LB-5448'; diff targets LB-6024 |
| 1987-09-13 | LB-06024 / LB-09301 | FLIP | partner named in diff phrase: "…13) > flac 8 bittorrent download 04/11; different recording than LTD LB-6024 based on different crowd at end o…" |
| 1987-09-19 | LB-00131 / LB-05156 | FLIP | partner named in diff phrase: "…Pink Robert bittorrent download 07/07; different recording than cb LB-0131 or LB-4281 based on different crowd…" |
| 1987-09-19 | LB-04281 / LB-05156 | FLIP | partner named in diff phrase: "…Pink Robert bittorrent download 07/07; different recording than cb LB-0131 or LB-4281 based on different crowd…" |
| 1987-09-20 | LB-00152 / LB-05246 | FLIP | 'so it is not the same recording as cb LB-0152' |
| 1987-09-20 | LB-05165 / LB-05246 | KEEP | 'this is same recording as pinkrobert LB-5165 based on same crowd on t1'; diff targets LB-0152 |
| 1987-09-23 | LB-00777 / LB-04318 | FLIP | partner named in diff phrase: "…time : 69:07 bittorrent download 12/06; different recording than LB-0777 and same recording as LB-2307 based o…" |
| 1987-10-05 | LB-00598 / LB-05538 | FLIP | partner named in diff phrase: "…n Taper: LTD bittorrent download 11/07; different recording than cb LB-0598 as the talking and crowd noise do …" |
| 1988-07-11 | LB-00800 / LB-10897 | UNSURE | curator: 'Unclear if this is the same recording as LB-800, since track timings don't match' — explicit uncertainty; audio leans different |
| 1988-07-25 | LB-03152 / LB-08006 | FLIP | partner named in diff phrase: "…ts and also from a different recording; this is a different recording than LB-3152 based on different crowd at…" |
| 1988-08-24 | LB-00806 / LB-09747 | FLIP | partner named in diff phrase: "…e whooshing sound on that one; ths is a different recording than LB-0806 based on different crowd at end of d1…" |
| 1988-08-24 | LB-08042 / LB-09747 | KEEP | 'probably same recording as LB-8042 as had same crowd noise at end of first 4 tracks'; diff targets LB-0806 |
| 1989-05-27 | LB-02468 / LB-12372 | UNSURE | 12372's uploader 'can't decide which LB-# this is' among 2468/7209/8464 — identity itself unresolved |
| 1989-05-27 | LB-07209 / LB-12372 | FLIP | partner named in diff phrase: "…t download 03/10; has noise reduction;, different recording than LTD LB-7209 based on different background tal…" |
| 1989-05-27 | LB-08464 / LB-12372 | UNSURE | same unresolved-identity text; the diff phrase is 8464-vs-7209, not pair-scoped |
| 1989-06-06 | LB-01256 / LB-07236 | FLIP | partner named in diff phrase: "…d1t2; in comparison that has more hiss; different recording than LB-1256 based on different crowd at end of d1…" |
| 1989-06-06 | LB-04623 / LB-07236 | KEEP | 'same recording as LB-4623 based on same clapping wavs at end of d1t2'; diff targets LB-1256 |
| 1989-06-07 | LB-00654 / LB-07917 | KEEP | 'probably same recording as LB-0654 and LTD LB-7250'; diff targets bootleg LB-6803 |
| 1989-06-07 | LB-06803 / LB-07917 | FLIP | partner named in diff phrase: "…e crowd and clapping at end of d1t5 and different recording than bootleg LB-6803 based on different crowd; LTD…" |
| 1989-06-07 | LB-07250 / LB-07917 | KEEP | same 4-way text affirms LB-7250 |
| 1989-06-10 | LB-01311 / LB-06591 | FLIP | partner named in diff phrase: "…g in any way bittorrent download 10/08; different recording than LB-1311 based on different crowd at end of t1…" |
| 1989-06-11 | LB-02120 / LB-07239 | FLIP | partner named in diff phrase: "…parison this has a fuller warmer sound; different recording than LB-2120 based on different crowd at beginning…" |
| 1989-06-11 | LB-02155 / LB-07239 | KEEP | 'same recording as LB-2155 based on same clapping wavs at end of d1t9'; diff targets LB-2120 |
| 1989-06-13 | LB-06551 / LB-07248 | FLIP | partner named in diff phrase: "…ing at beginning of d1t6 which makes it different recording than LTJ LB-6551 which has different talking; in c…" |
| 1989-06-13 | LB-07146 / LB-07248 | KEEP | 'same recording as sb LB-7146 based on same background talking at beginning of d1t6'; diff targets LB-6551 |
| 1989-06-17 | LB-01307 / LB-07252 | KEEP | 'same recording as hg LB-1307 and LB-1652 … with hg LB-1307 inverted'; diff targets LB-2124 |
| 1989-06-17 | LB-01652 / LB-07252 | KEEP | same text affirms LB-1652 |
| 1989-06-17 | LB-02124 / LB-07252 | FLIP | partner named in diff phrase: "…parison this has a fuller warmer sound; different recording than LB-2124 based on different cowd at end of d2t…" |
| 1989-06-19 | LB-01590 / LB-07254 | KEEP | 'same recording as hg LB-1590 and LB-2130 based on same clapping wavs at end of d2t4'; diff targets LB-6603 |
| 1989-06-19 | LB-02130 / LB-07254 | KEEP | same text affirms LB-2130 |
| 1989-06-19 | LB-06603 / LB-07254 | FLIP | partner named in diff phrase: "…parison this has a warmer fuller sound; different recording than LTJ LB-6603 based on different clapping wavs …" |
| 1989-07-01 | LB-01417 / LB-09806 | KEEP | 'same recording as LB-1417 and LB-2151 based on same clapping wavs at end of d1t4'; diff targets LB-7039 |
| 1989-07-01 | LB-02151 / LB-09806 | KEEP | same text affirms LB-2151 ('this has channels of LB-2151') |
| 1989-07-01 | LB-07039 / LB-09806 | FLIP | partner named in diff phrase: "…s most hiss, then this , then LB-1417 ; different recording than LB-7039 based on different crowd at end of d1…" |
| 1989-07-13 | LB-09904 / LB-10558 | FLIP | partner named in diff phrase: "…ac 5 > y'all bittorrent download 12/12; different recording than LB-9904 based on different crowd on d2t1; in …" |
| 1989-07-15 | LB-06806 / LB-14941 | KEEP | 'same recording as bootleg LB-6806 … with wavs inverted'; diff targets LB-7111 |
| 1989-07-15 | LB-07111 / LB-14941 | FLIP | partner named in diff phrase: "…and t7 this has a fuller warmer sound; this is a different recording than LB-7111 based on different crowd at …" |
| 1989-07-25 | LB-02223 / LB-05508 | KEEP | 'same recording as LB-2223 based on same crowd at end of d1t7'; diff targets LB-0851 (that pair flipped in batch 1) |
| 1989-08-22 | LB-00313 / LB-12513 | KEEP | 'probably same recording as LB-0313/LB-9842/LB-9954 LTC' with fingerprint; diff targets LB-5082 |
| 1989-08-22 | LB-05082 / LB-12513 | FLIP | partner named in diff phrase: "…00 (LTA) >, Transfer 8-Feb-2017 by LTA, different recording from LB-5082 (RD), probably same recording as LB-0…" |
| 1989-08-22 | LB-09842 / LB-12513 | KEEP | same text affirms LB-9842 |
| 1989-08-22 | LB-09954 / LB-12513 | KEEP | same text affirms LB-9954 |
| 1989-10-22 | LB-00507 / LB-04338 | UNSURE | only 'possibly same recording as LB-0507 based on similar crowd' — weaker hedge than 'probably'; audio leans different |
| 1989-10-22 | LB-02511 / LB-04338 | FLIP | partner named in diff phrase: "…d at end of d1t1; that is more muffled; different recording than LB-2511 based on different crowd at end of d1…" |
| 1990-01-14 | LB-00127 / LB-10600 | FLIP | 10600 is 'Alternative recording to LB-127/LB-7155/LB-10097 which all derive from the same recording' |
| 1990-01-14 | LB-07155 / LB-10600 | FLIP | same 'Alternative recording to' statement names LB-7155 |
| 1990-01-14 | LB-10097 / LB-10600 | FLIP | partner named in diff phrase: "…o available. bittorrent download 01/13; different recording than LB-10097 based on different crowd at end of d…" |
| 1990-02-01 | LB-01335 / LB-08523 | FLIP | 'different recording than hg LB-1335 and sony LB-3229'; the nearby same-recording text is an xref about LB-1335's own HG flac clone, not this pair |
| 1990-02-01 | LB-03229 / LB-08523 | FLIP | partner named in diff phrase: "…11 ; this has a lot less digital flaws; different recording than hg LB-1335 and sony LB-3229 based on differen…" |
| 1990-02-06 | LB-01848 / LB-05372 | FLIP | partner named in diff phrase: "…sound on d1t1 and clipping continues.; different recording than HG LB-1848 based on different crowd at end of …" |
| 1990-06-13 | LB-07153 / LB-15495 | FLIP | partner named in diff phrase: "…ive bittorrent download 05/22; probably different recording than LB-7153 based on different crowd at end of t1…" (curator hedged 'probably different'; audio agrees) |
| 1990-10-11 | LB-00166 / LB-04856 | FLIP | partner named in diff phrase: "…n LARS; looks like has noise reduction; different recording than LB-0166 and LB-0880 based on different crowd …" |
| 1990-10-11 | LB-00166 / LB-09963 | FLIP | partner named in diff phrase: "…B-0166. Does not have the cut in LARS;; different recording than LB-166 and LB-880 based on different crowd at…" |
| 1990-10-11 | LB-00880 / LB-04856 | FLIP | partner named in diff phrase: "…n LARS; looks like has noise reduction; different recording than LB-0166 and LB-0880 based on different crowd …" |
| 1990-10-11 | LB-00880 / LB-09963 | FLIP | partner named in diff phrase: "…B-0166. Does not have the cut in LARS;; different recording than LB-166 and LB-880 based on different crowd at…" |
| 1990-11-08 | LB-01219 / LB-13427 | FLIP | partner named in diff phrase: "…ffp, md5 >, qBitorrent 4.0.4 (64-bit), different recording from LTD LB-01219/LB-03730/LB-07094/LB-08251 LTD;, …" |
| 1990-11-08 | LB-03730 / LB-13427 | FLIP | partner named in diff phrase: "…ffp, md5 >, qBitorrent 4.0.4 (64-bit), different recording from LTD LB-01219/LB-03730/LB-07094/LB-08251 LTD;, …" |
| 1990-11-08 | LB-08251 / LB-13427 | FLIP | partner named in diff phrase: "…ffp, md5 >, qBitorrent 4.0.4 (64-bit), different recording from LTD LB-01219/LB-03730/LB-07094/LB-08251 LTD;, …" |
| 1991-05-11 | LB-04048 / LB-12267 | FLIP | partner named in diff phrase: "…g as LB-8833 bittorrent download 05/16; different recording than LB-4048 based on different crowd at end of d1…" |
| 1991-05-11 | LB-04048 / LB-12484 | FLIP | transitive: 12484 'seems to be same recording as LB-12267', and 12267 is 'different recording than LB-4048' (both curator claims) |
| 1991-05-11 | LB-08833 / LB-12267 | KEEP | 'Probably same recording as LB-8833'; diff targets LB-4048 |
| 1991-05-11 | LB-08833 / LB-12484 | FLIP | partner named in diff phrase: "…michi DRAGON >TASCAM DR-05>Amadeus Pro, different recording from LB-8833 and LB-12392, voiceprints:, t11 verse…" |
| 1991-05-11 | LB-12392 / LB-12484 | FLIP | partner named in diff phrase: "…michi DRAGON >TASCAM DR-05>Amadeus Pro, different recording from LB-8833 and LB-12392, voiceprints:, t11 verse…" |
| 1991-06-11 | LB-04403 / LB-09186 | FLIP | partner named in diff phrase: "…than that; on the non bootleg portion, this is a different recording than LTD LB-4403 based on different crowd…" |
| 1991-06-11 | LB-12342 / LB-12968 | KEEP | 'same recording as LB-12342 based on same clapping wavs at end of d1t9'; diff targets LB-4403 |
| 1991-11-04 | LB-00854 / LB-12565 | FLIP | partner named in diff phrase: "…rding. I've got [LB-854 xref-1337], and this is a different recording from that one, at least, based track 03 …" |
| 1991-11-16 | LB-03800 / LB-10664 | FLIP | partner named in diff phrase: "…January 2013 bittorrent download 01/13; different recording than LB-3800 based on different crowd at end of d1…" |
| 1991-11-16 | LB-07165 / LB-10664 | KEEP | census false hit — diff phrase targets LB-3800; no pair-scoped claim either way (only a sound-ranking mention of LB-7165) |
| 1991-11-16 | LB-08915 / LB-10664 | UNSURE | 'may be same recording as LB-8915 … but hard to tell because of quality of these' — explicit curator uncertainty |
| 1992-04-14 | LB-00823 / LB-11956 | UNSURE | 11956 is composite ('spectral change at d1t4 2:28 as if different sources'): both 'different recording than LB-0823' (d1t1) and 'same recording as LB-0823' (d1t8) are asserted |
| 1992-04-14 | LB-01568 / LB-11956 | FLIP | partner named in diff phrase: "…8 as if different sources used; this is different recording than LB-0823 and LB-1568 based on different crowd …" |
| 1992-04-15 | LB-01567 / LB-11957 | FLIP | 'different recording than LB-1567 and LB-5211 based on different crowd at end of d1t9' |
| 1992-04-15 | LB-05211 / LB-11957 | FLIP | same sentence names LB-5211 |
| 1992-06-30 | LB-00763 / LB-00764 | FLIP | partner named in diff phrase: "…ound; downloaded from a.b.m.s.d. 11/02; different recording than LB-0763 based on different clapping at end of…" |
| 1992-11-13 | LB-09098 / LB-12890 | KEEP | 'same recording as LB-9098 … with channels swapped'; diff targets LB-12847 |
| 1992-11-13 | LB-12847 / LB-12890 | FLIP | partner named in diff phrase: "…mile bittorrent download 08/17; this is different recording than LB-12847 based on different crowd at end of t…" |
| 1993-06-27 | LB-04963 / LB-10590 | FLIP | partner named in diff phrase: "…nothing above 16k except lego parapets; different recording than ltj LB-4883 and LB-4963 based on di…" |
| 1993-06-30 | LB-00913 / LB-05878 | FLIP | 'different recording than LB-0913' headline; same-source only for the patch tracks 913 borrowed (d2t6/d2t7) — main bodies differ |
| 1993-10-02 | LB-05820 / LB-09943 | FLIP | partner named in diff phrase: "…o LB entries bittorrent download 03/12; different recording than NTA LB-5820 based on different crowd at end o…" |
| 1993-10-09 | LB-03610 / LB-04996 | FLIP | 'Not the same recording as LB-3610' + curator 'different recording than LB-3610 based on different crowd at begin of d1t6' |
| 1994-07-04 | LB-01059 / LB-07615 | FLIP | partner named in diff phrase: "…circulated analog source of this show, different recording than LB-1059., Received this one in trade from the …" |
| 1994-11-08 | LB-00960 / LB-13158 | FLIP | partner named in diff phrase: "…, ffp, md5 > qBitorrent 4.0.3 (64-bit), different recording than LB-00960/LB-04293, and LB-12762, bittorrent d…" |
| 1994-11-08 | LB-04293 / LB-13158 | FLIP | partner named in diff phrase: "…, ffp, md5 > qBitorrent 4.0.3 (64-bit), different recording than LB-00960/LB-04293, and LB-12762, bittorrent d…" |
| 1994-11-08 | LB-09298 / LB-13158 | KEEP | 'same recording as LB-9298 based on same clapping wavs at end of t2'; diff targets 960/4293/12762 |
| 1994-11-08 | LB-12762 / LB-13158 | FLIP | partner named in diff phrase: "…, ffp, md5 > qBitorrent 4.0.3 (64-bit), different recording than LB-00960/LB-04293, and LB-12762, bittorrent d…" |
| 1994-11-09 | LB-03296 / LB-04864 | FLIP | 'Not the same recording as LB-3296, based on crowd during d2t05' + curator confirms different crowd at end of d1t2 |
| 1995-03-12 | LB-01017 / LB-07261 | FLIP | partner named in diff phrase: "…lower levels that do not clip as much; different recording than LB-1017 and LB-1923 based on different crowd a…" |
| 1995-03-15 | LB-00791 / LB-02939 | KEEP | 'same recording as LB-0791 based on same wav asymetric wav view on d1t1'; diff targets bootleg 'Down in the Flood' |
| 1995-03-15 | LB-01432 / LB-02939 | UNSURE | only a sound-quality comparison vs 'schubert remaster LB-1432'; no pair-scoped same/diff claim (diff targets the DITF bootleg; unclear whether 1432 remasters that bootleg) |
| 1996-04-30 | LB-03444 / LB-08045 | FLIP | partner named in diff phrase: "…f d1t1; this has a fuller warmer sound; different recording than LB-3444 and that has a fuller warmer sound an…" |
| 1996-05-16 | LB-07544 / LB-07545 | FLIP | partner named in diff phrase: "…sound than that one and has less flaws; different recording than NTG LB-7545 based on different crowd at end o…" |
| 1996-06-19 | LB-01520 / LB-07004 | KEEP | 'same recording as LB-1520 based on same clapping wavs at end of d2t1'; diff targets LB-6237 |
| 1996-06-22 | LB-03144 / LB-03601 | FLIP | partner named in diff phrase: "…me > ....... bittorrent download 03/06; different recording than LB-3144 which has a nicer warmer fuller sound…" |
| 1996-07-03 | LB-01396 / LB-05887 | FLIP | partner named in diff phrase: "…g in any way bittorrent download 02/08; different recording than LB-1396 based on different crowd at end of d1…" |
| 1996-11-17 | LB-03505 / LB-14042 | FLIP | partner named in diff phrase: "…t: t8 [male] 'He's tremendous!' @ 6:42, different recording than LB-03505, same recording as Pdub LB-07121/LB-…" |
| 1996-11-17 | LB-07121 / LB-14042 | KEEP | 'same recording as Pdub LB-07121/LB-13036'; diff targets LB-03505 |
| 1996-11-17 | LB-13036 / LB-14042 | KEEP | same text affirms LB-13036 |
| 1997-02-14 | LB-04461 / LB-07636 | FLIP | partner named in diff phrase: "…ne 13, 2009) bittorrent download 06/09; different recording than LB-4461 based on different crowd at end of d1…" |
| 1998-06-24 | LB-04794 / LB-06615 | FLIP | partner named in diff phrase: "…r Boundaries bittorrent download 10/08; different recording than sennheiser LB-4794 based on different crowd a…" |
| 2001-05-01 | LB-00993 / LB-04342 | FLIP | partner named in diff phrase: "…nt download 12/06; excellent sound [A]; different recording than LB-0993 based on different background talking…" |
| 2001-05-01 | LB-04222 / LB-04342 | KEEP | 'probably same recording as bootleg LB-4222 based on same crowd at beginning of d1t7'; diff targets LB-0993 |
| 2001-10-30 | LB-07888 / LB-08413 | FLIP | partner named in diff phrase: "…ent: unknown bittorrent download 03/10; different recording than LB-7888 based on different crowd at end of d1…" |

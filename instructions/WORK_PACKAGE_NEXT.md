# WORK_PACKAGE_NEXT — queue for the windows after 7/12

Agreed plan (Fable 5 + tj, 2026-07-11). Successor to `WORK_PACKAGE_2026-07-09.md`
(retire that one to `complete/` when the 7/12 window closes; retire this one the
same way when its windows land). Strike rows as they land.

---

## Standing preempt (any window)

**TODO-213 (High) — badge data curation.** The ranking/badge surface shipped 07-09
is live but untrusted ("pipeline works, badge DATA needs curation"). The moment tj
supplies wrong-badge examples, tracing their `evidence_json` preempts everything
below.

## Next window — LISTENING

Spec: `instructions/FABLE_LISTENING_INSIGHT_IDEAS.md` (§1 pairs sync + §9 tonight
card already shipped 07-10).

| Slot | Work | Notes |
|---|---|---|
| 1 | **LISTENING §3 — song-centric index** | Key update to the spec (written 07-06, pre-Olof): use `olof_songs` as the spine, NOT setlist.fm + free-text parsing — 61,708 normalized per-performance rows, 97.8% concert coverage, take statuses + positions. Remaining work: song-canonicalisation table (curator-editable, not code constants), `song_performances` derived table, join to `show_picks`/`abs_grade`, song browser screen. The canonicalisation work directly feeds TODO-225 (setlist fingerprinting) — consider landing both in one stream. |
| 2 | **LISTENING §2 — aligned A/B listening** | Start with a scoping pass: inspect one `data/tapematch/runs/<RUN_ID>/` archive for per-pair offset artifacts (`align.py` is the writer). v1 restricts to cleanly-aligned pairs (no staircase). Backend clip service (`POST /api/ab_clip`) + A/B player widget. |
| 3 | **TODO-215 — TapeMatch screen v2** | Corrections, run management, LB deep-links; natural home for the §2 A/B player and the dup-encodes GUI (TODO-210 rider). Pairs well with slot 2. |

Session hygiene unchanged: GUI slots end `/gui-next-i18n` + `/gui-check`; every
code session ends `/session-close`.

## Window after that

~~Originally earmarked for pipeline async-GUI (Phase 7)~~ — **already shipped
07-09** (CHANGELOG: "pipeline structural tier COMPLETE"); a stale memory had it
listed as open. Slot is unassigned. Candidates, no commitment yet: TAPER phase 3
fingerprints (TODO-214), Olof PDF chronicles (TODO-228), BobTalk search
(TODO-226A), LISTENING §4–§8, or the deferred SHARING / TRADING / CONCERT_RANKER
scoring specs.

## Carried context

- Crawl keeps churning zero-token; check `crawl_status.sh` at session open.
- Escalated analysis backlog (329, of which 210 merge-judgment) remains a
  recognized token sink — schedule deliberately or not at all.
- TODO-201 remainder (136 duration-only pairs) needs a partial/incomplete-set
  judgment method; rescore vs `regression_set_v3.json` stays behind the
  calibration freeze.

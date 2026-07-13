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

Spec: `instructions/complete/FABLE_LISTENING_INSIGHT_IDEAS.md` (retired to
complete/ 07-11; §1 pairs sync + §9 tonight card shipped 07-10 — §2/§3 below are
the live remainder).

| Slot | Work | Notes |
|---|---|---|
| 1 | ~~**TODO-215 — TapeMatch screen v2**~~ **DONE 2026-07-11 (TODO-215 closed)** — all 3 parts: (1) curator match feedback (POST /api/tapematch/pairs/judgment + JudgmentPanel), (2) crawl start/stop endpoints + buttons (crawl_start.sh/crawl_stop.sh wrappers, script stays single-instance authority), (3) LB deep-links (LbLinkButton → `/library?lb=`, one-shot consumption in ScreenLibrary + drag-resizable DetailPanel). 10 endpoint tests added. §2 A/B player + dup-encodes GUI riders move to slot 3's stream. |
| 2 | ~~**LISTENING §3 — song-centric index**~~ **DONE 2026-07-11 (TODO-230 opened+closed)** — olof_songs spine as planned: `song_canonical` (curator-sticky seeding) + `song_performances` (61,707 rows / 1,298 songs / 3,994 events), `backend/song_index.py` + CLI + 4th recompute-chain step, `GET /api/songs` + `/api/songs/performances` + curator `POST /api/songs/alias`, ScreenSongs at `/songs` (search rail, best-first sort, LB deep-links, curator rename). 13 tests. Canonicalisation table now exists for TODO-225 (still open). |
| 3 | ~~**LISTENING §2 — aligned A/B listening**~~ **DONE 2026-07-12 (TODO-231 closed)** — backend part 1/2 (2026-07-11): `backend/ab_clips.py` + POST `/api/ab_clip` + GET `/api/ab_clip/<name>` + `ab_eligible` pairs enrichment; 24 tests; real-audio smoke PASS (LB-5953/6162 1995-07-08, incl. track-boundary concat). GUI part 2/2 (2026-07-12): AbPlayerPanel next to JudgmentPanel in ScreenTapeMatch — position/duration inputs, `POST /api/ab_clip` load, two hidden `<audio>` elements started together with an instant (un)mute A/B toggle, inert when `!ab_eligible`. Same-session fix: `ab_eligible` enrichment was checking the stale synced `tapematch_pairs` run_id instead of each pair's actual latest common tapematch run (`get_pair_source_info`) — could read `false` for a pair `POST /api/ab_clip` would accept; now both routes share the same resolution. dup-encodes GUI rider was already live from TODO-210, not part of this slot. |

Session hygiene unchanged: GUI slots end `/gui-next-i18n` + `/gui-check`; every
code session ends `/session-close`.

## Window after that

~~Originally earmarked for pipeline async-GUI (Phase 7)~~ — **already shipped
07-09** (CHANGELOG: "pipeline structural tier COMPLETE"); a stale memory had it
listed as open. Slot is unassigned. Candidates, no commitment yet: TAPER phase 3
fingerprints (TODO-214), Olof PDF chronicles (TODO-228), BobTalk search
(TODO-226A), LISTENING §4–§8, or the deferred SHARING / TRADING / CONCERT_RANKER
scoring specs.

## RESUME POINT (2026-07-11, session stopped at usage-window edge)

State when the session stopped:

1. **Committed** (3 commits on main, not pushed): `7b5f5a74` TODO-215 complete
   (all 3 parts + pipeline severity/rename/queue fixes), `a8b565f9` docs
   (07-09 package retired to `complete/`), `74507645` geocoder test un-rot
   (52/52; failures were stale tests from TODO-220/224, backend untouched).
2. **Uncommitted, verified, ready to commit**: TODO-230 song index (backend +
   ScreenSongs + 5 locales + CHANGELOG/PROJECT/ledger done, TODO-230 already
   closed) and TODO-231 part 1/2 backend (ab_clips.py + routes + 24 tests +
   CHANGELOG entry done; TODO-231 still open). All targeted test files pass
   (song_index 13, ab_clips 24, tapematch_routes 23, geocoder 52); `/gui-check`
   PASS; i18n synced. Suggested: one commit `feat(backend+gui): TODO-230 +
   TODO-231 part 1` (they share backend/app.py hunks), then restart backend.
3. **Next session, in order**: (a) commit item 2; (b) TODO-231 part 2 — A/B
   player widget in ScreenTapeMatch + dup-encodes GUI rider + i18n/gui-check +
   todo-close 231 + strike slot 3 above; (c) `/session-close`; (d) retire this
   file to `complete/` — that's WORK_PACKAGE_NEXT's "Next window" at 100%.
4. **Known flake, pre-existing, NOT from this session**: full `pytest` suite
   intermittently SIGABRTs (native Qt, core dump) in
   `tests/test_lb_master.py::TestSearchTabStatusColumn::test_status_combobox_exists`;
   a clean run earlier today showed 621 passed. Worth a BUGS.md entry if it
   recurs; isolate with a solo run of that file.
5. **Question for tj**: untracked `adhoc_*.{py,json,md,html,pdf,log}` +
   `build_adhoc_pdf.py` at repo root (from the 1997-11-11 adhoc quality
   investigation, findings already captured in CALIBRATION_PROGRESS.md) —
   keep, move under tools/, or delete?
6. Backend on :5174 was restarted this session and serves the song routes;
   it does NOT yet have the ab_clips routes (restart after committing).

## Carried context

- Crawl keeps churning zero-token; check `crawl_status.sh` at session open.
- Escalated analysis backlog (329, of which 210 merge-judgment) remains a
  recognized token sink — schedule deliberately or not at all.
- TODO-201 remainder (136 duration-only pairs) needs a partial/incomplete-set
  judgment method; rescore vs `regression_set_v3.json` stays behind the
  calibration freeze.

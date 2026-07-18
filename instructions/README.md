# instructions/ — index

Active specs and plans live directly in `instructions/`. When a spec's last open
item is shipped or handed off to a TODO, `git mv` it into `instructions/complete/`
and update this index (drop its row from the table below).

`instructions/complete/` holds retired specs/plans — see that folder directly for
its contents; they are not listed individually here. `instructions/future/` holds
specs deliberately parked for a later window (currently SHARING_FEATURE.md).

| Name | Purpose | Status |
|---|---|---|
| complete/CC_CONCERT_RANKER.md | Handoff spec: audio quality ranking (`concert_ranker/` package) | closed 2026-07-15 — all 7 tasks + calibration shipped (TODO-183); leftovers signed off won't-do |
| FABLE_IDEAS.md | Raw idea dump from a Fable 5 brainstorm (2026-07-06) — not a spec, ideas need expansion before execution | triaged 2026-07-17 — dossier/activity-center/CI spec'd out, Repair Shop cancelled, arrangement explorer deferred indefinitely; remaining un-spec'd ideas statused in-file |
| FABLE_PLATFORM_ROADMAP.md | Platform leverage plan from 2026-07-15 brainstorm: private LB import (§1→TODO-245), xref audit (§2→TODO-246), gaps view, shadow-pile triage, preservation stack, lineage; §7 annex numbering parked | active — §2 (TODO-246) closed 2026-07-16; §1 (TODO-245) open |
| complete/FABLE_XREF_INCORPORATION.md | Xref incorporation handoff spec (TODO-246 steps 2+3): copy-level fileset ids end to end | closed 2026-07-16 — B1–B7 shipped across 8 commits; B8 promoted same day by tj D-2 decision to a reviewed import path → TODO-252 |
| FABLE_CI_FIXTURE.md | Handoff spec (sonnet): CI on GitHub Actions + synthetic fixture-DB generator — push-triggered tests/smoke/gui-check | written 2026-07-17, not started — bites B1–B6, TODO id allocated at first implementation session |
| FABLE_ACTIVITY_CENTER.md | Handoff spec (sonnet): unified activity center (FABLE_IDEAS UI §4) — status-bar job tray over a normalized `/api/activity/jobs` aggregator + SSE tee registry | written 2026-07-17, not started — bites B1–B4, TODO id allocated at first implementation session |
| FABLE_COMMAND_PALETTE.md | Handoff spec (sonnet): Ctrl+K command palette (FABLE_IDEAS UI §1) — shared nav registry, fuzzy commands, LB/entry jumps, `registerCommands` extension contract for future specs | written 2026-07-17, not started — bites B1–B5, TODO id allocated at first implementation session |
| complete/FABLE_GAPS_VIEW.md | Handoff spec (sonnet): gaps view / living Kokay list (PLATFORM_ROADMAP §3) — olof concert dates vs entries coverage grid, per-date drill-down with §6 tab room | closed 2026-07-17 — B1–B4 all landed (TODO-256); §4/§6 hooks still open |
| complete/FABLE_SHOW_DOSSIER.md | Handoff spec: show dossier / liner-notes export (FABLE_IDEAS §5, ⭐ tj priority) — date → self-contained HTML/PDF page | closed 2026-07-17 (TODO-257) — B1/B2/B3/B5 shipped same day as written |
| FABLE_PRESERVATION_STACK.md | Handoff spec (sonnet): preservation stack (PLATFORM_ROADMAP §5) — mirror self-verification, sealed BagIt-style snapshots, restore/link test; friends-only, zero upload paths | written 2026-07-17, not started — bites B1–B4, TODO id allocated at first implementation session |
| FABLE_TAPEMATCH_LISTENING_SIGNALS.md | TapeMatch "simulated listening" signals idea spec pack | active 2026-07-17 — §1 sonnet handoff prompt drafted in-spec (§1 HANDOFF), not yet launched; §2–§5 follow per in-spec order |
| complete/FABLE_TAPER_ATTRIBUTION.md | Taper Attribution Engine design spec | closed 2026-07-15 — phases 1–2 shipped 2026-07-09; phase 3 fingerprints (TODO-214) built + calibrated but gated OFF (`taper_fingerprints.LAYER2_ENABLED=False`, precision verdict); revisit options in WORK_PACKAGE_2026-07-14.md Session 6 |
| complete/FABLE_VISUAL_VERIFICATION.md | Electron visual-verification driver (attempt 3) — drive the real app, resize, scale, watch progress; Wayland/NVIDIA-proof capture | closed 2026-07-15 (TODO-247) — bites 1/2/3a/4 shipped (`/verify --electron`), criteria 1/2/3/5/6 met; bite 3b progress fixture won't-do by tj sign-off ("not enough animation to matter"), criterion 4 withdrawn. The `watch` action itself works — only the synthetic fixture was dropped |
| SPEC_INTEGRATION_NOTES.md | Cross-review / integration notes for the four Fable spec-pack docs | active — see SPEC_INTEGRATION_NOTES.md §2 for order, not yet implemented |
| complete/STRUCTURE_REVIEW.md | Structural & consistency review of backend + gui_next (2026-07-04) | closed 2026-07-15 — all 20 items cleared across 4 commits; PROJECT.md P1 regeneration = TODO-244 (done, incl. tools/check_project_refs.py drift checker); sole survivor item 15 → TODO-243 (open) |
| TAPEMATCH_CALIBRATION_GUIDE.md | Quick guide to TapeMatch calibration rules (never trade precision for recall) | not triaged |

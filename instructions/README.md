# instructions/ — index

Active specs and plans live directly in `instructions/`. When a spec's last open
item is shipped or handed off to a TODO, `git mv` it into `instructions/complete/`
and update this index (drop its row from the table below).

`instructions/complete/` holds retired specs/plans — see that folder directly for
its contents; they are not listed individually here.

| Name | Purpose | Status |
|---|---|---|
| CC_CONCERT_RANKER.md | Handoff spec for Claude Code: audio quality ranking — scoring brain already built, DB integration/mining/staging/calibration work remains | not triaged |
| CC_TRADING_PLAN.md | Collection Trading feature — export/import/diff/generate a trading list with friends | not triaged |
| concert ranker v1.zip | Source package (`concert_ranker/` code) attached to CC_CONCERT_RANKER.md | not triaged |
| design_handoff_unified_library/ | Design handoff docs for the unified Library screen (overview + theme additions) | not triaged |
| FABLE_IDEAS.md | Raw idea dump from a Fable 5 brainstorm (2026-07-06) — not a spec, ideas need expansion before execution | not triaged |
| FABLE_LISTENING_INSIGHT_IDEAS.md | Listening & Insight features idea spec pack | active — see SPEC_INTEGRATION_NOTES.md §2 for order, not yet implemented |
| FABLE_ONBOARDING_SYNC.md | New-user onboarding & data sync design spec | active — see SPEC_INTEGRATION_NOTES.md §2 for order, not yet implemented |
| FABLE_TAPEMATCH_LISTENING_SIGNALS.md | TapeMatch "simulated listening" signals idea spec pack | active — see SPEC_INTEGRATION_NOTES.md §2 for order, not yet implemented |
| FABLE_TAPER_ATTRIBUTION.md | Taper Attribution Engine design spec | active — phase 1 shipped 2026-07-09 (engine/schema/recompute, 7,817 attributions); phase 2 (confirm/reject API + GUI) open |
| library/ | Standalone HTML pixel specs for the unified Library screen | not triaged |
| SHARING_FEATURE.md | Plan to share an audio folder with a friend over the internet via Cloudflare Tunnel | not triaged |
| SPEC_INTEGRATION_NOTES.md | Cross-review / integration notes for the four Fable spec-pack docs | active — see SPEC_INTEGRATION_NOTES.md §2 for order, not yet implemented |
| STRUCTURE_REVIEW.md | Structural & consistency review of backend + gui_next (2026-07-04) | not triaged |
| TAPEMATCH_CALIBRATION_GUIDE.md | Quick guide to TapeMatch calibration rules (never trade precision for recall) | not triaged |
| WORK_PACKAGE_2026-07-09.md | Agreed work package for the 7/09–7/12 usage window — timeline, locked decisions, deferred list | active |

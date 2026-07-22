# LosslessBob Wiki

Agent-maintained wiki for the LosslessBob project — a checksum lookup & collection
management app for the Bob Dylan lossless archive. Pages are regenerated
section-by-section by the `/wiki-update` command; **PROJECT.md remains the
authoritative source**, this wiki is the readable overview layer on top.

| Page | Covers | Status | Last updated |
|---|---|---|---|
| [Architecture](Architecture.md) | Tech stack, repo layout, how the pieces connect | fresh | 2026-07-22 |
| [Database](Database.md) | SQLite schema, MASTER vs USER tables, integrity system | fresh | 2026-07-22 |
| [Backend-API](Backend-API.md) | Flask API (port 5174), route groups, backend modules | fresh | 2026-07-22 |
| [GUI](GUI.md) | gui_next (Electron/React, sole GUI; legacy PyQt6 removed) | seeded | 2026-07-16 |
| [TapeMatch](TapeMatch.md) | Recording-family matching pipeline, calibration workflow | fresh | 2026-07-22 |
| [Concert-Ranker](Concert-Ranker.md) | Quality scans, recording scores, ranking pipeline | fresh | 2026-07-22 |
| [Data-Flows](Data-Flows.md) | Key end-to-end flows, checksum format, publish/subscribe | fresh | 2026-07-22 |
| [Dev-Workflow](Dev-Workflow.md) | Sessions, bookkeeping, skills/commands, verification rules | fresh | 2026-07-22 |
| [Visual-Verification](Visual-Verification.md) | Screenshot engine: electron_driver two modes, tour file, /verify workflow | fresh | 2026-07-22 |
| [Taper-Attribution-Flow](Taper-Attribution-Flow.md) | Taper attribution pipeline: Layer 0/1/2, conflict queue, filtering | seeded | 2026-07-15 |
| [Setlist-Sources](Setlist-Sources.md) | Olof/bobserve/setlist.fm corpora, song spine, fingerprinting, gaps view | seeded | 2026-07-22 |
| [Show-Dossier](Show-Dossier.md) | Dossier assembly, HTML/BBcode exports, channels, ambiguity handling | seeded | 2026-07-22 |

**Statuses:** `seeded` = initial pass from existing docs, may lack depth ·
`fresh` = regenerated from source by `/wiki-update` · `stale` = sources changed since last update.

To refresh: run `/wiki-update` (one page per invocation, stalest first) or
`/wiki-update <Page>` for a specific page.

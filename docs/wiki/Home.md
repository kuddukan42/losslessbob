# LosslessBob Wiki

Agent-maintained wiki for the LosslessBob project — a checksum lookup & collection
management app for the Bob Dylan lossless archive. Pages are regenerated
section-by-section by the `/wiki-update` command; **PROJECT.md remains the
authoritative source**, this wiki is the readable overview layer on top.

| Page | Covers | Status | Last updated |
|---|---|---|---|
| [Architecture](Architecture.md) | Tech stack, repo layout, how the pieces connect | seeded | 2026-07-06 |
| [Database](Database.md) | SQLite schema, MASTER vs USER tables, integrity system | seeded | 2026-07-06 |
| [Backend-API](Backend-API.md) | Flask API (port 5174), route groups, backend modules | seeded | 2026-07-06 |
| [GUI](GUI.md) | gui_next (Electron/React, sole GUI; legacy PyQt6 removed) | seeded | 2026-07-16 |
| [TapeMatch](TapeMatch.md) | Recording-family matching pipeline, calibration workflow | seeded | 2026-07-06 |
| [Concert-Ranker](Concert-Ranker.md) | Quality scans, recording scores, ranking pipeline | seeded | 2026-07-06 |
| [Data-Flows](Data-Flows.md) | Key end-to-end flows, checksum format, publish/subscribe | seeded | 2026-07-06 |
| [Dev-Workflow](Dev-Workflow.md) | Sessions, bookkeeping, skills/commands, verification rules | seeded | 2026-07-06 |
| [Taper-Attribution-Flow](Taper-Attribution-Flow.md) | Taper attribution pipeline: Layer 0/1/2, conflict queue, filtering | seeded | 2026-07-15 |

**Statuses:** `seeded` = initial pass from existing docs, may lack depth ·
`fresh` = regenerated from source by `/wiki-update` · `stale` = sources changed since last update.

To refresh: run `/wiki-update` (one page per invocation, stalest first) or
`/wiki-update <Page>` for a specific page.

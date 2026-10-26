# LosslessBob Wiki

Agent-maintained wiki for the LosslessBob project — a checksum lookup & collection
management app for the Bob Dylan lossless archive. Pages are regenerated
section-by-section by the `/wiki-update` command; **PROJECT.md remains the
authoritative source**, this wiki is the readable overview layer on top.

| Page | Covers | Status | Last updated |
|---|---|---|---|
| [Architecture](Architecture.md) | Tech stack, repo layout, how the pieces connect | fresh | 2026-10-18 |
| [Database](Database.md) | SQLite schema, MASTER vs USER tables, integrity system | fresh | 2026-10-18 |
| [Backend-API](Backend-API.md) | Flask API (port 5174), route groups, backend modules | fresh | 2026-10-18 |
| [GUI](GUI.md) | gui_next (Electron/React, sole GUI; legacy PyQt6 removed) | fresh | 2026-10-18 |
| [TapeMatch](TapeMatch.md) | Recording-family matching pipeline, calibration workflow | fresh | 2026-10-18 |
| [Concert-Ranker](Concert-Ranker.md) | Quality scans, recording scores, ranking pipeline | fresh | 2026-10-18 |
| [Data-Flows](Data-Flows.md) | Key end-to-end flows, checksum format, publish/subscribe | fresh | 2026-10-18 |
| [Dev-Workflow](Dev-Workflow.md) | Sessions, bookkeeping, skills/commands, verification rules | fresh | 2026-10-18 |
| [Visual-Verification](Visual-Verification.md) | Screenshot engine: electron_driver two modes, tour file, /verify workflow | fresh | 2026-10-18 |
| [Taper-Attribution-Flow](Taper-Attribution-Flow.md) | Taper attribution pipeline: Layer 0/1/2, conflict queue, filtering | fresh | 2026-10-25 |
| [Setlist-Sources](Setlist-Sources.md) | Olof/bobserve/setlist.fm corpora, song spine, fingerprinting, coverage in Library rows | fresh | 2026-10-25 |
| [Show-Dossier](Show-Dossier.md) | Dossier assembly, HTML/BBcode exports, channels, ambiguity handling, golden set | fresh | 2026-10-25 |
| [Data-Quality](Data-Quality.md) | QC rules engine, /qc-review console, dossier gate G1–G8, sweep/acceptance/golden tooling | seeded | 2026-10-25 |
| [Master-Data-Sync](Master-Data-Sync.md) | lb_master integrity, export channels, flat-file/GitHub distribution, onboarding | fresh | 2026-10-18 |
| [Collection-Pipeline](Collection-Pipeline.md) | Pipeline steps, hash/state caches, filing + routing, integrity monitor | fresh | 2026-10-18 |
| [Release-Update](Release-Update.md) | New flat-file release: Apply → auto-scrape → derived recompute; why Reconcile-first broke | fresh | 2026-10-18 |
| [Pipeline-Refresh](Pipeline-Refresh.md) | Data-freshness planner, chained execution, human review queues | fresh | 2026-10-18 |
| [Integrations](Integrations.md) | Torrents, qBittorrent, WTRF forum, archive.org, trading, Cloudflare sharing | fresh | 2026-10-18 |

**Statuses:** `seeded` = initial pass from existing docs, may lack depth ·
`fresh` = regenerated from source by `/wiki-update` · `stale` = sources changed since last update.

To refresh: run `/wiki-update` (one page per invocation, stalest first) or
`/wiki-update <Page>` for a specific page.

**Related user-facing surfaces:** the marketing site `docs/index.html`
([kuddukan42.github.io/losslessbob](https://kuddukan42.github.io/losslessbob/)),
app screenshots in `docs/screenshots/`, and the interactive DB schema at
[losslessbob-schema.pages.dev](https://losslessbob-schema.pages.dev/).

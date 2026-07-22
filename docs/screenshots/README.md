# Website & docs screenshots

Real app screenshots captured with the sanctioned screenshot engine
(`tools/electron_driver.mjs`, Tier A renderer mode). Referenced by the
website (`docs/index.html`), `README.md`, and `docs/wiki/` pages.

| File | Shows |
|------|-------|
| `home.png` | Home screen — collection overview, at-a-glance stats, recent activity |
| `quicklookup.png` | Quick Lookup — pasted FFP checksums matched to an LB entry |
| `library.png` | Library — timeline of shows, recording formats, detail panel |
| `search.png` | Search — facet filters beside the virtualized results table |
| `map.png` | Concert map — clustered markers, decade colors, venue detail panel |
| `gaps.png` | Gaps — per-year grid of concert dates colored by circulation |

To refresh: start the backend, then run the tour
(`node tools/electron_driver.mjs --renderer-only session tools/debug_screens.json`)
and copy the wanted PNGs from `.debug/` here under the same names.
Keep each under ~300 KB (the website loads them all on one page).

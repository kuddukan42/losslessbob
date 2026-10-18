# Integrations

> Sources: `PROJECT.md` §Torrent Generation, §qBittorrent Integration,
> §Credentials Storage, §Forum Posting, §WTRF Torrent Search, §Archive.org
> Upload, §Trading / Friend Collections, §File Sharing, and the `tuit_*` table
> sections · `backend/forum_poster.py` · `backend/sharing.py` ·
> `backend/qbittorrent.py` · `backend/archive_org.py` · `backend/wtrf_scraper.py` ·
> `backend/wtrf_seed.py` · `backend/wtrf_board.py` · `backend/tuit_scraper.py` ·
> `backend/tuit_upload.py` · `backend/tracker_seed.py` · `backend/seed_overlay.py` ·
> `backend/torrent_verify.py` · `tools/tuit_sync.py` · Status: fresh 2026-10-18

Getting recordings *out* of the collection: torrents, forum posts, tracker
seeding/uploads, shares, trades. Credentials live in the **OS keyring**
(`backend/credentials.py`: qBittorrent, WTRF, IA S3, TUIT, TUIT RSS passkey);
the API never returns a stored password.

## Torrents & qBittorrent

`/api/torrent/create` builds a `.torrent` per LB (`torrent_maker.py`; trackers
via `/api/trackers`) into `torrents`. `/api/qbt/{test,add}` plus
`/api/torrent/<id>/qbt_{remove,check}` (removal never deletes content files;
check syncs the DB flag).

## WTRF forum

- **Post**: `/api/entry/<lb>/{preview_forum,lbdir_status,post_forum}`; posting
  is gated by an LBDIR integrity check of the filed folder (the forum-guard).
  No torrent yet → one is generated and added to qBittorrent first. Log in
  `forum_posts`.
- **Fetch**: `/api/wtrf/{fetch_torrent,crawl_missing}` → `wtrf_downloads`.
- **Seed**: `/api/wtrf/seed_links` (paste of topic links or bare LB numbers,
  SSE) and `/api/entry/<lb>/seed_wtrf` (`wtrf_seed.py`); `tools/wtrf_seed_board.py`
  walks the whole board (`wtrf_board.py`, `--resume`; a full overlay drive stops
  the walk). Non-public entries are refused before any forum round-trip.

## Seeding without touching the collection

`tracker_seed.py` (TUIT and WTRF share it) seeds an LB's `.torrent` through
three gates: `db.is_seedable_to_tracker()` (lb_status `public`), a linked
folder whose name matches the torrent root, and `torrent_verify.py` hashing it
to 100% read-only — qBittorrent is never handed a partial folder. Fallback
(partial overlay is the default): `seed_overlay.py` builds
`<mount>/<Tracker> Seeds/<name>` with audio **hardlinked** from the collection,
sidecars copied or re-fetched, piece-hash repair; files sharing a piece with
unresolved data are copied, never linked. Deleting or cross-volume-moving a
collection folder (`filer.py`) leaves the overlay as sole holder —
`seed_overlay.warn_if_seeded()` warns; `tuit_sync.py --check-overlays` audits.

## TUIT private tracker

`tangledupintorrents.org` — Laravel, CSRF login, no JSON API; **3s/request**.
`tuit_scraper.py` fills `tuit_recordings` (HTML archived under
`data/downloads/tuit/html/`), `tuit_shows`/`tuit_venues` (venue paging drifts;
`db.backfill_tuit_venues_from_shows()` fills gaps) and `tuit_songs`/
`tuit_song_performances` (a cross-check of the Olof spine; page with
`sort=alpha`). "No tape" means not on this tracker — see
[Setlist-Sources](Setlist-Sources.md). `tools/tuit_sync.py` drives it:
`--fetch-torrents --seed --overlay`, `--sync-tours/-venues/-songs`, `--rss`
(passkey in keyring `SERVICE_TUIT_RSS`, `--set-rss-key`), `--retry-unseeded`;
hourly `data/tuit/cron_rss.sh` (gitignored). `tuit_upload.py` composes the
`/upload` form (`prepare_upload` is a dry run; only `post_upload` posts, behind
seedable/duplicate/verify gates) and seeds via `tracker_seed`; log in
`tuit_uploads`.

## Archive.org

`/api/archive_org/{credentials,test,upload,status,stop,uploads}` — async
single-LB upload with IA S3 keys; per-file + byte progress; history in
`archive_org_uploads`.

## Trading & file sharing

- **Trading**: `/api/trading/{export,friends,compare/<id>}` — `.lbcollection`
  blobs into `friend_collections`/`friend_collection_entries` (USER tier, never
  in master data).
- **Sharing** (Cloudflare Tunnel, `sharing.py`): `/api/share/*` — token shares,
  HTML listing, Range/206 file streaming, ZIP streaming; revoking the last
  share stops the tunnel. UI: ScreenSharing.

## Related

Master/site-data GitHub releases are curator publishing, not sharing:
[Master-Data-Sync](Master-Data-Sync.md). Dossier BBcode digests:
[Show-Dossier](Show-Dossier.md). Private-entry metadata never leaves via any of
these ([Database](Database.md)).

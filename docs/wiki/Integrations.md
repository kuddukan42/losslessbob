# Integrations

> Sources: `PROJECT.md` §Torrent/qBittorrent/Credentials/Forum/WTRF/Archive.org/
> Trading/Sharing routes (~lines 1556–1631) · `backend/forum_poster.py`,
> `sharing.py`, `qbittorrent.py`, `archive_org.py`, `wtrf_scraper.py` ·
> Status: seeded 2026-07-22

Outbound surfaces: getting recordings *out* of the collection — torrents,
forum posts, uploads, shares, trades. All credentials live in the **OS
keyring** (WTRF, qBittorrent, IA S3); the API never returns a stored password.

## Torrents & qBittorrent

`/api/torrent/create` generates a `.torrent` per LB (tracker lists managed via
`/api/trackers`); records in `torrents` with live `source_folder_exists` /
`torrent_file_exists` checks. qBittorrent WebUI integration: test / add
(by torrent_id or bulk lb_numbers, with category/tags) / remove (content files
never deleted) / presence-check that syncs the DB flag.

## WTRF forum

- **Posting**: `/api/entry/<lb>/preview_forum` builds subject + BBcode body;
  `post_forum` is gated by an LBDIR integrity check on the entry's collection
  folder (400 on fail/incomplete — the forum-guard). If no torrent exists one
  is auto-generated and added to qBittorrent first (qbt failure non-fatal).
  Posts log to `forum_posts`.
- **Fetching**: WTRF torrent search downloads matching torrents for missing
  LB items (`wtrf_downloads`); `crawl_missing` batch-crawls via SSE.

## Archive.org

Async single-LB uploads via IA S3 credentials: start → poll status (per-file
+ byte progress) → stop-after-current-file. History in `archive_org_uploads`.

## Trading / friend collections

Export own collection as a `.lbcollection` JSON blob; import friends' blobs
into `friend_collections`/`friend_collection_entries`; `/api/trading/compare`
diffs holdings both ways. Friend data is USER-tier and never exported in
master data.

## File sharing (Cloudflare Tunnel)

Token-based shares of collection folders: self-contained HTML listing,
per-file streaming with Range/206 support, whole-share ZIP streaming. Revoking
the last share stops the tunnel. Status surface: ScreenSharing.

## Related

- Master/site-data GitHub releases are curator publishing, not sharing — see
  [Master-Data-Sync](Master-Data-Sync.md).
- Dossier BBcode digests for forum posts: [Show-Dossier](Show-Dossier.md).
- Private-entry metadata never leaves via any of these surfaces
  ([Database](Database.md) channels).

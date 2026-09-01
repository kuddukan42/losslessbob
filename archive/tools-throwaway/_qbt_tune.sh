#!/usr/bin/env bash
# Retune qBittorrent 5.2.3 (flatpak) — Dylan archive profile:
#   ~10k torrents, sparse cold access, 1 MiB/s uplink, all discoverable.
# Applies live via WebUI API — no restart. Delete when done.
set -euo pipefail
API=http://127.0.0.1:8080/api/v2

read -r -d '' PREFS <<'JSON' || true
{
  "up_limit": 1048576,

  "queueing_enabled": true,
  "dont_count_slow_torrents": true,
  "max_active_torrents": -1,
  "max_active_uploads": 8,
  "max_active_downloads": 5,

  "max_uploads": 10,
  "max_uploads_per_torrent": 3,

  "file_pool_size": 2000,
  "async_io_threads": 16,
  "hashing_threads": 4,
  "checking_memory_use": 256,
  "enable_piece_extent_affinity": true,

  "connection_speed": 10,
  "max_connec": 1000,
  "max_connec_per_torrent": 20,
  "socket_backlog_size": 300,
  "max_concurrent_http_announces": 20,
  "stop_tracker_timeout": 5,

  "send_buffer_watermark": 500,
  "send_buffer_low_watermark": 10,
  "send_buffer_watermark_factor": 50,

  "refresh_interval": 5000,
  "resolve_peer_countries": false
}
JSON

curl -s -X POST "$API/app/setPreferences" --data-urlencode "json=$PREFS" && echo "applied"
echo "--- verify ---"
curl -s "$API/app/preferences" | python3 -c '
import json,sys;d=json.load(sys.stdin)
for k in ["up_limit","queueing_enabled","dont_count_slow_torrents","max_active_torrents","max_active_uploads","max_uploads","max_uploads_per_torrent","file_pool_size","async_io_threads","hashing_threads","enable_piece_extent_affinity","connection_speed","max_connec","max_connec_per_torrent","max_concurrent_http_announces","stop_tracker_timeout","send_buffer_watermark","send_buffer_watermark_factor","refresh_interval","resolve_peer_countries","max_ratio_enabled"]:
    print(f"{k:34}{d.get(k)}")'

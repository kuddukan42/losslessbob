#!/usr/bin/env bash
# TODO-337 step (4): re-run the partial TUIT overlays so they reach 100% locally.
# Dry-run by default; pass --apply to seed. Output is tee'd to data/tuit/overlay_repair_<date>.log.
#
#   tools/tuit_overlay_repair.sh            # list partials + dry-run pass
#   tools/tuit_overlay_repair.sh --apply    # rebuild/repair + seed + qbt recheck
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python3
LOG="data/tuit/overlay_repair_$(date +%F).log"
LIST="/tmp/tuit_partial_recs.txt"

# A. list the partial overlays (read-only, local, zero tracker traffic).
"$PY" - > "$LIST" <<'PYEOF'
import backend.db as db
from backend.torrent_verify import verify_torrent_against_folder
sql = ("SELECT rec_id, torrent_path, seed_folder, MAX(attempted_at) FROM tuit_downloads"
       " WHERE status='qbt_added' AND torrent_path IS NOT NULL"
       " AND seed_folder LIKE '% Seeds/%' GROUP BY rec_id")
with db.get_connection() as conn:
    rows = conn.execute(sql).fetchall()
for rec_id, tp, folder, _ts in rows:
    if not verify_torrent_against_folder(tp, folder).complete:
        print(rec_id)
PYEOF
echo "partial overlays: $(wc -l < "$LIST") (expect ~29-31)" | tee "$LOG"

# B. re-run just those recordings.
MODE=(--dry-run)
[[ "${1:-}" == "--apply" ]] && MODE=()
RECS=()
while read -r r; do RECS+=(--rec "$r"); done < "$LIST"
"$PY" tools/tuit_sync.py --rescan --fetch-torrents --seed --overlay --refetch-sidecars -v \
    "${MODE[@]}" "${RECS[@]}" 2>&1 | tee -a "$LOG"

echo "--- summary ---" | tee -a "$LOG"
echo "100% locally: $(grep -cE 'assembled 100% locally' "$LOG" || true)" | tee -a "$LOG"
grep -E 'overlay repair|recheck:|still [0-9]|WARNING' "$LOG" || true

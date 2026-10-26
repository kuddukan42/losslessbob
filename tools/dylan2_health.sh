#!/usr/bin/env bash
# TODO-264: DYLAN2 disk health + the two BUG-120 corrupt files. Read-only throughout:
# SMART report, a no-write filesystem check, md5 + flac -t of the two files.
# Run as root (smartctl / fsck need it). Output is tee'd to a log; paste it back.
#
#   sudo tools/dylan2_health.sh [mountpoint]        # default /mnt/DYLAN2
set -u
MNT="${1:-/mnt/DYLAN2}"
LOG="data/logs/dylan2_health_$(date +%Y%m%d_%H%M).log"
mkdir -p data/logs
exec > >(tee "$LOG") 2>&1

echo "== dylan2_health $(date -Is) mount=$MNT"
DEV=$(findmnt -no SOURCE "$MNT" 2>/dev/null || true)
[ -z "$DEV" ] && DEV=$(blkid -L DYLAN2 2>/dev/null || true)
if [ -z "$DEV" ]; then echo "DYLAN2 not mounted and no DYLAN2 label found"; exit 1; fi
FSTYPE=$(lsblk -no FSTYPE "$DEV" | head -1)
DISK=/dev/$(lsblk -no PKNAME "$DEV" | head -1)
echo "partition=$DEV fstype=$FSTYPE disk=$DISK"
lsblk -o NAME,SIZE,MODEL,SERIAL "$DISK"

echo; echo "== SMART (smartctl -x)"
if command -v smartctl >/dev/null; then smartctl -x "$DISK"
else echo "smartctl missing: apt install smartmontools"; fi

echo; echo "== filesystem check (no writes)"
case "$FSTYPE" in
  ntfs|ntfs3) ntfsfix --no-action "$DEV" ;;
  ext2|ext3|ext4)
    if findmnt -no SOURCE "$DEV" >/dev/null; then
      echo "mounted: e2fsck -n on a mounted fs gives false positives; umount $MNT and re-run for a clean read"
    fi
    e2fsck -fn "$DEV" ;;
  xfs) xfs_repair -n "$DEV" ;;
  btrfs) btrfs check --readonly "$DEV" ;;
  *) echo "no read-only checker wired for '$FSTYPE'" ;;
esac

check_file() {  # path expected_md5
  local f="$1" want="$2"
  echo; echo "-- $f"
  if [ ! -f "$f" ]; then echo "MISSING"; return; fi
  local got; got=$(md5sum "$f" | cut -d' ' -f1)
  echo "md5 got=$got want=${want:-?} $([ "$got" = "$want" ] && echo MATCH || echo DIFF)"
  head -c 420000 "$f" | md5sum | sed 's/^/first-420KB md5 /'
  command -v flac >/dev/null && flac -t -s "$f" && echo "flac -t OK"
}

echo; echo "== the two BUG-120 files"
check_file "$MNT/Concerts/1978/1978-06-20 London, England (LB-06548)/09 Don't Think Twice.flac" \
  21116b8f97590bb15f8da8dbdcbbca23
CE=$(find "$MNT" -maxdepth 4 -type d -name '*Cutting Edge*12181*' 2>/dev/null | head -1)
if [ -n "$CE" ]; then
  F=$(find "$CE" -name 'd18 2 - *More and More*.flac' | head -1)
  MD5F=$(find "$CE" -name 'bd65-Cutting-Edge.md5' | head -1)
  WANT=""
  [ -n "$MD5F" ] && [ -n "$F" ] && WANT=$(grep -F "$(basename "$F")" "$MD5F" | head -1 | cut -c1-32)
  check_file "${F:-$CE/<d18 2 not found>}" "$WANT"
else
  echo "Cutting Edge LB 12181 folder not found under $MNT (maxdepth 4)"
fi
echo; echo "== done -> $LOG"

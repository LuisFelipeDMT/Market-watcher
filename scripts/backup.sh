#!/usr/bin/env bash
# Encrypted backup of the irreplaceable bits (sealed secrets + config).
# Snapshots/watchlist are derived and intentionally excluded.
#
# Usage: scripts/backup.sh <app_dir> <out_dir>
# Requires `age` and a recipient key in $AGE_RECIPIENT (e.g. age1...).
set -euo pipefail

APP_DIR="${1:?app dir required}"
OUT_DIR="${2:?output dir required}"
: "${AGE_RECIPIENT:?set AGE_RECIPIENT to your age public key}"

mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUT_DIR/market-watcher-$STAMP.tar.age"

tar -C "$APP_DIR" -c \
    secrets \
    .env.collector \
    .env.analysis \
    2>/dev/null | age -r "$AGE_RECIPIENT" -o "$OUT"

chmod 600 "$OUT"
echo "Wrote encrypted backup: $OUT"
echo "Restore: age -d -i <key> '$OUT' | tar -x -C <dir>"

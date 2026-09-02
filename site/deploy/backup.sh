#!/usr/bin/env bash
###############################################################################
# 数据备份 —— 全部业务数据 + 账号都在一个 SQLite 目录里
#
#   bash /opt/zhisou/app/site/deploy/backup.sh            # 备份到 /opt/zhisou/backup
#   BACKUP_DIR=/data/bak bash .../backup.sh               # 自定义目录
#
# 建议加 cron（root）:
#   0 3 * * * bash /opt/zhisou/app/site/deploy/backup.sh >/dev/null 2>&1
###############################################################################
set -euo pipefail

DATA_DIR=/opt/zhisou/app/site/backend/data
BACKUP_DIR="${BACKUP_DIR:-/opt/zhisou/backup}"
KEEP_DAYS="${KEEP_DAYS:-14}"

[ -d "$DATA_DIR" ] || { echo "找不到数据目录 $DATA_DIR"; exit 1; }
mkdir -p "$BACKUP_DIR"

STAMP="$(date +%F_%H%M%S)"
OUT="$BACKUP_DIR/zhisou-data-$STAMP.tgz"

# 用 sqlite3 .backup 拿一致性快照（若有 sqlite3），否则直接打包目录
if command -v sqlite3 >/dev/null 2>&1 && [ -f "$DATA_DIR/app.db" ]; then
  TMP="$(mktemp -d)"
  sqlite3 "$DATA_DIR/app.db" ".backup '$TMP/app.db'"
  tar czf "$OUT" -C "$TMP" app.db
  rm -rf "$TMP"
else
  tar czf "$OUT" -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"
fi

echo "已备份: $OUT ($(du -h "$OUT" | cut -f1))"

# 清理过期备份
find "$BACKUP_DIR" -name 'zhisou-data-*.tgz' -mtime +"$KEEP_DAYS" -delete 2>/dev/null || true

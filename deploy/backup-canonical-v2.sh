#!/usr/bin/env bash
# Canonical V2 每日备份：release 产物 + 访问日志库 -> /md1
# SQLite 库用 python sqlite3 在线 backup API（服务运行中也一致），
# 其余文件直接 tar 拷贝。保留最近 KEEP 份。
set -euo pipefail

SRC="/var/tmp/mirothinker-canonical-v2-s12f"
DST_ROOT="/md1/backups/canonical-v2"
KEEP=14

ts="$(date +%Y%m%d-%H%M%S)"
dst="$DST_ROOT/$ts"
mkdir -p "$dst"

backup_sqlite() { # $1=源库 $2=目标路径
  python3 - "$1" "$2" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
d = sqlite3.connect(dst)
with d:
    s.backup(d)
d.close()
s.close()
PY
}

# 1) 在线一致性备份所有 sqlite 库
for db in \
  "$SRC/access-logs.sqlite3" \
  "$SRC/index-v1/milvus.db" \
  "$SRC/index-v1/lookup.sqlite3" \
  "$SRC/serving-pack/milvus.db" \
  "$SRC/serving-pack/lookup.sqlite3"; do
  [ -f "$db" ] || continue
  rel="${db#"$SRC"/}"
  mkdir -p "$dst/$(dirname "$rel")"
  backup_sqlite "$db" "$dst/$rel"
done

# 2) 其余文件直接拷贝（排除 sqlite 主文件及 wal/shm，已由步骤 1 覆盖）
tar -C "$SRC" \
  --exclude='*.sqlite3' --exclude='*.sqlite3-shm' --exclude='*.sqlite3-wal' \
  --exclude='*.db' --exclude='*.db-shm' --exclude='*.db-wal' \
  -cf - . | tar -C "$dst" -xf -

# 3) 保留策略：只留最新 KEEP 份
ls -1dt "$DST_ROOT"/*/ | tail -n "+$((KEEP + 1))" | while read -r old; do
  rm -rf "$old"
done

echo "backup done: $dst ($(du -sh "$dst" | cut -f1))"

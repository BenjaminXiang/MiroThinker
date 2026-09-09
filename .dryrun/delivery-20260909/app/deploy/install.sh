#!/usr/bin/env bash
# 安装 canonical-v2 后端的用户级 systemd 守护 + 每日备份 cron。
# 不需要 sudo（linger 已开启，服务随用户会话常驻）。
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_NAME="canonical-v2-backend.service"

mkdir -p "$UNIT_DIR"
cp "$DEPLOY_DIR/$UNIT_NAME" "$UNIT_DIR/"
systemctl --user daemon-reload
systemctl --user enable "$UNIT_NAME"

# 每日 03:17 备份 + 03:41 访问日志滚动清理（幂等：先清掉旧行再追加）
CRON_LINE="17 3 * * * $DEPLOY_DIR/backup-canonical-v2.sh >> $DEPLOY_DIR/backup.log 2>&1"
PURGE_LINE="41 3 * * * $DEPLOY_DIR/purge-access-logs.sh >> $DEPLOY_DIR/backup.log 2>&1"
( crontab -l 2>/dev/null | grep -vF 'backup-canonical-v2.sh' | grep -vF 'purge-access-logs.sh' || true
  echo "$CRON_LINE"
  echo "$PURGE_LINE" ) | crontab -

cat <<EOF
安装完成。

注意：18188 当前由手工后台进程占用，切换前请先停掉旧进程，再：
  systemctl --user start $UNIT_NAME
  systemctl --user status $UNIT_NAME
  journalctl --user -u $UNIT_NAME -f

备份已排入 cron（每日 03:17），可手工先跑一次验证：
  $DEPLOY_DIR/backup-canonical-v2.sh
EOF

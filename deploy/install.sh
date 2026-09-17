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

# 管理台账号库/会话密钥/首启口令都落在服务期状态目录；目录不存在时后端
# 首启播种会失败（日志里只有一行 warning），所以这里先建好。
STATE_DIR="${CANONICAL_V2_STATE_DIR:-/var/tmp/mirothinker-canonical-v2-s12f}"
mkdir -p "$STATE_DIR"

cat <<EOF
安装完成。

管理台登录（首启播种）：
  - 首次启动时后端会创建一个 admin 账号，随机口令打印一次到 journalctl：
      journalctl --user -u $UNIT_NAME | grep 'first-boot administrator'
  - 同一口令同时写入 0600 文件（服务期状态目录）：
      $STATE_DIR/admin-initial-password.txt
  - 登录入口 http://<主机>:18188/main ；首次登录后请在「账号管理」里改密，
    然后删除上面那个文件（页面会一直提示直到文件被删除）
  - 账号库 $STATE_DIR/admin-auth.sqlite3 与会话密钥 $STATE_DIR/admin-auth.key
    都是 0600；备份/回滚都不会删除它们（见 deploy/README.md）
  - 如需固定首启口令（例如自动化部署）：设 CANONICAL_V2_ADMIN_INITIAL_PASSWORD，
    或直接预置 CANONICAL_V2_ADMIN_AUTH_DB

注意：18188 当前由手工后台进程占用，切换前请先停掉旧进程，再：
  systemctl --user start $UNIT_NAME
  systemctl --user status $UNIT_NAME
  journalctl --user -u $UNIT_NAME -f

备份已排入 cron（每日 03:17），可手工先跑一次验证：
  $DEPLOY_DIR/backup-canonical-v2.sh
EOF

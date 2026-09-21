#!/usr/bin/env bash
# 容器内 replay 回归门（7 组真实会话，验收/热更新前的必过门）。
#
# 等价于仓库文档里的：
#   cd apps/admin-console && uv run python scripts/replay_fix_round1.py --base-url … --out-dir …
# 差别只在解释器：这里直接用镜像内已同步好的 `/opt/mirothinker/.venv`，
# 因此**完全离线**可用 —— 现场没有 Python 环境、也不允许出网时照样能跑验收门。
# （裸形态的 `uv run` 在 apps/admin-console 下会去同步 admin-console 自己的 venv，
#   镜像里刻意不带那 1.3 GB；见 README §6 的说明。）
#
# 用法：
#   docker compose exec -T app mirothinker-replay --out-dir /tmp/accept
#   docker compose exec -T app mirothinker-replay --out-dir /tmp/accept --only G1_framing
# 传了 --base-url 就以你传的为准（容器内应指向 http://127.0.0.1:18188）。

set -euo pipefail

PORT="${MIROTHINKER_PORT:-18188}"
exec /opt/mirothinker/.venv/bin/python \
  /opt/mirothinker/apps/admin-console/scripts/replay_fix_round1.py \
  --base-url "http://127.0.0.1:${PORT}" \
  "$@"

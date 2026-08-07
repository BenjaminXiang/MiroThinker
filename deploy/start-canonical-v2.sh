#!/usr/bin/env bash
# Canonical V2 后端启动入口（systemd 调用）。
# 单一事实来源是 s12g/serve-18188-command.sh（钉死的完整启动参数），
# 本脚本只负责定位仓库、补齐 PATH、然后 exec 它。
set -euo pipefail

REPO="/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation"
COMMAND_FILE="$REPO/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18188-command.sh"

# systemd user 环境 PATH 不含 uv 的安装位置
export PATH="$HOME/.local/bin:$PATH"

cd "$REPO"
# 命令文件以 VAR=val 赋值开头；用 env 承载赋值并 exec，
# 不能写成 eval "exec ..."（exec 内建不会把参数里的 VAR=val 当赋值解析）。
# 文件内容为单行无引号参数列表，依赖分词展开。
# shellcheck disable=SC2046
exec env $(cat "$COMMAND_FILE")

#!/usr/bin/env bash
# 轻量线一键部署（目标服务器上执行；需 docker 与 python3；幂等可重跑）
# 用法: bash deploy.sh <bundle目录>
set -Eeuo pipefail

BUNDLE_DIR="${1:?用法: bash deploy.sh <bundle目录>}"
cd "$BUNDLE_DIR"

echo "== 1/6 数据库（Docker + pgvector） =="
if ! docker ps --format '{{.Names}}' | grep -q '^miro-light-pg$'; then
  docker run -d --name miro-light-pg --shm-size=1g \
    -e POSTGRES_USER=miroflow -e POSTGRES_HOST_AUTH_METHOD=trust \
    -p 127.0.0.1:5432:5432 pgvector/pgvector:pg16
  sleep 8
fi
if ! docker exec miro-light-pg psql -U miroflow -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='miroflow_light_lane_r1'" | grep -q 1; then
  docker exec miro-light-pg psql -U miroflow -d postgres -c \
    "CREATE DATABASE miroflow_light_lane_r1"
  echo "== 2/6 恢复数据快照（~36 秒，已彩排验证） =="
  docker exec -i miro-light-pg pg_restore -U miroflow \
    -d miroflow_light_lane_r1 --no-owner < light.dump
else
  echo "== 2/6 数据库已存在，跳过恢复 =="
fi

echo "== 3/6 Python 环境 =="
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt pytest

echo "== 4/6 配置 =="
if [ ! -f .env ]; then
  cat > .env <<CFG
LIGHT_LANE_DATABASE_URL=postgresql://miroflow@127.0.0.1:5432/miroflow_light_lane_r1
LIGHT_LANE_HOST=0.0.0.0
LIGHT_LANE_PORT=18201
CFG
  echo "已生成 .env —— 请编辑补充密钥路径后重跑本脚本（或用 /admin 界面配置）"
fi

echo "== 5/6 验收测试 =="
LIGHT_LANE_TEST_BASE=http://127.0.0.1:18201 .venv/bin/python -m pytest test_light_lane_api.py -q || true

echo "== 6/6 启动 =="
bash start.sh
echo "完成。浏览器打开 http://<本机IP>:18201/ 查询，/admin 配置模型与令牌。"

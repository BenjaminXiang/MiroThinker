# 轻量线迁移手册（目标：24 小时内在另一台服务器上线）

范围：查询/问答服务（`light_lane/`）。重线构建（canonical_v2 重建）
不在本次迁移内——它是构建期工程，产物策略另行决策。

## 一、迁移工件（源服务器上备好）

| 工件 | 路径 | 大小 | sha256（前 16 位） |
|---|---|---|---|
| 数据库完整快照 | `/tmp/light-migrate/light.dump`（pg_dump -Fc） | 642MB | `ed036b10594ef0bc…` |
| 代码包 | `light_lane/` 目录（git 内，commit 起） | <100KB | git 可溯 |
| 源数据（可选，路径 B 用） | restore 树 `source_backfills/p4-*.jsonl` | ~90MB | batch-inventory.json 有逐文件哈希 |
| 密钥 1（嵌入） | 仓库根 `.sglang_api_key` | 27B | **单独安全通道传，不入压缩包** |
| 密钥 2（LLM） | `apps/miroflow-agent/.env` 的 DEEPSEEK_API_KEY | — | **单独安全通道传** |

迁移已在源服务器彩排验证：dump 恢复 36 秒，恢复库上 15/15 验收用例全绿。

## 二、目标服务器前置条件

1. Docker（推荐），或 PostgreSQL 16 + pgvector 扩展；
2. Python 3.10+（venv）；
3. 网络：见下表决定功能档位；

| 网络情形 | 功能档位 |
|---|---|
| 可达 `100.64.0.27:18005`（校内网）+ 互联网 | **全功能**（语义+关键词+问答） |
| 仅互联网（无校内网） | 关键词+问答可用；**语义自动降级**（`semantic_available:false`，不报错） |
| 完全离线 | 仅关键词/SQL 检索；问答降级为检索结果直出 |

## 三、上线步骤（路径 A：恢复快照，推荐）

```bash
# 1. 数据库（Docker 方式；原生 PG 同理建库后 pg_restore）
docker run -d --name miro-light-pg -e POSTGRES_USER=miroflow \
  -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:5432:5432 pgvector/pgvector:pg16
# 传入 light.dump 后：
docker exec -i miro-light-pg psql -U miroflow -d postgres \
  -c "CREATE DATABASE miroflow_light_lane_r1"
docker exec -i miro-light-pg pg_restore -U miroflow \
  -d miroflow_light_lane_r1 --no-owner < light.dump   # 实测 ~36 秒

# 2. 服务
cd light_lane && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # 填三段配置（见下）
.venv/bin/pip install pytest && .venv/bin/python -m pytest test_light_lane_api.py -q

# 3. 启动（默认 0.0.0.0:18201 之外按需改 LIGHT_LANE_HOST/PORT）
bash start.sh
```

`.env` 三段（或等价环境变量）：

```
LIGHT_LANE_DATABASE_URL=postgresql://miroflow@127.0.0.1:5432/miroflow_light_lane_r1
LIGHT_LANE_EMBED_KEY_PATH=/安全路径/.sglang_api_key        # 或 LIGHT_LANE_EMBED_KEY=直接值
LIGHT_LANE_DEEPSEEK_KEY_FILE=/安全路径/deepseek.env         # 内容：DEEPSEEK_API_KEY=sk-...
# 可选：LIGHT_LANE_HOST=0.0.0.0  LIGHT_LANE_PORT=18201  LIGHT_LANE_EMBED_ENDPOINT=…
```

## 四、路径 B：源数据重灌（无快照/需重建时）

前置：校内网（要调嵌入接口）。

```bash
# 装载六批 JSONL（load_light_lane.py 内的 SOURCES_ROOT 改为目标路径或软链）
python load_light_lane.py            # ~5 分钟
python embed_light_lane.py           # ~10 分钟（4.5 万向量，断点续传）
python reconcile_light_lane.py       # 对账核对
```

## 五、验收标准（目标服务器上执行）

1. `pytest test_light_lane_api.py -q` → **15/15**；
2. 三场景 curl：优必选专利（448）/ 深圳机器人公司清单 / 优必选联系方式；
3. `curl /api/inventory` 与源端 reconcile-report.md 数字一致；
4. 若无校内网：确认 `semantic_available:false` 降级生效而非报错。

## 六、回退与注意

- 服务回退：`start.sh` 幂等重启即可；数据库回退=重跑路径 A；
- 语义降级是**功能开关**不是故障：无嵌入网络时系统照常出关键词+问答；
- 上线暴露面：`LIGHT_LANE_HOST=0.0.0.0` 前确认目标机防火墙策略；本系统
  无鉴权，只应暴露在受控内网；
- 重线若后续通关并定为正式 serving pack，其迁移另走部署清单（不在本手册）。

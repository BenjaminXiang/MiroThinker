# 轻量检索线（light lane）运维说明

全列数据（4.5 万对象）+ 语义/关键词/SQL 三路检索 + 有据问答，
独立于重线构建与线上服务。

## 组件

| 文件 | 作用 |
|---|---|
| `load_light_lane.py` | 六批 JSONL → Postgres（幂等重灌；**不会**动 embedding 表） |
| `embed_light_lane.py` | 全量向量（断点续传，内容哈希键控幂等；~10 分钟/4.5 万） |
| `api.py` | 查询/问答服务（127.0.0.1:18201，admin-console venv） |
| `test_light_lane_api.py` | 验收套件（14 用例：三场景/检索/详情/出处/P10） |
| `reconcile_light_lane.py` | P8 口径对账 → `reconcile-report.md` |
| `start.sh` | 启动/重启服务 |

## 快速操作

```bash
# 启动/重启（幂等）
bash start.sh

# 跑验收
/home/longxiang/MiroThinker/apps/admin-console/.venv/bin/python -m pytest test_light_lane_api.py -q

# 数据重灌（源文件更新后；向量表不受影响）
/home/longxiang/MiroThinker/.worktrees/data-rebuild/apps/miroflow-agent/.venv/bin/python load_light_lane.py

# 向量补齐（只嵌新增/变更）
/home/longxiang/MiroThinker/.worktrees/data-rebuild/apps/miroflow-agent/.venv/bin/python embed_light_lane.py

# 重新对账
/home/longxiang/MiroThinker/.worktrees/data-rebuild/apps/miroflow-agent/.venv/bin/python reconcile_light_lane.py
```

## 端点

- `GET /` — 对话页（自然语言问答）
- `GET /api/ask?q=…` — 有据问答（规则：只依据资料/P10 话术/占位符不展示/出处必附）
- `GET /api/search?q=…&type=company|patent|paper|professor&mode=hybrid|semantic|keyword`
- `GET /api/company/{名}`（别名扩展的专利列表）/`/api/professor/{id}`（论文+DOI）/
  `/api/patent/{id}`（申请人解析）/`/api/paper/{id}`（公开链接）
- `GET /api/inventory` — 对账数字

## 依赖与安全

- 数据库：`miroflow_light_lane_r1`（55458 集群，带 disposable marker）
- LLM key：`apps/miroflow-agent/.env` 的 `DEEPSEEK_API_KEY`（批准的密钥文件，不落代码）
- 嵌入：学校接口 Qwen3-8B（key 在仓库根 `.sglang_api_key`）
- 只绑 127.0.0.1；对外暴露需另做部署决策

## 已知边界（详见 reconcile-report.md）

1,239 个未解析申请人（源侧真实缺口，归一化直连已验证仅能再捞 2 条，
即确定性上限）；6,417 条悬空教授链接；企业别名覆盖不全；论文无
锚定门（与重线口径不同）。

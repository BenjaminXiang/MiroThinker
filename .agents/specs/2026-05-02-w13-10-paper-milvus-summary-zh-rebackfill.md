---
title: "W13-10: Milvus paper_chunks 重 backfill 用 summary_zh 优先"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（脚本调整 + dogfood）
wave: Wave 13 follow-up
related_specs:
  - .agents/specs/2026-05-02-w13-V1-paper-summary-zh-dogfood.md
  - .agents/specs/2026-05-02-w12-6-paper-summary-zh.md
---

# W13-10: paper_chunks Milvus 重 backfill — 用 summary_zh 优先

## 1. Goal

V1 dogfood 后 paper.summary_zh 已 47.4% 覆盖（3456 / 7297）。但 `apps/miroflow-agent/src/data_agents/paper/milvus_backfill.py:48-64` 当前优先级链：

```
summary_zh > abstract_clean > paper_full_text.abstract
```

虽然代码逻辑对，但**Milvus paper_chunks collection 已含 17155 行旧 chunks**（mtime 06:10），都基于 `abstract_clean`（英文）embedding。新写入的 summary_zh 没进 Milvus。

直接结果：chat B 类 query 用中文搜索时，Milvus 命中是英文 abstract chunks，召回 relevance 不如中文 chunks。

本 spec：**rebuild paper_chunks collection** 让 chunker 优先用 summary_zh。

## 2. Non-goals

- **不**改 chunker 优先级链逻辑（已对）
- **不**改 abstract_translator
- **不**等 paper.summary_zh 100% 才做（47% 已可见 ROI）

## 3. Affected paths

```
ops（脚本已存在；只是跑）：
  cd apps/miroflow-agent
  MILVUS_USE_REAL_CLIENT=1 DATABASE_URL=...miroflow_real \
    uv run python scripts/run_milvus_backfill.py --domain=paper --rebuild

修改（如需）：
  apps/miroflow-agent/src/data_agents/paper/milvus_backfill.py
    （仅核对优先级链；不改）
```

## 4. 顺序

- 临时停 admin-console（同 W13-3 patent backfill；milvus-lite 不支持并发）
- 跑 `--domain=paper --rebuild`
- 重启 admin-console
- curl 验证 B 类中文 query 命中 chunk 是中文

## 5. Validation

```bash
# 跑前后对比：抽 paper_chunk content_text 看中文比例
unset https_proxy HTTPS_PROXY
uv run python -c "
from pymilvus import MilvusClient
c = MilvusClient(uri='/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db')
import os; os.environ['MILVUS_USE_REAL_CLIENT']='1'
res = c.query('paper_chunks', filter='', limit=5, output_fields=['content_text'])
for r in res:
    print((r.get('content_text') or '')[:80])
"

# 跑 host bash dogfood：chat 中文 query
curl -sX POST http://localhost:8088/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"低空经济无人机的最新研究"}' | python3 -m json.tool | head -30
# 期望：retrieval evidence snippet 含中文 summary_zh 文本
```

## 6. Done criteria

1. ✅ paper_chunks rebuild 完毕（行数与 47% summary_zh + abstract_clean 之和接近）
2. ✅ 抽样 5 条 chunk content_text 主要是中文（V1 已写 summary_zh 的 paper）
3. ✅ chat 中文 B 类 query 命中 chunk snippet 是中文

## 7. Stop conditions

- rebuild 时 milvus.db 损坏 / 锁失败 → 必须先停 admin-console
- 跑完后 chat 实测 0 hits → 检查 collection schema 是否变化（应该没；不变）
- 行数比 17155 大幅减少 → 检查 chunker 是否漏 paper（rejected/skipped）

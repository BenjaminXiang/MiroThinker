---
title: "W13-3 patent e2e + Milvus 真实端到端完成 2026-05-02"
date: 2026-05-02
owner: claude
status: archived
related_specs:
  - .agents/specs/2026-05-02-w13-3-patent-postgres-writer.md
  - .agents/specs/2026-05-02-w13-6-quality-status-alembic-v019.md
  - .agents/specs/2026-05-02-w10-2-patent-milvus.md
context: W13-3 spec rev 2 实施 + V019 schema + e2e 真实数据 + Milvus backfill + chat 路由实测
---

# W13-3 patent 端到端完成 2026-05-02

## 1. patent e2e full LLM 结果

| 指标 | 值 |
|---|---|
| patent rows | 1931/1931 = 100% |
| summary_text 写入率 | 1931/1931 = 100% |
| LLM-generated（非 fallback）| 1931/1931 = 100% — **0 fallback** |
| quality_status='ready' | 1931/1931 = 100% |
| company_patent_link 写入率 | 76/76 = 100% |
| distinct patents linked | 76 |
| distinct companies linked | 33 |

## 2. Patent Milvus backfill

```json
{"patents_total": 1931, "patents_processed": 1931, "patents_skipped": 0,
 "patents_with_errors": 0, "duration_seconds": 32.92}
```

## 3. 4 域 Milvus 全景

```
collections: company_profiles 1024 / paper_chunks 17155 /
             patent_profiles 1931 (NEW) / professor_profiles 787
```

## 4. chat 路由实测

```
POST /api/chat {"query": "广和通有什么专利"} → HTTP 200
- query_type: A_patent_by_applicant
- answer: "深圳市广和通无线股份有限公司拥有的专利包括一项名为
  '基于单目相机的稠密点云生成方法、装置及电子设备'的发明专利，
  其专利号为 CN120635295A"
```

W13-3 spec §13 stop conditions 全部满足；
multi-applicant hit rate 76/1931 = 3.9%（< 1.5x 提升 — normalize 后续单立）。

## 5. Files

- `docs/source_backfills/w13-3-patent-e2e-full-2026-05-02.txt`
- 本文

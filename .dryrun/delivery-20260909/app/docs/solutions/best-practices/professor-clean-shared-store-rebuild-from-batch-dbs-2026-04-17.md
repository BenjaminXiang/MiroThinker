---
title: Professor Clean Shared-Store Rebuild From Batch DBs
date: 2026-04-17
category: docs/solutions/best-practices
module: professor-data-pipeline
problem_type: release-rebuild
status: active
component: shared-store
severity: high
tags: [professor, paper, shared-store, rebuild, workbook, sqlite]
---

# Professor Clean Shared-Store Rebuild From Batch DBs

## Problem

旧的 professor/paper shared-store 已经清空，但新的 clean professor pipeline 产物首先落在 URL-MD E2E 的 batch-level `released_objects.db` 里。直接沿用旧的 consolidate 路径会有两个问题：

1. 旧 consolidate 默认从历史 `professor/search_service/released_objects.sqlite3` 取 professor 数据，容易重新把旧时代产物混回来。
2. `SqliteReleasedObjectStore.upsert_released_objects()` 只会 upsert，不会清理旧 professor/paper 行；如果不先从 scratch DB 重建，就会把旧脏对象残留在 live shared store 里。

## Working Pattern

当前可复用的安全路径是：

1. 从 clean professor full-harvest batch 的顶层 `released_objects.db` 读取 `professor / paper / professor_paper_link`
2. 从当前 live shared DB 保留已通过 workbook 的 `company / patent`
3. 在 rebuild 过程中合并 serving-side verified backfills：
   - `docs/source_backfills/professor_company_roles.jsonl`
   - `docs/source_backfills/paper_exact_identifier_backfills.jsonl`
4. 把所有对象写入 scratch SQLite
5. 通过原子替换把 scratch DB 切成新的 shared `released_objects.db`

实现脚本：

- [rebuild_shared_store_from_batch_dbs.py](/home/longxiang/MiroThinker/apps/miroflow-agent/scripts/rebuild_shared_store_from_batch_dbs.py)

## Why This Works

- professor/paper/link 全部来自 clean batch，不再依赖旧 search-service professor source
- company/patent 保留当前已经通过 workbook 的 live serving 数据，不需要重复做 company/patent 大重建
- `丁文伯 -> 深圳无界智航` 这类 public-web relation 和 `pFedGPA` 这类 exact identifier 可以在 serving 层补齐，不会阻塞 professor 主采集链
- scratch DB + atomic replace 可以防止写到一半把 live shared store 置于半更新状态

## Real Validation

这条路径已经在真实数据上验证过，不是纯单测：

- 输入 professor batch：
  - [professor_url_md_e2e_tsinghua_key_profiles_round4_20260417](/home/longxiang/MiroThinker/logs/data_agents/professor_url_md_e2e_tsinghua_key_profiles_round4_20260417)
- 输出 scratch shared DB：
  - [released_objects_tsinghua_workbook_probe_20260417.db](/home/longxiang/MiroThinker/logs/data_agents/released_objects_tsinghua_workbook_probe_20260417.db)
- 真实 workbook audit：
  - [workbook_coverage_report.json](/home/longxiang/MiroThinker/logs/data_agents/workbook_coverage_tsinghua_probe_20260417/workbook_coverage_report.json)

验证结果：

- `company = 1037`
- `patent = 1931`
- `professor = 2`
- `paper = 41`
- `professor_paper_link = 40`
- workbook：`16 pass + 1 out_of_scope`

这里说明两件事：

1. 新的 shared-store rebuild 技术路径本身已经成立。
2. live shared-store 还没切过去时，主问题已经不再是 schema 或 rebuild 能力，而是 full-harvest family shards 何时完成。

## Operational Rule

- sample-limited URL-MD E2E 只能用于质量探测，不能直接喂 live serving rebuild
- live rebuild 只接受 `--limit-per-url 0` 的 clean batch outputs
- 若 workbook 剩余问题只差 public-web relation / exact identifier，不要反复在 professor crawl 主链里空转；优先使用 verified serving-side backfill 补齐

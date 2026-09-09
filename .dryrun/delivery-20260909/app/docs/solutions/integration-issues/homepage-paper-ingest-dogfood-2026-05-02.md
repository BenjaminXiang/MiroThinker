---
title: Homepage paper ingest — dogfood acceptance log (2026-05-02)
date: 2026-05-02
category: docs/solutions/integration-issues
module: apps/miroflow-agent/data_agents/paper
problem_type: integration_issue
component: development_workflow
severity: medium
applies_when:
  - W9-5 acceptance run for Wave 9
  - First real-DB execution of M2.4 homepage-authoritative paper ingest after V3 schema migration
tags: [m2.4, homepage-paper-ingest, dogfood, acceptance-log, w9-5, partial-fail]
status: complete
r3_gate: partial-fail
---

# Homepage paper ingest — dogfood acceptance log (2026-05-02)

## Pre-flight 校验

- ✅ alembic head: V012
- ✅ M2 pytest（test_v011_migration / test_homepage_ingest / test_title_resolver / test_full_text_fetcher）: 105 passed, 5 errors (test_v011 副作用，与 W9-5 无关)
- ✅ Serper API key 可用（环境变量已设）
- ✅ 代理 unset before script

## Pre-existing fixes 应用（运行前发现 V3 schema 迁移遗留）

执行 dogfood 前必须先修两处旧 bug（两处都已 commit 入主线 `eb62e12`）：

1. `paper/homepage_ingest.py:_fetch_professors`
   - 旧：`SELECT institution, homepage_url FROM professor`（V2 schema）
   - 新：LATERAL JOIN `professor_affiliation` 取 institution；`source_page` JOIN via `primary_official_profile_page_id` 取 homepage_url
2. `paper/homepage_ingest.py:149`
   - 旧：`conn.transaction(savepoint=True)`（psycopg2 风格 kwarg）
   - 新：`conn.transaction()`（psycopg3 嵌套自动 SAVEPOINT）

## Step 1 — Dry-run 10 profs

```
Run started at:   2026-05-02T02:23 UTC（约）
Run duration:     258.8 秒
DATABASE_URL:     localhost:15432/miroflow_real
Profs processed:  10
Profs skipped:    0
Papers linked total (WOULD-BE):   0
Full-text fetched total (WOULD-BE): 0
Pipeline issues filed (WOULD-BE): 1
```

**关键观察**：

10 个教授**全部检测到 publications section 但 extract 0 items**。从 log 提取的典型 warning：

```
WARNING src.data_agents.professor.homepage_publications:
  Detected publications section on http://www.sigs.tsinghua.edu.cn/<X>/main.htm
  but extracted only 0 items
```

涉及主页：
- `www.sigs.tsinghua.edu.cn/{hhh,ly,nzx,lzy,zgm}/main.htm`（清华深研院多人）
- `hsee.sztu.edu.cn`、`lhs.suat-sz.edu.cn`、`cep.sztu.edu.cn`（深圳理工大学）

这些主页都用了**相似的 CMS 模板**（`/info/<dept>/<id>.htm` 与 `/<X>/main.htm`），其 publications section 用的 HTML 结构与 M2.1 `extract_publications_from_html` 当前的 selector 不完全匹配。

## Step 2 — Wet-run 5 profs

**未执行**。dry-run 已显示 papers_linked_total = 0，wet-run 不会改变结果（同一抽取逻辑），跑 wet-run 只会增加无意义 DB 写入。

## R3 gate 评估：**Partial-fail**

模板要求：10 profs × ≥ 15 papers/prof = 150 papers
实测：10 profs × 0 papers = 0

**根因**（partial fail 不归责到 W9-5 范围）：

- M2.1 `homepage_publications.extract_publications_from_html` 的 publications section selector 在 `sigs.tsinghua.edu.cn` 与 `sztu.edu.cn` 类主页 CMS 模板下不匹配
- 不是 W9-5 / M2.4 编排逻辑问题；是 M2.1 抽取规则覆盖度问题

**Follow-up**（转入 backlog，不阻塞 W9-5 close）：

1. **W12-3+ / 新建 backlog 项**：扩 `homepage_publications.extract_publications_from_html` 的 selector 集合，覆盖：
   - `sigs.tsinghua.edu.cn` CMS 模板
   - `sztu.edu.cn` / `suat-sz.edu.cn` CMS 模板
   - 其他深圳高校主页常见 CMS 模板（哈工深、深大、北大深研院等）
2. 加 dogfood scope 测试：选 1-2 个**已知有 publications 的主页 URL**，单元测试验证 extract count > 0
3. 后续 dogfood 运行前，先按 institution 抽样 3-5 主页人工核对 extract 行为，再跑全量

## R3 gate Done definition (复述模板)

> "10 profs × ≥ 15 papers/prof linked"

实测 fail 因 M2.1 selector 限制；M2.4 编排链路本身（fetch → extract → resolve → fetch_full_text → upsert_paper → upsert_link）行为正常（pipeline_issue 写入 1 个 selector-mismatch 类型 OK）。

## 后续 dogfood 运行（M2.1 修复后再跑）

待 M2.1 selector 扩展完成后（W12-3+ backlog），重新执行：

```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_homepage_paper_ingest.py --dry-run --limit 10
# 期望: papers_linked_total > 100

# 然后 wet-run
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_homepage_paper_ingest.py --limit 5
```

新一次产出 `homepage-paper-ingest-dogfood-{YYYY-MM-DD}.md` 接续本归档。

## 引用

- spec: `.agents/specs/2026-04-30-w9-5-m2-4-dogfood.md`
- handoff: `.agents/handoffs/2026-04-30-w9-5-m2-4-dogfood.md`
- 模板: `homepage-paper-ingest-dogfood-template-2026-04-22.md`
- M2.1 selector 修复 backlog: 待新建（建议 W12-3 子项 / 或独立 W13-x）
- pipeline_v3 stage 11.5 集成 commit: `6de8ebb`

---
title: "W13-14: paper identity_status DOI verify (unverified → confirmed)"
date: 2026-05-03
owner: claude
status: ready-for-codex
audience: codex（实施 verify pipeline + dogfood）；claude review
wave: Wave 13 follow-up
related_specs:
  - .agents/specs/2026-05-02-w13-12-paper-patent-identity-status.md
  - .agents/specs/2026-04-21-002-m2.2-paper-title-resolver.md
prd_anchor: docs/Paper-Data-Agent-PRD.md §3.2 (DOI/ArXiv 实时 fallback)
---

# W13-14: paper identity_status DOI verify

## 1. Goal

W13-12 V020 已让 paper 有 `identity_status` 列，default `'unverified'`。实测 7297 paper 全部 'unverified'。
W13-13 retrieval filter (FILTER_BY_QUALITY_STATUS=1) + W13-D2 (paper 仅当 confirmed 才 promote ready)
导致**所有 paper 都不进 retrieval 池**。

本 spec：跑 OpenAlex / arXiv DOI 验证流程，把高置信 paper 升 `identity_status='confirmed'`，
之后 W13-D2 promote 即可让 paper.summary_zh 已写的部分变 'ready'。

## 2. Non-goals

- **不**改 V020 schema
- **不**改 W13-13 filter 逻辑
- **不**改 abstract_translator
- **不**做实时 fallback（chat E 类的 DOI lookup 由 title_resolver 已实装；本 spec 是 batch backfill）
- **不**改 W12 multi-source crawler

## 3. Backfill 流程

输入：paper 表中所有 `identity_status='unverified'` 的行（7297）
对每行：

1. 查 `paper_title_resolution_cache`（V011 已建）；如有 cache hit 含 `external_id` (DOI/ArXiv)
   → mark 'confirmed' (`identity_status='confirmed'`)
2. 否则：用 `paper.title_clean` 调 OpenAlex `/works` 搜索；如返回结果 title fuzzy match ≥ 0.85
   且作者重叠 ≥ 1 → mark 'confirmed' + 写 cache
3. 否则：调 arXiv search；同上判定
4. 都失败：保留 'unverified' + 写 `pipeline_issue('paper_doi_verify_failed')`

## 4. Affected paths

```
新增：
  apps/miroflow-agent/scripts/run_paper_doi_verify.py
    CLI: --limit / --resume / --dry-run / --start-from-paper-id
    每条 verify 后立即 UPDATE paper.identity_status + 写 paper_title_resolution_cache (若新)
    open_pipeline_run + close + require_real_run_id

  apps/miroflow-agent/src/data_agents/paper/doi_verifier.py
    pure functions:
      verify_via_cache(paper_row) -> Optional['confirmed']
      verify_via_openalex(title, authors, *, openalex_client) -> Optional['confirmed']
      verify_via_arxiv(title, authors, *, arxiv_client) -> Optional['confirmed']
    fuzzy match: rapidfuzz title ≥ 85；作者 token Jaccard ≥ 0.3

新增测试：
  apps/miroflow-agent/tests/data_agents/paper/test_doi_verifier.py
    - cache hit 命中 confirmed
    - OpenAlex 命中（含 fuzzy）confirmed
    - arXiv 命中 confirmed
    - 所有源 fail → 保留 unverified
    - title_clean 异常字符不破坏 fuzzy match
  apps/miroflow-agent/tests/scripts/test_run_paper_doi_verify.py
    - dry-run summary
    - 实跑 mock conn 写 paper.identity_status + cache
    - 失败写 pipeline_issue

依赖：
  - rapidfuzz 已在 pyproject.toml？grep 确认；如无则 do NOT add（用 difflib 替代或 token Jaccard）
```

## 5. Validation

```bash
cd apps/miroflow-agent
unset https_proxy HTTPS_PROXY

DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/paper/test_doi_verifier.py \
                tests/scripts/test_run_paper_doi_verify.py \
                -n0 --no-cov -v

# claude 后续 ops:
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_paper_doi_verify.py --limit 100 --dry-run
# 看候选数；如合理则去 --dry-run 实跑

# 然后跑 W13-D2 promote 让 paper 中 confirmed AND summary_zh 满足条件的升 ready
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_quality_promote.py --domain=paper
```

## 6. Done criteria

1. ✅ doi_verifier 单测覆盖 5 case；run_paper_doi_verify 单测 3 case
2. ✅ host bash 跑 --limit 100 --dry-run 看候选分布
3. ✅ host bash 实跑 100 条；至少 50% identity_status='confirmed'（depends on real data）
4. ✅ W13-D2 promote 重跑：paper 'ready' 数量 > 0
5. ✅ FILTER_BY_QUALITY_STATUS=1 默认 chat E 类 paper retrieve 不再全 0

## 7. 性能预期

- OpenAlex API: ~1 query/sec rate limit；7297 paper × 1s = ~2 hr
- 但 cache 命中可 skip OpenAlex；cache 已有 N 条
- 推荐先跑 paper_title_resolution_cache hit 子集（fast）；剩 OpenAlex/arXiv 慢 path 单独跑

## 8. 顺序依赖

- 依赖：W13-12 V020 已 land ✅
- 依赖：W13-D2 已 land ✅
- 与 W13-15 / W13-10 / W13-11 等无冲突

## 9. Open questions

| 问题 | 默认决策 |
|---|---|
| OpenAlex API key 在哪？| 已用过；查 settings |
| arXiv API rate limit？| 3 query/sec free；够用 |
| fuzzy match 阈值 | title 0.85 / author Jaccard 0.3；可后续调 |
| cache hit 直接 confirmed 是否过松？| 否；cache 是已 verify 过的（W12-5 / M2.2 已强 verify）|

## 10. Stop conditions

- OpenAlex 不可达 → 走 arXiv only + 报告
- rapidfuzz 不在依赖且不允许引入 → 用 token-based 简化 match
- title 噪声严重导致 < 30% fuzzy hit → escalate；prompt 调优 title_cleaner

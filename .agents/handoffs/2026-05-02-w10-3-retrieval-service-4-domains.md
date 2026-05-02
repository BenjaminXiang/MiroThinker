---
title: "W10-3: RetrievalService 4 域全覆盖"
date: 2026-05-02
owner: codex
spec: .agents/specs/2026-05-02-w10-3-retrieval-service-4-domains.md
slice: 1 of 1
status: ready
---

# W10-3 handoff

## CRITICAL

```bash
export https_proxy=http://100.64.0.14:10003
export HTTPS_PROXY=http://100.64.0.14:10003
```

沙箱：不要 git commit；不要 git checkout；direct work in current state。claude 后续 commit。

## Read order

1. 本 handoff
2. `.agents/specs/2026-05-02-w10-3-retrieval-service-4-domains.md` 全文
3. `apps/miroflow-agent/src/data_agents/service/retrieval.py` (263 行) — 完整结构
4. `apps/miroflow-agent/src/data_agents/storage/milvus_collections.py` — COMPANY_PROFILES_COLLECTION / PATENT_PROFILES_COLLECTION 常量（W10-1+W10-2 加的）
5. `apps/miroflow-agent/tests/data_agents/service/test_retrieval.py` — 现有模式

## Files

MODIFY:
- `apps/miroflow-agent/src/data_agents/service/retrieval.py`
  - 加 `_COMPANY_OUTPUT_FIELDS` / `_PATENT_OUTPUT_FIELDS` 常量
  - import COMPANY_PROFILES_COLLECTION / PATENT_PROFILES_COLLECTION
  - `_domain_search_config(domain)` 加 company / patent 分支（spec §5.1 给签名）
  - `_row_to_evidence(domain, row)` 加 company / patent 映射（spec §5.2 给完整代码）

CREATE:
- `apps/miroflow-agent/tests/data_agents/service/test_retrieval_company_patent.py`
  - test_retrieve_company_returns_evidence
  - test_retrieve_company_metadata_contains_industry_and_city
  - test_retrieve_patent_returns_evidence
  - test_retrieve_patent_metadata_contains_ipc
  - test_retrieve_unknown_domain_returns_empty (regression)

## Critical decisions（spec 已锁）

- Evidence.object_type Literal 现为 "professor" | "paper"；本 spec 扩展为 4 域。如 Literal 严格，改成 str 或扩 Literal。
- snippet：company 用 profile_summary > technology_route_summary > description > name；patent 用 title + abstract（前 500）
- metadata 直接传 dict(entity)
- 无 source_url 字段（company / patent 不在 Milvus 存 URL）

## Do-not

- ❌ 不动公开 retrieve() 接口签名
- ❌ 不动 cache 层
- ❌ 不动 search_service.py（W10-3 仅 retrieval 层）
- ❌ 不 commit

## Tests / checks

```bash
cd apps/miroflow-agent

DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/service/test_retrieval_company_patent.py \
                tests/data_agents/service/test_retrieval.py \
                tests/data_agents/service/test_search_service.py \
                -n0 --no-cov -v
# 期望: 所有过；新增 5+ 个；既有不退化
```

## Done criteria

1. ✅ retrieval.py 4 域支持
2. ✅ 5 个新单测过
3. ✅ 既有 service tests 不退化

## Stop conditions

- Evidence Literal 严格不接受 company/patent → 改成 str 类型；如改影响下游 →  escalate
- Milvus collection 在 test_mock 下未建（首次跑 W10-1+W10-2 测试时通过 ensure_*() 创建）→ 单测 mock client 即可

## Report

```
Summary:
Changed files:
- apps/miroflow-agent/src/data_agents/service/retrieval.py
- apps/miroflow-agent/tests/data_agents/service/test_retrieval_company_patent.py (new)

Verification:
- pytest test_retrieval_company_patent: N passed
- 既有 retrieval/search_service: N passed
```

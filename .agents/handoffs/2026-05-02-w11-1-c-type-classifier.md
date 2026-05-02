---
title: "W11-1: C 类型分类器接入"
date: 2026-05-02
owner: codex
spec: .agents/specs/2026-05-02-w11-1-c-type-classifier.md
slice: 1 of 1
status: ready
---

# W11-1 handoff（单 slice）

## CRITICAL — codex CLI proxy + sandbox

```bash
export https_proxy=http://100.64.0.14:10003
export HTTPS_PROXY=http://100.64.0.14:10003
```

沙箱：不要 git commit；claude 后续 commit。

## Read order

1. 本 handoff
2. `.agents/specs/2026-05-02-w11-1-c-type-classifier.md` 全文
3. `apps/admin-console/backend/api/chat.py:_classify_query_with_llm` 现实现
4. `apps/admin-console/tests/fixtures/intent_classifier_benchmark.jsonl`（W9-3 100 条 fixture，含 15 条 C 类型）
5. `docs/Agentic-RAG-PRD.md` §2.1 type C 描述

## Files

MODIFY:
- `apps/admin-console/backend/api/chat.py`
  - `_CLASSIFIER_SYSTEM` prompt 加 C 类型描述 + 2 example
  - `ClassifyResult` 加 `target_domain: Literal["professor","paper","company","patent"] | None = None`
  - `QueryType` Literal 含 'C'（如已有则 noop）
  - `_classify_query_with_llm` 后处理 LLM JSON：若 type='C' 但缺 target_domain，default 'paper'

CREATE:
- `apps/admin-console/tests/test_chat_classifier_c_type.py`
  - test_c_type_returns_target_domain_paper / company / patent
  - test_c_type_default_paper_if_missing
  - test_existing_a_b_d_e_f_g_unchanged

## Critical decisions（spec 已锁）

- C 类型 prompt 描述见 spec §5.1
- target_domain default = "paper" if missing
- 不动 fixture（W9-3 已含 C 15 条）

## Do-not

- ❌ 不实施 C handler 业务逻辑（W11-6 + W11-3）
- ❌ 不改 multi-turn pronoun 解析
- ❌ 不动其他 query type 行为
- ❌ 不 commit

## Tests / checks

```bash
cd apps/admin-console

uv run pytest tests/test_chat_classifier_c_type.py -n0 --no-cov -v
uv run pytest tests/ -k chat -n0 --no-cov

# benchmark 复跑（claude 操作；需 LLM 可达）
uv run pytest tests/test_classifier_benchmark.py -m requires_classifier_llm -v
```

## Done criteria

1. ✅ 4 项改动（prompt / ClassifyResult / target_domain / 后处理）
2. ✅ 单测 + 既有 chat tests 全过
3. ✅ benchmark overall ≥ 90%, C ≥ 80%（claude 后续验）

## Stop conditions

- ClassifyResult schema 改动破坏 chat.py handler import → 用 default None 兼容
- benchmark C 准确率 < 80% → 1 轮 prompt 调优；仍不过 escalate

## Report

```
Summary:
Changed files:
- apps/admin-console/backend/api/chat.py (modified)
- apps/admin-console/tests/test_chat_classifier_c_type.py (new)

Verification:
- pytest test_chat_classifier_c_type: N passed
- 既有 chat tests: N passed
- benchmark (claude 操作后): overall=X, C=Y

Risks/notes:
- benchmark fixture C 类型 query 可能 LLM 输出不稳定
```

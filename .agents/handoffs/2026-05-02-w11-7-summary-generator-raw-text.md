---
title: "W11-7: summary_generator 用 raw_text + reinforcement 阈值 150"
date: 2026-05-02
owner: codex
spec: .agents/specs/2026-05-02-w11-7-summary-generator-raw-text.md
slice: 1 of 1
status: ready
---

# W11-7 handoff（单 slice）

## CRITICAL — codex CLI proxy + sandbox

```bash
export https_proxy=http://100.64.0.14:10003
export HTTPS_PROXY=http://100.64.0.14:10003
```

沙箱限制：**不要 git commit**；claude 后续 commit。Python pipeline 跑时（如果你跑）需 `unset https_proxy HTTPS_PROXY`。

## Read order

1. **本 handoff**
2. `.agents/specs/2026-05-02-w11-7-summary-generator-raw-text.md` 完整契约（§5 数据流 / §6 接口 / §8 边界 / §9 验证）
3. `apps/miroflow-agent/src/data_agents/professor/summary_generator.py:200-237`（要改的 prompt builder）
4. `apps/miroflow-agent/src/data_agents/professor/summary_reinforcement.py:24-29`（默认 min_length 50）
5. `apps/miroflow-agent/scripts/run_profile_summary_reinforcement.py:116-131`（SQL 阈值）
6. `apps/miroflow-agent/src/data_agents/professor/models.py:106-119` `OfficialAnchorProfile.bio_text`（即 raw_text 字段所在；**不修改**模型）

## 重要修订（vs 初版）

V1 错误地说 raw_text 字段在 `EnrichedProfessorProfile` 顶层。实际它在 `OfficialAnchorProfile.bio_text`，通过 `profile.official_anchor_profile.bio_text` 访问（`OfficialAnchorProfile | None`，需 null-check）。**不需要**改 models.py。

## Files

MODIFY:
- `apps/miroflow-agent/src/data_agents/professor/summary_generator.py`
  - `build_profile_summary_prompt`：在 prompt 模板尾部追加 `raw_text_section`（spec §6.1 给完整代码）
  - raw_text 来自 `profile.official_anchor_profile.bio_text`（null-check）
  - 截断 `bio_text[:4000]`
  - raw_text 为空 → section 空字符串（不破坏现有行为）
- `apps/miroflow-agent/src/data_agents/professor/summary_reinforcement.py`
  - `_DEFAULT_MIN_REINFORCE_LENGTH = 150`（was 50）
- `apps/miroflow-agent/scripts/run_profile_summary_reinforcement.py`
  - 加 `--min-length` CLI arg, default 150
  - `_build_select_sql` 接 `min_length` 参数；SQL 中 `length(profile_summary) < {int(min_length)}`（int 强转防 injection）
  - main 调用链路传参

CREATE:
- `apps/miroflow-agent/tests/data_agents/professor/test_summary_generator_raw_text.py`
  - test_prompt_includes_raw_text_when_anchor_profile_has_bio_text
  - test_prompt_truncates_raw_text_to_4000_chars
  - test_prompt_omits_raw_text_section_when_anchor_profile_is_none
  - test_prompt_omits_raw_text_section_when_bio_text_empty
  - 共 4 个单测；mock EnrichedProfessorProfile（构造时设置 OfficialAnchorProfile）
- `apps/miroflow-agent/tests/scripts/test_run_profile_summary_reinforcement_threshold.py`
  - test_default_min_length_is_150
  - test_min_length_cli_override
  - assert SQL 字符串含 "150" 和 "50"（CLI override case）

## Critical decisions（spec 已锁，codex 不要发挥）

- raw_text 截 4000 chars（不要改 8000 / 6000）
- 截断从 head（不要 tail / summary）
- raw_text 不预清洗
- 阈值默认 150（不要 100 / 200）
- 不动 `validate_profile_summary` 200-300
- 不动 `_build_fallback_profile_summary`

## Do-not

- ❌ 不动 `quality_gate.py`（W12-7）
- ❌ 不动 `summary_reinforcement.py` 的 LLM 调用 / system prompt / max_length 800
- ❌ 不改 `_DEFAULT_MAX_PAPERS = 5`
- ❌ 不动 `EnrichedProfessorProfile` 字段
- ❌ 不动 `professor` 表 schema
- ❌ 不跑实际 backfill（claude 后续操作）
- ❌ 不 commit

## Tests / checks

```bash
cd apps/miroflow-agent

# 新增单测
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/professor/test_summary_generator_raw_text.py \
    tests/scripts/test_run_profile_summary_reinforcement_threshold.py \
    -n0 --no-cov -v
# 期望: 5+ passed

# 既有不退化
uv run pytest tests/data_agents/professor/ -k summary -n0 --no-cov
# 期望: 全过

uv run pytest tests/scripts/ -k reinforcement -n0 --no-cov
# 期望: 全过
```

## Done criteria

1. ✅ summary_generator.py 改动满足 spec §6.1
2. ✅ reinforcement default 150
3. ✅ 单测全过
4. ✅ 既有单测不退化
5. ✅ 报告路径列全（NOT commited）

## Stop conditions

- 既有 summary 单测大批退化（> 5 个 fail） → stop，spec 没考虑某 mock 路径
- `OfficialAnchorProfile.bio_text` 字段不存在 → stop, escalate
- prompt 总长超 Gemma-4 context 限制（罕见） → 改截到 3000

## Report

```
Summary: <changes>
Changed files:
- apps/miroflow-agent/src/data_agents/professor/summary_generator.py
- apps/miroflow-agent/src/data_agents/professor/summary_reinforcement.py
- apps/miroflow-agent/scripts/run_profile_summary_reinforcement.py
- apps/miroflow-agent/tests/data_agents/professor/test_summary_generator_raw_text.py (new)
- apps/miroflow-agent/tests/scripts/test_run_profile_summary_reinforcement_threshold.py (new)

Verification:
- pytest test_summary_generator_raw_text: N passed
- pytest test_run_profile_summary_reinforcement_threshold: N passed
- 既有 summary tests: N passed (无退化)

Risks/notes:
- raw_text 4000 chars 是否够（待 claude 跑全量回填后验证 Gemma-4 上下文余量）
- 现有 75 chars 那批 prof 是否应也走 V3 重跑（claude 决策；reinforcement 可能足够）
```

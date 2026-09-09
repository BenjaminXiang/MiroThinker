---
title: "W9-3: 100 条意图识别基准集 + CI ≥ 90% gate"
date: 2026-05-02
owner: codex
spec: .agents/specs/2026-04-30-w9-3-intent-classifier-benchmark.md
slice: 1 of 1
status: ready
---

# W9-3 handoff（单 slice）

## CRITICAL — codex CLI proxy

```bash
export https_proxy=http://100.64.0.14:10003
export HTTPS_PROXY=http://100.64.0.14:10003
```

**沙箱限制**：不要 git commit；claude 后续 commit。

## Read order

1. **本 handoff**
2. `.agents/specs/2026-04-30-w9-3-intent-classifier-benchmark.md` 完整设计契约（§6.1 fixture 字段 / §6.2 类别分布 / §6.3 测试代码 / §6.4 marker）
3. `apps/admin-console/backend/api/chat.py:111` `_classify_query_with_llm` 实现
4. `docs/Agentic-RAG-PRD.md` §2.1（A-G 类型 example queries）

## Files

CREATE:
- `apps/admin-console/tests/fixtures/intent_classifier_benchmark.jsonl` — **100 条**，按 spec §6.2 分布：A 50 / B 20 / C 15 / D 5 / E 5 / F 3 / G 2
- `apps/admin-console/tests/fixtures/intent_classifier_benchmark_README.md` — 字段说明 + 编辑规则
- `apps/admin-console/tests/test_classifier_benchmark.py` — 加载 fixture + 调 chat.py classifier + 计算准确率 + 断言（spec §6.3 给完整代码骨架）

MODIFY:
- `apps/admin-console/pyproject.toml` — 加 pytest marker `requires_classifier_llm`

## Fixture 编排建议

按域分批：
- **A 50 条**：单域精确（25 条教授姓名/院校 + 10 条企业名/工商 + 10 条专利号/标题 + 5 条论文标题/作者）
- **B 20 条**：单域语义检索（"做 XX 的教授" / "深圳 XX 公司" / "XX 方向论文" 系列）
- **C 15 条**：跨域跳转（"他的论文" / "他参与企业" / "公司专利" 类多轮）
- **D 5 条**：D 类型全景（"做 XX 的教授和企业" 类）
- **E 5 条**：科创知识问答（PRD §2.1 type E example）
- **F 3 条**：拒答（写诗 / 天气 / 翻译）
- **G 2 条**：同名歧义（"无界智航" / 同名教授）

每条 query 必填字段（spec §6.1）：`id` (Q001-Q100) / `query` / `expected_type` / `category_label` / `rationale` / `language` (`zh` 主) / `source` (`PRD example` / `manual`)。

PRD §2.1 已经给了每类 5-10 条 example query，从这里 seed，再人工扩展。

## Tests

```bash
cd apps/admin-console

# fixture 完整性快速 check（spec §10 给出脚本）
python3 -c "
import json
from pathlib import Path
from collections import Counter
fixture = Path('tests/fixtures/intent_classifier_benchmark.jsonl')
cases = [json.loads(l) for l in fixture.read_text().splitlines() if l.strip()]
assert len(cases) == 100, len(cases)
ids = [c['id'] for c in cases]
assert len(set(ids)) == 100
types = {c['expected_type'] for c in cases}
assert types == set('ABCDEFG')
print(Counter(c['expected_type'] for c in cases))
"
# 期望: Counter({'A': 50, 'B': 20, 'C': 15, 'D': 5, 'E': 5, 'F': 3, 'G': 2})

# benchmark 测试（需要 LLM 可达）
uv run pytest tests/test_classifier_benchmark.py -m requires_classifier_llm -v
# 期望: overall accuracy ≥ 90%, per-class ≥ 70%
```

## Done criteria

1. ✅ 100 条 fixture 入仓库
2. ✅ test_classifier_benchmark.py 在 LLM 可达环境跑过；overall accuracy ≥ 90% + per-class ≥ 70%
3. ✅ baseline accuracy 报告归档：`.agents/reviews/2026-05-02-w9-3-baseline-accuracy.md`（含每类 accuracy + 失败的 query 列表）
4. ✅ pyproject.toml 含 marker

## Stop conditions

- LLM 不可达 → 测试 fail，归档说明无法验收，stop（baseline 报告也无法生成）
- fixture 100 条凑不齐（特定类不够 example）→ 用 PRD example 重复扩展，并标记 `source: derived from PRD <type>`
- `_classify_query_with_llm` 接口已变 → 适配后跑

## Report

```
Summary: 100 条 fixture + benchmark 测试 + baseline 报告
Changed files (NOT commited):
- apps/admin-console/tests/fixtures/intent_classifier_benchmark.jsonl (new, 100 行)
- apps/admin-console/tests/fixtures/intent_classifier_benchmark_README.md (new)
- apps/admin-console/tests/test_classifier_benchmark.py (new)
- apps/admin-console/pyproject.toml (marker 加)
- .agents/reviews/2026-05-02-w9-3-baseline-accuracy.md (new, baseline 报告)

Verification:
- fixture 完整性: 100/100, ids unique, type distribution Counter({...})
- pytest test_classifier_benchmark.py: overall=X.XXX, per-class={A:..., B:..., ...}
  PASS/FAIL（PRD §F-R1 ≥ 90% 阈值）

Risks/notes:
- LLM 调用次数（100 条 query × 0.3-2s/query）
- 未达阈值的 query 列表已写入 baseline 报告
```

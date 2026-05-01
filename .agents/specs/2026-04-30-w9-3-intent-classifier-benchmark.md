---
title: "W9-3: 100 条意图识别基准集 + CI ≥ 90% gate"
date: 2026-04-30
owner: claude
status: ready-for-codex
audience: codex（实施）
wave: Wave 9
gap: "#15"
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
prd_anchor: docs/Agentic-RAG-PRD.md §F-R1（意图识别准确率 ≥ 90%）
---

# W9-3: 100 条意图识别基准集 + CI ≥ 90% gate

## 1. Goal

PRD Agentic-RAG §F-R1 明确要求意图识别（A/B/C/D/E/F/G 七类）在 100 条测试 query 上准确率 ≥ 90%。当前 `apps/admin-console/backend/api/chat.py:111` 的 `_classify_query_with_llm` 已实现 classifier，但**没有评测基线**，无法证明达到 90%，更无法防回归。

本 spec 建立：
- `apps/admin-console/tests/fixtures/intent_classifier_benchmark.jsonl` — 100 条标注查询
- `apps/admin-console/tests/test_classifier_benchmark.py` — 跑 classifier + 比对 + 计算准确率
- CI 集成：accuracy < 90% 或 per-class accuracy < 70% → fail PR

## 2. Non-goals

- **不**改 `_classify_query_with_llm` 实现（仅评测它）
- **不**收集生产 access log（隐私 + 当前没有日志聚合管道）；用 PRD 已有 example query + 人工扩展
- **不**做多语言 benchmark（中文为主，英文可少量但本 spec 不强制）
- **不**做置信度 calibration（评测是 hard accuracy，不是 likelihood）

## 3. User-visible behavior

- CI 运行 `pytest tests/test_classifier_benchmark.py` 时：
  - 加载 100 条 fixture
  - 对每条调用 chat.py 的 `_classify_query_with_llm`
  - 计算 overall accuracy + per-class accuracy
  - overall < 0.9 或任一 class < 0.7 → fail
- 失败时报告中列出每条 mismatched query 的 expected vs actual + reason
- 本地开发可跑 `uv run pytest tests/test_classifier_benchmark.py -v -k benchmark` 看完整结果

## 4. Affected paths

```
CREATE:
  apps/admin-console/tests/fixtures/intent_classifier_benchmark.jsonl  # 100 行
  apps/admin-console/tests/test_classifier_benchmark.py
  apps/admin-console/tests/fixtures/intent_classifier_benchmark_README.md  # 字段说明 + 编辑规则

MODIFY (可选):
  apps/admin-console/pyproject.toml — 加 pytest marker `requires_classifier_llm`
```

## 5. Architecture / Data flow

```
intent_classifier_benchmark.jsonl  ← 静态 fixture（git-tracked）
        ↓
test_classifier_benchmark.py 加载 100 条
        ↓
对每条 调用 chat.py._classify_query_with_llm(query)
        ↓
得 actual = {type, topic, name, reason}
        ↓
比对 expected_type；统计 overall + per-class
        ↓
assert overall >= 0.9 and min(per-class) >= 0.7
        ↓
失败时 print 每条 mismatch 详情
```

## 6. Interface contracts

### 6.1 Fixture JSONL 格式

每行一条：

```json
{
  "id": "Q001",
  "query": "介绍清华的丁文伯",
  "expected_type": "A",
  "expected_topic": "",
  "expected_name": "丁文伯",
  "category_label": "教授精确查询",
  "rationale": "明确指向单个教授对象，按姓名+院校匹配，类型 A 单域精确",
  "language": "zh",
  "source": "Agentic-RAG-PRD §2.1 type A example"
}
```

字段：
- `id`：`Q001`–`Q100` 唯一标识
- `query`：用户原始输入
- `expected_type`：`A`/`B`/`C`/`D`/`E`/`F`/`G` 之一
- `expected_topic`：可选，PRD 风格的"topic"语义；空字符串表示无强期望
- `expected_name`：可选，A/G 类常涉及人名/企业名
- `category_label`：人类可读的中文类别标签
- `rationale`：标注理由（一句话）
- `language`：`zh` / `en`
- `source`：`PRD example` / `manual` / `production` / 其他

### 6.2 类别分布（按 PRD §2.1 现实分布）

| 类型 | 数量 | 比例 | 含义 |
|---|---|---|---|
| A | 50 | 50% | 单域精确（教授姓名 / 企业名 / 专利号 / 论文标题） |
| B | 20 | 20% | 单域语义（"做 XX 的教授" 类）+ 多轮收窄子情境 |
| C | 15 | 15% | 跨域跳转（"他的论文" 等需上下文） |
| D | 5  | 5%  | 全景式跨域聚合（"做 XX 的教授和企业"） |
| E | 5  | 5%  | 知识问答（PRD §2.1 type E 例） |
| F | 3  | 3%  | 拒答（"今天天气" 类） |
| G | 2  | 2%  | 同名歧义（"无界智航"、"张三教授") |

100 条总；每类至少 5 条以避免小样本不稳定（F/G 例外，因这两类样本天然少）。

### 6.3 测试代码结构

```python
# apps/admin-console/tests/test_classifier_benchmark.py
import json
from pathlib import Path
import pytest

from backend.api.chat import _classify_query_with_llm

FIXTURE = Path(__file__).parent / "fixtures" / "intent_classifier_benchmark.jsonl"
PASS_OVERALL = 0.90
PASS_PER_CLASS = 0.70


@pytest.fixture(scope="module")
def benchmark_cases() -> list[dict]:
    cases = []
    with FIXTURE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    assert len(cases) == 100, f"expected 100 cases, got {len(cases)}"
    return cases


@pytest.mark.requires_classifier_llm
def test_classifier_benchmark(benchmark_cases):
    results = []
    for case in benchmark_cases:
        actual = _classify_query_with_llm(case["query"])
        actual_type = (actual or {}).get("type", "UNKNOWN")
        results.append({
            **case,
            "actual_type": actual_type,
            "match": actual_type == case["expected_type"],
        })

    overall = sum(r["match"] for r in results) / len(results)
    by_class = {}
    for cls in {"A", "B", "C", "D", "E", "F", "G"}:
        cls_results = [r for r in results if r["expected_type"] == cls]
        if not cls_results:
            continue
        by_class[cls] = sum(r["match"] for r in cls_results) / len(cls_results)

    # 失败时 print 详情
    if overall < PASS_OVERALL or any(v < PASS_PER_CLASS for v in by_class.values()):
        mismatches = [r for r in results if not r["match"]]
        for m in mismatches:
            print(f"  MISS [{m['expected_type']}→{m['actual_type']}] {m['id']}: {m['query']}")
        print(f"\n  Overall: {overall:.3f} (gate {PASS_OVERALL})")
        for cls, acc in sorted(by_class.items()):
            print(f"  {cls}: {acc:.3f} (gate {PASS_PER_CLASS})")

    assert overall >= PASS_OVERALL, f"overall {overall:.3f} < {PASS_OVERALL}"
    for cls, acc in by_class.items():
        assert acc >= PASS_PER_CLASS, f"{cls} {acc:.3f} < {PASS_PER_CLASS}"
```

### 6.4 pytest marker 注册

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "requires_classifier_llm: classifier benchmark; needs LLM (gemma-4) reachable",
]
```

CI 默认跑这个 marker；本地开发若 LLM 不可达，会失败但提示明确。

## 7. Invariants

1. fixture 100 条不多不少；增减必须改 spec
2. 每条必有 `id` / `query` / `expected_type` / `category_label` / `rationale`
3. id 全局唯一（`Q001`-`Q100`）
4. expected_type 必在 `{A,B,C,D,E,F,G}`
5. 任何 fixture 修改必带 commit message 说明（添加 / 修正 / 删除哪条以及为什么）
6. 测试在 CI 环境 LLM 不可达时 fail（不 skip）—— 因为 PRD 是产品验收，必须强制
7. 不得在测试代码中"猜" classifier 行为（不能 hardcode 期望非 expected_type 的 type）

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| LLM 返回 None（classifier 错误） | actual_type 取 `"UNKNOWN"`；视为不 match |
| LLM 返回不在 enum 内的 type | 按实际字符串比对，不会 match |
| 同一 query 在 LLM 上出现 non-determinism | 测试用 temperature=0（chat.py 已是）；如仍不稳定，需 codex 与 claude 协商加 retry |
| Fixture 空行 / 注释行 | 跳过 |
| Fixture 文件缺失 | 测试 fail with 明确错误 |

## 9. Failure modes

- LLM 服务挂 → benchmark fail；非 W9-3 范围（基础设施问题）
- LLM 升级导致 classifier 行为变化 → benchmark 报告 mismatch；触发 spec § 编辑修正 fixture 或调整 prompt（chat.py）

## 10. Validation commands

```bash
cd apps/admin-console

# 仅本地（LLM 可达）
uv run pytest tests/test_classifier_benchmark.py -v

# CI 模拟
uv run pytest tests/test_classifier_benchmark.py -m requires_classifier_llm -v --no-cov

# fixture 完整性快速检查
python3 -c "
import json
from pathlib import Path
fixture = Path('tests/fixtures/intent_classifier_benchmark.jsonl')
cases = [json.loads(l) for l in fixture.read_text().splitlines() if l.strip()]
assert len(cases) == 100, len(cases)
ids = [c['id'] for c in cases]
assert len(set(ids)) == 100, 'duplicate ids'
types = {c['expected_type'] for c in cases}
assert types == set('ABCDEFG'), f'missing types: {set(\"ABCDEFG\") - types}'
from collections import Counter
print(Counter(c['expected_type'] for c in cases))
"
# 期望: Counter({'A': 50, 'B': 20, 'C': 15, 'D': 5, 'E': 5, 'F': 3, 'G': 2})
```

## 11. Expected evidence

- ✅ 100 条 fixture 入 git
- ✅ test_classifier_benchmark.py 通过（accuracy 第一次跑结果归档）
- ✅ 第一次跑的 accuracy 报告写入 `.agents/reviews/2026-XX-XX-w9-3-baseline-accuracy.md`，含每类 accuracy 数字
- ✅ pyproject.toml 含 marker

## 12. Assumptions

- `_classify_query_with_llm` 接口稳定；LLM 默认 temperature=0
- gemma-4 LLM 在 CI / local 都可达（如 CI 没有，需先在 dev infra 配；可标 skip-on-no-LLM 但作为 W11+ 跟进，本 spec 仍要求 fail）
- PRD §2.1 的 query example 当前足够代表性

## 13. Open questions（claude 自决，2026-05-01）

- [x] **数据来源**：PRD §2.1 example + 人工扩展（不取生产 log）。理由：当前没有日志聚合 + 隐私顾虑
- [x] **类别分布**：按 PRD 现实分布（A 50% B 20% ...），最小每类 5 条。F/G 例外（实际占比小，本身样本难凑）
- [x] **通过门**：overall ≥ 90% + per-class ≥ 70%。理由：overall 顶住 PRD F-R1，per-class 防止小类掉队
- [x] **运行环境**：integration 测试 + 真实 LLM；fixture 不 mock。CI 环境必须配 LLM
- [x] **失败行为**：LLM 不可达时 fail（不 skip）。理由：basis 是产品验收门
- [x] **fixture 是否含真实姓名**：是（公开信息，无隐私）。"丁文伯"（清华教授官网公开）、"优必选"（上市公司）等
- [x] **第一次 baseline 是否在 W9-3 内打**：是。codex 实施时跑一次，归档到 `.agents/reviews/2026-XX-XX-w9-3-baseline-accuracy.md`

**所有阻塞 codex 实施的决策已锁定；本 spec 状态：`ready-for-codex`**。

## 14. 与其他 spec / wave 的衔接

- W9-1 完成后教授卡片 metrics 暴露不影响本 spec（classifier 输入仅 query 文本）
- W11-1 (C 类型一级实装)：W11-1 落地后 C 类型 fixture 必须重新评估；可能需要扩 5-10 条新 C 多轮 query
- W11-2 / W11-3 / W11-4 同理
- 本 spec 是后续所有 chat 改进的回归基线

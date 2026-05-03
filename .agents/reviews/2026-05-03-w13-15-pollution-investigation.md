---
title: "W13-15 fixture pollution investigation 完整调研"
date: 2026-05-03
owner: claude
status: investigation-complete
related_specs:
  - .agents/specs/2026-05-02-w13-15-test-fixture-pollution.md
context: 大批量 pytest run 25 fail / 单文件 PASS；调研后定位污染源 + 修复路径
---

# W13-15 fixture pollution 完整调研报告

## 1. 现象

```
$ pytest tests/data_agents/professor/ tests/data_agents/company/ \
         tests/data_agents/test_run_id_wiring.py \
         tests/data_agents/test_contracts.py \
         tests/data_agents/test_runtime.py
======= 25 failed, 879 passed, 1 xfailed =======
```

但每个失败文件**单独跑都 PASS**：
- `test_summary_generator.py` 单跑 9 passed
- `test_web_search_enrichment.py` 单跑 30+1xfail
- `test_runtime.py` 单跑 15 passed
- `test_serper_news_connector.py` 单跑 11 passed
- `test_contracts.py` 单跑 19 passed

## 2. Bisect 路径

| 子集 | 结果 |
|---|---|
| prof/ + company/ + 3 test_*.py 单一 | 25 fail |
| prof/ 单跑 | **21 fail** ← 污染完全在 prof/ 内部 |
| company/ 单跑 | 84 passed |
| prof/ 前 30 文件 | 428 passed |
| prof/ 末 18 文件 | 21 fail |
| 末 8 (sed -n '40,47p' = roster_validation → vectorizer) | 3 fail (test_summary_generator) |
| 末 7 (school_adapters → vectorizer，不含 roster_validation) | passes |
| `test_roster_validation + test_summary_generator` 顺序跑 | **3 fail** |
| `test_summary_generator + test_roster_validation` 反向跑 | passes |

## 3. 根因

```python
RuntimeError: This event loop is already running
  File "asyncio/base_events.py:626", in _check_running

# pytest-asyncio plugin warning:
RuntimeWarning: Error cleaning up asyncio loop: Cannot run the event loop
  while another loop is running
RuntimeWarning: coroutine 'BaseEventLoop.shutdown_asyncgens' was never awaited
```

**`tests/data_agents/professor/test_roster_validation.py`** 中某个 async test / fixture 启动了
asyncio event loop 后**没有正确 teardown**。test_summary_generator 中 `TestGenerateSummaries`
的 3 个 test 用 `asyncio.run` 调 LLM 时拿到 already-running loop，触发 RuntimeError。

## 4. 直接受污染的 3 个 test

```
test_summary_generator.py::TestGenerateSummaries::test_with_valid_llm_response
test_summary_generator.py::TestGenerateSummaries::test_falls_back_to_rule_based_summaries_when_llm_raises
test_summary_generator.py::TestGenerateSummaries::test_falls_back_when_llm_returns_invalid_length_outputs
```

剩 18 个 fail（test_web_search_enrichment / test_serper / test_runtime）应该是**二次污染**：
被 test_summary_generator 已损坏的 event loop 进一步污染。

## 5. 修复方向（按推荐度）

### 方案 A（推荐）：conftest.py 加 autouse fixture 重置 event loop
```python
# apps/miroflow-agent/tests/data_agents/professor/conftest.py
import asyncio
import pytest

@pytest.fixture(autouse=True)
def _reset_event_loop_per_function():
    """Some async tests in test_roster_validation leak running event loops;
    reset per function so subsequent tests that call asyncio.run don't fail
    with 'event loop is already running'."""
    yield
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop()
        loop.close()
    except (RuntimeError, AttributeError):
        pass
    asyncio.set_event_loop(asyncio.new_event_loop())
```

### 方案 B：定位 roster_validation 中 async fixture 修 teardown
- 在 `test_roster_validation.py` 找出哪个 async test/fixture 没用 `pytest_asyncio.fixture`
- 改为 `@pytest_asyncio.fixture(scope='function')`

### 方案 C：升级 pytest-asyncio mode
- 确认 `pyproject.toml` 含 `asyncio_mode = "auto"` 或 `"strict"`；如缺失加上 strict
- 让 pytest-asyncio 强制管理 event loop

## 6. 验证条件

修复后必须满足：
```bash
# 大批跑：0 fail
pytest tests/data_agents/professor/ tests/data_agents/company/ -n0 --no-cov

# 单跑：仍全 PASS
pytest tests/data_agents/professor/test_roster_validation.py -n0 --no-cov
pytest tests/data_agents/professor/test_summary_generator.py -n0 --no-cov
```

## 7. Open questions

- 是否同时修 `test_web_search_enrichment.py` 的潜在 leak？（推测被 test_summary_generator 二次污染，自身无 leak）
- 是否需要全仓 `pytest_asyncio.fixture` 审计？

## 8. 推荐 follow-up spec

起 W13-15-impl spec：
1. 加 `apps/miroflow-agent/tests/data_agents/professor/conftest.py` 用方案 A 实现
2. 加 `apps/miroflow-agent/tests/data_agents/conftest.py`（如不存在）作为通用层
3. 单测加 marker 验证 fixture 起作用
4. CI 加 `pytest tests/data_agents/professor/ -n0 --no-cov` 不退化检查

## 9. 已落 commit

无（本调研未改源码；fix 由后续 W13-15-impl spec 落地）

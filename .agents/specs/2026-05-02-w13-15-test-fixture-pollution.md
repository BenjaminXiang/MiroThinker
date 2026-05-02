---
title: "W13-15: 测试 fixture pollution 调研 — 25 单跑 PASS / 批跑 FAIL"
date: 2026-05-02
owner: claude
status: ready-for-codex（先调研后修）
audience: codex（调研 + 报告 → 等 claude 决策修复方案）
wave: Wave 13 follow-up
context: W13-D1 v2 大批量 pytest 25 failures；同 25 个测试单文件跑全 PASS
---

# W13-15: 测试 fixture pollution 调研

## 1. Goal

W13-D1 v2 land 后实测：

```
$ pytest tests/data_agents/professor/ tests/data_agents/company/ tests/data_agents/test_run_id_wiring.py
  tests/data_agents/test_contracts.py tests/data_agents/test_runtime.py -n0 --no-cov
======= 25 failed, 879 passed, 1 xfailed, 48 warnings in 86.00s =======
```

但单文件直跑：
```
$ pytest tests/data_agents/professor/test_summary_generator.py -n0 --no-cov
======= 9 passed in 0.36s =======

$ pytest tests/data_agents/test_runtime.py -n0 --no-cov
======= 15 passed in 2.61s =======

$ pytest tests/data_agents/company/test_serper_news_connector.py -n0 --no-cov
======= 11 passed in 0.46s =======
```

= **fixture pollution / monkeypatch 全局态污染** — 测试相互依赖。

## 2. 假设根因

候选：

1. **monkeypatch 全局 module 属性**（如 `pymilvus.MilvusClient`）后没在 fixture teardown 恢复
2. **lru_cache 跨测试持久**：admin-console 的 `_get_milvus_client / _get_embedding_client` 被 cache，第一次调用结果污染后续测试
3. **环境变量被 export**：某个测试 set os.environ 没在 teardown 删
4. **conftest.py 共享 fixture 顺序**：autouse fixture 副作用被错序执行
5. **数据库状态未 truncate**：某个测试 insert 后没 rollback；后续测试看到老数据

## 3. 调研步骤（codex 做）

```bash
cd apps/miroflow-agent
unset https_proxy HTTPS_PROXY

# Step 1: 复现 25 failures
DATABASE_URL_TEST=... uv run pytest \
    tests/data_agents/professor/ tests/data_agents/company/ \
    tests/data_agents/test_run_id_wiring.py tests/data_agents/test_contracts.py \
    tests/data_agents/test_runtime.py \
    -n0 --no-cov --tb=short 2>&1 | tee /tmp/w13-15-failures.log

# Step 2: 二分定位是哪些 test 引发污染
# 把 25 个失败 test 单独跑 → 全 pass，确认单跑无问题
# 用 pytest -p no:randomly --collect-only 列 test 顺序
# 注释掉前 10 个 file → 看 25 fail 是否变 0

# Step 3: 检查 conftest.py
find apps/miroflow-agent/tests -name conftest.py | xargs grep -nl "monkeypatch\|os.environ\|lru_cache\|MilvusClient"

# Step 4: 检查 lru_cache 清理
grep -rn "lru_cache" apps/miroflow-agent/src apps/admin-console/backend
# 这些 cache 在测试间不会自动清空
```

## 4. 修复策略（按调研结果）

| 假设 | 修复 |
|---|---|
| lru_cache 污染 | 加 `@pytest.fixture(autouse=True)` 在 conftest 调 `_get_xxx.cache_clear()` |
| os.environ 污染 | 测试用 `monkeypatch.setenv` 而非 `os.environ[...] = ...` |
| pymilvus 全局 patch 污染 | 用 `pytest.MonkeyPatch.context()` 隔离每个 test |
| DB 状态污染 | 每个 test 用 transaction rollback fixture |

## 5. Affected paths（修复阶段）

```
修改（按调研结论）：
  apps/miroflow-agent/tests/conftest.py
  apps/miroflow-agent/tests/data_agents/conftest.py（如不存在则创建）
  apps/miroflow-agent/src/data_agents/professor/llm_profiles.py
    （如有 lru_cache，加 cache_clear helper）
  apps/admin-console/backend/deps.py
    （考虑暴露 cache_clear functions for tests）

新增：
  apps/miroflow-agent/tests/test_fixture_isolation.py
    - 跑两个相互可能污染的 test，验证彼此独立
```

## 6. Validation

```bash
# 修复后大批跑应该全过
DATABASE_URL_TEST=... uv run pytest tests/data_agents/professor/ \
    tests/data_agents/company/ tests/data_agents/test_run_id_wiring.py \
    tests/data_agents/test_contracts.py tests/data_agents/test_runtime.py \
    -n0 --no-cov 2>&1 | tail -5
# 期望：0 failed
```

## 7. Done criteria

调研阶段：
1. ✅ 25 failures 根因定位（前 3 假设至少排除 / 确认 1 个）
2. ✅ 报告写到 `.agents/reviews/2026-05-02-w13-15-pollution-investigation.md`

修复阶段（按报告结论起 follow-up）：
1. ✅ 大批 pytest 0 failed
2. ✅ ruff / lint 通过
3. ✅ 不引入新依赖

## 8. Open questions

| 问题 | 默认决策 |
|---|---|
| 是否在 CI 加固定 pytest 顺序（-p no:randomly）？| 否；测试应该顺序无关 |
| pytest-xdist 并行是否同样有问题？| 暂不调研；本 spec 仅看 -n0 |
| W13-D1 引入还是 W13-D1 之前已有？| 调研第一步：在 commit 41b43ca 之前 reset HEAD~1 跑同样命令对比 |

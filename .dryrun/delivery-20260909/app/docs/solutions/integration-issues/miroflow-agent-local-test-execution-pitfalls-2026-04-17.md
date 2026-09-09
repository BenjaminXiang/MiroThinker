---
title: miroflow-agent Local Test Execution Pitfalls
date: 2026-04-17
category: docs/solutions/integration-issues
module: professor-data-pipeline
problem_type: local_env_mismatch
status: active
component: test-execution
severity: medium
tags: [pytest, uv, environment, miroflow-agent, local-testing]
---

# miroflow-agent Local Test Execution Pitfalls

## Problem

在本地为 `apps/miroflow-agent` 跑定向回归时，测试经常不是死在代码逻辑，而是死在执行环境：`pytest` addopts、`PYTHONPATH`、依赖环境、以及错误的 venv 混用。

## Confirmed Failure Modes

### 1. 直接跑 `pytest` 会吃到项目默认 `addopts`

已确认现象：

```text
pytest: error: unrecognized arguments: -n=auto --html=report.html --self-contained-html
```

原因：

- `apps/miroflow-agent/pyproject.toml` 里配置了默认 `addopts`
- 当前 shell 环境没有对应的 pytest 插件
- 所以逻辑还没开始跑，参数解析就先失败

### 2. 直接跑 `pytest` 容易缺项目依赖

已确认现象：

```text
ModuleNotFoundError: No module named 'json_repair'
```

原因：

- 直接用系统 Python 或错误 venv 跑测试时，没有进入 `miroflow-agent` 项目自己的依赖环境
- 项目依赖虽然在 `uv.lock` 里，但并不会自动注入到当前 shell

### 3. 从错误工作目录运行会导致测试路径错误

已确认现象：

- 在 `apps/miroflow-agent` 目录里，继续使用 repo-root 相对路径，会报 `file or directory not found`

原因：

- 测试路径和工作目录不一致
- 这是纯执行问题，不是测试文件不存在

### 4. admin-console 的 venv 会和 miroflow-agent 项目环境冲突

已确认现象：

```text
warning: VIRTUAL_ENV=/home/longxiang/MiroThinker/apps/admin-console/.venv does not match the project environment path `.venv` and will be ignored
```

原因：

- 当前 shell 继承了 `apps/admin-console/.venv`
- 但 `miroflow-agent` 应该使用自己项目的 `uv` 环境
- `uv run` 会忽略不匹配的 `VIRTUAL_ENV`，但这个 warning 容易误导排查方向

## Working Command

当前已验证可用的最小命令是：

```bash
cd /home/longxiang/MiroThinker/apps/miroflow-agent
unset VIRTUAL_ENV
uv run pytest -q -o addopts='' tests/data_agents/professor/test_school_adapters.py tests/data_agents/professor/test_roster_validation.py
```

同一规则也已在 2026-04-17 UTC 复验通过更大的 professor rebuild 回归集：`58 passed`。

这条命令的关键点：

- 工作目录必须是 `apps/miroflow-agent`
- 通过 `uv run` 进入项目自己的依赖环境
- 通过 `-o addopts=''` 临时去掉项目默认 `pytest` addopts
- 测试路径必须相对于当前工作目录写

## Recommended Rule

后续在 `miroflow-agent` 做任何定向回归，默认都按下面规则执行：

1. 先 `cd apps/miroflow-agent`
2. 如果当前 shell 继承了 `apps/admin-console/.venv`，先 `unset VIRTUAL_ENV`
3. 一律优先用 `uv run pytest`
4. 定向回归默认追加 `-o addopts=''`
5. 测试文件路径一律写成 `tests/...`
6. 不要复用 `admin-console` 的 venv 来跑 `miroflow-agent` 测试

## Admin Console test env pitfalls

已确认 `apps/admin-console` 也有一类非常像“缺依赖”、但根因是“命令跑错解释器”的问题。

### 已确认现象

```text
Form data requires "python-multipart" to be installed.
```

同时 traceback 指向：

```text
~/.local/lib/python3.10/site-packages/fastapi/...
```

### 真正根因

- `apps/admin-console/.venv` 里其实已经安装了 `python-multipart`
- 但如果直接运行 `pytest`，shell 会优先命中全局 `pytest`
- 最终导入的是全局 Python 3.10 环境，而不是项目 `.venv` / `uv run python`

### 当前可用命令

```bash
cd /home/longxiang/MiroThinker/apps/admin-console
PYTHONPATH=/home/longxiang/MiroThinker/apps/miroflow-agent uv run python -m pytest -q tests
```

已在 2026-04-17 UTC 复验通过：`41 passed`。

关键点：

- 用 `uv run python -m pytest`，不要直接用 `pytest`
- 如果测试依赖 `miroflow-agent` 的 `src/...` 包，补上 `PYTHONPATH=/home/longxiang/MiroThinker/apps/miroflow-agent`

## `milvus_lite` / `pkg_resources` / setuptools trap

已确认另一类非常像“Milvus 挂了”的失败，其实是 Python 打包栈漂移。

### 已确认现象

```text
ModuleNotFoundError: No module named 'pkg_resources'
```

触发位置通常在：

- `milvus_lite`
- `pymilvus`
- 依赖 `MilvusVectorStore` 的 service / retrieval 测试

### 真正根因

- 当前 `uv` 环境如果解到较新的 `setuptools`，可能不再提供 `pkg_resources`
- `milvus_lite` 仍依赖 `pkg_resources`
- 结果就是向量库一初始化就失败，看起来像 Milvus 或测试代码回归

### 当前已验证的修复

项目级约束已经补上：

- `apps/miroflow-agent/pyproject.toml` 直接声明 `setuptools<81`
- `uv.lock` 已锁到兼容版本

所以后续不要再在 shell 里临时 `pip install setuptools==...` 硬修；那样一旦 `uv run` 重新同步环境，问题会复发。

### 推荐规则

1. `miroflow-agent` 相关测试一律通过 `uv run` 进入锁定环境
2. 如果再次出现 `pkg_resources` 缺失，先检查 `pyproject.toml` 和 `uv.lock` 是否被改坏
3. 不要把这类报错误判成 Milvus service outage 或代码逻辑回归

## Why This Matters

如果不先把执行环境收紧，会反复把“环境缺件”误判成“代码回归失败”，从而浪费时间在无效重试上。当前 professor 重构要求每一步都跑真实 E2E 和定向回归，所以这条执行规范必须固定下来。


## Local HTTP model services and proxy env

When probing repo-local embedding or rerank services on `http://100.64.*`, clear `all_proxy`, `http_proxy`, and `https_proxy` first. Otherwise the request can fail through a SOCKS/proxy path and look like a model outage even when the service is healthy.


## Real E2E web search credentials

Professor real-data E2E only enables `web search` when `SERPER_API_KEY` is present.

Confirmed pitfall:

- `source scripts/load_professor_e2e_env.sh` only works if repo-local `.serper_api_key` exists or the env var is already exported
- if the key is missing, the run does **not** fail loudly; it simply behaves like `search_provider = None`, and the summary will show `0 web searched`

Recommended rule:

1. keep repo-local `.serper_api_key` in place for real professor E2E
2. or explicitly `export SERPER_API_KEY=...` before running `run_professor_url_md_e2e.py`
3. if a supposedly fixed paper-backed issue still shows `0 web searched`, treat that as an environment regression first, not a logic regression

## OpenAI/httpx SOCKS proxy trap

When running one-off real LLM checks with `openai.OpenAI(...)`, inherited proxy env can fail **before** the request reaches the model service.

Confirmed pitfall:

- if `all_proxy/http_proxy/https_proxy` points to a SOCKS proxy
- and the environment does not have `socksio` installed
- `httpx` raises:

```text
ImportError: Using SOCKS proxy, but the 'socksio' package is not installed.
```

This is an environment issue, not a `gemma4` or DashScope outage.

Recommended rule:

1. before ad-hoc real LLM validation, clear
   - `all_proxy`
   - `ALL_PROXY`
   - `http_proxy`
   - `HTTP_PROXY`
   - `https_proxy`
   - `HTTPS_PROXY`
2. or reuse the same proxy-clearing semantics as professor pipeline `_clear_proxy_env()`
3. if a standalone validation script fails during client construction, check proxy env first before blaming the model endpoint


## Claude cross-review prompt-size trap

在当前工作区里，`python3 scripts/claude_review.py` 并不是总能稳定返回。

已确认现象：

- `--dry-run` 能正常工作
- scope 太大时，真正的 review 调用可能长时间无输出
- 这时容易误以为是代码或 Claude CLI 不可用，其实更像是 prompt 过大或本地 review 流程在等待/卡住

推荐规则：

1. 先跑 `--dry-run` 确认 scope
2. 真正 review 时优先使用窄 `--path`
3. 代码 review 和文档 review 分开跑，不要一次塞整个工作区
4. 如果 review 长时间无输出，先缩 scope，而不是先怀疑代码变更本身
5. 即使 `claude_review.py --dry-run` 显示的 `prompt_bytes` 还在 200KB 量级，也不代表本地 `claude -p` 一定会稳定返回；当前机器上已经确认存在“子进程活着但持续无 stdout”的 transport 层静默问题，所以不要把 CLI 标称 context window 当成单次 review 一定可用的保证

## Unified exec session cap

当前工具层还有一个固定噪音：如果同时保留过多长跑命令或挂起 review，会反复出现：

```text
Warning: The maximum number of unified exec processes you can keep open is 60 ...
```

这不是 professor pipeline 的逻辑失败，而是本地代理工具的会话上限提醒。

推荐规则：

1. 长跑 E2E 只保留真正需要的几条
2. review / probe 尽量用短命令和窄 scope
3. 不要把这类 warning 当成抓取、LLM、或数据质量回归


## Async-heavy pytest batching trap

已确认另一类容易误判成“代码大面积回归”的问题，其实是 pytest 运行方式问题。

### 已确认现象

把多个 async-heavy professor 测试文件一次性拼成一条超长 `uv run pytest ...` 命令时，可能出现：

```text
RuntimeError: This event loop is already running
```

### 现象特征

- 单独跑 `tests/data_agents/professor/test_homepage_crawler.py`：通过
- 单独跑 `tests/data_agents/professor/test_paper_collector.py`：通过
- 单独跑 `tests/data_agents/professor/test_pipeline_v3.py`：通过
- 但把这些文件一次性串到同一条命令里，可能出现 event-loop 复用错误

### 推荐规则

1. async-heavy professor 回归优先按文件分组执行
2. 先跑最贴近当前改动的单文件回归，再决定是否扩组
3. 如果单文件都绿、但大拼盘命令炸 event loop，先视为测试执行环境问题，不要直接把它当成代码逻辑回归

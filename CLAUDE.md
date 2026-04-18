# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

深圳科创数据平台：一个面向深圳科创生态的对话式科创信息检索系统。用户通过微信公众号用自然语言提问，系统在教授、企业、论文、专利四个数据域中智能路由检索，返回结构化、可追溯的回答。

项目基于 MiroThinker 深度研究 agent 框架构建，复用其 agent runtime、多轮工具调用编排、搜索/抓取/抽取能力，在此之上构建了四域数据采集智能体和 Agentic RAG 检索服务层。

## Key Documentation

文档按分层结构组织，冲突时以共享规范为准。完整导航见 `docs/index.md`。

- **`docs/index.md`** — 文档导航与术语表（ID 前缀、摘要字段命名、evidence 结构、去重锚点）
- **`docs/Data-Agent-Shared-Spec.md`** — 四域共享权威源：架构、逻辑契约、质量标准、MiroThinker 实现映射
- **`docs/{Company,Professor,Paper,Patent}-Data-Agent-PRD.md`** — 各域特有需求
- **`docs/Professor-Pipeline-V2-User-Guide.md`** — 教授 Pipeline V2 使用说明（运行、配置、检索、排查）
- **`docs/Agentic-RAG-PRD.md`** — 面向用户的检索增强智能体（服务层）：查询分类（A-G 七种类型）、语义路由、多源召回/融合/rerank
- **`docs/Multi-turn-Context-Manager-Design.md`** — 多轮对话上下文管理器：指代消解、跨模块跳转、话题切换检测
- **`docs/solutions/`** — 经验沉淀：部署模式、基础设施问题、集成陷阱

`docs/solutions/` 下的经验文档按 `docs/solutions/<category>/` 分类存放，并使用 YAML frontmatter 标记 `module`、`problem_type`、`component`、`tags` 等检索字段。这些文档在实现、调试或调整已记录过的模块时通常最有价值。

## Common Commands

```bash
# Task runner: just (https://github.com/casey/just)
# Package manager: uv (https://docs.astral.sh/uv/)

# Install dependencies (from repo root)
uv sync

# Linting & formatting (from repo root, pinned to ruff@0.8.0)
just lint              # Ruff linter with auto-fix
just format            # Ruff formatter
just sort-imports      # Organize imports
just precommit         # Run all pre-commit checks (lint + format + license + markdown)

# License compliance
just check-license     # Verify REUSE license headers
just insert-license    # Add missing license headers

# Markdown formatting
just format-md         # Format with mdformat

# Tests (from apps/miroflow-agent/)
cd apps/miroflow-agent
uv run pytest                              # Run all tests (parallel by default via -n=auto in pyproject.toml)
uv run pytest tests/test_foo.py            # Single test file
uv run pytest -k "test_name"               # Single test by name
uv run pytest -m unit                      # By marker: unit, integration, slow, requires_api_key
uv run pytest -n0                          # Disable parallel execution for debugging

# Running the agent (from apps/miroflow-agent/)
uv run python -m src.core.pipeline agent=mirothinker_v1.5 llm=default benchmark=debug
# Override Hydra config groups: agent=<variant> llm=<provider> benchmark=<suite> data_agent=<config>

# Data agent E2E scripts (from apps/miroflow-agent/)
uv run python scripts/run_company_import_e2e.py
uv run python scripts/run_professor_crawler_e2e.py
uv run python scripts/run_paper_release_e2e.py
uv run python scripts/run_patent_import_e2e.py
```

## Architecture

### Monorepo Layout

- **`apps/miroflow-agent/`** — Core agent framework (primary app). Hydra-based config in `conf/`, source in `src/`.
- **`apps/collect-trace/`** — Harvests training data from agent runs, converts to SFT/DPO format.
- **`apps/gradio-demo/`** — Local web UI using Gradio + vLLM.
- **`apps/visualize-trace/`** — Flask dashboard for analyzing agent reasoning traces.
- **`apps/lobehub-compatibility/`** — LobeChat integration adapter.
- **`libs/miroflow-tools/`** — Shared library: `ToolManager` + pre-built MCP servers.
- **`docs/solutions/`** — Documented solutions to past implementation/debugging issues.

### Core Agent Runtime (`apps/miroflow-agent/src/core/`)

The base runtime from MiroThinker, reused by both benchmark tasks and data agents:

- **Pipeline** — Factory & entry point: creates tool managers, formatters, kicks off task execution.
- **Orchestrator** — Main execution loop: multi-turn reasoning, sub-agent delegation, context compression, rollback.
- **ToolExecutor** — Runs tool calls with retries/error handling; handles both MCP tools and sub-agent calls.
- **AnswerGenerator** — Produces final answers; supports both `\boxed{}` (benchmark) and JSON (data agents) output modes.
- **StreamHandler** — Real-time streaming event management.

### Data Agents (`apps/miroflow-agent/src/data_agents/`)

Four domain-specific data collection agents built on top of the core runtime. Each follows the shared spec in `docs/Data-Agent-Shared-Spec.md`.

**Shared layer:**
- **`contracts.py`** — Pydantic models for all domains: `Evidence`, `QualityStatus`, `ObjectType`, ID prefixes (`PROF-`, `COMP-`, `PAPER-`, `PAT-`), Shenzhen institution keywords.
- **`runtime.py`** — Structured-output task execution: wraps `pipeline.py` to emit validated JSON instead of `\boxed{}` answers.
- **`normalization.py`** / **`linking.py`** / **`evidence.py`** — Cross-domain normalization, entity linking, evidence tracking.
- **`publish.py`** — Publishing pipeline for release artifacts.
- **`providers/`** — LLM adapters (MiroThinker, Qwen) and web search provider, configured via `conf/data_agent/default.yaml`.
- **`storage/`** — SQLite and Milvus persistence. **`service/`** — Cross-domain search service.

**Domain modules** (each has `models.py`, pipeline, import/enrichment, release):
- **`company/`** — Import from 企名片 xlsx, enrichment via web scraping, profile/evaluation/tech-route summary generation.
- **`professor/`** — Roster discovery from Shenzhen university websites, profile enrichment, name selection/disambiguation, validation.
- **`paper/`** — Professor-anchored paper collection from Semantic Scholar, OpenAlex, CrossRef; hybrid merge; professor feedback loop.
- **`patent/`** — Import from patent xlsx, company/professor linkage, summary generation.

### Hydra Configuration (`apps/miroflow-agent/conf/`)

- **`config.yaml`** — Entry point with defaults: `llm`, `agent`, `benchmark`, `data_agent`.
- **`agent/`** — 13 agent variants. `default.yaml` defines main_agent tools + sub_agents. `mirothinker_v1.5.yaml` is the main research variant.
- **`llm/`** — 4 LLM provider configs (default, Claude 3.7, GPT-5, Qwen-3).
- **`benchmark/`** — 17 benchmark suite configs.
- **`data_agent/`** — Data agent configs (provider endpoints, output paths, publish settings).

### MCP Tool Ecosystem (`libs/miroflow-tools/`)

`ToolManager` manages MCP server lifecycle (stdio/SSE transports). Servers in `mcp_servers/`:
- Search: Google, Sogou, Serper
- Execution: Python sandbox (local + E2B)
- Extraction: Vision (VQA), Audio transcription, Document reading
- Reasoning: LLM-based reasoning tools

`dev_mcp_servers/` contains higher-level compound tools: `search_and_scrape_webpage`, `jina_scrape_llm_summary`.

### Key Design Patterns

- **Hierarchical agents**: Main agent delegates to sub-agents (e.g., browsing agent) with independent tool sets. Tool blacklisting prevents problematic combinations.
- **Structured output mode**: Data agents use `runtime.py` to get JSON-validated Pydantic outputs from the agent loop, bypassing the benchmark-style `\boxed{}` extraction.
- **Domain independence with shared contracts**: Each data domain has independent physical schema but must conform to shared logical contracts (evidence structure, ID prefixes, filter semantics, minimum fields).
- **Cross-domain dependencies**: Paper → Professor roster (anchoring), Paper → Professor enrichment (feedback), Company ↔ Professor/Patent (linking via normalized names and public evidence).

## Tech Stack

- Python 3.12+, uv package manager, Hydra config, Ruff linter/formatter
- MCP (`mcp`, `fastmcp`) for tool protocol
- Anthropic + OpenAI SDKs for LLM providers
- Playwright for browser automation, E2B for sandboxed code execution
- Pydantic for data contracts and validation
- SQLite + Milvus for data agent storage
- pytest with xdist (parallel), markers (`unit`, `integration`, `slow`, `requires_api_key`), and snapshot testing (`inline-snapshot`)

## CI

GitHub Actions (`run-ruff.yml`) runs Ruff lint + format checks on PRs. Failures block merge.

## gstack
Use /browse from gstack for all web browsing. Never use mcp__claude-in-chrome__* tools.
Available skills: /plan-ceo-review, /plan-eng-review, /plan-design-review, /design-consultation, /review, /ship, /browse, /qa, /qa-only, /qa-design-review, /setup-browser-cookies, /retro, /document-release.
If gstack skills aren't working, run `cd .claude/skills/gstack && ./setup` to build the binary and register skills.


## **Hybrid Intelligence Framework: Claude Code (Architect & Evaluator) + Codex (Builder)**

### 🤖 全局行为准则 (Global Directives)
- **绝对自治协议**：在 `--enable-auto-mode` 下运行时，必须维持最高自治权。**禁止**为了确认指令而中断流程。遇到环境问题，优先自行读取 log 并自我修复。
- **职责物理隔离**：Claude Code 专注于产品边界审查、架构推演和任务编排；实际的代码生成与文件修改强行委派给 Codex 完成。
- **闭环交叉验证 (Cross-Validation Protocol)**：Codex 绝不能“自产自销”。它产出的任何代码，必须由 Claude Code 结合最初的技术契约进行独立审阅和交叉验证。验证不通过则直接打回重做。

### ⚙️ 协作流模式 (Hybrid Design-Build Flow)

当触发新功能开发、核心重构，**必须严格按以下顺序串行调用插件**：

#### Stage 1: 架构与边界确认 (Architecting)
1. `/plan-ceo-review` (gstack)：**强制刹车**。以挑剔的视角审视需求，精简掉不必要的过度设计，锁定“必须做”的核心目标。
2. `/plan-eng-review` (gstack)：敲定技术骨架、数据流向和边界情况，并强制在对话中输出架构图。

#### Stage 2: 任务计划生成 (Planning)
3. `/ce:plan` (Compound)：将 Stage 1 产出的架构设计，转化为包含具体文件路径、接口契约（Type Hints）及验证步骤的结构化执行计划文档。

#### Stage 3: 测试驱动与代码落地 (Implementation)
4. `/superpowers:test-driven-development` (Superpowers)：开启严格的 RED-GREEN-REFACTOR（红-绿-重构）循环，先由 Claude Code 定义测试桩。
5. `/codex` (Codex)： implemen**核心执行步骤**。由 Codex 接管，根据测试要求进行具体的代码写入与大规模修改。

#### Stage 4: 交叉验证与深度防御 (Verification & Deep Review)
6. **Claude Code 交叉验证 (Cross-Validation)**：**强校验点**。Claude Code 必须主动读取 Codex 生成的源码，对照 Stage 2 的 `/ce:plan` 计划书逐行校验。检查逻辑是否对齐、类型注解是否完整。如发现偏差或“幻觉”，立即重新触发 Codex 进行修正。如果是Claude Code 实现的代码，必须使用 Codex 对照 Stage 2 的 `/ce:plan` 计划书逐行校验。 检查逻辑是否对齐、类型注解是否完整。如发现偏差或“幻觉”，立即重新触发 Claude Code 进行修正。
7. `/ce:review` ：**禁止挑剔代码风格**。多代理审查，专门排查常规 AI 容易漏掉的致命生产 Bug：N+1 数据库查询、并发竞争条件、安全信任边界越权。

#### Stage 5: 知识复利 (Compounding)
8. `/ce:compound` (Compound)：将本次迭代遇到的坑、架构决策及解决方案，永久沉淀至 `docs/solutions/` 目录，确保系统随时间推移越来越聪明。

### 🛠️ 项目约定 (Project Conventions)
- **语言/框架**：Python 3.11+, FastAPI (Async native)。
- **凭据管理**：Secrets、API Keys 必须通过环境变量注入，Codex 生成的代码严禁包含任何硬编码凭据。

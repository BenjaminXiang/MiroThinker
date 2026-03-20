# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MiroThinker is a deep research agent framework for research and prediction tasks, achieving 88.2 on BrowseComp. It's a monorepo with multiple apps and a shared tools library, built around MCP (Model Context Protocol) for tool standardization.

## Common Commands

```bash
# Task runner: just (https://github.com/casey/just)
# Package manager: uv (https://docs.astral.sh/uv/)

# Install dependencies (from apps/miroflow-agent/)
uv sync

# Linting & formatting
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
uv run pytest                              # Run all tests
uv run pytest tests/test_foo.py            # Single test file
uv run pytest -k "test_name"               # Single test by name
uv run pytest -m unit                      # By marker: unit, integration, slow, requires_api_key
uv run pytest -n auto                      # Parallel execution
```

## Architecture

### Monorepo Layout

- **`apps/miroflow-agent/`** — Core agent framework (primary app). Hydra-based config in `conf/`, source in `src/`.
- **`apps/collect-trace/`** — Harvests training data from agent runs, converts to SFT/DPO format.
- **`apps/gradio-demo/`** — Local web UI using Gradio + vLLM.
- **`apps/visualize-trace/`** — Flask dashboard for analyzing agent reasoning traces.
- **`apps/lobehub-compatibility/`** — LobeChat integration adapter.
- **`libs/miroflow-tools/`** — Shared library: `ToolManager` + pre-built MCP servers.

### Core Agent Architecture (`apps/miroflow-agent/src/core/`)

- **Orchestrator** — Main execution loop: coordinates multi-turn reasoning, sub-agent delegation, and tool management.
- **Pipeline** — Factory & entry point: creates tool managers, formatters, and kicks off task execution.
- **ToolExecutor** — Runs tool calls with retries/error handling; handles both MCP tools and sub-agent calls.
- **AnswerGenerator** — Produces final answers from collected context; optional LLM-as-judge verification.
- **StreamHandler** — Real-time streaming event management.

### Key Design Patterns

- **Hierarchical agents**: Main agent delegates to sub-agents (e.g., browsing agent) with independent tool sets. Tool blacklisting prevents problematic combinations.
- **Hydra config system**: `conf/` contains agent variants (11), benchmark configs (14), and LLM provider configs. Main entry: `conf/config.yaml` with defaults for `llm`, `agent`, `benchmark`.
- **MCP tool ecosystem**: `ToolManager` in `libs/miroflow-tools/` manages MCP server lifecycle (stdio/SSE transports). 13+ pre-built servers for search, code execution, vision, audio, reasoning, document reading.
- **LLM provider factory**: `ClientFactory` in `src/llm/` supports Anthropic, OpenAI, and custom HTTP endpoints.

### Configuration

- **Settings**: `apps/miroflow-agent/src/config/settings.py` — environment variables and MCP server setup.
- **Environment**: `apps/miroflow-agent/.env.example` — API keys template (SERPER, JINA, E2B, ANTHROPIC, OPENAI, etc.).
- **Agent variants**: `conf/agent/mirothinker_v1.5.yaml` is the main variant (search + scrape + python tools).

## Tech Stack

- Python 3.12+, uv package manager, Hydra config, Ruff linter/formatter
- MCP (`mcp`, `fastmcp`) for tool protocol
- Anthropic + OpenAI SDKs for LLM providers
- Playwright for browser automation, E2B for sandboxed code execution
- pytest with xdist (parallel), markers (`unit`, `integration`, `slow`, `requires_api_key`), and snapshot testing (`inline-snapshot`)

## CI

GitHub Actions (`run-ruff.yml`) runs Ruff lint + format checks on PRs. Failures block merge.

## gstack
Use /browse from gstack for all web browsing. Never use mcp__claude-in-chrome__* tools.
Available skills: /plan-ceo-review, /plan-eng-review, /plan-design-review, /design-consultation, /review, /ship, /browse, /qa, /qa-only, /qa-design-review, /setup-browser-cookies, /retro, /document-release.
If gstack skills aren't working, run `cd .claude/skills/gstack && ./setup` to build the binary and register skills.
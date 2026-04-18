---
title: "Gemma 4 LLM Integration: Proxy, extra_body, and Provider Compatibility"
date: "2026-04-06"
last_updated: "2026-04-07"
category: integration-issues
module: src/data_agents/professor
problem_type: integration_issue
component: tooling
severity: high
symptoms:
  - "502 Bad Gateway from local Gemma 4 API through proxy at 100.64.0.15:7893"
  - "HTTPS connections hang indefinitely when crawling university websites through proxy"
  - "401 Unauthorized from Gemma 4 endpoint due to missing API key"
  - "DashScope fallback failures from Gemma-specific extra_body parameter"
  - "Incomplete proxy clearing leaving all_proxy/ALL_PROXY active"
root_cause: config_error
resolution_type: config_change
tags:
  - gemma-4
  - llm-integration
  - proxy
  - dashscope
  - extra-body
  - authentication
  - professor-pipeline
  - vllm
---

# Gemma 4 LLM Integration: Proxy, extra_body, and Provider Compatibility

## Problem

Integrating Google Gemma 4 (gemma-4-26b-a4b-it) as the local LLM for Professor Pipeline V3 surfaced five interrelated issues: model-specific API parameters, proxy environment pollution blocking both LLM and web-crawling HTTP calls, missing API key configuration, cross-provider parameter incompatibility, and incomplete environment cleanup in auxiliary entry points.

## Symptoms

- **502 Bad Gateway** on POST to `star.sustech.edu.cn/service/model/gemma4/v1/chat/completions` — local LLM calls routed through proxy `100.64.0.15:7893` which cannot reach the internal endpoint
- **Indefinite hangs** during Stage 1 Discovery when crawling university websites (e.g., `sse.cuhk.edu.cn`) — HTTPS connections stalled through proxy
- **401 Unauthorized** from the Gemma 4 endpoint — `API_KEY` env var unset
- **Unexpected LLM output** — Gemma 4's thinking mode enabled by default, producing chain-of-thought tokens in structured JSON extraction results
- **Potential request failures on DashScope fallback** — Gemma-specific `extra_body` parameter rejected by DashScope's qwen3.6-plus endpoint

## What Didn't Work

1. **Clearing proxy only in `_build_llm_client()`**: Fixed the 502 for LLM calls, but Stage 1 Discovery web crawling still routed through the proxy and hung indefinitely. The proxy was already loaded into process environment before the LLM client constructor ran.

2. **Adding proxy clearing at `run_professor_pipeline_v3()` entry**: The V1 `run_professor_pipeline` function is called synchronously, and HTTP clients (requests, httpx) had already captured the proxy settings at import time. Clearing at pipeline entry was too late for some code paths.

3. **Applying `extra_body` uniformly to all LLM calls**: Worked for Gemma 4 (Tier 1 local), but broke DashScope (Tier 2 online) because DashScope does not recognize `chat_template_kwargs`. Caught by Codex cross-validation.

## Solution

### Fix 1: Gemma 4 thinking mode control via `extra_body`

Central constant in `translation_spec.py`:

```python
LLM_EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}
```

Applied to all 8 local-LLM `chat.completions.create()` calls across 7 files:

```python
from .translation_spec import LLM_EXTRA_BODY

response = llm_client.chat.completions.create(
    model=llm_model,
    messages=[...],
    extra_body=LLM_EXTRA_BODY,  # Gemma 4 requires this
)
```

Files: `paper_collector.py`, `homepage_crawler.py`, `identity_verifier.py`, `web_search_enrichment.py`, `agent_enrichment.py` (Tier 1 only), `company_linker.py`, `summary_generator.py`.

### Fix 2: Three-level proxy clearing

```python
def _clear_proxy_env() -> None:
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY"):
        os.environ.pop(var, None)
```

Called at three levels:
1. **Script entry** (`main()` in E2E scripts) — before any imports trigger HTTP client initialization
2. **Pipeline entry** (`run_professor_pipeline_v3()`, `run_batch_reprocess()`) — catches library callers
3. **LLM client construction** (`_build_llm_client()`) — defense-in-depth

### Fix 3: API key via environment variable

```bash
API_KEY='k8#pL2@mN9!qjfkew87@#$0204' .venv/bin/python scripts/run_professor_pipeline_v3_e2e.py
```

Key stored in `.sglang_api_key` at repo root. E2E scripts read from `API_KEY` env var.

### Fix 4: Provider-aware `extra_body` (found by Codex cross-validation)

Before (broken):
```python
# agent_enrichment.py — Tier 2 Online (DashScope)
response = online_llm_client.chat.completions.create(
    model=online_llm_model, messages=[...],
    extra_body=LLM_EXTRA_BODY,  # WRONG: Gemma-specific, breaks DashScope
)
```

After (correct):
```python
# Tier 1 Local (Gemma 4) — includes extra_body
response = local_llm_client.chat.completions.create(
    model=local_llm_model, messages=[...],
    extra_body=LLM_EXTRA_BODY,
)

# Tier 2 Online (DashScope) — NO extra_body
response = online_llm_client.chat.completions.create(
    model=online_llm_model, messages=[...],
)
```

### Fix 5: Complete proxy variable list

Before (`batch_reprocess.py`): only 4 vars cleared.
After: all 6 variants (`http_proxy`, `https_proxy`, `HTTP_PROXY`, `HTTPS_PROXY`, `all_proxy`, `ALL_PROXY`).

## Why This Works

**Thinking mode**: Gemma 4's chat template defaults to thinking mode enabled, prepending chain-of-thought tokens to every response. For structured JSON extraction, these extra tokens corrupt parsing. `enable_thinking: False` disables this at the Jinja template level before tokenization.

**Proxy**: Python's `httpx`, `requests`, and `urllib3` read proxy env vars at client-construction time. The local LLM at `star.sustech.edu.cn` and university websites are reachable directly but not through the `100.64.0.15:7893` proxy. Three-level clearing ensures no code path inherits proxy settings regardless of entry point.

**API key**: SGLang-served Gemma 4 requires Bearer token auth. Without `API_KEY` env var, the OpenAI client sends no `Authorization` header.

**DashScope incompatibility**: `extra_body` is an OpenAI SDK pass-through. `chat_template_kwargs` is SGLang/vLLM-specific. DashScope rejects unknown parameters.

## Prevention

1. **Centralize LLM client construction** behind a factory that encapsulates provider-specific parameters. Each provider gets a registered profile; call sites never pass raw provider-specific kwargs.

2. **Pin proxy cleanup list as module-level constant**: `_PROXY_VARS = ("http_proxy", ...)` — single source of truth prevents future omissions in new entry points.

3. **Fail-fast on missing credentials**: Add explicit check at pipeline startup that validates API key is non-empty and endpoint is reachable (lightweight `/v1/models` GET).

4. **Integration test with health-check probe**: Before full pipeline, issue one minimal `chat.completions.create` call to catch thinking-mode corruption, auth failures, and proxy issues in <1 second.

5. **Provider Compatibility Matrix**: Document which `extra_body` / extension parameters are valid for each LLM backend (SGLang/vLLM, DashScope, Volcano) in the shared spec.

## Verification

- **242 unit tests** pass across all professor modules
- **E2E (SUSTech, 2 professors)**: 2 released, 0 blocked, 10 Gemma 4 calls all HTTP 200 OK
- **Codex cross-validation**: 1 CRITICAL (DashScope extra_body) + 1 HIGH (incomplete proxy clearing) found and fixed

## Files Modified

| File | Change |
|------|--------|
| `src/data_agents/professor/translation_spec.py` | `LLM_EXTRA_BODY` constant |
| `src/data_agents/professor/paper_collector.py` | import + `extra_body` on create() |
| `src/data_agents/professor/homepage_crawler.py` | `extra_body` on create() |
| `src/data_agents/professor/identity_verifier.py` | `extra_body` on create() |
| `src/data_agents/professor/web_search_enrichment.py` | `extra_body` on create() |
| `src/data_agents/professor/agent_enrichment.py` | `extra_body` on local Tier 1 only |
| `src/data_agents/professor/company_linker.py` | `extra_body` on create() |
| `src/data_agents/professor/summary_generator.py` | `extra_body` on create() |
| `src/data_agents/professor/pipeline_v3.py` | `_clear_proxy_env()`, Gemma 4 defaults |
| `src/data_agents/professor/batch_reprocess.py` | `_clear_proxy_env()`, Gemma 4 defaults |
| `scripts/run_professor_pipeline_v3_e2e.py` | Proxy clearing at main() |
| `scripts/run_batch_reprocess_v3.py` | Proxy clearing at main() |

## Related Issues

- `docs/solutions/workflow-issues/data-agent-real-e2e-gates-2026-04-02.md` — earlier proxy workaround using `trust_env=False` on OpenAI client; superseded by full env var clearing
- `docs/solutions/professor-pipeline-v2-deployment-patterns-2026-04-05.md` — same proxy (`100.64.0.15:7893`) documented for SSL failures, same sglang auth pattern for embedding endpoint
- Proxy handling evolution: `trust_env=False` (Apr 2) -> fetch cache fallback (Apr 5) -> explicit `_clear_proxy_env()` (Apr 6)

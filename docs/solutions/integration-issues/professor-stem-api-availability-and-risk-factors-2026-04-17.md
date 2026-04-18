---
title: Professor STEM API Availability And Risk Factors
date: 2026-04-17
status: active
owner: codex
---

# Professor STEM API Availability And Risk Factors

## Scope

This note captures the verified API availability status for the current professor STEM rebuild, and separates true API outages from environment or parser issues.

## Verified API Status

As of 2026-04-17 UTC, the following endpoints were directly probed from this workspace:

| API | Status | Notes |
|---|---|---|
| `star.sustech gemma4` | available | `chat/completions` returned HTTP 200 with `gemma-4-26b-a4b-it`. |
| `DashScope qwen3.6-plus` | available | HTTP 200. Suitable fallback/alternate LLM path. |
| `Volcengine Ark` mixed route | available | HTTP 200. Route endpoint resolves to a concrete Doubao model at runtime. |
| `Embedding` (`Qwen3-Embedding-8B`) | available | HTTP 200 after clearing proxy env for local `http://100.64.*` calls. |
| `Rerank` (`qwen3-reranker-8b`) | available | HTTP 200 after clearing proxy env for local `http://100.64.*` calls. |
| `Serper web search` | available when key is loaded | Direct `curl` and repo provider path both work once `SERPER_API_KEY` / `.serper_api_key` is present. |
| `OpenAlex` | available | Public API directly reachable with HTTP 200. |

## What Is Actually Blocking The Pipeline

The current professor rebuild is not blocked by LLM platform availability.

The real blockers seen in recent real-data E2E are:

1. Parser and cleaning robustness after LLM succeeds.
   - Example: homepage extraction can fail with JSON parse errors such as `Extra data`, even when the model endpoint itself is healthy.
2. Paper evidence coverage for STEM faculty.
   - Some schools and departments still fail on `paper_backed_failed` despite successful roster discovery and homepage crawling.
3. Environment credentials for optional enrichment.
   - `Serper` is healthy, but real E2E silently degrades to `0 web searched` when `SERPER_API_KEY` / `.serper_api_key` is not loaded.
4. Local proxy contamination for internal HTTP services.
   - `Embedding` and `Rerank` can fail falsely if `all_proxy/http_proxy/https_proxy` leak into local `100.64.*` requests.

## Dependency Classification

### Hard Dependencies

These must work for the STEM rebuild mainline to pass real E2E:

- one working LLM path (`gemma4`, `dashscope`, or `ark`)
- official-site crawling
- OpenAlex / official publication evidence path for STEM paper-backed validation

### Degradable Dependencies

These can be disabled without blocking collection-quality closure:

- Serper web search when paper-backed closure depends on alternate official pages or scholar links
- vectorization / embedding
- rerank

This is why current real rebuild runs continue to use `--skip-web-search` and `--skip-vectorize` while still remaining valid for collection E2E.

## Main Risk Factors

1. Missing repo-local key files or env vars.
   - `load_professor_e2e_env.sh` only loads keys that exist locally.
   - `Serper` currently fails here.
2. Local proxy environment leakage.
   - Internal HTTP model services on `100.64.*` can appear broken unless proxy env vars are cleared first.
3. LLM output formatting drift.
   - Healthy model responses can still break brittle JSON parsing and downstream structured cleaning.
4. School-specific TLS / homepage fallback behavior.
   - These show up as fetch-format problems, not model-platform outages.
4. STEM paper identity disambiguation.
   - Availability of academic APIs is not enough; evidence quality still determines whether the profile reaches `ready`.

## Operational Decision

For the current rebuild wave:

- keep `gemma4` as default LLM
- keep `dashscope` and `ark` as verified fallback paths
- treat `Serper` as required for hard cases whose paper evidence comes from alternate official pages or official-linked scholar profiles
- do not block STEM crawler rebuild on embedding/rerank
- prioritize parser robustness and paper-backed closure over API switching

# Slice Contract: s12g-chat-mobile-streaming-ux

## Status

Candidate

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Task: `12.5j`

## Goal

Deliver five observable results for the framework-free public chat:

1. `国先检索助手` remains usable across the approved 13 viewports, safe areas, software keyboards, and rotation.
2. IME and input-modality behavior is reliable, and streaming respects detached reading with return-to-latest.
3. When safe streamable content is produced normally, at least one safe answer chunk is public before the complete synthesis final result and `done`; the successful final result remains that same synthesis.
4. Raw SSE and rendered DOM omit internal identifiers and structural fields across representative chunk boundaries.
5. Retries never mix visible attempts; when the server observes stop, disconnect, or cancellation before commit, the unfinished turn never becomes successful session context. No guarantee is made for an unobserved client disconnect.

## Non-goals

- No query, retrieval, ranking, Web, evidence-admission, citation-policy, or answer-completeness change.
- No public response schema, SSE event-name, payload-shape, route, or transport change.
- No answer-length reduction and no additional LLM call.
- No frontend framework, runtime dependency, device allowlist, or broad backend refactor.
- No production promotion, source/data/index write, archive, or destructive cleanup.
- Desktop emulation is not native iPhone or Android validation.

## Allowed scope

- Focused streaming and final-result work in the existing Canonical V2 answer path.
- Focused public-output, server-observed pre-commit stop/disconnect/cancellation, and session-result work in the existing admin chat path.
- Page-local HTML, CSS, and native JavaScript in `apps/admin-console/backend/static/chat.html`.
- One approved-logo static derivative with an ASCII path.
- Focused tests in the existing Canonical V2 answer, HTTP adapter, and chat UI test files.
- One repository-owned browser runner and additive S12G verification artifacts.
- Additive task, acceptance, design, change-log, verification, and slice-status updates.

## Forbidden changes

- Query planning, provider queries, candidate budgets, fusion, reranking, or answer policy.
- Canonical schemas, databases, indexes, releases, pointers, sources, credentials, or production config.
- New truncation, rejection, or extra model calls as a mobile or output-safety fix.
- Historical S9J, S11, S12D, or S12F evidence and accepted status.
- Case-specific query behavior, workbook-answer shortcuts, global browser installation, or unrelated refactors.

## Expected unchanged behavior

- The existing final parser continues to determine accepted claims, citations, displayed entities, and next-turn scope.
- When the provider is healthy and safe streamable content exists, at least one safe `answer_chunk` becomes public before the complete final result is available and before `done` is emitted; chunking is not simulated after the complete answer is already available.
- Successful streaming and non-streaming paths produce the same complete validated synthesis.
- Public SSE event names and payload schemas remain compatible.
- Previously committed session context remains unchanged when the server observes stop, disconnect, or cancellation before commit and does not commit that interrupted turn; there is no non-commit guarantee for a client disconnect the server does not observe before commit.
- Final answers are not shortened, and provider-call count does not increase.
- `/chat`, collapsed official `查看依据`, and the four-public-domain boundary remain intact.

## Required checks

- Focused answer-path tests prove that, when the provider is healthy and safe streamable content exists, at least one safe `answer_chunk` is public before the complete final result is available and before `done`, is not simulated after completion, and preserves final consistency, retry non-mixing, and accepted scope.
- Focused HTTP/SSE tests cover representative beginning, middle, and end chunk boundaries, normal Chinese/Markdown, unchanged schemas, and non-commit when the server observes stop, disconnect, or cancellation before commit; they make no non-commit guarantee for an unobserved client disconnect.
- Focused UI checks for all 13 viewports, keyboard/rotation behavior, containment, IME, scroll detachment, return-to-latest, branding, and complete final answers.
- Run every browser-runner invocation from the repository root through `uv run --project apps/miroflow-agent python`, using the uv-managed project that declares Playwright.
- Before the production browser gate, record lightweight provenance that `127.0.0.1:18188` was launched from the current worktree and serves its current Candidate code; an HTTP response from a pre-existing process is insufficient.
- If establishing provenance requires starting or restarting the service, first obtain explicit user authorization for that one action. After authorization, reuse the existing Candidate serving command from the current worktree and wait for `GET /api/health` to return HTTP 200. This slice does not itself authorize the action.
- On that confirmed current Candidate, preflight candidate real queries through the existing public chat SSE path. Record and export as `S12G_REAL_SSE_QUERY` only a query that returns HTTP 200 and exposes at least one progressive `answer_chunk` before final result/`done`. `请介绍丁文伯教授的研究方向` and `深圳无界智航科技有限公司是做什么的` are non-binding examples; observed preflight results control, and a known business badcase is not an S12G UI blocker.
- If provenance cannot be confirmed, required authorization is unavailable, or no candidate query passes preflight, record the production gate as blocked/skipped and do not use old-process results as Candidate evidence.
- In the final Candidate sequence, rerun the same runner's `--self-test` immediately before the single production acceptance command:

  ```bash
  : "${S12G_REAL_SSE_QUERY:?export the query recorded by the current-Candidate preflight}"
  uv run --project apps/miroflow-agent python .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/browser_acceptance.py \
    --browser chromium \
    --self-test \
    --output-dir .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/artifacts
  uv run --project apps/miroflow-agent python .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/browser_acceptance.py \
    --url http://127.0.0.1:18188/chat \
    --browser chromium \
    --real-sse-query "$S12G_REAL_SSE_QUERY" \
    --output-dir .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/artifacts
  ```

- Run `openspec validate rebuild-canonical-v2-knowledge-platform --strict` and `git diff --check` from the repository root.

### Rollout-conditional native-device gate (not required for Candidate)

Before production-like rollout, run a short smoke on one recent physical iPhone and Android covering keyboard, long streaming, detached scrolling, return-to-latest, stop, rotation, and safe areas. At Candidate time, disclose whether this ran and never describe desktop emulation as native validation.

## Evidence to update

- Keep Task `12.5j` and every S12G acceptance item unchecked until implementation evidence exists.
- Append exact commands, results, artifact paths, current-worktree serving provenance, any one-time start/restart authorization, `/api/health` readiness, and the passing preflight query/result to the current verification ledger and change log.
- Move this slice from `Ready` to `Candidate` only after Candidate-required checks pass; acceptance remains separate.

## Stop conditions

- Correctness would require a public schema/protocol, retrieval, answer-policy, or answer-length change.
- The five observable results cannot be met without an extra LLM call, frontend dependency, broad refactor, or edits outside allowed scope.
- Focused tests expose a required rewrite of accepted historical evidence rather than an additive S12G change.
- Candidate-required focused checks, browser outcomes, strict OpenSpec validation, or diff checks cannot pass.
- Current-worktree serving provenance, any required one-time user authorization, `/api/health` readiness, or a passing real-query preflight cannot be established; keep the production gate blocked/skipped and do not advance the slice.
- Production-like rollout is requested without the rollout-conditional native-device smoke.

## Done means

- The five observable results have current focused automated and browser evidence.
- All 13 viewports pass responsive, input, scroll, and branding checks.
- When the provider is healthy and safe streamable content exists, at least one safe `answer_chunk` becomes public before the complete final result is available and before `done`; progressive output is not simulated after completion and reconciles to the complete accepted final result without leaks, truncation, or retry mixing.
- A turn is not committed when the server observes stop, disconnect, or cancellation before commit; no non-commit guarantee applies to an unobserved client disconnect.
- Public SSE/schema, retrieval behavior, answer scope, and LLM-call count remain unchanged.
- Strict OpenSpec validation and `git diff --check` pass, evidence is additive, and the slice reaches `Candidate` rather than `Accepted`.

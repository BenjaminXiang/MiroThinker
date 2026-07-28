# Slice Contract: s12d-universal-web-llm-public-evidence

## Status

Candidate

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Tasks: `12.5a`-`12.5f`

## Goal

Make the isolated Canonical V2 chat use bounded local plus current-Web retrieval and real
evidence-bound LLM synthesis for every normal information request, while exposing only collapsed
official public-source links to the public browser. Use Bocha and Serper together and keep external
provider paths responsive after long idle periods without adding work to the real request path.

## Non-goals

- No production promotion, active-pointer change, canonical/index write, or source recollection.
- No application authentication or authorization change for `/browse`.
- No new public entity-detail page, citation proxy, source registry, or broad UI redesign.
- No generic scheduler, distributed lock, cache service, provider health dashboard, or persistence of
  synthetic keep-warm traffic.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
- `apps/admin-console/backend/services/canonical_v2_keepwarm.py`
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py` for the non-serialized
  current-query input passed to prose synthesis only.
- `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`
- `apps/admin-console/backend/services/canonical_v2_chat.py`
- `apps/admin-console/backend/main.py`
- `apps/admin-console/backend/api/canonical_v2_chat.py`
- `apps/admin-console/backend/static/chat.html`
- `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py` for synchronized fixture-owner
  content addressing after focused runtime regression coverage changes.
- Focused Canonical V2 chat/UI tests and this change's task/acceptance/verification artifacts.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py` and its
  focused runner test only for passing the recorded keep-warm callable into the Candidate app.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/serving-bundle-r8.json` only for replacing
  the secret-free Serper-only policy with the approved dual-provider policy and recomputing its
  self-hash; no release, database, index, or envelope content changes.

## Forbidden changes

- Original PostgreSQL/Milvus/source files, active release pointers, production credentials, or
  `/browse` deployment controls.
- Public domain set, canonical schemas, relationship meanings, or claim/evidence validation.
- Case-specific query strings or workbook answers in production code.
- Keep-warm calls through `CanonicalV2ChatAdapter`, session creation, evidence/citation generation,
  gap recording, database/index writes, or mutable provider sessions shared concurrently.

## Expected unchanged behavior

- Typed claim admission and citation grounding remain fail-closed.
- Web and LLM failures preserve usable local evidence and produce typed deterministic degradation.
- Refusal, clarification-only, safety, and interface-control inputs skip general Web search.
- Server-side feedback checkpoints retain complete internal trace identity.

## Implementation slices

1. RED: prove normal information requests require Web and the serving answer factory requires the LLM
   renderer; prove the founder relationship survives claim selection.
2. GREEN: add the bounded LLM prose adapter and make the selector admit relevant local and Web claims.
3. RED/GREEN: map only official public citations, remove public internal evidence/trace fields, and
   render a closed `查看依据` disclosure.
4. Verify focused provider failure, four-domain citation policy, Ding Wenbo two-turn HTTP, and browser
   disclosure behavior; restart the isolated candidate.
5. Preserve answer and evidence semantics while reusing the Serper transport across turns; verify
   warm end-to-end and browser-visible latency separately from cold/upstream-tail behavior.
6. RED/GREEN: run Bocha and Serper concurrently under one outer Web budget, normalize and deduplicate
   by URL, prefer richer Bocha content on duplicates, and retain all corroborating provider versions.
7. RED/GREEN: add one lifecycle-owned adaptive idle keep-warm loop; mark activity before real answer
   execution and prove skip, non-overlap, shutdown, and zero business-write behavior.
8. Restart the isolated Candidate and record warm plus post-idle timings without changing answer,
   citation sanitization, or source-isolation behavior.

## Required checks

- `uv run pytest -q -n0 tests/canonical_v2/test_knowledge_serving_isolated.py`
- `uv run pytest -q -n0 ../../apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`
- `uv run pytest -q -n0 ../../apps/admin-console/tests/test_canonical_v2_real_preview_ui.py`
- Focused Ruff/Pyright for changed Python, strict OpenSpec validation, and `git diff --check`.
- Real two-turn Ding Wenbo HTTP replay plus browser check at desktop and mobile widths.
- Repeated four-domain HTTP timing and a browser DOM-visible-answer timing check against the same
  restarted Candidate process.
- Focused dual-provider success, normalized duplicate, single-provider failure, and both-provider
  failure tests.
- Deterministic keep-warm activity, idle, non-overlap, and shutdown tests with an injected clock and
  wake event; no real external sleeps in tests.

## Evidence to update

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`

## Stop conditions

- Correctness requires weakening claim/evidence validation or exposing internal trace data.
- The configured Web or LLM provider cannot be loaded without embedding credentials in an artifact.
- Keep-warm requires a Canonical/index/business-data write or makes real requests wait on its work.
- The running Candidate cannot be updated without canonical/index mutation or promotion.

## Done means

- The reported founder follow-up is synthesized from the relationship plus relevant Web evidence.
- Normal information answers use the real LLM path, with explicit deterministic failure fallback.
- Public chat exposes only a collapsed official-source list and no internal navigation/data.
- Bocha and Serper are fused under the existing outer budget with retained provider provenance and
  graceful one-provider/local degradation.
- Long-idle provider paths are warmed in the background with no request-path wait or business write.
- Focused checks pass and `:18188` is ready for direct user iteration.

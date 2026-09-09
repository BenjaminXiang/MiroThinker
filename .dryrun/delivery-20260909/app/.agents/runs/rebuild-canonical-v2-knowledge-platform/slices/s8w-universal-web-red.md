# Slice Contract: s8w-universal-web-red

## Status

Accepted at `2026-07-15T02:55:04Z`. This test-only RED slice completes OpenSpec Task 8.4. Exact RED,
complete no-external regression, static/strict/package/source checks, and both pre-review correction
sets pass. Two targeted independent re-reviews report zero Critical/Important findings. It uses
synthetic typed plans, local evidence, and recorded Web-adapter outcomes; it does not consume the
pending S2C corpus, run an acceptance oracle, or call a real provider.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `8.4`
- Depends on: Accepted S3A `KnowledgeRead.execute(RetrievalPlan) -> EvidenceSet` interface contract,
  Accepted S7 release/index substrate, and the active Universal-Web/safety-guidance behavior contract
- Parallel-start authority: the current user directive limits S2C3C2 to S8/S9 acceptance-oracle
  execution; `agent-links.md` permits fixture-only RED tasks without their own reviewed-corpus
  predecessor to start against synthetic typed fixtures

## Goal

Freeze three strict RED groups through the single future `KnowledgeRead.execute` interface:

1. every A/B/C/D/E/G information-retrieval plan executes server-owned current Web augmentation even
   when a caller/model plan omits or disables the Web lane and exact local evidence is already usable,
   while local/Web items and traces remain distinguishable;
2. ordinary refusal, blocking clarification, interface control, and default `safety_guidance` plans
   execute no Web lookup, while an explicit current-official-information safety request may execute
   only a bounded official-source lookup whose accepted evidence has a retained content-addressed
   snapshot identity and retrieval time;
3. Web timeout, connection failure, or schema-invalid output retains usable local evidence, records
   the Web lane as unavailable, and exposes a material freshness/coverage limitation without
   presenting the result as current-Web verified.

## Non-goals

- Do not implement Task 8.2/8.3/8.5+, `knowledge_read.py`, planning/classification, fusion/rerank,
  sufficiency retry, Web snapshot expiry/tamper/resolution lifecycle, Web entity handles, provider
  clients, prompts, sessions, answers, continuation offers, or aggregate S8 acceptance.
- Do not calibrate Task 8.1 ambiguity policy, materialize reviewed-corpus trace replay, consume S2C
  cases/reference prose, or claim 100% real-provider invocation.
- Do not introduce a second public retrieval/Web interface, a live network call, a global Web
  disable shortcut, database/index/release mutation, or production-like target.

## Allowed scope

- One new test owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_universal_web_contract.py`.
- This Slice Contract and, after Candidate review, existing OpenSpec task/change-log/agent-link,
  portfolio, mainline-plan, and verification evidence files.
- Synthetic future-shaped `RetrievalPlan`, local `EvidenceItem`, Web policy/budget, recorded adapter
  request/result, `RetrievalTrace`, and `EvidenceSet` fixtures only. The test imports the absent
  KnowledgeRead target before constructing any future shape.

## Forbidden changes

- Any production/shared contract/migration/provider/runtime/source/database/index/consumer file.
- A second public read/Web behavior seam; all observable behavior must emerge from
  `KnowledgeRead.execute(RetrievalPlan) -> EvidenceSet` returned by a package-internal recorded-fake
  composition factory.
- A test-local `KnowledgeRead` implementation, broad `ModuleNotFoundError` xfail, private call-order
  assertion, real provider credential/network access, reference-prose oracle, or model-memory fact.
- Any Task 8.1-8.3/8.5-8.8, aggregate S8, S2C, S9, provider-quality, latency, or cost acceptance claim.

## Expected unchanged behavior

- S9A/S10A/S10B and all S1-S7 Accepted behavior remain unchanged.
- S2C3C2 remains Ready and externally pending; Task 8.1 reviewed-case calibration and S8/S9 corpus
  acceptance execution remain blocked, but this synthetic Task 8.4 RED does not.
- Existing KnowledgeRead and KnowledgeAnswer/S9A xfails remain expected.
- Original Postgres/Milvus/forensic sources, candidate/index state, and active pointers remain
  unchanged.

## Required checks

- Focused normal execution reports exactly three strict xfails and zero failures/errors/XPASS.
- Focused `--runxfail` reports exactly three failures caused only by the exact absent
  `src.data_agents.canonical_v2.knowledge_read` target sentinel.
- Complete no-external Canonical V2 has no real failure and only the existing KnowledgeRead,
  KnowledgeAnswer/S9A, and these three S8W scenarios as named xfails.
- Ruff check/format and Canonical V2 Pyright pass for changed/applicable scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, package-content, and frozen-
  source checks pass.
- One independent review reports zero open Critical/Important findings. Minor/YAGNI findings are
  recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `change-log.md`, and `agent-links.md` only after complete Task 8.4 RED
  acceptance.
- `.agents/portfolio.md` and current code-grounded mainline plan after acceptance.

## Stop conditions

- A test requires behavior absent from the active Universal-Web/safety-guidance requirements.
- Universal Web can pass only because the caller/model preselected `web_required=True`/a Web lane, or
  current official evidence without a valid retained snapshot can pass the safety lookup.
- The fixture must claim accepted S2C/S8 runtime/oracle or real-provider evidence, or introduces
  another public retrieval/Web seam.
- RED can pass through a local read implementation, broad exception masking, or assertion-order
  accident.
- A production/shared-contract edit or unresolved Critical/Important finding is needed to accept
  this test-only slice.

## Done means

- Three strict groups cover server-owned Universal Web enforcement against plan opt-out, all named
  skip/official-safety and minimal snapshot-grounding boundaries, and timeout/connection/schema-
  invalid degradation through the future single read interface.
- Exact RED, static/strict/scope/package/source checks, and independent review pass with zero open
  Critical/Important findings.
- Task 8.4/S8W is Accepted as RED only; Tasks 8.1-8.3 and 8.5-8.8 remain open.

## Plan

1. Add three exact-target strict RED groups without production/shared-contract edits.
2. Prove normal and forced RED identity, then run complete no-external/static/strict/package/source
   checks.
3. Obtain one independent read-only review and repair only Critical/Important findings.
4. Persist Task 8.4 RED acceptance. Do not implement Task 8.3/8.5 without separate Ready Slice
   Contracts and Accepted predecessors.

## Rollback note

Remove the new RED test, this contract, and its status/evidence entries. No external state exists to
roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256 is
  `5c255b071637c41dd9136a40c65327ec90cfab9a952003285c9cc1f54b6d9a22`; final test SHA-256 is
  `f6e0e75e7248144f41c03f5e7a84f9250cd05156408a81020a1a51b59561cdb7`.
- Focused normal execution is exactly `3 xfailed`; forced `--runxfail` is exactly three
  `_MissingKnowledgeReadModule` failures for the absent
  `src.data_agents.canonical_v2.knowledge_read` target. Nested dependency failures remain real.
- A/B/C/D/E/G information plans explicitly disable/omit Web, but the package-internal server policy
  still requires distinct current-Web evidence and successful trace after exact local evidence.
  Ordinary refusal, blocking clarification, interface control, and default safety guidance use a
  fail-on-call adapter and produce no Web trace/unavailability limitation.
- Explicit current-official safety lookup is bounded to one official-only request and filters
  nonofficial results. Accepted official evidence binds official authority plus a content-addressed
  snapshot ID/hash, retrieval time, and positive byte length; missing-snapshot output is rejected as
  invalid/unavailable without claiming the future lifecycle work.
- Timeout, connection, and invalid-output cases retain exact local evidence, emit no current-Web
  evidence/success trace, record the unavailable failure kind, and expose one material freshness
  limitation.
- Complete no-external Canonical V2 is `296 passed, 141 skipped, 8 xfailed`; the xfails are exactly
  the existing KnowledgeRead, KnowledgeAnswer/S9A, and three S8W groups. Complete Canonical V2 Ruff
  and Pyright pass; the changed test is Ruff-formatted.
- Strict OpenSpec, `git diff --check`, scope/secret/cache, and fresh wheel checks pass. Wheel SHA-256
  remains `af7332f68739a5d87c87639089765580a0e446f3788d2d8aeeb87ade1c884d00`; it excludes tests/
  `.agents` and contains no S8W production module.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; recovery lab remains
  network-none/no-port; original Milvus hash remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Pre-review closed server-policy opt-out, minimal official snapshot grounding, request-count/order,
  and freshness-limitation false-green gaps. Both targeted re-reviews end zero Critical/Important.
  Nonblocking Minor/YAGNI: the S3A-compatible `web_required` flag and structured Web policy mode are
  redundant inputs until Task 8.2/8.3 consolidates the validated plan shape.
- Task 8.4/S8W is Accepted at 51/80. Tasks 8.1-8.3 and 8.5-8.8 remain open; Task 8.1 and S8/S9
  claim-level acceptance-oracle execution still await S2C. No provider, database, index, source,
  release pointer, production code, Commit, Push, PR, archive, or Cutover changed.

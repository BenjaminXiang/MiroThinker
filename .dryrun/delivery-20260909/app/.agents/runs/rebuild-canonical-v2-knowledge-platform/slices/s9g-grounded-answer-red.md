# Slice Contract: s9g-grounded-answer-red

## Status

Accepted at `2026-07-15T04:58:03Z`. This synthetic fixture-only RED slice completes OpenSpec Task
9.1. Exact RED, complete no-external regression, static/strict/package/source checks, and two
independent targeted review tracks pass with zero Critical/Important findings. It does not consume
the pending S2C corpus, execute a claim-level acceptance oracle, call a real provider, or implement
answer production behavior.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `9.1`
- Depends on: Accepted S3A `KnowledgeAnswer.answer(TurnRequest) -> TurnResult` interface contract,
  Accepted S6R/S7 Technology/release semantics, and synthetic typed evidence/coverage shapes
  consistent with Accepted S8W/S8S
- Parallel-start authority: `agent-links.md` permits S9 answer RED contracts against typed synthetic
  evidence; S2C3C2/S2C3C3 still gate only claim-level acceptance-oracle execution

## Goal

Freeze four strict RED groups through the single future answer interface:

1. every material local/current-Web identity, relationship, role, date, numeric, or consequential
   claim binds exact subject/predicate/value evidence and a typed citation; bounded Web citation
   retains source nature/snapshot/time, a material local/Web conflict cannot silently become one
   confirmed value, unrelated/model-memory facts are rejected, and permitted model-only conclusions
   remain explicit uncertain noncanonical inference;
2. a named Product capability is supported only by direct same-Product/exact-capability evidence with
   source/time/status; Company, other-Product, same-Product/wrong-capability, Technology, and model-
   memory traps cannot support it, demonstrated evidence cannot be promoted to commercial status,
   and the final claim remains answer-scoped/noncanonical with no `product_has_capability` relation;
3. a release-scoped/as-of Shenzhen Industry Brief compares two accepted internal Technology routes,
   preserves definition plus discussion/claimed-adoption/demonstrated-use distinctions, maps material
   local/Web conclusions to evidence/conflicts/limitations, and renders the supplied representative
   coverage honestly despite a hidden-first candidate and hostile exhaustive/Product proposal; the
   brief remains derived/noncanonical and Technology remains internal;
4. after structured claims/citations/coverage are validated, a precise prose-renderer timeout returns
   a deterministic structured/template fallback with the same claims/evidence/coverage plus a stage
   limitation, no poisoned raw draft, and no new fact.

## Non-goals

- Do not implement Tasks 9.2/9.4/9.6-9.8, `knowledge_answer.py`, claim/prose production, prompts,
  HTTP/chat/session behavior, assessment dimensions, ambiguity, continuation offers, or safety
  rendering.
- Do not repeat S8 planning/fusion/sufficiency/coverage calculation, Web-handle lifecycle, the full
  three-mode enumeration matrix, or real query/runtime acceptance.
- Do not run S2C case/reference-prose judging, live provider/latency/TTFT/unsupported-claim-rate gates,
  or claim aggregate S9 acceptance.
- Do not introduce public ClaimValidator/Citation/IndustryBrief services, a fifth public Technology
  domain, a canonical Product-capability relation, or any database/index/source write.

## Allowed scope

- One new test owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_grounding_contract.py`.
- This Slice Contract and, after Candidate review, existing OpenSpec task/change-log/agent-link,
  portfolio, mainline-plan, and verification evidence files.
- Synthetic future-shaped evidence sets/items/bindings, bounded Web snapshots, conflicts, material
  question parts, answer-selection proposals, Product-capability status, Technology route/Industry-
  Brief inputs, supplied enumeration coverage, citations, claims, limitations, and recorded prose
  outcomes only. The test imports the exact absent KnowledgeAnswer target before future dependencies.

## Forbidden changes

- Any production/shared-contract/migration/provider/runtime/source/database/index/consumer file.
- A second public behavior seam; observable behavior must emerge from
  `KnowledgeAnswer.answer(TurnRequest) -> TurnResult` using only injected recorded selector/prose
  dependency boundaries.
- A test-local `KnowledgeAnswer`, hand-built returned `TurnResult`, broad `ModuleNotFoundError`,
  `importorskip`, runtime `pytest.xfail`, reference prose/LLM judge as truth, private call-order
  assertion, real credential/network access, or exact prose-string gold beyond poisoned-output
  exclusion and deterministic fallback identity.
- Any Task 9.2 GREEN, S9A assessment, S9M session/continuation, Task 9.8 acceptance, S2C, storage,
  provider-quality, numeric-policy, or aggregate S9 claim.

## Expected unchanged behavior

- S8W/S8S/S9A/S9M/S10A/S10B and all S1-S7 Accepted behavior remain unchanged.
- S2C3C2 remains Ready and externally pending; S8/S9 claim-level acceptance-oracle execution remains
  blocked, but this synthetic Task 9.1 RED does not.
- Existing KnowledgeRead, KnowledgeAnswer/S9A/S9M, S8W, and S8S xfails remain expected.
- Original Postgres/Milvus/forensic sources, candidate/index state, and active pointers remain
  unchanged.

## Required checks

- Focused normal execution reports exactly four strict xfails and zero failures/errors/XPASS.
- Focused `--runxfail` reports exactly four failures caused only by the exact absent
  `src.data_agents.canonical_v2.knowledge_answer` target sentinel.
- Complete no-external Canonical V2 reports no real failure and only the existing KnowledgeRead,
  KnowledgeAnswer/S9A/S9M, S8W, S8S, and these four S9G scenarios as named xfails.
- Ruff check/format and Canonical V2 Pyright pass for changed/applicable scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, package-content, and frozen-
  source checks pass.
- At least one independent review reports zero open Critical/Important findings. Minor/YAGNI findings
  are recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `change-log.md`, and `agent-links.md` only after complete Task 9.1 RED
  acceptance.
- `.agents/portfolio.md` and current code-grounded mainline plan after acceptance.

## Stop conditions

- A case requires behavior absent from the active grounded-answer/Technology/Product/coverage
  contracts or depends on an unaccepted S8 runtime result rather than a synthetic typed fixture.
- Evidence IDs can pass without exact subject/predicate/value/citation binding; Web provenance can
  lose snapshot/time/nature; conflict can become a silent confirmed value; or model memory can become
  a confirmed material fact.
- Product traps can support the named capability/status, Industry Brief can collapse route semantics/
  coverage or create canonical facts, or fallback can lose validated content or render poison.
- RED can pass through a local implementation/broad exception mask, introduces another public seam,
  or needs production/shared-contract edits or an unresolved Critical/Important finding.

## Done means

- Four strict groups close material claim/citation/conflict/inference, direct Product capability,
  scoped Industry Brief/representative coverage, and deterministic fallback behavior through the
  single future answer interface, including the named hostile traps.
- Exact RED, complete no-external/static/strict/scope/package/source checks, and independent review
  pass with zero open Critical/Important findings.
- Task 9.1/S9G is Accepted as RED only; Tasks 9.2 and 9.4/9.6-9.8 remain open.

## Plan

1. Add four exact-target strict RED groups without production/shared-contract edits.
2. Prove normal and forced RED identity, then run complete no-external/static/strict/package/source
   checks.
3. Obtain independent read-only review and repair only Critical/Important findings.
4. Persist Task 9.1 RED acceptance. Do not implement Task 9.2 without a separate Ready Slice Contract.

## Rollback note

Remove the new RED test, this contract, and its status/evidence entries. No external state exists to
roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256 is
  `789df77a11a02048e14d0f1289f99e9f474e29bfd63b4613fcb50df1917aae0e`; final test SHA-256 is
  `1836f8b439a29dcbed3f76d0f09b85136116d1ccf73aed4b5d39ac6e4aae5df9`.
- Focused normal execution is exactly `4 xfailed`; forced `--runxfail` is exactly four
  `_MissingKnowledgeAnswerModule` failures for the absent
  `src.data_agents.canonical_v2.knowledge_answer` target. Nested dependency failures remain real.
- Material founder, current-role conflict, and bounded maturity-inference claims bind exact expected
  subject/predicate/value/status/outcome/evidence tuples, exact mapping/citation closure, and local/
  bounded-Web provenance. Orthogonal subject/predicate/value traps, unrelated evidence, silent
  conflict selection, and model-memory financing are rejected.
- Named-Product capability traps independently cover Company, other Product, wrong capability,
  Technology, model memory, and status promotion. The unsupported branch has an explicit empty-
  evidence mapping and zero citations; the supported branch retains only direct same-Product/exact-
  capability demonstrated evidence. Neither result can create `product_has_capability`.
- The derived Industry Brief preserves two internal Technology route definitions and exact
  discussion/claimed-adoption/demonstrated-use/conflicting semantics per displayed Company. Top-
  level TurnResult claims, mappings, citations, conflicts, enumeration coverage, and open-world
  limitation mirror the brief; hidden/promoted/Product hostile proposals cannot survive anywhere in
  the result. Representative/as-of coverage remains non-exhaustive and the brief remains
  noncanonical.
- Prose timeout returns the same exact one-claim/one-map/one-citation deterministic fallback across
  independent instances, retains coverage and a typed stage limitation, and excludes the poisoned
  raw draft and extra facts.
- Complete no-external Canonical V2 is `296 passed, 141 skipped, 19 xfailed`; the xfails are exactly
  the existing KnowledgeRead, KnowledgeAnswer/S9A/S9M, S8W/S8S, and four S9G groups. Complete
  Canonical V2 Ruff check/Pyright and changed-test Ruff format checks pass. A whole-directory format
  inventory also reports two unchanged historical S3A interface RED files; they are outside S9G and
  were not reformatted.
- Strict OpenSpec and `git diff --check` pass. Scope/secret/cache checks are clean for the two S9G
  files. A fresh locked offline wheel has unchanged SHA-256
  `af7332f68739a5d87c87639089765580a0e446f3788d2d8aeeb87ade1c884d00`, includes Accepted
  `knowledge_gap_feedback.py`, excludes tests/`.agents`, and contains no S9G production module.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; recovery remains network-
  none/no-port/restart-no; original Milvus SHA-256 remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Two independent pre-review/re-review tracks end zero Critical/Important after closing exact
  claim/evidence semantics, Product binding/status masking, negative/top-level result leakage,
  Industry route/coverage/limitation closure, and fallback no-extra-fact gaps. Nonblocking Minor:
  `fallback_sha256` identity is compared across independent runs but is not separately asserted
  nonempty/content-bound; this is recorded without extending the RED contract.
- Task 9.1/S9G is Accepted at 54/80. Task 9.2 and Tasks 9.4/9.6-9.8 remain open; S2C3C2/S2C3C3 still
  gate only S8/S9 claim-level acceptance-oracle execution. No provider, database, index, source,
  release pointer, production code, Commit, Push, PR, archive, or Cutover changed.

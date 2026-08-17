# Slice Contract: s8s-sufficiency-retry-red

## Status

Accepted at `2026-07-15T03:28:45Z`. This test-only RED slice completes OpenSpec Task 8.6. Exact RED,
complete no-external regression, static/strict/package/source checks, and two independent targeted
reviews pass with zero Critical/Important findings. It uses synthetic typed fused evidence, material
question parts, enumeration inputs, and recorded supplemental outcomes; it does not consume the
pending S2C corpus, run an acceptance oracle, or call a real provider.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `8.6`
- Depends on: Accepted S3A `KnowledgeRead.execute(RetrievalPlan) -> EvidenceSet` interface contract,
  Accepted S7 substrate, and Accepted S8W/Task 8.4 RED policy/trace shape
- Parallel-start authority: Task 8.6 is fixture-only RED with no reviewed-corpus predecessor;
  `agent-links.md` and the current user directive reserve S2C only for Task 8.1 calibration and S8/S9
  claim-level acceptance-oracle execution

## Goal

Freeze three strict RED groups through the single future `KnowledgeRead.execute` interface:

1. a content-bound structured sufficiency report classifies every material question part as
   `supported`, `conflicting`, or `missing` with current evidence IDs, rationale, and uncertainty; a
   nonempty candidate set is not sufficient, direct named Product-capability evidence with source/
   time may support its answer-scoped part, and Company/other-Product/Technology/model evidence may not;
2. `exhaustive_bounded`, `required_members`, and `representative` enumeration plans return scope/as-
   of plus ID/count-consistent checked/eligible/retrieved/displayed/omitted/unknown accounting and a
   continuation state; only a fully accounted finite universe may be exhaustive, while each required
   member receives an included or explicit unsupported/omission outcome without implying exhaustive;
3. `supported` parts never create supplemental views, while targeted `missing` or unresolved
   `conflicting` material parts may; independent wall-time/provider-call/retry/cost budgets stop
   execution with the best supported evidence, unresolved parts, exact-axis usage/limit receipt,
   limitation, and typed continuation reason rather than an unbounded loop or invented fact.

## Non-goals

- Do not implement Task 8.2/8.3/8.5/8.7+, `knowledge_read.py`, planning/classification, retrieval
  adapters, fusion/rerank, production sufficiency, enumeration execution, supplemental provider,
  sessions, answers, continuation rendering, or aggregate S8 acceptance.
- Do not materialize Task 8.1 reviewed trace replay/calibration, consume S2C cases/reference prose,
  claim real-provider quality/latency/cost, or choose product-wide numeric budgets.
- Do not introduce a public Sufficiency/Enumeration/Retry service, global Product-capability relation,
  database/index/release mutation, live network call, or production-like target.

## Allowed scope

- One new test owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_sufficiency_retry_contract.py`.
- This Slice Contract and, after Candidate review, existing OpenSpec task/change-log/agent-link,
  portfolio, mainline-plan, and verification evidence files.
- Synthetic future-shaped `RetrievalPlan`, `MaterialQuestionPart`, `EvidenceItem`, sufficiency proposal/
  report, enumeration policy/coverage, supplemental budget/result/trace/receipt, limitation, and
  `EvidenceSet` fixtures only. The test imports the absent KnowledgeRead target before constructing
  any future shape.

## Forbidden changes

- Any production/shared contract/migration/provider/runtime/source/database/index/consumer file.
- A second public read/sufficiency behavior seam; all observable behavior must emerge from
  `KnowledgeRead.execute(RetrievalPlan) -> EvidenceSet` returned by a package-internal recorded-fake
  composition factory.
- A test-local `KnowledgeRead` implementation, broad `ModuleNotFoundError` xfail, private helper/
  call-order assertion, real provider credential/network access, reference-prose oracle, or model-
  memory evidence.
- Any Task 8.1-8.3/8.5/8.7-8.8, aggregate S8, S2C, S9, real latency/cost, or Product-capability
  acceptance claim.

## Expected unchanged behavior

- S8W/S9A/S10A/S10B and all S1-S7 Accepted behavior remain unchanged.
- S2C3C2 remains Ready and externally pending; Task 8.1 calibration and S8/S9 corpus acceptance
  execution remain blocked, but this synthetic Task 8.6 RED does not.
- Existing KnowledgeRead, KnowledgeAnswer/S9A, and S8W xfails remain expected.
- Original Postgres/Milvus/forensic sources, candidate/index state, and active pointers remain
  unchanged.

## Required checks

- Focused normal execution reports exactly three strict xfails and zero failures/errors/XPASS.
- Focused `--runxfail` reports exactly three failures caused only by the exact absent
  `src.data_agents.canonical_v2.knowledge_read` target sentinel.
- Complete no-external Canonical V2 has no real failure and only the existing KnowledgeRead,
  KnowledgeAnswer/S9A, S8W, and these three S8S scenarios as named xfails.
- Ruff check/format and Canonical V2 Pyright pass for changed/applicable scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, package-content, and frozen-
  source checks pass.
- One independent review reports zero open Critical/Important findings. Minor/YAGNI findings are
  recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `change-log.md`, and `agent-links.md` only after complete Task 8.6 RED
  acceptance.
- `.agents/portfolio.md` and current code-grounded mainline plan after acceptance.

## Stop conditions

- A test requires behavior absent from the active sufficiency/enumeration/supplemental requirements.
- Product capability can become supported through Company-only evidence/model memory, or any list
  can claim exhaustive without exact finite-universe accounting.
- Supplemental work can target a supported part, ignore an explicitly unresolved conflicting gap,
  exceed any of the four declared budget axes without an exact terminal usage/limit receipt and
  limitation, or lose initial supported evidence.
- The fixture must claim accepted S2C/S8 runtime/oracle or real-provider evidence, introduces another
  public seam, passes through a local implementation/broad exception mask, or needs a production/
  shared-contract edit or unresolved Critical/Important finding.

## Done means

- Three strict groups cover content-bound material-part supported/conflicting/missing plus positive/
  negative direct Product binding, all three enumeration modes/per-member accounting/false-
  exhaustiveness boundaries, and targeted unresolved-part exhaustion on all four budget axes through
  the future single read interface.
- Exact RED, static/strict/scope/package/source checks, and independent review pass with zero open
  Critical/Important findings.
- Task 8.6/S8S is Accepted as RED only; Tasks 8.1-8.3, 8.5, and 8.7-8.8 remain open.

## Plan

1. Add three exact-target strict RED groups without production/shared-contract edits.
2. Prove normal and forced RED identity, then run complete no-external/static/strict/package/source
   checks.
3. Obtain one independent read-only review and repair only Critical/Important findings.
4. Persist Task 8.6 RED acceptance. Do not implement Task 8.7 or production predecessors without
   separate Ready Slice Contracts.

## Rollback note

Remove the new RED test, this contract, and its status/evidence entries. No external state exists to
roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256 is
  `f1ef506419c2da8207d51d19e1dd8f38dfe230fe80e8332ccf14c6185eebf2c5`; final test SHA-256 is
  `4bbb82985a84c85559fe91a8485f663cf9b34642249df35ec77624251f743bdf`.
- Focused normal execution is exactly `3 xfailed`; forced `--runxfail` is exactly three
  `_MissingKnowledgeReadModule` failures for the absent
  `src.data_agents.canonical_v2.knowledge_read` target. Nested dependency failures remain real.
- Material-part decisions bind supported/conflicting/missing outcomes to current evidence IDs,
  rationale, uncertainty, and content identity. Named Product capability is answer-scoped and
  requires the same Product, predicate, requested capability value, source nature, and observation
  time; Company, other-Product, Technology, same-Product/wrong-capability, and model-memory evidence
  cannot support it.
- All three enumeration modes expose ID/count-consistent scope/as-of accounting and continuation
  state. Only the fully accounted finite universe is exhaustive; every required member has exactly
  one evidence-bound included outcome or explicit unsupported outcome with no evidence and a reason.
- Supported parts never enter supplemental retrieval. Each wall-time/provider-call/retry/cost case
  makes exactly one recorded boundary call for only the unresolved conflicting/missing parts, stops
  on the exact exhausted axis, retains exact initial evidence, and returns aligned trace/receipt,
  limitation, and typed continuation reasons.
- Complete no-external Canonical V2 is `296 passed, 141 skipped, 11 xfailed`; the xfails are exactly
  the existing KnowledgeRead, KnowledgeAnswer/S9A, S8W, and three S8S groups. Complete Canonical V2
  Ruff and Pyright pass; all applicable dirty runtime/test Canonical V2 Python files are Ruff-
  formatted. The two unchanged historical S3A interface tests remain outside this slice's formatting
  scope.
- Strict OpenSpec, `git diff --check`, scope/secret/cache, and fresh wheel checks pass. Wheel SHA-256
  remains `af7332f68739a5d87c87639089765580a0e446f3788d2d8aeeb87ade1c884d00`; it excludes tests/
  `.agents`, includes the Accepted S10B module, and contains no S8S production module.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; recovery lab remains
  network-none/no-port; original Milvus SHA-256 remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Pre-review and targeted re-review closed capability-value, per-required-member evidence, real
  supplemental-call, conflict eligibility, false-exhaustiveness, accounting, four-axis budget, and
  retained-evidence false-green gaps. Candidate identity re-review confirms zero Critical/Important;
  no additional Minor/YAGNI finding blocks this deliberately test-only slice.
- Task 8.6/S8S is Accepted at 52/80. Tasks 8.1-8.3, 8.5, and 8.7-8.8 remain open; Task 8.1 and S8/S9
  claim-level acceptance-oracle execution still await S2C. No provider, database, index, source,
  release pointer, production code, Commit, Push, PR, archive, or Cutover changed.

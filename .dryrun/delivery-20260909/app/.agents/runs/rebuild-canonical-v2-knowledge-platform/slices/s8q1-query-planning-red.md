# Slice Contract: s8q1-query-planning-red

## Status

Accepted at `2026-07-15T06:16:26Z`. This synthetic fixture-only RED predecessor freezes the
mechanically decidable part of OpenSpec Task 8.1. Exact RED, query-owner/full no-external regression,
static/strict/package/source checks, and independent contract/test final reviews pass with zero
Critical/Important findings. It does not check Task 8.1, calibrate ambiguity thresholds, consume
reviewed S2C cases, or claim query-runtime acceptance. S2C3C2/S2C3C3 block only the separate reviewed
calibration and claim-level acceptance-oracle work.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `8.1` (fixture RED predecessor only; the task remains unchecked)
- Depends on: Accepted S6R internal Person/Technology semantics and Accepted S7 release/index seams
- Parallel-start authority: `agent-links.md` permits S8 fixture-only RED against synthetic typed
  fixtures after the applicable S6R/S7 seams; reviewed-case calibration still awaits Accepted S2C

## Goal

Freeze four strict RED groups through one package-internal planning seam:

```python
planner = create_ephemeral_query_planner(...)
plan = planner.plan(QueryPlanningRequest(...))
```

The implementation remains hidden behind the future `KnowledgeAnswer` orchestration and produces a
validated `RetrievalPlan` for `KnowledgeRead.execute`; this slice does not add a sixth public deep
module.

1. Preserve the A-G behavior taxonomy without a fixed one-handler switch; distinguish A/B/C/D/E/G
   information retrieval, ordinary F refusal, blocking G clarification, interface control, and the
   narrow F `safety_guidance` policy. Refusal, default safety guidance, blocking clarification, and
   interface control produce no general-Web plan; an explicit request for current official contact/
   policy information may produce only a bounded `official_only` plan, never venue/district/business
   discovery. At least one information request produces a typed multi-lane cross-domain plan. List
   plans select `exhaustive_bounded` only with an exact finite universe, `required_members` only with
   exact accepted members, and otherwise `representative` with explicit scope/as-of/budget state.
2. Deterministically protect exact IDs, explicit names/titles, dates/years, geography, negation,
   relationship direction, exact displayed-set membership, and typed release-scoped institution
   slots before planning. A contextual rewrite binds “the above Companies” to the exact displayed
   Canonical IDs; every later contextual/canonical-alias/semantic/domain/relationship/Web view retains
   that membership plus every other hard constraint, original query, and producer identity. A
   parameterized injected-catalog matrix covers full names, aliases, multiple institutions,
   ambiguous/unknown/absent values, repeated mentions, and overlapping spans. Each result retains
   matched spans, raw text, resolution state, exact candidate ID/name pairs, catalog/release identity,
   pure topical text, and lane-specific query/filter. Full name and alias produce the same Canonical
   constraint and topic; ambiguous/unknown never false-canonicalize; absent creates no slot; overlap/
   repetition loses no topical term. A newly injected fixture alias works without rewrite-code
   changes, and generic topic stopwords contain no institution name/alias. Unsupported relationships/
   directions, lost slots, malformed views, or excessive budgets fail validation before execution.
3. Exercise ambiguity mechanics only with an explicitly injected, versioned synthetic policy: no
   numeric default is frozen. Protected-constraint conflict and model confidence alone cannot clear
   the gate; zero or several qualifying candidates block with evidenced discriminators; exactly one
   evidence-backed dominant candidate may be selected while retaining viable alternatives and the
   exact policy/candidate decision trace.
4. Plan a bounded internal Person query using typed education, Company-role, and geography filters
   bound to the accepted release and originating public-domain evidence. Unresolved Person references
   remain separately traceable with evidence but cannot satisfy identity-dependent filters or
   traversals. Resolve accepted-release Technology aliases/routes for a two-route comparison with
   definition/relationship evidence, scope, and as-of; preserve discussion-or-mention, claimed-
   adoption, and demonstrated-use as non-promotable distinct filters. An unresolved term remains
   only a traceable search view/gap. Use representative enumeration absent a finite universe.
   Person/Technology remain internal auxiliaries, and Product capability remains answer-scoped
   rather than a canonical relation.

## Non-goals

- Do not implement Tasks 8.2/8.3/8.5/8.7/8.8, `knowledge_read.py`, query execution, retrieval/fusion/
  rerank/sufficiency, provider calls, answer rendering, sessions, or consumer wiring.
- Do not calibrate or select ambiguity evidence floors, confidence thresholds, lead margins, domain
  defaults, provider budgets, latency/cost targets, or claim-level expected outcomes.
- Do not execute S2C cases, live LLM/Web/Milvus/PostgreSQL, real release lookup, or real Person/
  Technology retrieval.
- Do not create a public QueryPlanner service, a fifth public Person/Technology domain, a canonical
  Product-capability relation, or an institution topic-stopword/name-specific production patch.
- Do not check Task 8.1 or claim aggregate S8 acceptance from fixture RED evidence.

## Allowed scope

- One new test owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_query_planning_contract.py`.
- This Slice Contract and, after Candidate review, existing change-log/agent-link, portfolio,
  mainline-plan, and verification evidence files. `tasks.md` remains unchanged.
- Synthetic immutable request/context, institution catalog, entity candidate/evidence, ambiguity
  policy, internal Person/Technology reference, enumeration-universe, and recorded structured-plan
  fixtures only.

## Interface and seam constraints

- `create_ephemeral_query_planner(...).plan(QueryPlanningRequest) -> RetrievalPlan` is the only
  behavior seam. The composed implementation is package-internal and future-owned by
  `KnowledgeAnswer`; it is not a sixth public ABC or an added method on `KnowledgeRead`.
- Deterministic extraction and validation remain server-owned. A recorded structured planner may
  propose semantics, but it cannot author protected slots, accepted institution/Person/Technology
  identity, ambiguity acceptance, enumeration evidence, supported paths, or final budget validity.
- Every accepted plan and rewrite is content-bound to the exact request, release, policy/catalog,
  recorded proposal, and resolved references. Tests assert observable typed values and validation
  failures, not private helper order or prompt strings.
- Ambiguity policy values are mandatory injected fixture data with version/content identity. The RED
  asserts mechanics and boundary behavior only; later S2C-reviewed calibration owns real values.

## Forbidden changes

- Any production/shared-contract/migration/database/index/provider/admin/chat/answer/source file.
- Existing Accepted S8W/S8S/S9/S10 assertions or accepted S6R/S7 implementation bytes.
- A public sixth module/service, test-local planner implementation, hand-built final returned plan,
  broad exception-mask xfail, `importorskip`, runtime `pytest.xfail`, private call-order assertion,
  real credential/network access, or reference prose/model memory as truth.
- Hardcoded calibrated ambiguity defaults, institution stopword enumeration, unsupported canonical
  Person/Technology population, or query-time canonical/index mutation.

## Expected unchanged behavior

- Accepted S6R/S7/S8W/S8S and all other Accepted behavior remain GREEN and byte-unchanged.
- Existing KnowledgeRead/KnowledgeAnswer fixture REDs remain expected; this slice adds exactly four
  named RED groups for the exact absent `src.data_agents.canonical_v2.knowledge_read` target.
- S2C3C2 remains externally pending and continues to gate only reviewed calibration/claim-level S8/
  S9 oracle execution, not this synthetic planning contract.
- Original PostgreSQL/Milvus/forensic sources, candidate/index state, and active pointers remain
  unchanged.

## Required checks

- Focused normal execution reports exactly four strict xfails and zero failures/errors/XPASS.
- Focused `--runxfail` reports exactly four failures caused only by the exact absent
  `src.data_agents.canonical_v2.knowledge_read` target sentinel.
- Accepted S8W/S8S interface-owner tests pass unchanged or retain only their exact expected xfails.
- Complete no-external Canonical V2 reports no real failure and exactly the existing 22 named xfails
  plus these four S8Q1 groups.
- Ruff check/format and Canonical V2 Pyright pass for changed/applicable scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, package-content, and frozen-
  source checks pass.
- At least one independent review reports zero open Critical/Important findings. Minor/YAGNI
  findings are recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `change-log.md` and `agent-links.md` after RED Candidate acceptance; `tasks.md` stays
  unchecked until reviewed calibration and the full Task 8.1 contract are Accepted.
- `.agents/portfolio.md` and the current code-grounded mainline plan after acceptance.

## Stop conditions

- The fixture RED cannot express the behavior through one package-internal planning seam without
  changing a public/shared/production contract.
- Correct mechanics depend on real calibrated thresholds, reviewed S2C claims, provider truth,
  durable storage, or active release/index mutation rather than explicitly injected typed fixtures.
- A planner proposal can author or drop protected facts, clear ambiguity from model confidence,
  claim exhaustiveness without a finite/member contract, promote unresolved internal references, or
  execute an unsupported path/budget.
- The RED needs another public service, masks nested failures, broadens into GREEN/runtime/answer
  work, or retains an unresolved Critical/Important finding.

## Done means

- Four strict groups close taxonomy/safety/enumeration, protected slots/rewrites/institution/invalid-
  plan refusal, synthetic ambiguity mechanics, and internal Person/Technology plan semantics through
  one package-internal planning seam.
- Exact RED, owner/full no-external/static/strict/scope/package/source checks, and independent review
  pass with zero open Critical/Important findings.
- S8Q1 is Accepted as a fixture RED predecessor only; Task 8.1 and Tasks 8.2-8.3/8.5/8.7-8.8 remain
  open, and the global ledger remains 54/80.

## Plan

1. Add four exact-target strict RED groups without production/shared-contract edits.
2. Prove normal/forced RED identity and unchanged Accepted query-owner behavior.
3. Run complete no-external/static/strict/package/source checks and independent read-only review.
4. Persist predecessor acceptance. Do not implement GREEN or numeric calibration without a separate
   Ready Slice Contract and Accepted reviewed inputs.

## Rollback note

Remove the new RED test, this contract, and its RED acceptance evidence. No external state exists to
roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256 is
  `1623d6764b3a7db354bd523d69f1da4802eb6acc3ea143ddb57a37c5647a4503`; final test SHA-256 is
  `cb0e83611c9c58c99b72ebb60320ef5955956704393be2d659f3cf8708177c62`.
- Focused normal execution is exactly `4 xfailed`; forced `--runxfail` is exactly four
  `_MissingKnowledgeReadModule` failures for the absent
  `src.data_agents.canonical_v2.knowledge_read` target. Nested dependencies, missing symbols, and
  fixture/construction defects remain real failures.
- The taxonomy group covers A-G effects, same-class plan diversity, ordinary refusal, default and
  bounded `official_only` safety guidance, interface control, typed cross-domain/multi-lane plans,
  and the three enumeration modes without freezing one handler map or real product thresholds.
- The protected-planning group binds exact slots and displayed-set membership through every view;
  resolves a release/catalog-driven full-name/alias/multi/ambiguous/unknown/absent/repeated/overlap
  institution matrix with exact span/raw/topic/lane evidence; and rejects lost slots, invented paths,
  wrong supported-path direction, unknown operations, excessive budgets, wrong request, and wrong
  catalog release through the planner seam.
- The ambiguity group uses two distinct synthetic policies plus one same-request/candidate margin-
  only flip. It verifies evidence counts/confidence, protected conflicts, qualifying sets, lead-margin
  math, no-candidate versus multiple-candidate outcomes, policy/candidate/proposal identities, and no
  ambient policy default; no calibrated numeric product value is selected.
- The internal-reference group keeps four public domains, binds resolved Person filters to exact
  public evidence, retains resolved-nonmatching and unresolved Person traces, resolves exactly two
  accepted Technology routes while retaining an unqueried third route and an unresolved term, and
  forbids semantic-state promotion, public auxiliary populations, false exhaustiveness, and canonical
  Product-capability propagation. Request/release/policy/catalog/reference/proposal cross-wires fail
  closed and same inputs remain stable while single-axis inputs separate.
- The existing KnowledgeRead interface/S8W/S8S owner matrix is exactly `11 xfailed`, comprising its
  seven unchanged named REDs plus these four S8Q1 groups. Complete no-external Canonical V2 is `296
  passed, 141 skipped, 26 xfailed` with no real failure.
- Complete Canonical V2 Pyright and Ruff check pass; the changed test passes Ruff format and
  `py_compile`. Strict OpenSpec and `git diff --check` pass. Scope/secret/cache checks are clean.
- A locked offline wheel retains SHA-256
  `af7332f68739a5d87c87639089765580a0e446f3788d2d8aeeb87ade1c884d00`, contains 273 entries, and
  contains no `knowledge_read.py`, tests, or `.agents` artifact.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; recovery remains network-
  none/no-port/restart-no; original Milvus SHA-256 remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Independent contract review and two test-integrity/final-gate reviews end at zero Critical,
  Important, Minor, and YAGNI findings. Task 8.1 remains unchecked and the ledger remains 54/80;
  reviewed ambiguity calibration and claim-level oracle execution still await S2C.

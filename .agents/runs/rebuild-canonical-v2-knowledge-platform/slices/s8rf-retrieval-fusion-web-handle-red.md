# Slice Contract: s8rf-retrieval-fusion-web-handle-red

## Status

Accepted at `2026-07-15T07:29:28Z`. This synthetic fixture-only RED predecessor freezes the
mechanically decidable retrieval, fusion, rerank, and Web-handle behavior still missing from OpenSpec
Tasks 8.3 and 8.5. It does not check either task, consume reviewed S2C cases, run a real provider, or
claim query-runtime acceptance. The global task ledger remains 54/80. S2C3C2/S2C3C3 continue to gate
only reviewed Task 8.1 calibration and S8/S9 claim-level acceptance-oracle execution.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec tasks: `8.3` and `8.5` (fixture RED predecessor only; both remain unchecked)
- Depends on: Accepted S6R auxiliary-reference semantics, Accepted S7 release/index substrate,
  Accepted S8Q1 planning RED, Accepted S8W Universal-Web RED, and Accepted S8S sufficiency RED
- Parallel-start authority: `agent-links.md` permits synthetic S8 fixture RED after applicable S6R/
  S7 seams; no reviewed-case calibration or claim-level oracle outcome is selected here

## Goal

Freeze exactly three strict RED groups through the single future interface:

```python
read = create_ephemeral_knowledge_read(...)
result = read.execute(RetrievalPlan(...))
```

1. Execute all seven `exact`, `structured`, `lexical`, `vector`, `relationship`,
   `internal_reference`, and `web` lanes in one execution batch and prove that independent adapters
   can overlap without freezing scheduler width. Every recalled raw candidate, including later
   dropped or fused candidates, retains its exact query view, lane, attempt, release, adapter/
   provider version, raw score, source evidence, and disposition.
   Resolved Person/Technology auxiliary matches retain originating public-domain evidence and typed
   relationship semantics; unresolved references remain separately traced and neither auxiliary
   becomes a fifth public domain or a canonical Product-capability relation.
2. Resolve candidate identity and aggregate distinct local/Web evidence before deterministic hard
   constraints and structured late reranking. Two aliases for one accepted Canonical identity occupy
   one result with both evidence contributions, while the same display name on different accepted
   Canonical IDs remains separate; an ordinary quality gap remains recall-visible rather than being
   broadly excluded early. The reranker sees the complete aggregated evidence and quality state for
   the exact eligible fused input and may only reorder/select eligible candidates. Wrong-bound,
   duplicate/unknown, or timeout output degrades deterministically without losing valid evidence or
   resurrecting a hard-constraint rejection. Additional provider exception/schema permutations are
   deferred rather than expanded into a universal matrix.
3. Bind every displayed Web-only entity to a distinct typed session handle and bounded content-
   addressed snapshot plus originating query/lane/attempt/provider trace. A URL remains evidence
   metadata, never a public-domain ID; two distinct entities sharing one URL keep distinct handles.
   Snapshot tamper or changed live content cannot replace accepted bytes or establish continuity;
   an expired handle cannot remain a live referent. Later read-only resolution may bind an exact
   accepted-release Canonical identity while retaining the original handle/snapshot/resolution
   lineage and recording zero online canonical/index mutation.

## Non-goals

- Do not implement Tasks 8.2/8.3/8.5/8.7/8.8, add `knowledge_read.py`, or awaken any existing strict
  RED. Do not check Tasks 8.3/8.5 or aggregate S8.
- Do not repeat S8Q1 taxonomy/protected-slot/institution/ambiguity planning, S8W Universal-Web skip/
  failure policy, or S8S sufficiency/enumeration/supplemental-retry coverage. Execution-time
  ambiguity handoff remains part of the later atomic `KnowledgeRead` implementation contract; this
  predecessor does not claim complete Task 8.5 coverage.
- Do not freeze numeric ambiguity/rank/quality thresholds, a universal pairwise fusion matrix,
  provider-specific scoring, worker count, executor type, private algorithm order, or production
  latency/cost targets.
- Do not consume S2C claim cases, real LLM/Web/PostgreSQL/Milvus, live release lookup, durable session
  storage, answer rendering, or consumer wiring.
- Do not create another public retrieval/fusion/handle service, public Person/Technology domain, or
  query-time canonical/index write path.

## Allowed scope

- One new test owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_retrieval_fusion_contract.py`.
- This Slice Contract and, after Candidate review, existing change-log/agent-link, portfolio,
  mainline-plan, and verification evidence files. `tasks.md` remains unchanged.
- Synthetic immutable plan/view, recorded lane-candidate/evidence/trace, identity/fusion/rerank,
  Web snapshot/handle/replay/resolution, clock, and package-internal adapter fixtures only.

## Interface and seam constraints

- `KnowledgeRead.execute(RetrievalPlan) -> EvidenceSet` is the only public behavior seam. Recorded
  lane, reranker, and read-only handle-resolution ports are injected only through the package-
  internal ephemeral composition factory; tests do not call a second service or private helper.
- Server-owned deterministic validation closes release/view/lane/attempt/evidence identity, hard
  constraints, Web snapshot/handle state, and accepted-release resolution. Recorded model/provider
  output can propose relevance or identity but cannot author final protected facts or mutation.
- Concurrency is asserted only as overlap among independent blocking fixture adapters, not by thread
  count, call order, executor type, or timing threshold. Result ordering/identity is asserted through
  observable content-bound records.
- The exact target import occurs before any future record construction. Only absence of
  `src.data_agents.canonical_v2.knowledge_read` is translated to the strict sentinel; nested missing
  dependencies and construction/assertion defects remain real failures.

## Forbidden changes

- Any production/shared-contract/migration/database/index/provider/admin/chat/answer/source file or
  existing Accepted test assertion.
- Test-local `KnowledgeRead` implementation, hand-built final `EvidenceSet`, broad exception-mask
  xfail, `importorskip`, runtime `pytest.xfail`, sleep-based concurrency proof, live credential/
  network access, reference prose/model memory as truth, or hardcoded production rank thresholds.
- Another public method/service for fusion, rerank, Web handles, or resolution; URL-derived entity
  identity; online canonical/source-map/index mutation; or a fifth public inclusion domain.

## Expected unchanged behavior

- Accepted S6R/S7/S8Q1/S8W/S8S and every other Accepted behavior remain byte-unchanged.
- The existing KnowledgeRead owner matrix remains exactly 11 named xfails; this slice adds exactly
  three strict xfails for the same absent target, producing a 14-xfail read-owner matrix.
- Complete no-external Canonical V2 moves only from `299 passed, 141 skipped, 23 xfailed` to
  `299 passed, 141 skipped, 26 xfailed` with no real failure.
- Original PostgreSQL/Milvus/forensic sources, recovery lab, candidate/index state, and active
  pointers remain unchanged.

## Required checks

- Focused normal execution reports exactly three strict xfails and zero failures/errors/XPASS.
- Focused `--runxfail` reports exactly three failures caused only by the exact absent
  `src.data_agents.canonical_v2.knowledge_read` target sentinel.
- Existing KnowledgeRead interface/S8Q1/S8W/S8S plus this file report exactly 14 named xfails.
- Complete no-external Canonical V2 reports exactly `299 passed, 141 skipped, 26 xfailed` and no real
  failure.
- Ruff check/format, `py_compile`, and Canonical V2 Pyright pass for changed/applicable scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, package-content, and frozen-
  source checks pass.
- At least one independent contract/test-integrity review reports zero open Critical/Important
  findings. Minor/YAGNI findings are recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `change-log.md` and `agent-links.md` after RED Candidate acceptance; Tasks 8.3/8.5 and
  `tasks.md` stay unchanged.
- `.agents/portfolio.md` and the current code-grounded mainline plan after acceptance.

## Stop conditions

- The three fixture groups cannot be expressed through one `KnowledgeRead.execute` seam without a
  public/shared/production contract edit or another behavior service.
- Fusion can pass before evidence aggregation or merge same-name distinct accepted identities; a
  reranker can admit unknown/duplicate/ineligible candidates; a dropped candidate loses its trace;
  or Web tamper/expiry/URL collision can replace or merge handle lineage.
- Correct behavior requires real S2C labels, calibrated numeric thresholds, real provider truth,
  persistence, or active release/index mutation rather than explicit recorded fixtures.
- The RED masks a nested failure, weakens an Accepted test, broadens into GREEN/S9, or retains an
  unresolved Critical/Important finding.

## Done means

- Three strict groups close multi-lane/auxiliary/full-candidate trace, identity/evidence-late-fusion
  plus structured-rerank degradation, and Web snapshot/handle/replay/read-only-resolution mechanics.
- Exact RED, owner/full no-external/static/strict/scope/package/source checks, and independent review
  pass with zero open Critical/Important findings.
- S8RF is Accepted as a fixture RED predecessor only; Tasks 8.3/8.5 and aggregate S8 remain open,
  and the global ledger remains 54/80.

## Plan

1. Add three exact-target strict RED groups without production/shared-contract edits.
2. Prove focused normal/forced RED identity and the unchanged 11-plus-3 read-owner matrix.
3. Run complete no-external/static/strict/package/source checks and independent read-only review.
4. Persist predecessor acceptance. Before any GREEN, establish one atomic `KnowledgeRead` bundle or
   explicitly re-sentinel and re-accept every existing strict RED; never awaken a partial module.

## Rollback note

Remove the new RED test, this contract, and its RED acceptance evidence. No external state exists to
roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256 is
  `0d9af4e0e1253980e06570b564a2ff40d51bb26f197274f4c0ad399c1aea5ae0`; final test SHA-256 is
  `1fd10efe3b5a981e90982922b37a49c100b525e7e2454ae80078db8e5899b0fc`.
- Focused normal execution is exactly `3 xfailed`; forced `--runxfail --tb=line` is exactly three
  line-34 `_MissingKnowledgeReadModule` failures for only the absent
  `src.data_agents.canonical_v2.knowledge_read` target. Nested dependency, construction, and
  assertion failures remain real.
- The seven-lane group executes exact/structured/lexical/vector/relationship/internal-reference/Web
  in one batch, proves independent overlap without scheduler-width coupling, and retains every raw
  candidate's query/lane/attempt/release/adapter/provider/score/evidence/disposition trace. Internal
  Person/Technology results retain exact public origins and semantic state without becoming public
  populations or Product-capability relations.
- The fusion group aggregates accepted-ID aliases and local/Web evidence before hard constraints and
  rerank, preserves same-name different accepted IDs, retains ordinary quality-gap candidates and
  hard-rejection receipts, and rejects a hostile conflicting-ID merge. Structured rerank binds the
  exact eligible aggregate; wrong-bound, unknown, duplicate, and timeout proposals degrade with exact
  reasons to one deterministic evidence-preserving result without resurrecting rejected candidates.
- The Web-handle group binds distinct same-URL entities to separate session handles, exact snapshots,
  evidence and provider candidate trace. Snapshot-byte tamper, independent live-provider change,
  expiry, wrong release, invented same-release identity, and wrong Canonical evidence fail closed.
  Exact accepted-release read-only resolution retains handle/snapshot lineage and leaves the accepted
  identity mapping plus all canonical/index/source mutation counters unchanged.
- Existing KnowledgeRead interface/S8Q1/S8W/S8S plus S8RF are exactly `14 xfailed`. Complete no-
  external Canonical V2 is exactly `299 passed, 141 skipped, 26 xfailed` with no real failure.
  Complete Canonical V2 Ruff/Pyright, changed-test format/`py_compile`, strict OpenSpec,
  `git diff --check`, scope/secret/cache, and package gates pass.
- The locked offline wheel SHA-256 remains
  `78f4cd8a199de8ba79141528c3db958b65c05ea5ce20056d7d932162fa8a4791`, contains 273 entries, and
  excludes `knowledge_read.py`, tests, and `.agents` artifacts.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; recovery remains network-
  none/no-port/restart-no; original Milvus SHA-256 remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Two independent final reviews on the exact Candidate/test identities report zero Critical,
  Important, Minor, and YAGNI findings. Execution-time ambiguity handoff, cross-session enforcement,
  policy-owned max-bytes/oversize, and broader provider/schema permutations remain explicitly scoped
  to the later atomic GREEN/Task 9.6/Task 8.8 rather than open findings.
- Tasks 8.3/8.5 and aggregate S8 remain unchecked/open, and the OpenSpec ledger remains 54/80. No
  production/shared code, provider, database/index/source, active pointer, Commit, Push, PR, archive,
  or Cutover changed.

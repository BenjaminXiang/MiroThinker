# Slice Contract: S10O Durable Knowledge-Gap Operations Closure

## Status

Accepted at `2026-07-20T13:25:40Z`; Candidate was reached at `2026-07-20T13:20:32Z`. Exact RED and
review-counterexample RED were observed before
implementation/repair. The final real disposable PostgreSQL and online matrix is `7 passed` with
warnings denied; the admin owner is `1 passed`; the complete no-external suite is `357 passed, 148
skipped` with only three pre-existing hostile-model serializer warnings. Complete Ruff/Pyright,
strict OpenSpec, diff, migration-head, package/source-parity, frozen-source, and no-write checks pass.
The targeted frozen re-review reports `Critical=0/Important=0`. Acceptance checks exactly Tasks
`10.3`-`10.5` and moves the formal ledger `62/80 -> 65/80`. S8C and S9I are
Accepted with verified receipt SHA-256 values
`9e912de80fad1d82c6b6e27d71f04b458a0c78799c104ff6ca0e659e0f43ebca` and
`658c12f519a55d3e5ca02eea7b2a5deba36d47954fe04d9233934a434e0ac366`. The fresh S10A-D baseline
is `8 passed`; the migration graph has one `C2_0010` head; planned ownership, strict OpenSpec, and
diff checks pass. Seven agent owner groups fail only at the absent durable module sentinel and the
one admin owner fails only at the absent V2 router sentinel. The corrected independent review reports `Critical=0/Important=0`; Minor/YAGNI
are nonblocking. Reviewed Specified hashes are audit
`0955f4077db5ce848ae556fc94743bde7d72aca01df79f11a5f11bdf7eac67ab`, plan
`ba2d4330ac3d8fbf693c2878a462c0f9b3ae93dadbe8dae8cd20d9a20ba8334a`, and contract
`2ee9787e4905957dc0d73c8d775ae0fe2ec76609ef45dc2894a6412f7a9593cf`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec tasks to close after acceptance: `10.3`, `10.4`, and `10.5`
- Requirements: canonical gaps close only through accepted offline release/effect evidence;
  remediation is linked to recollection/enrichment/build provenance; operators see demand/PRD
  impact and V2 gaps/assertions/decisions/releases/provenance; online Web/LLM evidence never writes
  active canonical or Milvus state.
- Depends on: Accepted S2B/S3/S7/S10A/S10B/S10C/S10D, plus future Accepted S8C and S9I.
- Audit: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s10o/dependency-audit.md`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s10o/implementation-plan.md`

S2C3C2/S2C3C3 are not predecessors for this deterministic operations slice. They continue to gate
the reviewed claim-level acceptance-oracle executions in Tasks `8.8` and `9.8` only.

## Goal

Close the remaining S10 implementation and verification tasks through one ordered vertical slice:

```python
operations = create_postgres_knowledge_gap_operations(
    database_url=explicit_candidate_url,
    expected_database=explicit_candidate_name,
    target_kind="isolated-candidate",
    backup_gate_root=accepted_backup_gate_root,
)

# These two IDs are the canonical-JSON SHA-256 identities of the complete
# public EvidenceSet and TurnResult returned immediately before this call.
gap = operations.record(
    GapSignal(
        signal_id="signal:s10o:missing-relationship",
        trigger="missing_relationship",
        release_id=evidence_set.release_id,
        affected_domains=("professor", "paper"),
        affected_paths=("professor_attributed_to_paper",),
        query_trace_id=query_trace_id,
        answer_trace_id=answer_trace_id,
        benchmark_case_id=None,
        telemetry_key=None,
        observed_symptom="A material relationship remains unsupported.",
        evidence_ids=tuple(item.evidence_id for item in evidence_set.items),
        demand_observation_ids=("demand:s10o:1",),
        observed_at=observed_at,
    )
)

linked = operations.apply_remediation(candidate_request)
resolved = operations.apply_remediation(accepted_release_and_effect_request)
detail = operations.get_for_admin(gap.gap_id)
```

The initial gap and every remediation transition survive restart as exact typed, content-bound,
append-only records. A candidate may be linked without closing. Resolution requires the exact
accepted candidate/build manifest, accepted zero-deviation release verification, and later accepted
intended-effect verification bound to the original gap scope. The operator view exposes the current
gap and immutable history together with any matching V2 assertions, decisions, releases, and local
provenance; unmatched evidence identities remain explicit.

One real-disposable-Postgres owner must prove an accepted S8C `KnowledgeRead.execute` result can flow
through accepted S9I `KnowledgeAnswer.answer` into a typed durable gap while only `ops` gap history
changes. Active canonical assertions/decisions, release/build/publish state, deterministic index
state, and original Milvus bytes remain unchanged.

## Non-goals

- Do not implement S11 chat/admin/writer consumer cutover, replace every legacy `pipeline_issue`
  caller, quarantine V042 writers, or remove legacy admin routes in this slice.
- Do not implement Task `8.8`, Task `9.8`, S12 candidate acceptance, reviewed corpus replay, live
  provider quality, or production-like Cutover.
- Do not add a remediation queue, scheduler, assignment service, SLA/cost model, retry worker,
  generic workflow engine, universal remediation-kind compatibility matrix, batch close, reopen,
  dismissal, or automatic canonical mutation.
- Do not add a generic graph/SQL admin browser, React redesign, arbitrary operator-authored
  assertion/decision/release rows, or a bare `resolved=true` endpoint.
- Do not persist current-Web facts, answer prose, assessment, Product capability, model memory, or
  query-time identity hypotheses as canonical knowledge.
- Do not call live Web/LLM providers, open original Milvus with a client, connect to original
  Postgres, promote a release, mutate an active pointer, or write any source evidence.

## Allowed scope

- New migration:
  `apps/miroflow-agent/canonical_v2_alembic/versions/C2_0011_persist_knowledge_gap_operations.py`.
  If another Accepted predecessor legitimately advances the single migration head before Ready,
  renumber this new file/down-revision mechanically and re-run the plan review; never rewrite the
  predecessor.
- New durable adapter/read model:
  `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_gap_postgres.py`.
- New owners:
  - `apps/miroflow-agent/tests/canonical_v2/test_knowledge_gap_postgres.py`
  - `apps/miroflow-agent/tests/canonical_v2/test_knowledge_gap_online_write_boundary.py`
  - `apps/admin-console/tests/test_canonical_v2_operations_api.py`
- Thin read-only admin adapter:
  - `apps/admin-console/backend/api/canonical_v2_operations.py`
  - `apps/admin-console/backend/canonical_v2_deps.py` as the V2-only dependency seam
  - mechanically required router registration in `apps/admin-console/backend/main.py`
  - one bounded V2 Gaps list/detail addition in
    `apps/admin-console/backend/static/browse.html`.
- This S10O contract/plan/run evidence and, only after Candidate acceptance, existing
  `verification.md`, OpenSpec `tasks.md`/`acceptance.md`/`change-log.md`/`agent-links.md`, portfolio,
  and current mainline/convergence status summaries.

## Forbidden changes

- `knowledge_gap_feedback.py`, shared `contracts.py`, Accepted S10A–S10D assertions, S8/S9
  production/tests, historical migrations, release publication, build, read, answer, index, domain,
  identity, assertion, or decision writers.
- Legacy `apps/admin-console/backend/api/review.py`, `pipeline_issues.py`, `chat.py`, `upload.py`,
  generic `apps/admin-console/backend/deps.py`, their tests, or legacy database schema. They remain
  comparison/consumer-migration evidence for S11 and are not the accepted V2 operations path.
- A caller-provided final gap, bare status/review transition, accepted release label without exact
  manifest/parity evidence, effect evidence not bound to the original scope, online remediation
  receipt, or same-release self-closure.
- Generic `DATABASE_URL`/`DATABASE_URL_TEST` fallback, ambiguous database target, non-disposable/
  non-candidate write, nonempty destructive downgrade, destructive cleanup, or implicit table
  cascade.
- Test-local production implementation, mocked-away Postgres behavior, assertion weakening,
  `importorskip`, runtime `pytest.xfail`, broad exception swallowing, live credentials/network, or
  reference prose/model memory as truth.
- Commit, Push, PR, archive, production-like promotion, Cutover, original-source write, or original
  Milvus client open.

## Durable persistence contract

The new migration owns exactly two tables and one view:

```text
ops.knowledge_gap
  immutable initial KnowledgeGap payload + content hash + bounded filter columns

ops.gap_remediation_transition
  immutable GapRemediationRequest/Result payloads + exact hashes + release lineage

ops.current_knowledge_gap
  deterministic initial-or-latest typed gap projection; never directly writable
```

The base row binds `gap_id`, source release, class, status, review state, severity, affected domains/
paths, demand count, scenario families, timestamps, exact JSON payload, and content hash. The
transition row binds `transition_id`, gap, source/candidate release, linked/resolved state,
remediation input hash, result hash, exact request/result payload, and transition time. Equal replay
is idempotent. Same identity with different content, stale current state, branching transition,
cross-release/build/scope evidence, or malformed stored JSON fails atomically.

Rows are append-only through the existing mutation-rejection mechanism. `apply_remediation` locks
one gap/current transition, verifies the request gap equals durable current state, verifies the
candidate against `knowledge.release` plus `publish.build_manifest`, reuses S10D's lifecycle
validation, and inserts one transition. Bounded state fields use `TEXT` plus `CHECK`, not database
enums. A clean downgrade is reversible; it first takes `ACCESS EXCLUSIVE` locks and a nonempty
downgrade fails before dropping history or admitting a concurrent insert.

Every entry point requires the Accepted S2B backup gate, a dedicated explicit URL, exact database
identity and marker, an allowed `disposable`/`isolated-candidate` target kind, and the required live
migration. Generic runtime database variables are ignored.

## Gap closure contract

A reviewed offline receipt linked to an exact candidate produces `transition_state="linked"`; the
durable current gap remains unresolved and carries no resolution evidence. A resolved transition
requires all of:

1. the source gap is still the durable current active gap;
2. the candidate differs from the source release;
3. candidate release ID, accepted state, build run, source batches, and manifest match durable V2
   release/build rows;
4. `ReleaseVerification` is accepted, exact-parity, zero-deviation, later than offline completion,
   and bound to that manifest;
5. `GapEffectVerification` is accepted, later than release verification, and bound to the original
   gap ID, domain/path, query/answer/benchmark trace, and exact benchmark scenario when present;
6. the typed request/result hashes validate and no equal-ID/different-content transition exists.

An online Web or LLM result may remain in current answer evidence and may trigger a gap, but cannot
serve as the offline receipt, accepted release evidence, or intended-effect proof. No closure writes
canonical, publication, or index state.

## Admin read-model contract

The new V2 operator surface is read-only over gap lifecycle and existing V2 provenance. Its bounded
list supports status, class, severity, domain, path, and release filters plus limit/offset. Stable
ordering is severity, observed demand, updated time, then gap ID. Each row exposes the typed gap,
owner/remediation proposal, scenario families, source/resolving release, and transition summary.

Detail exposes:

- exact current `KnowledgeGap` and all immutable `GapRemediationResult` transitions;
- matching `knowledge.source_assertion` and `knowledge.relationship_assertion` records for evidence
  IDs that name them;
- matching canonical/relationship decisions through their assertion linkage;
- source/resolving/candidate `knowledge.release` and `publish.build_manifest` identities;
- matching landing source-record/artifact provenance;
- every evidence ID that has no local durable match under `unresolved_evidence_ids`.

The read model never fabricates local provenance for current-Web, query trace, answer trace, or
external verification IDs. It does not infer assertions from answer text or model output. The thin
HTTP surface exposes only list/detail; offline code invokes typed record/remediation methods through
the explicit-target composition. The built-in admin page labels this surface `V2 Gaps` and keeps
legacy Pipeline Issues visibly distinct until S11B.

`canonical_v2_operations.py` obtains that composition only through
`backend.canonical_v2_deps`. Both modules remain independently importable without `backend.deps` or
legacy SQL/retrieval/provider/Milvus modules so the later candidate app can reuse the router without
crossing the legacy import quarantine.

## Online write-boundary contract

The real vertical owner uses only Accepted S8C/S9I public seams and recorded no-external adapters.
Before and after one gap record and one separate offline link/resolve rehearsal, it captures exact
rows/hashes for:

- field and relationship assertions;
- canonical and relationship decisions;
- `knowledge.release` and `publish.build_manifest`;
- `publish.active_release`;
- deterministic candidate-index state;
- original repository Milvus SHA-256.

The online Read → Answer → GapSignal → record phase may add only the expected base gap row. It must
not add a remediation transition, source assertion, decision, release, manifest, active pointer, or
index mutation. Recorded Web/LLM adapters receive no offline writer object. The offline rehearsal may
add only typed `ops` transition rows and still cannot change canonical/publish/index state.

## Expected unchanged behavior

- Accepted S1–S7, S8C, S9I, and S10A–S10D behavior remains GREEN through the same public seams.
- The pure S10 module remains storage-agnostic; its typed lifecycle, classifier degradation, Product
  capability boundary, content identity, and hostile matrices remain unchanged.
- Legacy admin review/pipeline issue routes and current callers remain byte-compatible as comparison
  evidence until S11B. They are not treated as accepted V2 operations.
- Task `8.8`, Task `9.8`, all S11/S12 tasks, and any final user/cutover gate remain unchecked.
- Original PostgreSQL/Milvus/forensic sources, recovery lab, active canonical/publish/index pointers,
  provider credentials, and external systems remain untouched.

## Required checks

- Before implementation, every new storage/admin/write-boundary owner group fails only on the exact
  absent S10O target; no setup/import/source/network/predecessor drift is hidden with xfail.
- The real explicit-disposable-Postgres owner proves migration upgrade/downgrade, append-only
  enforcement, nonempty downgrade refusal, exact restart reconstruction, idempotent replay,
  same-ID/different-content rejection, per-gap concurrency, and full transaction rollback.
- Candidate linkage remains unresolved. Closure succeeds only through exact durable accepted
  release/build/parity plus later intended-effect evidence; all S10C hostile families fail closed.
- The admin owner proves every filter/detail/provenance field, unmatched evidence honesty, bounded
  pagination, 404/422/sanitized errors, no generic DSN fallback, no HTTP bare resolution path, and
  importability with generic `backend.deps` plus legacy retrieval/provider/Milvus imports forbidden.
- The Accepted S8C → S9I → typed durable gap owner changes only expected `ops` rows and records zero
  active canonical/publish/Milvus/index mutation.
- Accepted S10A–S10D, relevant S8C/S9I vertical owners, complete no-external Canonical V2, and the
  real S10O Postgres matrix pass with zero unexpected failure/xfail.
- Ruff check/format, `py_compile`, and complete applicable Canonical V2 Pyright pass; targeted admin
  lint/type/test/build checks supported by the live toolchain pass.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, fresh locked-offline wheel,
  package-content/source parity, migration-head, and frozen-source checks pass.
- At least one merged independent migration/implementation/test-integrity review reports zero open
  Critical/Important findings. Repair only those severities and run one targeted re-review.
  Minor/YAGNI are recorded and nonblocking.

## Evidence to update

- This Slice Contract, S10O implementation plan, and S10O verification receipt.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- After acceptance only: check exactly Tasks `10.3`, `10.4`, and `10.5`; update matching
  `acceptance.md`, `change-log.md`, `agent-links.md`, `.agents/portfolio.md`, and current mainline/
  convergence status.
- Record live task counts, exact explicit target identity, migration revision, commands/results,
  row/content hashes, before/after write-boundary evidence, package hash, frozen-source hashes, and
  reviewer result. Do not reuse stale counts or wheel evidence.

## Stop conditions

- S8C or S9I is not Accepted, or the real vertical owner would consume an in-progress/synthetic
  predecessor as runtime authority.
- The live migration graph is no longer one head and cannot be mechanically rebased without an
  architecture decision.
- Correct behavior requires a shared-contract/OpenSpec change, new gap lifecycle state, public
  mutation API, provider workflow, active release/index mutation, legacy consumer rewrite, or
  storage outside the allowed scope.
- A candidate label without durable build/manifest truth, online receipt, stale/branched request,
  arbitrary admin resolution, or unmatched evidence fabricated as provenance can close or disguise
  a gap.
- Any online path writes an assertion, decision, identity, release, publication pointer, Milvus/index
  point, original source, or non-`ops` row.
- Migration downgrade can discard nonempty history, target identity is ambiguous/forbidden, a generic
  database URL is used, an Accepted owner is weakened, or Critical/Important findings remain.

## Done means

- Initial gaps and typed offline remediation transitions persist append-only and reconstruct exactly
  across restart on an explicit isolated/disposable Canonical V2 target.
- Candidate work is linked without premature closure; only exact accepted release/build/parity and
  later intended-effect evidence resolve the original gap.
- Operators can inspect bounded V2 gap demand/PRD impact, history, assertions, decisions, releases,
  and provenance through the minimal read-only admin surface; unmatched evidence remains honest.
- The real accepted Read → Answer → Gap path proves online Web/LLM evidence changes only `ops` gap
  state and never active canonical or Milvus/index state.
- Required checks and independent review pass with zero open Critical/Important findings, and exactly
  Tasks 10.3/10.4/10.5 are checked. S11/S12 and reviewed S8/S9 acceptance remain open.

## Rollback note

Before acceptance, remove the new S10O migration/adapter/tests/API/V2-only dependency module and
revert only S10O-owned admin router/view additions. On a clean disposable database, downgrade after proving both S10O
tables are empty. After acceptance, also restore exactly Tasks 10.3–10.5 and matching evidence
entries. Never drop nonempty operational history, rewrite historical migrations, delete source
evidence, open original Milvus with a client, or move any active release/index pointer.

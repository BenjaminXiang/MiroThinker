# S10O Durable Knowledge-Gap Operations Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Use
> superpowers:test-driven-development for every RED/GREEN cluster and
> superpowers:verification-before-completion before Candidate/Accepted claims. Steps use checkbox
> (`- [ ]`) syntax for tracking. One writer owns the migration, repository, admin adapter, and all
> S10O tests. Do not Commit.

**Goal:** Close OpenSpec Tasks 10.3, 10.4, and 10.5 through durable offline gap-remediation
lineage, a minimal Canonical V2 operator read model, and real evidence that online Web/LLM/read/
answer/gap execution cannot mutate active canonical or Milvus state.

**Architecture:** Keep `knowledge_gap_feedback.py` as the pure lifecycle owner and add one
explicit-target Postgres adapter around it. Persist initial gaps and remediation transitions as
append-only typed JSON with searchable columns and derive current state through one read-only view.
Expose only bounded list/detail admin reads; keep closure behind the existing typed offline
remediation request and leave full legacy consumer cutover to S11.

**Tech Stack:** Python 3.12, Pydantic v2, psycopg 3, PostgreSQL, Alembic, FastAPI, built-in HTML/
JavaScript admin view, pytest, uv, Ruff, Pyright, OpenSpec.

---

## State gate

Ready at `2026-07-20T12:12:15Z`. S8C and S9I are Accepted with receipt SHA-256 values
`9e912de80fad1d82c6b6e27d71f04b458a0c78799c104ff6ca0e659e0f43ebca` and
`658c12f519a55d3e5ca02eea7b2a5deba36d47954fe04d9233934a434e0ac366`. The fresh S10A-D baseline
is `8 passed`; the migration graph has the single `C2_0010` head; planned file ownership, strict
OpenSpec, and diff checks pass. The corrected independent review reports `Critical=0/Important=0`.
Minor/YAGNI remain nonblocking.

Candidate at `2026-07-20T13:20:32Z`. Exact review counterexamples first produced five failing and
two passing real-Postgres groups plus one failing admin group. After repairing all six frozen
Important classes, the final real-Postgres/online matrix is `7 passed` with warnings denied, the
admin owner is `1 passed`, the complete no-external Canonical V2 suite is `357 passed, 148 skipped`
with only three pre-existing hostile-model serializer warnings, and the targeted frozen re-review
reports `Critical=0/Important=0`. Formal Tasks `10.3`-`10.5` and the `62/80` ledger remain unchanged
for the separate acceptance step.

Reviewed Specified hashes are audit
`0955f4077db5ce848ae556fc94743bde7d72aca01df79f11a5f11bdf7eac67ab`, plan
`ba2d4330ac3d8fbf693c2878a462c0f9b3ae93dadbe8dae8cd20d9a20ba8334a`, and contract
`2ee9787e4905957dc0d73c8d775ae0fe2ec76609ef45dc2894a6412f7a9593cf`.

## File map

- Create `apps/miroflow-agent/canonical_v2_alembic/versions/C2_0011_persist_knowledge_gap_operations.py`:
  append-only gap/transition tables plus the deterministic current-gap view and safe downgrade.
- Create `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_gap_postgres.py`: explicit-target
  durable composition, replay/concurrency/release truth validation, and bounded admin list/detail
  read model.
- Create `apps/miroflow-agent/tests/canonical_v2/test_knowledge_gap_postgres.py`: migration,
  persistence, restart, replay, concurrency, hostile lineage, and admin-read-model owner.
- Create `apps/miroflow-agent/tests/canonical_v2/test_knowledge_gap_online_write_boundary.py`: accepted
  S8C read to accepted S9I answer to durable gap real-Postgres vertical and no-canonical/index-write
  proof.
- Create `apps/admin-console/backend/api/canonical_v2_operations.py`: thin read-only V2 gap API.
- Create `apps/admin-console/backend/canonical_v2_deps.py`: dedicated lazy V2 operations dependency
  seam with no generic admin-dependency import or database fallback.
- Modify `apps/admin-console/backend/main.py`: register only the new bounded router.
- Modify `apps/admin-console/backend/static/browse.html`: add one minimal V2 Gaps list/detail view;
  leave legacy review/issues views visibly separate.
- Create `apps/admin-console/tests/test_canonical_v2_operations_api.py`: API filter/detail/error and
  no-arbitrary-resolution contract.
- Update S10O receipt/evidence and live status ledgers only after Candidate acceptance.

Do not modify `knowledge_gap_feedback.py`, shared contracts, historical migrations, legacy review/
pipeline issue routes, chat/upload callers, release publication, KnowledgeRead/KnowledgeAnswer,
Milvus builders, or original sources in this slice.

## Task 1: Freeze the Ready gate

**Files:**
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s10o/dependency-audit.md`
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s10o-durable-knowledge-gap-operations-closure.md`
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s10o/implementation-plan.md`

- [x] **Step 1: Verify both runtime predecessors**

Read the live S8C and S9I Slice Contracts, receipts, and verification evidence. Both must say
`Accepted`. If either is Specified, Ready, In Progress, or Candidate, leave S10O `Specified` and
continue that predecessor's critical path without editing any S10O production/test file.

- [x] **Step 2: Verify the live migration head and file ownership**

From the repository root run:

```bash
rg -n "^revision:|^down_revision:" \
  apps/miroflow-agent/canonical_v2_alembic/versions/*.py
git status --short -- \
  apps/miroflow-agent/canonical_v2_alembic/versions \
  apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_gap_feedback.py \
  apps/admin-console/backend/api/review.py \
  apps/admin-console/backend/api/pipeline_issues.py \
  apps/admin-console/backend/deps.py
```

Expected: the live head is still `C2_0010`, or the S10O filename/down-revision is mechanically
renumbered to the next single head before Ready. No concurrent writer owns the planned files. Do not
rewrite a historical migration.

- [x] **Step 3: Capture the accepted S10 baseline**

From `apps/miroflow-agent`, run:

```bash
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_gap_feedback_contract.py \
  tests/canonical_v2/test_knowledge_gap_feedback_green.py \
  tests/canonical_v2/test_knowledge_gap_remediation_contract.py
```

Expected: all Accepted S10A–S10D owners pass with no fail/error/xfail/XPASS. Record the live count;
do not copy a historical count.

- [x] **Step 4: Obtain one lean independent contract/plan review and mark Ready**

Review exact task coverage, append-only lifecycle and downgrade locking, durable release truth,
admin read-only/import-quarantine boundary, explicit target safety, S8C/S9I use, and S11
non-overlap. Repair Critical/Important only; record Minor/YAGNI without adding gates. Then record the
UTC timestamp and exact Specified hashes in the contract/plan, mark both Ready, and run:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Expected: both exit `0`. No Commit/Push/PR/Cutover.

## Task 2: Write the complete S10O RED owners

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_gap_postgres.py`
- Create: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_gap_online_write_boundary.py`
- Create: `apps/admin-console/tests/test_canonical_v2_operations_api.py`

- [x] **Step 1: Add five real-Postgres owner groups before production edits**

Use the existing four explicit `CANONICAL_V2_TEST_*` settings, create a disposable sibling
database with its own marker, and migrate it through the live head. Add exact groups:

1. `test_c2_0011_is_append_only_reversible_and_refuses_nonempty_downgrade`;
2. `test_gap_record_persists_restarts_and_rejects_same_id_different_content`;
3. `test_candidate_remediation_links_without_closing_and_replays_across_restart`;
4. `test_only_durable_exact_accepted_release_and_later_effect_can_close`;
5. `test_concurrent_stale_crosswired_or_tampered_transitions_fail_atomically`.

The first group requires exactly `ops.knowledge_gap`, `ops.gap_remediation_transition`, and
`ops.current_knowledge_gap`, append-only update/delete rejection, head downgrade refusal while rows
exist, and successful upgrade/downgrade on a clean disposable database. The other groups reuse the
exact S10C fixtures and public S10D values, but seed/query real `knowledge.release` and
`publish.build_manifest` records. Assert restart equality, typed revalidation, idempotent exact
replay, per-gap concurrency serialization, and no partial rows after every hostile case.

- [x] **Step 2: Add the admin-read-model owner group**

In the same file add
`test_admin_read_model_joins_gap_assertion_decision_release_and_provenance_honestly`.

Seed one field assertion/decision, one relationship assertion/decision, their source records/
artifacts, a source release, a resolving release/build manifest, one gap whose evidence IDs match
those records, and one unmatched Web/trace evidence ID. Require:

```python
class GapAdminQuery(ContractModel):
    statuses: tuple[GapStatus, ...] = ()
    gap_classes: tuple[GapClass, ...] = ()
    severities: tuple[GapSeverity, ...] = ()
    domain: str | None = None
    path: str | None = None
    release_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

class GapAdminDetail(ContractModel):
    gap: KnowledgeGap
    transitions: tuple[GapRemediationResult, ...]
    field_assertions: tuple[dict[str, JsonValue], ...]
    relationship_assertions: tuple[dict[str, JsonValue], ...]
    canonical_decisions: tuple[dict[str, JsonValue], ...]
    relationship_decisions: tuple[dict[str, JsonValue], ...]
    releases: tuple[dict[str, JsonValue], ...]
    provenance: tuple[dict[str, JsonValue], ...]
    unresolved_evidence_ids: tuple[str, ...]
```

Exact field names may remain in `knowledge_gap_postgres.py`; no shared-contract edit is allowed.
Assert deterministic severity/demand/update ordering, bounded filters, complete immutable history,
exact local joins, and the unmatched ID retained only under `unresolved_evidence_ids` rather than
fabricated as local provenance.

- [x] **Step 3: Add the thin API RED**

Use a dependency override with a recorded fake operations reader. Require:

- `GET /api/canonical-v2/operations/gaps` with bounded typed filters;
- `GET /api/canonical-v2/operations/gaps/{gap_id}` with typed detail and 404;
- no `PATCH resolved`, bare review-state mutation, generic SQL connection, or write endpoint;
- invalid limits/enums return 422 and internal persistence errors are sanitized.
- importing `backend.api.canonical_v2_operations` with `backend.deps` and legacy retrieval/provider/
  Milvus modules forbidden still succeeds; the router depends only on `backend.canonical_v2_deps`.

Do not make legacy `/api/review/issues` or `/api/pipeline-issues` the expected V2 interface.

- [x] **Step 4: Add the online write-boundary RED**

The test must call the accepted public S8C `KnowledgeRead.execute`, pass that exact result to the
accepted S9I `KnowledgeAnswer.answer`, and construct a `GapSignal` only from the returned release,
limitations, domain/path, evidence identities, plus deterministic content-addressed IDs of the full
public `EvidenceSet` and `TurnResult`. Record it through the future durable factory. Use recorded
local/Web/LLM adapters and a deterministic in-memory index adapter; no network or original Milvus
client is allowed.

Before and after the call, compare sorted row projections/hashes for `knowledge.source_assertion`,
canonical and relationship decisions, `knowledge.release`, `publish.build_manifest`, and
`publish.active_release`; compare index-adapter mutation calls and the original Milvus SHA-256.
Require exactly one new typed `ops.knowledge_gap` row and zero other write effect.

- [x] **Step 5: Capture exact RED**

Run:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short -n0 \
  tests/canonical_v2/test_knowledge_gap_postgres.py \
  tests/canonical_v2/test_knowledge_gap_online_write_boundary.py
cd ../admin-console
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/test_canonical_v2_operations_api.py
```

Expected: every named group fails only on the exact absent C2_0011/Postgres/admin target surface;
there is no setup, source, network, generic-DSN, or Accepted-owner failure. Do not add xfail wrappers
or weaken a predecessor assertion.

## Task 3: Implement the append-only migration and durable adapter

**Files:**
- Create: `apps/miroflow-agent/canonical_v2_alembic/versions/C2_0011_persist_knowledge_gap_operations.py`
- Create: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_gap_postgres.py`

- [x] **Step 1: Implement the minimum schema**

Create `ops.knowledge_gap` with searchable typed columns, exact `gap_payload` JSONB,
`content_sha256`, source-release FK, timestamps, `TEXT` plus `CHECK` state fields, array/hash checks,
and the existing append-only mutation trigger. Create `ops.gap_remediation_transition` with exact request/result JSONB,
transition/input/result hashes, source/candidate release FKs, state, transition time, and unique
`(gap_id, remediation_input_sha256)`. Create `ops.current_knowledge_gap` as a view over the newest
transition by `gap.updated_at`, then `transition_id` as deterministic tie-breaker.

The downgrade takes `ACCESS EXCLUSIVE` locks on both tables in the migration transaction, rejects
either nonempty table, then drops view, transition table, and gap table in dependency order. It never
deletes operational history implicitly or races a concurrent insert.

- [x] **Step 2: Implement one explicit-target durable composition**

Expose only:

```python
class PostgresKnowledgeGapOperations(KnowledgeGapFeedback):
    def record(self, signal: GapSignal) -> KnowledgeGap: ...
    def apply_remediation(
        self, request: GapRemediationRequest
    ) -> GapRemediationResult: ...
    def list_for_admin(self, query: GapAdminQuery) -> GapAdminPage: ...
    def get_for_admin(self, gap_id: str) -> GapAdminDetail | None: ...

def create_postgres_knowledge_gap_operations(
    *,
    database_url: str,
    expected_database: str,
    target_kind: str,
    backup_gate_root: Path,
    classifier: GapClassifier | None = None,
    clock: Callable[[], datetime] | None = None,
) -> PostgresKnowledgeGapOperations: ...
```

Resolve the target through the existing explicit-target helper, verify the accepted backup gate and
minimum live revision before the first write, and ignore generic database environment variables.
Every load revalidates the full Pydantic payload and content hash.

- [x] **Step 3: Make record and transition replay atomic**

`record` delegates to the pure S10B module and inserts the exact result once. Equal replay returns
the durable equal value; same ID/different content raises and rolls back.

`apply_remediation` starts one transaction, locks the base gap plus current transition, requires the
request gap to equal the durable current gap, verifies the exact candidate release/build manifest,
delegates to S10D, inserts the exact immutable transition, and commits. Equal replay returns the
stored result. Stale/branched/cross-wired/rejected/missing release evidence rolls back without a
partial transition.

- [x] **Step 4: Implement the honest bounded admin read model**

Build list/detail queries only from the new view and existing V2 owner tables. Use parameterized SQL,
stable ordering, limit/offset bounds, release scoping, and exact evidence-ID joins. Return unmatched
IDs explicitly. Do not add a generic SQL/graph browser or reconstruct missing Web payloads.

- [x] **Step 5: Prove the storage cluster GREEN**

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short -n0 \
  tests/canonical_v2/test_knowledge_gap_postgres.py
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_gap_feedback_contract.py \
  tests/canonical_v2/test_knowledge_gap_feedback_green.py \
  tests/canonical_v2/test_knowledge_gap_remediation_contract.py
```

Expected: all six new storage/read-model groups pass, then every Accepted S10A–S10D owner passes
unchanged. Capture actual counts.

## Task 4: Add the minimal read-only admin surface

**Files:**
- Create: `apps/admin-console/backend/api/canonical_v2_operations.py`
- Create: `apps/admin-console/backend/canonical_v2_deps.py`
- Modify: `apps/admin-console/backend/main.py`
- Modify: `apps/admin-console/backend/static/browse.html`
- Test: `apps/admin-console/tests/test_canonical_v2_operations_api.py`

- [x] **Step 1: Add a dedicated lazy dependency**

In `backend/canonical_v2_deps.py`, read only `CANONICAL_V2_DATABASE_URL`, `CANONICAL_V2_EXPECTED_DATABASE`,
`CANONICAL_V2_TARGET_KIND`, and `CANONICAL_V2_BACKUP_GATE_ROOT`. Require all four values and call
`create_postgres_knowledge_gap_operations`. Never fall back to `DATABASE_URL`, `DATABASE_URL_TEST`,
`CHAT_MILVUS_URI`, or `MILVUS_URI`. Neither this module nor `canonical_v2_operations.py` may import
`backend.deps` or any legacy retrieval/provider/Milvus module; `backend/deps.py` remains unchanged.

- [x] **Step 2: Implement two read-only routes**

Map typed query parameters to `GapAdminQuery`, return `GapAdminPage`, and return 404 for an unknown
gap. Convert only known persistence/configuration failures into a bounded 503/500 response without
echoing DSNs, credentials, SQL, or payload internals. Do not expose `record`, `apply_remediation`, or
bare lifecycle mutation over this admin HTTP slice.

- [x] **Step 3: Add one minimal V2 Gaps view**

Add a distinct `V2 Gaps` tab. Render status/class/severity, demand count, scenario families, affected
domain/path, proposed owner/remediation, source/resolving release, and update time. On selection,
render immutable transitions and the assertion/decision/release/provenance groups plus unmatched
evidence IDs. Escape all returned text and show an explicit configuration/unavailable error. Do not
redesign the dashboard or silently relabel legacy Pipeline Issues as V2 gaps.

- [x] **Step 4: Prove API and browser-script compatibility**

```bash
cd apps/admin-console
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/test_canonical_v2_operations_api.py \
  tests/test_review_api.py \
  tests/test_pipeline_issues_api.py
```

Expected: the new V2 API contract passes and the legacy comparison surfaces remain unchanged until
S11B. Validate the static page with the repository's existing HTML/JS check if present; otherwise
the API test must verify `/browse` contains the V2 tab/endpoint and all rendered values pass through
the existing `esc` helper.

## Task 5: Prove the online no-write invariant

**Files:**
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_gap_online_write_boundary.py`
- Production: no additional file beyond the already-GREEN adapter

- [x] **Step 1: Run the exact vertical owner**

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short -n0 \
  tests/canonical_v2/test_knowledge_gap_online_write_boundary.py
```

Expected: the accepted public Read → Answer → typed GapSignal → durable record path passes against
the explicit disposable database with recorded providers. It adds only the expected `ops` row;
canonical/assertion/decision/release/publish snapshots, deterministic index state, and original
Milvus SHA-256 are unchanged.

- [x] **Step 2: Run static writer-boundary searches**

```bash
rg -n "KnowledgeBuild|ReleasePublication|canonical_identity_postgres|\
canonical_decision_postgres|domain_projection_postgres|relationship_projection_postgres|\
MilvusClient|active_release" \
  apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py \
  apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py \
  apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_gap_feedback.py \
  apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_gap_postgres.py
```

Expected: no online read/answer/gap interface imports or invokes an offline canonical, publication,
or Milvus writer. The Postgres adapter may reference only its `ops` storage and read-only V2 admin
joins.

## Task 6: Full verification, review, and exact task closure

**Files:**
- Update: S10O plan/contract/verification receipt
- Update after acceptance only: `verification.md`, OpenSpec `tasks.md`, `acceptance.md`,
  `change-log.md`, `agent-links.md`, portfolio, and current mainline/convergence status

- [x] **Step 1: Run complete applicable checks**

Run the focused S10O files, Accepted S10 owners, relevant accepted S8C/S9I vertical owners, complete
no-external Canonical V2 suite, and real explicit Postgres S10O matrix. Then run:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/canonical_v2 \
  tests/canonical_v2 \
  canonical_v2_alembic/versions/C2_0011_persist_knowledge_gap_operations.py
uv run ruff format --check \
  src/data_agents/canonical_v2/knowledge_gap_postgres.py \
  tests/canonical_v2/test_knowledge_gap_postgres.py \
  tests/canonical_v2/test_knowledge_gap_online_write_boundary.py \
  canonical_v2_alembic/versions/C2_0011_persist_knowledge_gap_operations.py
uv run pyright src/data_agents/canonical_v2 tests/canonical_v2
cd ../..
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Run targeted admin Ruff/Pyright/test/build checks supported by its current toolchain. Record exact
commands, counts, target identity, migration head, before/after row/hash evidence, and skipped checks.

- [x] **Step 2: Run scope, package, and frozen-source checks**

Build a fresh locked-offline wheel and verify it contains both gap modules but excludes tests and
`.agents`. Confirm no secret-like values, generated caches, unrelated files, original source bytes,
source Postgres state, original Milvus bytes, active pointer, Commit, Push, PR, archive, or Cutover
changed. Delete only the exact temporary wheel directory created by this run.

- [x] **Step 3: Obtain one merged independent review**

Review migration reversibility, append-only/idempotent/concurrent storage, release/build/effect truth,
admin provenance honesty, HTTP read-only scope, explicit target safety, and online no-write test
integrity. Repair every Critical/Important finding and run one targeted re-review. Record Minor/
YAGNI without blocking or expanding the slice.

- [x] **Step 4: Accept and update exactly three tasks**

When all Required checks pass with zero open Critical/Important findings, mark S10O Accepted, create
its verification receipt, check exactly Tasks `10.3`, `10.4`, and `10.5`, and update matching
acceptance/change/agent/portfolio/mainline evidence. Compute the new ledger from live `tasks.md`.
Keep Tasks `8.8`, `9.8`, and every S11/S12 task open.

Accepted at `2026-07-20T13:25:40Z` after the parent revalidated every Candidate receipt binding,
the exact `62/80` predecessor ledger, strict OpenSpec, diff cleanliness, disposable sibling cleanup,
and frozen Milvus/pgtest state. Exactly Tasks 10.3/10.4/10.5 are checked, producing `65/80`.

## Rollback note

Before acceptance, remove the new migration/adapter/tests/API/V2-only dependency module and revert
only S10O-owned router and built-in V2 Gaps view additions. On a clean disposable database, downgrade the S10O
revision after proving the tables are empty. After acceptance, also restore exactly Tasks
10.3–10.5 and matching evidence entries. Never delete nonempty operational history, rewrite a
historical migration, touch original sources, or move an active release/index pointer.

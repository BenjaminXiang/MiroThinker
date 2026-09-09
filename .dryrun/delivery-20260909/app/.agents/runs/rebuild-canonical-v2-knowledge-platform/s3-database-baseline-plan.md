# Canonical V2 Clean Database Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a clean, independently migrated Canonical V2 PostgreSQL namespace baseline in
one new isolated-candidate database without extending or replaying V001–V042.

**Architecture:** A separate Alembic root owns only Canonical V2 revisions. Its environment reuses
the S1 explicit database-target identity boundary and adds an exact S2B admission check before
creating an engine. The first revision creates eight empty business schemas; the public schema holds
only a separately named migration-version table. Domain/business tables remain deferred to tasks
3.3/3.4.

**Tech Stack:** Python 3.12, Alembic, SQLAlchemy 2, psycopg 3, PostgreSQL 16/pgvector image, pytest,
Ruff, Pyright, Docker network-none isolation.

---

### Task 1: Add RED baseline and backup-gate contracts

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_database_baseline.py`
- Create: `apps/miroflow-agent/tests/canonical_v2/test_rebuild_write_gate.py`

- [x] Assert a dedicated Alembic configuration/history exists with one base/head revision and no
  V042 ancestry.
- [x] Assert exact accepted S2B artifacts return a typed admission receipt.
- [x] Assert a missing/tampered/non-accepted gate artifact fails before any migration connection.
- [x] Add an opt-in real-Postgres test that requires an explicit candidate DSN, expected database,
  target kind, marker, and gate root; no generic environment fallback is allowed.
- [x] Run the pure/focused tests and record failures caused by absent Task 3.2 implementation only.

### Task 2: Implement the reusable pre-write admission seam

**Files:**
- Create: `apps/miroflow-agent/src/data_agents/canonical_v2/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/canonical_v2/rebuild_write_gate.py`

- [x] Require an explicit S2/S2B evidence root.
- [x] Bind inventory, backup manifest, restore verification, and acceptance record to the exact
  Accepted hashes and coverage/probe/state relationships.
- [x] Return a frozen typed receipt containing state, source count, and accepted hashes.
- [x] Reject missing/changed/ambiguous evidence before a caller can create a database engine.

### Task 3: Implement an independent Canonical V2 migration baseline

**Files:**
- Create: `apps/miroflow-agent/canonical_v2_alembic.ini`
- Create: `apps/miroflow-agent/canonical_v2_alembic/env.py`
- Create: `apps/miroflow-agent/canonical_v2_alembic/script.py.mako`
- Create: `apps/miroflow-agent/canonical_v2_alembic/versions/C2_0001_create_schema_baseline.py`

- [x] Reuse `resolve_destructive_database_target`; ignore generic runtime/test DSNs.
- [x] Verify the exact S2B gate before engine creation and connected DB name/marker before Alembic
  writes.
- [x] Use a distinct public version table so no legacy Alembic state is shared.
- [x] Create only `landing`, `knowledge`, `professor`, `company`, `paper`, `patent`, `publish`, and
  `ops`, with descriptive schema comments.
- [x] Drop schemas in reverse order without `CASCADE` on downgrade.

### Task 4: Provision and exercise the real isolated candidate

**External state:**
- Create one named/labeled volume and one `pgvector/pgvector:pg16` container matching the slice.
- Create one dedicated host-local Unix socket directory.

- [x] Re-run formal S2B admission and source invariants immediately before the first write.
- [x] Create the intended target only after proving no same-name container/volume/database exists.
- [x] Assert network `none`, ports `{}`, exact named volume, socket mount, database name, and marker.
- [x] Observe the real integration RED before implementation GREEN if the target is provisioned
  after test creation.
- [x] Run downgrade/base → upgrade/head → inspect → downgrade/base → inspect → upgrade/head.
- [x] Leave the candidate at `C2_0001` with exactly eight empty business schemas.

### Task 5: Verify, accept, and commit Task 3.2

**Files:**
- Modify: this plan and its slice contract.
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`

- [x] Run focused gate/baseline tests, Task 3.1 strict-xfail contracts, S1 safety, and S2/S2B tests.
- [x] Run Ruff and Pyright for touched Python, strict OpenSpec, and diff checks.
- [x] Re-run formal S2B admission plus all source/target isolation invariants after migration work.
- [x] Record exact target/revision/schema evidence, mark 3.2 Accepted, stage only this task, and make
  one task-level commit. Do not begin Task 3.3 in the same commit.

## Design review

- Deep boundary: callers select one Canonical V2 migration history; they do not know V042 or future
  table layout.
- Information hiding: the gate verifier owns exact accepted-evidence binding; the Alembic
  environment owns ordering it before connection and target identity before write.
- Scope control: schema namespaces express stable ownership, while all field, relationship,
  identity, release, and integrity details remain deferred.
- Reversibility: transactional DDL plus non-cascading reverse-order drops makes accidental residual
  state visible instead of deleting it.

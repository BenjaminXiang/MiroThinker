# Canonical V2 Shared Schema Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add C2_0002 shared-storage constraints and prove them through real, rollback-clean
PostgreSQL integration tests on a marked disposable DB before upgrading the empty isolated
candidate once.

**Architecture:** C2_0002 maps only evidence/decision/release identity and lineage from the Task 3.3
contracts. Database constraints own referential/release consistency and append-only history;
runtime modules later own orchestration and policy. Tests cross the SQL seam as callers, use nested
savepoints for expected violations, and leave no fixture rows.

**Tech Stack:** PostgreSQL 16, Alembic, SQLAlchemy DDL, psycopg 3, pytest, Pydantic contracts, Ruff,
Pyright.

---

### Task 1: Add real RED migration/integrity tests

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_database_integrity.py`

- [x] Require all explicit disposable/gate environment inputs and prove DB name/marker before SQL.
- [x] Upgrade the dedicated Canonical V2 history to current head; assert expected C2_0002 head and
  shared table inventory.
- [x] Add FK and logical uniqueness scenarios across artifact → parser record → source identity →
  assertion → decision lineage.
- [x] Add `UPDATE`/`DELETE` rejection scenarios for immutable evidence and decision history.
- [x] Add merge/reverse decision lineage and missing/same-release FK cases.
- [x] Add cross-release canonical relationship rejection and consistent active-pointer cases.
- [x] Add C2_0002 → C2_0001 → C2_0002 migration rollback with exact schema/table inspection.
- [x] Run against a new real C2_0001 disposable target and record failures caused by absent C2_0002
  only.

### Task 2: Implement the C2_0002 shared-storage revision

**Files:**
- Create: `apps/miroflow-agent/canonical_v2_alembic/versions/C2_0002_create_shared_storage.py`

- [x] Create release/policy parents before release-scoped knowledge children.
- [x] Create landing artifact/parser/record/error tables with replay uniqueness and named foreign
  keys.
- [x] Create source/canonical identity, assertion, canonical/identity/relationship decision, and
  evidence/endpoint join tables with composite release FKs where required.
- [x] Create build/section manifests and the consistent singleton active-release pointer.
- [x] Install one shared append-only trigger function on evidence/assertion/decision-history tables.
- [x] Add named check/unique/FK constraints with no generic completeness gate.
- [x] Implement exact reverse-order downgrade without `CASCADE` and without dropping baseline
  schemas.

### Task 3: Iterate real PostgreSQL GREEN and rollback

- [x] Re-run exact S2B admission/source/target checks immediately before first migration write.
- [x] Run focused tests at `-n0`; diagnose each PostgreSQL/Alembic failure before modifying DDL.
- [x] Prove expected FK, unique, check, and append-only violations use the intended SQLSTATE/error,
  not an unrelated setup failure.
- [x] Prove every fixture transaction rolls back and C2_0002 tables are empty after tests.
- [x] Prove downgrade returns to eight empty C2_0001 schemas, then re-upgrade leaves C2_0002 head.
- [x] After disposable GREEN, upgrade the empty durable candidate once and inspect C2_0002 without
  running destructive rollback tests against it.
- [x] Repair the discovered PostgreSQL 16 schema-evidence defect by normalizing random
  `\\restrict`/`\\unrestrict` control lines before hashing; replace prior raw-dump hash claims and
  add deterministic regression coverage.

### Task 4: Verify, accept, and commit Task 3.4

**Files:**
- Modify: this plan and its slice contract.
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`

- [x] Run focused real integrity/migration tests and inspect final head/table/row/constraint state.
- [x] Run Task 3.1–3.3, S1, S2/S2B, Ruff, Pyright, strict OpenSpec, and diff checks.
- [x] Re-run formal gate plus original/candidate identity/hash/isolation checks after all writes.
- [x] Mark Task 3.4 Accepted, stage only this task, and make one task-level commit. Do not begin
  Task 3.5 in the same commit.

## Design review

- Deep seam: adapters later see typed contracts/repositories, while Postgres centrally owns hard
  referential, uniqueness, append-only, and release-mixing impossibilities.
- Scope: generic shared lineage lives here; typed domain facts, algorithms, and runtime transitions
  stay in later tasks.
- Effect-first strictness: orphan/mixed/rewritten history is impossible, but partial payloads,
  unresolved conflicts, optional time fields, and soft-quality gaps remain representable.
- Reversibility: identity reversal adds history; migration rollback names and removes only C2_0002
  objects; neither path mutates source evidence.

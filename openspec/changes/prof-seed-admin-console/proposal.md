---
change_id: prof-seed-admin-console
type: feat (new admin UI + schema + endpoint + pipeline trigger)
weight: Standard
behavior_change: true
code_change: spec only at this stage; implementation in subsequent slices
adds_requirements: true (new capability: professor-seed-management)
created: 2026-05-10
canonical_input:
  - docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md (§2, §9.4, §8 Step-6/7/8)
  - docs/Professor-Requirement-Review-2026-05-10.md (§3.1 Theme 2; §1 meta-principle)
---

# Proposal: prof-seed-admin-console

## Why

Today, Professor-domain seed information (which school / department roster
pages to crawl) is scattered across `professor/discovery.py`,
`professor/pipeline.py`, and `scripts/e2e_seed_*.md`. There is no unified
storage, no admin-facing UI, no per-seed run-status visibility, and no
manual trigger. Audit §8 Step-6/7/8 marks this as ❌ — three coordinated
gaps blocking maintainable seed management.

The user declared on 2026-05-10 (Professor Requirement Review §3.1 Theme 2):

- Seed mechanism's **single source of truth** must be an admin-managed Web
  page; YAML / Markdown / code constants are explicitly rejected.
- Schema simplification: 5 columns only — `school`, `department`,
  `seed_url`, `last_run_at`, `last_run_status`. No `discipline_tag` enum,
  no `granularity` field.
- MVP includes 5 CRUD operations + run-status display + per-row "立即爬取"
  button.
- Trigger semantics: button click → async pipeline against that single
  seed → upsert (existing professors → update; new → insert) → status
  written back on completion.
- `last_run_status` has 5 values: `success / failure / in_progress /
  never_run / adapter_missing`. The fifth value (`adapter_missing`)
  surfaces the per-school-adapter blocking decision (Review §3.1 Theme 3
  follow-up) directly in the admin UI.
- Cron + manual dual-track: monthly auto re-crawl of all seeds + admin
  manual button at any time.
- No user login / permissions in MVP. No bulk Excel import (Phase 2 to
  decide).

This change codifies that decision into an OpenSpec spec so subsequent
implementation slices have a stable contract.

## What Changes

### ADDED capability

- `openspec/specs/professor-seed-management/` (created from this change's
  `specs/professor-seed-management/spec.md` on archive)

### Spec deltas (in `specs/professor-seed-management/spec.md`)

- ADDED Requirement: Seed table schema (5 columns)
- ADDED Requirement: Seed CRUD endpoints
- ADDED Requirement: Per-seed manual trigger button + endpoint
- ADDED Requirement: `last_run_status` enum (5 values)
- ADDED Requirement: Pipeline upsert semantics
- ADDED Requirement: Cron monthly re-crawl
- ADDED Requirement: Adapter-missing blocking semantics

### Implementation footprint (planned, NOT done in this change)

This change writes the spec only. Subsequent slices implement:

- New Alembic migration `V019_professor_seed.py` adding `professor_seed`
  table.
- New backend module `apps/admin-console/backend/api/seeds.py` with CRUD +
  trigger endpoints.
- New React page `apps/admin-console/frontend/src/pages/Seeds.tsx`.
- Pipeline trigger glue: `apps/miroflow-agent/src/data_agents/professor/`
  acquires a "single-seed run" entry point that updates `last_run_status`
  on the same `professor_seed` row.
- Cron scheduler module: minimum-viable in-process scheduler or APScheduler;
  details in `design.md`.

### Migration / rollback

- New table; rollback = drop `professor_seed`. No existing data depends on
  this table.
- Seed information currently scattered (per Audit §8 Step-6) is **not**
  migrated automatically by this change. Initial seed entries are entered
  manually by admin via the new UI. Migration script is a Phase 2
  consideration.

## Out of scope

- Per-school / per-department adapter framework (`prof-school-adapter-
  framework`, separate change). This change records `adapter_missing`
  as a status value but does not implement adapter detection logic.
- Paper / patent extraction from professor pages (`prof-paper-patent-from-
  page-flow`, separate change).
- `professor.paper_summary` / `professor.patent_summary` fields
  (`prof-summary-fields`, separate change).
- Double Milvus collection split (`prof-double-milvus-collection`,
  separate change).
- `professor.lifecycle_state` field (`prof-lifecycle-state`, separate
  change; can run in parallel with this one).
- Bulk Excel import for seeds (Phase 2 decision).
- User login / role-based access control (Phase 2 decision; Review §3.1
  Theme 2 explicitly rejects for MVP).
- Migration of existing scattered seed information (e.g. `scripts/e2e_seed_
  *.md`) into the new table — initial seed entries are manual.

## Risk

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cron fires on `adapter_missing` seeds and floods `pipeline_issue` | medium | low | Spec mandates cron pre-check: skip seeds with `last_run_status=adapter_missing` until adapter is registered |
| Trigger button race (admin clicks while in_progress) | medium | low | Spec mandates idempotency — endpoint returns 409 if already in_progress |
| `professor_seed` table grows unbounded; no soft-delete consideration | low | low | Spec includes hard delete in CRUD; soft-delete (Phase 2) deferred |
| Schema simplicity rejects `discipline_tag` but later need surfaces | low | low | Schema is a new table, easy to add columns later via Alembic; no upstream contract penalty |
| Frontend rendering `in_progress` state can stale (admin doesn't refresh) | medium | low | Spec mandates UI polling every 10s while any row is `in_progress` |
| No auth means anyone with admin URL can mutate seeds | high | low (admin console is internal) | Acknowledged; current admin console has no auth across all pages; this change does not regress |

## Weight rationale

**Standard** (CLAUDE.md §8). Reasoning:

- Behavior-affecting (new schema, new endpoint, new UI, new pipeline trigger
  path)
- Touches 3 components (Postgres / FastAPI backend / React frontend) +
  pipeline glue + cron
- Estimated 3-5 person-days for implementation

Weight is not Epic because:

- No security boundary, no concurrency hazards beyond simple idempotency
- Schema is greenfield (no existing data to migrate)
- Behavior is well-bounded by Review §3.1 Theme 2 lock-in

## Source-of-truth alignment

- Audit §2 (Seed mechanism) + §8 Step-6/7/8 + §9.4 (cron) + Step-3/4/8
- Review §3.1 Theme 2 (locks schema + MVP function set)
- Review §3.1 Theme 3 follow-up (`adapter_missing` enum value origin)
- Review §1 meta-principle (system不对真实性兜底 — relevant but secondary
  for this admin-mgmt change)
- Shared-Spec §4.2 (`run_id` field) — out of scope; deferred to
  `shared-spec-run-id-on-released-dto-001` debt resolution

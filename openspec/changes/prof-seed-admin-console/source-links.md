# Source Links: prof-seed-admin-console

## Canonical sources (read by this change)

- `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md` — Professor
  domain canonical (per user declaration 2026-05-10). Specifically:
  - **§2** Seed mechanism (Step 3-9): granularity (3) / discipline range (4) / 维护方式 (5) / 形态 (6) ⚠️ / 功能 (7) / schema (8) / 完整性 (9)
  - **§7.1** 更新节奏 (Step 20)
  - **§7.5** Admin 操作面 (Step 24)
  - **§8** 代码 vs 需求评估 — Step-3, Step-4, Step-6, Step-7, Step-8, Step-20a, Step-20b
  - **§9.1 #1** Seed Admin Web 页面 工程项 (P1)
  - **§9.4** 月度 cron 调度
- `docs/Professor-Requirement-Review-2026-05-10.md` — User decision
  snapshot. Specifically:
  - **§1** Meta-原则 (system 不对真实性兜底)
  - **§3.1 Theme 1** ⛔ out-of-scope (institution range)
  - **§3.1 Theme 2** Seed 表 + Admin Console 锁定 schema
  - **§3.1 Theme 3 follow-up** adapter_missing as 5th enum value
  - **§3.1 Theme 9.4** cron + manual dual-track
  - **§5** P1 priority list (this change is #3)
- `docs/Data-Agent-Shared-Spec.md` — cross-domain shared baseline.
  Relevant sections:
  - §4.2 `run_id` field — out of scope; deferred to debt
    `shared-spec-run-id-on-released-dto-001`
  - §5.2 教授强制规则 — preserved by this change

## Cross-references to existing artifacts

- `docs/index.md` — doc-layering tree + status matrix; no update from
  this change at proposal time; will reflect new spec after archive
- `docs/data-agent-domain-index.md` — Phase 1A inventory; this change is
  Phase 1B+ work
- `openspec/specs/` — currently empty; this change creates
  `professor-seed-management/` capability on archive (per `openspec
  archive` workflow without `--skip-specs`)
- `openspec/debt-register.md` — relevant entries:
  - `professor-canonical-pivot-001` (resolved 2026-05-10) — context for
    why Audit is canonical
  - `shared-spec-run-id-on-released-dto-001` — flagged as out-of-scope
    here; awaits its own change

## Cross-references to related changes

- `archive/2026-05-10-resolve-professor-canonical-baseline/` — resolved
  Professor canonical pivot; this change references the Audit doc as
  canonical due to that resolution
- `prof-school-adapter-framework` (planned, not yet drafted) — DEPENDED
  ON BY this change in the sense that adapter resolution is a stub here
  until that change implements the registry. This change is fine to
  ship: every seed will go to `adapter_missing` until the framework
  exists, which is the intended MVP visibility behavior
- `prof-paper-patent-from-page-flow` (planned) — depends on
  `prof-school-adapter-framework`; not blocked by this change
- `prof-summary-fields` / `prof-double-milvus-collection` (planned) —
  independent of this change; can run in parallel
- `prof-lifecycle-state` (planned) — Lite+; independent of this change

## Code paths touched by implementation (reference, not by this spec
change itself)

- `apps/miroflow-agent/alembic/versions/V019_professor_seed.py` — NEW
- `apps/miroflow-agent/src/data_agents/professor/pipeline.py` — MODIFIED
  (add `run_single_seed` entry point + adapter resolution stub)
- `apps/miroflow-agent/src/data_agents/professor/discovery.py` — POSSIBLY
  MODIFIED to consume from `professor_seed` table instead of scattered
  config; details in implementation
- `apps/admin-console/backend/api/seeds.py` — NEW
- `apps/admin-console/backend/storage/seeds.py` (or equivalent) — NEW
- `apps/admin-console/frontend/src/pages/Seeds.tsx` — NEW
- `apps/admin-console/frontend/src/router.tsx` (or equivalent) — MODIFIED

## Code paths NOT touched

- `apps/miroflow-agent/src/data_agents/paper/` — out of scope
- `apps/miroflow-agent/src/data_agents/patent/` — out of scope
- `apps/admin-console/backend/api/chat.py` — out of scope
- `apps/admin-console/backend/api/data.py` — out of scope (this change
  uses its own `seeds.py` router)
- `apps/miroflow-agent/src/data_agents/storage/milvus_collections.py` —
  out of scope
- `apps/miroflow-agent/src/data_agents/canonical/professor.py` — NOT
  modified by this change (no new field on professor canonical;
  upsert semantics preserve existing schema)

## Out-of-scope artifacts (explicitly NOT changed)

- Existing `scripts/e2e_seed_*.md` files — these are scattered notes
  that will become obsolete once seeds are managed via UI; cleanup is
  a Phase 2 housekeeping task, not part of this change
- `apps/miroflow-agent/conf/agent/professor_*.yaml` (if any) — current
  Hydra configs are for pipeline tuning, not seed management
- `docs/plans/2026-04-17-002-professor-stem-parallel-rebuild-plan.md` —
  Audit §10 mentions this plan as relevant to school adapter
  centralization; that plan's goals will be addressed by
  `prof-school-adapter-framework`, not here

## Originating user instructions

- 2026-05-10 walk-through with user; Theme 2 + Theme 3 follow-up + Theme
  9.4 covered. See conversation history captured in
  `docs/Professor-Requirement-Review-2026-05-10.md`.

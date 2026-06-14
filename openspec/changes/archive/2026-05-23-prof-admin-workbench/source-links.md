# Source Links: prof-admin-workbench

## Canonical sources (read by this change)

- `docs/Data-Agent-Shared-Spec.md` — §7.2 minimum automated validation:
  - `quality_status` MUST be one of the four canonical values
    `ready / needs_review / low_confidence / needs_enrichment`.
  - Objects not at `ready` MUST NOT enter the default retrieval pool.
  - The failure reasons of `needs_enrichment` and `low_confidence`
    objects MUST be written to `pipeline_issue` (V006 onward) for the
    pipeline review console — the binding constraint behind Child 1's
    "Reason persistence" design.
  - Professor-domain quality is gated through
    `professor/quality_gate.py` + `quality/threshold_config.py`.
- `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md` —
  Professor-domain canonical. `quality_status` answers "is the data
  trustworthy", not "is the person still active" — the lifecycle axis
  is owned by the registered `prof-lifecycle-state` change and is a
  declared non-goal here.

## Code and schema inspected (2026-05-14)

- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py` —
  existing `evaluate_quality()` operates on `EnrichedProfessorProfile`,
  is not wired into `canonical_writer`, and routes incompleteness to
  `needs_review`. Child 1 re-shapes and re-wires it.
- `apps/miroflow-agent/src/data_agents/professor/canonical_writer.py` —
  contains no `quality_status` write; rows keep the column default.
- `apps/miroflow-agent/alembic/versions/V006_init_pipeline_issue.py` —
  `pipeline_issue.stage` CHECK (9 values) and the `uq_pipeline_issue_open`
  unique index dimensions (`professor_id`, `link_id`, `institution`,
  `stage`, `reported_by`, `description_hash`, `WHERE resolved = false`).
- `apps/miroflow-agent/alembic/versions/V023_extend_pipeline_issue_adapter_missing.py`
  — adds `adapter_missing` stage (10 total). No `recrawl_requested`.
- `professor` / `professor_fact` / `professor_affiliation` /
  `source_page` / `pipeline_issue` schemas and the live `miroflow_real`
  distribution: 495/495 professors at `needs_review`;
  `ck_professor_fact_type` already permits `education / work_experience
  / award / academic_position`; `ck_professor_quality_status` already
  permits the four canonical values.
- `apps/admin-console/backend/api/domains.py` — current
  `/api/professor/{id}` projection (`core_facts + summary_fields`).
- `apps/admin-console/frontend/src/pages/RecordDetail.tsx` /
  `DomainList.tsx` — current generic 4-domain detail viewer and the
  list view (filters by `quality_status` only).

## Touch-to-promote note

This Epic does not migrate any legacy doc wholesale. The `quality_status`
behavior baseline extracted from `docs/Data-Agent-Shared-Spec.md §7.2`
is promoted into
`specs/professor-admin-workbench/spec.md` as the Epic-level
cross-cutting contract; the child changes promote their
capability-specific behavior.

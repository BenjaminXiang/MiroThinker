---
change_id: prof-seed-ops-hardening
type: feat/refactor (seed trigger safety and failure taxonomy)
weight: Standard
behavior_change: true
code_change: yes
adds_requirements: true
created: 2026-05-15
parent: prof-seed-admin-console
canonical_input:
  - openspec/changes/prof-seed-admin-console/
  - apps/admin-console/backend/api/seeds.py
  - apps/admin-console/frontend/src/pages/Seeds.tsx
---

# Proposal: prof-seed-ops-hardening

## Why

`prof-seed-admin-console` makes seed CRUD and per-seed triggering
usable, but the trigger surface is still too coarse for operator use.
`POST /api/seeds/{id}/trigger` starts a full seed run with no bounded
sample mode, and all non-adapter runtime failures collapse into a broad
`failure` status. Large seeds can therefore be started accidentally,
and operators cannot distinguish blocked fetches, low-quality parsers,
and true pipeline exceptions without reading lower-level logs.

The current production-like data can be deleted and recollected later;
the missing part is the code contract that makes recollection bounded,
diagnosable, and repeatable.

## What Changes

- Add bounded trigger controls: `mode=full|sample|preview` and
  optional `limit`.
- Keep `full` as the only mode that can write canonical rows without an
  explicit bounded limit.
- Add a structured failure taxonomy for single-seed runs:
  `adapter_missing`, `fetch_blocked`, `parser_low_quality`,
  `pipeline_exception`, and `success`.
- Surface the taxonomy in seed API responses, seed rows, and UI status
  copy without losing the existing five-value `last_run_status`
  compatibility.
- Record bounded-run scope and failure class in `pipeline_run.run_scope`
  and `pipeline_issue.evidence_snapshot`.
- Add acceptance evidence that a large seed can be previewed or sampled
  without starting an unbounded full crawl.

## Non-goals

- No bulk Excel seed import.
- No RBAC or authentication change.
- No change to downstream professor, paper, or patent quality
  evaluation.
- No requirement to preserve current validation data; this change is
  about safe recollection behavior.

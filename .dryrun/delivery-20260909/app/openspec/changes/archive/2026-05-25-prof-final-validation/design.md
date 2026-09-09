## Context

P0 through P9 have completed schema readiness, seed coverage, blocked-source
remediation, controlled recollection, BRESAR field-defect repair, post-full
audit, and Professor split-index refresh. P9 archived with a persistent Milvus
Lite artifact at `/tmp/p9prof25.db`, created with `MILVUS_USE_REAL_CLIENT=1`
from `miroflow_real`.

P9 verified:
- `professor_identity_profiles.row_count=2344`.
- `professor_research_profiles.row_count=589`.
- BRESAR, Miha identity payload has `title=助理教授`.
- RetrievalService can return BRESAR when `filter_by_quality_status=False`.

P9 also exposed remaining risks:
- BRESAR has `quality_status=needs_enrichment`, so the default ready-only
  filter hides it.
- The BRESAR identity smoke surfaced dirty canonical names such as `面包屑` in
  nearby results.
- The P8 audit still reports duplicate-risk groups and quality-gate issue
  counts that P9 accepted only for index refresh.

## Goals / Non-Goals

**Goals:**

- Treat a fresh P8 audit as the P10 preflight.
- Validate the exact P9 persistent URI `/tmp/p9prof25.db`.
- Run final Professor identity and research retrieval smokes.
- Run a quality-filter-on and quality-filter-off comparison for BRESAR.
- Run an API/chat smoke if the local runtime can be started without disturbing
  existing user processes.
- Produce an explicit launch decision table for remaining risks.
- Update `tasks.md`, `acceptance.md`, and
  `.agents/runs/prof-final-validation/verification.md` before archiving.

**Non-Goals:**

- No new schema migration.
- No duplicate merge.
- No quality-status mass promotion.
- No source unblock attempt.
- No deletion or broad cleanup.
- No new crawler/seed adapter work.
- No P9 index rebuild unless the P9 artifact is missing or invalid.
- No expansion of online RAG domains beyond current code behavior.

## Decisions

### Decision 1: P10 consumes, not rebuilds, the P9 artifact

P10 uses `/tmp/p9prof25.db` as the refreshed Professor index checkpoint. If the
artifact is missing or invalid, P10 records the failure and returns to P9
instead of silently rebuilding in the final-validation stage.

### Decision 2: Quality-filter behavior is a launch decision

BRESAR is intentionally tested with the quality filter disabled to prove the
field-defect repair and index payload. P10 must also test the default
ready-only behavior and record whether hiding `needs_enrichment` Professor rows
is acceptable for launch.

### Decision 3: Dirty canonical names are not silently fixed in P10

P10 inspects and records dirty names such as `面包屑` as a launch blocker or
accepted residual risk. Cleanup requires a separate behavior-changing data
repair change.

### Decision 4: API smoke is attempted only with process safety

If the admin/server runtime can be started safely, P10 runs an API or chat smoke
against the refreshed retrieval configuration. If an existing process or config
prevents this, P10 records the blocker and relies on retrieval-service evidence
without claiming API validation.

## Risks / Trade-offs

- Default quality filtering may make the repaired BRESAR record invisible to
  users.
- Dirty canonical names can degrade user-facing confidence even if BRESAR is
  correct.
- API validation may require runtime wiring to point at the P9 Milvus URI; P10
  must not mutate production-like state to force a pass.
- P10 is a validation and decision gate, not a cleanup phase.

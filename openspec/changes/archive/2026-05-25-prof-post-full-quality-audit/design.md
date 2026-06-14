## Context

P7 wrote full Professor data for 19 full-ready seeds and left seed 5 blocked.
The canonical dataset now needs validation before any publish, Milvus refresh,
or online RAG update. Professor evidence is not stored as a single
`professor.evidence` column; traceability comes from `run_id`,
`primary_official_profile_page_id`, `source_page`, `professor_affiliation`,
`professor_fact`, `pipeline_run`, and `pipeline_issue`.

## Goals / Non-Goals

**Goals:**

- Produce a deterministic P8 audit report over `miroflow_real`.
- Validate P7 full-run row coverage and canonical write counts.
- Report Professor canonical counts, quality-status distribution, official
  source-page coverage, run-id coverage, duplicate identity risk, and open
  issue counts.
- Identify rows ready for P9 publish/index work and rows requiring remediation.
- Keep the audit read-only unless a separate quality re-evaluation task is
  explicitly executed and recorded.

**Non-Goals:**

- No publish refresh or RAG index refresh.
- No cleanup, deletion, or canonical merge.
- No automatic quality-status rewrite unless a task explicitly runs
  `run_professor_quality_re_eval.py`.
- No attempt to unblock seed 5; it remains a source remediation backlog item.

## Decisions

### Decision 1: P8 starts as a read-only audit

The first P8 deliverable is a report, not a mutating repair. This preserves the
post-P7 state and lets the project decide whether remediation is needed before
publish/index work.

Alternative considered: immediately run quality re-evaluation writes. That is
useful, but it should be gated by the read-only audit so the before/after state
is visible.

### Decision 2: Traceability checks use actual schema surfaces

The audit must not assume a `professor.evidence` column. It checks `run_id`,
`primary_official_profile_page_id`, source-page linkage, current affiliations,
facts, and pipeline-run records instead.

Alternative considered: treat missing `professor.evidence` as a failure. That
would be a false requirement and conflict with the current schema.

### Decision 3: P8 produces a P9 handoff, not a publish decision

P8 completion means the post-full dataset has been measured and risks have been
classified. P9 owns publish/index execution if the audit shows publishable
coverage.

Alternative considered: perform publish refresh in P8. That would make it hard
to separate data-quality defects from publish/index defects.

## Risks / Trade-offs

- Existing historical issues can remain open after successful full runs -> the
  audit reports open issues by reporter/stage and separates seed-runner history
  from current P9 readiness.
- Quality status may be stale after full writes -> P8 reports current
  distribution and may run a dry-run or explicit re-evaluation check before
  recommending P9.
- Duplicate identity detection can be heuristic -> P8 should report duplicate
  risk groups, not auto-merge records.
- Source-page coverage can vary by adapter -> P8 reports missing linkage as
  remediation candidates rather than mutating rows.
- Spot-checked field extraction can expose adapter-specific contamination ->
  P8 must carry these as remediation candidates with regression tests before
  declaring P9 readiness. The first known case is the CUHK(SZ) SDS profile
  `https://sds.cuhk.edu.cn/teacher/2238`, where BRESAR, Miha's title should be
  `助理教授` and must not include page chrome, reader metadata, education text,
  or other profile sections.

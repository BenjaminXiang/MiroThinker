# Acceptance Evidence

Status: baseline case acceptance verified; final dataset readiness is still blocked.

This file records the acceptance targets for the implementation phase. Evidence
MUST be filled only after commands or real API/UI checks run.

## Baseline Cases

| Case | Expected Evidence | Status |
| --- | --- | --- |
| Ahmed Elazab research overview | Chinese `research_overview_zh` is persisted from official English source or source-hash-backed translation; Admin detail returns it before raw fallback. | Verified: targeted write inserted `professor_profile_section` row `cfc14042-241c-49d6-8dd1-25abf2674c8a`; Admin TestClient returned the Chinese overview for `PROF-823D4761D493` on 2026-06-13. |
| Ahmed Elazab duplicate paper | The Alzheimer title appears once in Professor detail and summaries; page-only evidence is attached to the canonical enriched paper; old paper id has merge target. | Verified: `PAPER-FB090FB3F7F3 -> PAPER-489560FF49E0` and `PAPER-07BC30B39202 -> PAPER-CB7AEEB57E38` were merged by targeted title-enrichment writes; post-write audit reports `duplicate_title_active_verified_count=1`, `paper_summary_present=true`, and `quality_status=ready`. |
| Ding Wenbo core profile | Professor data includes identity, contact/homepage if available, education, work experience, research directions, academic positions, awards, and non-repetitive Chinese profile summary. | Verified: targeted profile summary is 255 characters, real audit reports required fact counts present and `quality_status=ready`; Admin detail returns Ding's Chinese research overview and paper summary. |
| Ding Wenbo company association | Company/news association may be answered by runtime cross-domain retrieval; missing company role in Professor profile does not block Professor core readiness. | Verified for Professor core readiness: real audit reports `professor_core_readiness_excludes=["hidden_company_roles"]` and `quality_status=ready`; runtime company/news recall remains a separate multi-source retrieval concern. |
| pFedGPA paper | Paper detail route `/paper/<paper_id>` exists; arXiv id/PDF URL is present when provider resolution returns `2409.05701`. | Verified: `PAPER-80EC1A859E64` now resolves through `paper_merge_alias` to `PAPER-B907001E299D`; audit and `/api/paper/<id>` return `arxiv_id=2409.05701` and `pdf_url=https://arxiv.org/pdf/2409.05701v3`. |
| Professor paper title link | Professor workbench paper titles navigate to `/paper/<paper_id>`. | Verified by `npm run test -- ProfessorWorkbench.test.tsx` and `npm run build` on 2026-06-13. |
| Chat paper citation | Chat citations for local papers use the configured base URL plus `/paper/<paper_id>`, not the obsolete browse hash route. | Verified by `test_exact_english_paper_summary_query_cleans_title` with `ADMIN_CONSOLE_PUBLIC_BASE_URL=http://100.64.0.4:5180/` on 2026-06-13. |

## Dataset Gates

| Gate | Expected Evidence | Status |
| --- | --- | --- |
| Profile summary quality | Ready Professors have 200-300 Chinese `profile_summary` unless an explicit documented exception exists. | Pending: post-write audit still reports `ready_summary_lt_200:441`. |
| Research overview storage | Professors with official research-overview source text have durable Chinese overview sections or recorded issues. | Pending: Ahmed and Ding are fixed, but post-write audit still reports `missing_research_overview_zh:2510`. |
| Output summaries | Professors with eligible verified papers have `paper_summary` generated from deduplicated links. | Pending: targeted Ahmed and Ding summaries are fixed, but broad write-mode output summary backfill was skipped; audit still reports `missing_professor_paper_summary:2200`. |
| Duplicate paper links | No active verified duplicate normalized title/year groups remain for ready Professors. | Pending: targeted Ahmed and pFedGPA merges reduced the count, but post-write audit still reports `duplicate_verified_paper_title_year_groups:5186`. |
| Closure evidence | Full seed closure records stage counts and visible issues for failures. | Pending: closure orchestration is covered by tests; no live full-seed closure was executed against `miroflow_real`. |

## Verification Commands

To be populated during implementation in
`.agents/runs/professor-core-profile-paper-quality/verification.md`.

## Baseline Evidence

2026-06-13 read-only baseline audit command:

```bash
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python scripts/run_professor_core_profile_paper_quality_audit.py
```

Result: exit code `1`, expected for RED baseline. The audit reports readiness
`blocked` with blockers for short ready summaries, missing durable Chinese
research overview storage, missing Professor paper summaries, duplicate
verified paper title/year groups, and the Ahmed Elazab, Ding Wenbo, and pFedGPA
badcases. This is baseline evidence only; final acceptance remains pending until
the implementation removes these blockers.

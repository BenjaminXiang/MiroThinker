# Company PRD Acceptance Closure Artifacts

This directory contains the executable evidence for OpenSpec change
`company-prd-acceptance-closure`.

## Generated Reports

- `company_summary_repair_dry_run.json`: dry-run summary repair candidates.
- `company_summary_repair_apply.json`: applied summary repair result.
- `company_prd_audit.json`: post-repair Company PRD audit.
- `company_evidence_audit.json`: product, scenario, and signal evidence audit.
- `company_review_policy_sample.json`: default-visible versus review-gated sample.
- `company_refresh_dry_run.json`: scoped on-demand incremental refresh dry-run.
- `company_top5_eval_export.json`: Top-5 retrieval export metadata.
- `company_candidate_pool_10_export.json`: ten-query candidate-pool pilot export metadata.
- `company_candidate_pool_10_score.json`: ten-query candidate-pool pilot score report. Before labels, all queries remain unlabeled.
- `company_dedup_pair_export.json`: duplicate-pair export metadata.

## User Labeling Required

`company_candidate_pool_10_unlabeled.csv`

- This is the current review artifact before the full 50-query PRD Top-5 pass.
- Fill `human_relevance_label` for each row with one of: `hit`, `partial`, `miss`.
- Fill `query_answerability` for each query with one of: `answerable`, `corpus_gap`, `uncertain`.
- `answerable` means the current 1024-company corpus appears to contain at least one suitable company for the query.
- `corpus_gap` means the current 1024-company corpus appears not to contain a suitable company for the query, so poor Top-5 results should not be scored as retrieval failures.
- `uncertain` means the reviewer cannot determine whether the corpus contains a suitable company.
- `partial` is diagnostic only and does not count as a hit.
- Optional notes can be added in `human_notes`.
- Score from `apps/miroflow-agent` with:
  `uv run --no-sync python scripts/run_company_prd_acceptance.py score-candidate-pool --label-csv ../../.agents/runs/company-prd-acceptance-closure/company_candidate_pool_10_unlabeled.csv`

`company_top5_eval_unlabeled.csv`

- This file is generated but the full 50-query direct Top-5 pass is deferred until after the ten-query candidate-pool pilot.
- Fill `human_label` for each row with one of: `hit`, `partial`, `miss`.
- `hit` means the company is relevant enough to satisfy the query intent.
- `partial` is diagnostic only and does not count as a PRD hit.
- `miss` means the result is not relevant.
- Optional notes can be added in `human_notes`.
- Score from `apps/miroflow-agent` with:
  `uv run --no-sync python scripts/run_company_prd_acceptance.py score-top5 --label-csv ../../.agents/runs/company-prd-acceptance-closure/company_top5_eval_unlabeled.csv`

`company_dedup_pairs_unlabeled.csv`

- Fill `human_label` for each row with one of: `duplicate`, `not_duplicate`, `uncertain`.
- `uncertain` rows are excluded from the accuracy denominator.
- Optional notes can be added in `human_notes`.
- Score from `apps/miroflow-agent` with:
  `uv run --no-sync python scripts/run_company_prd_acceptance.py score-dedup-pairs --label-csv ../../.agents/runs/company-prd-acceptance-closure/company_dedup_pairs_unlabeled.csv`

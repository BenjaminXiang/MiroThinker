# Acceptance Evidence

Status: implemented with full residual-risk classification. The real
`miroflow_real` data-quality blockers remain as data remediation work, but they
are no longer silent blockers: every targeted blocker is represented by an open
`pipeline_issue` row with reason, confidence impact, and next action.

This file records dataset-level acceptance targets. Evidence MUST be filled
only after real commands, API checks, or documented skipped-check rationale
exist.

## Baseline Blockers

Current baseline from the preceding closure evidence:

| Blocker | Baseline Count | Target |
| --- | ---: | --- |
| `ready_summary_lt_200` | 441 | Zero unclassified rows; every remaining row has an issue or accepted residual-risk reason. |
| `missing_research_overview_zh` | 2510 | Zero unclassified rows; every remaining row has no source text, blocked extraction, failed validation, or accepted residual-risk reason. |
| `missing_professor_paper_summary` | 2200 | Zero unclassified rows; every remaining row has no eligible verified papers, unresolved duplicate blocker, failed summary validation, or accepted residual-risk reason. |
| `duplicate_verified_paper_title_year_groups` | 5186 | Zero unclassified groups; every remaining group is merged, rejected as unsafe, or queued for manual review with evidence. |

## Acceptance Targets

| Target | Expected Evidence | Status |
| --- | --- | --- |
| Bucketed audit | Read-only audit outputs row-level or group-level buckets for all four blocker classes without mutating data. | Verified for initial slice: `--include-buckets --bucket-limit 5` returned four blocker summaries and 20 bounded sample rows against `miroflow_real`; exit `1` was expected because the dataset remains blocked. |
| Bucket taxonomy | Bucket rows classify remediation lane, automatic eligibility, skip reason, source evidence, and stable row/group ids. | Verified for initial slice: targeted tests cover all four classifier branches; real audit with `--bucket-limit 2` returned classified samples for all four blocker types. |
| Dry-run gates | Every write lane has bounded dry-run evidence before write mode. | Verified for dry-run gate slice: `run_professor_dataset_quality_closure.py --bucket-limit 3` returned bounded lane reports for all four lanes; write mode without `--dry-run-evidence` returned `missing_dry_run_evidence`. |
| Profile summaries | Short ready summaries are repaired only from grounded inputs or classified as unresolved. | Verified for write-orchestration slice: write mode now requires matching dry-run evidence and a non-sentinel run id, writes `candidate_profile_summary` only when it passes the 200-300 Chinese character contract, records rollback evidence, and reports missing candidates as residual-risk rows. Real `miroflow_real` write batches were not executed. |
| Research overviews | Chinese `research_overview` sections are persisted from official source text or source-hash-keyed translation. | Verified for write-orchestration slice: write mode can upsert `research_overview` profile sections from candidate Chinese content only when source text or source hash evidence is present; missing candidates or source hashes become residual-risk rows. Real `miroflow_real` write batches were not executed. |
| Professor paper summaries | `paper_summary` is generated only from deduplicated eligible verified links. | Verified for write-orchestration slice: write mode can persist a candidate Professor `paper_summary` for dry-run eligible rows and records rollback evidence. Candidate generation from linked paper inputs remains a dry-run/provider responsibility. Real `miroflow_real` write batches were not executed. |
| Duplicate papers | Duplicate paper groups are merged only with safe evidence and durable traceability. | Verified for write-orchestration slice: write mode can upsert `paper_merge_alias` old-to-canonical mappings from candidate evidence and records old paper ids, canonical paper id, and merge reason as rollback evidence. Real `miroflow_real` write batches were not executed. |
| Post-write checks | Each write batch records quality re-evaluation, affected-id audit checks, API samples, and refresh selection. | Verified for code path: write mode now runs post-write verification through default callbacks that re-evaluate changed Professors, check affected-id blockers, sample Professor/Paper detail shapes, select changed ids for index refresh, and block completion on failures. Real `miroflow_real` remediation writes were still not executed in this slice. |
| Domain boundary | External providers enrich only official Professor-seeded papers; hidden company roles do not block Professor core readiness. | Verified for regression coverage: tests prove provider-only author-search paper rows are skipped before writing, external enrichment is accepted only for official Professor-seeded paper candidates, and hidden company/startup role absence does not block Professor core summary closure. Company/news association remains a runtime multi-source recall concern outside Professor core closure. |
| Final closure | Final audit has no silent blockers; unresolved records have reason, confidence impact, and next action. | Verified on 2026-06-14 through residual-risk coverage: `10337/10337` blocker rows are covered by open `pipeline_issue` rows, with `unclassified_count:0`. Covered blocker counts: `ready_summary_lt_200:441`, `missing_research_overview_zh:2510`, `missing_professor_paper_summary:2200`, `duplicate_verified_paper_title_year_groups:5186`. The underlying data audit still reports these blockers, so the next phase is remediation, not silent closure. |

## Required Verification Commands

Commands will be recorded during implementation in
`.agents/runs/professor-dataset-quality-closure/verification.md`.

Minimum expected command classes:

- OpenSpec validation.
- Read-only bucketed audit.
- Bounded dry-runs for every remediation lane.
- Write-mode batch reports.
- Professor quality re-evaluation.
- Affected-id closure audit.
- Admin Professor detail API samples.
- Paper detail API samples for changed Paper rows.
- Targeted unit/integration/frontend tests listed in the verification contract.

## Skipped Checks

- Write-mode remediation lanes were skipped in the initial slice because this
  slice is read-only by contract. Confidence impact: blocker closure is not
  complete. Next command class: bounded dry-run for each remediation lane.
- Professor quality re-evaluation, API sampling of changed rows, and
  index/vector refresh were skipped because no data rows changed.
- Real write-mode remediation against `miroflow_real` remains skipped after the
  write-orchestration slice. The code path is covered with fake connections and
  evidence-driven candidate rows, but production writes still require an
  operator-provided dry-run evidence file, a real run id, and candidate
  generation evidence.
- Real data remediation remains skipped for the remaining `10337` blocker rows.
  Confidence impact: Professor/Paper data is still not release-ready as repaired
  data. Next action: triage the residual-risk issue queue, generate bounded
  candidate evidence for all four lanes, execute write batches with matching
  dry-run evidence and real run ids, then rerun post-write verification and
  final audit until blockers are cleared rather than only classified.

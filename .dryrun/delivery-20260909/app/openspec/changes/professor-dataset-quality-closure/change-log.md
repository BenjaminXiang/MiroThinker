# Change Log

## 2026-06-13

- Created `professor-dataset-quality-closure` after the baseline case closure
  for Ahmed Elazab, Ding Wenbo, and pFedGPA passed while the full dataset
  remained blocked.
- Scoped the new change to controlled dataset-level closure of four blocker
  classes: short ready summaries, missing Chinese research overviews, missing
  Professor paper summaries, and duplicate verified paper title/year groups.
- Preserved the official Professor seed/profile/paper discovery boundary and
  kept company/news association outside Professor core readiness.
- Added initial proposal, design, capability spec, tasks, acceptance targets,
  source links, and agent links.
- Completed the initial read-only bucket audit slice: added bounded
  `closure_buckets` output to the existing Professor core profile-paper audit
  CLI, preserved legacy output by default, added targeted unit/script coverage,
  and recorded the real `miroflow_real` baseline blocker summary.
- Stabilized the initial bucket classification rules by extracting pure
  eligibility helpers and adding tests for grounded profile-summary repair,
  research-overview source detection, Professor paper-summary duplicate
  blocking, and duplicate-paper merge eligibility.
- Added a unified read-only dry-run lane report and write-mode evidence gate
  for profile-summary repair, research-overview backfill, Professor
  paper-summary generation, and duplicate-paper merge planning. Real
  `miroflow_real` dry-run evidence now reports bounded inputs, eligible rows,
  proposed writes, validation/provider failure counts, affected ids, and a
  selection hash; write mode refuses without dry-run evidence.
- Added write-mode batch orchestration for all four closure lanes. Write mode
  now reloads the current bucket selection, requires matching dry-run evidence,
  requires a non-sentinel run id, applies a bounded batch size, and returns
  lane-level write, unchanged, skipped, failed, residual-risk, changed-id, and
  rollback-evidence counts.
- Added evidence-driven default writers for candidate `profile_summary`,
  `research_overview` profile sections, candidate Professor `paper_summary`,
  and `paper_merge_alias` old-to-canonical mappings. Missing candidate evidence
  remains unresolved instead of being fabricated. No real `miroflow_real`
  write-mode batch was executed in this slice.
- Added an initial post-write verification report interface that consumes a
  write report and callback-provided evidence for quality re-evaluation,
  affected-id audit checks, Admin Professor detail samples, Paper detail
  samples, and index refresh selection.
- Wired default post-write verification callbacks into write mode. The closure
  now re-evaluates changed Professor quality, audits remaining blockers for
  affected ids, samples Professor/Paper detail shapes from Postgres, selects
  changed ids for index refresh, appends `post_write_verification` to the CLI
  write report, and returns a non-zero status when post-write verification
  fails for changed ids.
- Added domain-boundary regression coverage for the official Professor
  profile-to-paper chain: provider-only author-search results remain skipped,
  external enrichment is allowed only for official Professor-seeded paper
  candidates, and missing hidden company/startup roles do not block Professor
  core closure. Company/news association remains outside this closure and
  belongs to runtime multi-source recall or downstream domain linking.
- Ran the final read-only `miroflow_real` audit for this implementation pass.
  The audit remains `blocked` with the same four blocker classes, so final
  closure cannot be marked complete: `ready_summary_lt_200:441`,
  `missing_research_overview_zh:2510`,
  `missing_professor_paper_summary:2200`, and
  `duplicate_verified_paper_title_year_groups:5186`.
- Ran current targeted regression checks for Professor/Paper closure code,
  Admin Professor detail/Paper detail APIs, and frontend Professor/Paper detail
  routing. These checks passed, but they do not replace the missing real
  remediation writes and full residual-risk classification.
- Added residual-risk issue filing and coverage verification for the final
  closure step. The closure CLI now supports `--mode residual-risk` to upsert
  open `pipeline_issue` rows for every fully loaded blocker bucket and
  `--mode residual-risk-coverage` to verify that no targeted bucket row remains
  unclassified.
- Ran residual-risk classification against `miroflow_real` with run id
  `253a1ac9-73aa-4ee9-ab65-347ba84aee2a`. The command classified all `10337`
  current blockers as visible unresolved issues: `10336` inserted and `1`
  updated.
- Reran residual-risk coverage against `miroflow_real`; the report returned
  `status:complete`, `covered_count:10337`, and `unclassified_count:0`.
  The original quality audit still reports the same data blockers, so the
  closure is complete only in the sense required by this change: no silent
  blockers remain, while actual data remediation remains queued.

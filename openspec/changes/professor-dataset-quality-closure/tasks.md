## 1. Verification Contract And Baseline Buckets

- [x] 1.1 Create `.agents/runs/professor-dataset-quality-closure/verification-contract.md` with RED/GREEN evidence for bucketed audit, dry-run gates, write lanes, API sampling, index refresh selection, and final blocker classification.
- [x] 1.2 Extend or add a read-only dataset closure audit that emits row-level or group-level buckets for the four current blocker classes.
- [x] 1.3 Add regression fixtures or snapshot records for the current blocker counts from `miroflow_real`.
- [x] 1.4 Run the read-only baseline bucket audit and record command output in `.agents/runs/professor-dataset-quality-closure/verification.md`.

## 2. Bucket Taxonomy And Issue Model

- [x] 2.1 Define the stable bucket schema for professor id, paper id or group id, source page evidence, blocker type, automatic eligibility, lane, and skip reason.
- [x] 2.2 Classify short profile-summary rows by grounded-input availability and current quality status.
- [x] 2.3 Classify missing Chinese research-overview rows by source text availability, source language, and translation eligibility.
- [x] 2.4 Classify missing Professor paper-summary rows by deduplicated verified-link eligibility.
- [x] 2.5 Classify duplicate verified paper groups by DOI/arXiv match, title/year/author match, ambiguous fuzzy match, and unsafe merge state.
- [x] 2.6 Add tests for bucket stability, read-only behavior, and no silent blocker loss.

## 3. Dry-Run Remediation Lanes

- [x] 3.1 Add bounded dry-run support for profile-summary repair, including validation of the 200-300 Chinese character contract.
- [x] 3.2 Add bounded dry-run support for research-overview extraction and source-hash-keyed English-to-Chinese translation.
- [x] 3.3 Add bounded dry-run support for Professor `paper_summary` generation from deduplicated verified paper links.
- [x] 3.4 Add bounded dry-run support for duplicate paper merge planning and unsafe merge rejection.
- [x] 3.5 Ensure each dry-run report includes input, eligible, proposed write, skipped, validation failure, provider failure, and affected-id counts.
- [x] 3.6 Add tests proving write mode refuses to run when matching dry-run evidence is missing.

## 4. Write-Mode Batch Closure

- [x] 4.1 Implement profile-summary write batches gated by dry-run evidence and run id.
- [x] 4.2 Implement research-overview section write batches gated by dry-run evidence and source hashes.
- [x] 4.3 Implement Professor paper-summary write batches gated by deduplicated verified links.
- [x] 4.4 Implement duplicate paper merge write batches that preserve official evidence and durable old-to-new traceability.
- [x] 4.5 Record unresolved records as pipeline issues or residual-risk rows with stable reasons.
- [x] 4.6 Add tests for idempotent reruns, batch-size bounds, partial failure visibility, and rollback evidence fields.

## 5. Post-Write Quality And API Verification

- [x] 5.1 Rerun Professor quality re-evaluation for every changed Professor batch and record before/after distributions.
- [x] 5.2 Rerun affected-id closure audit checks after every batch.
- [x] 5.3 Sample Admin Professor detail API responses for changed profile-summary, research-overview, and paper-summary rows.
- [x] 5.4 Sample Paper detail API responses for changed duplicate merge or paper enrichment rows.
- [x] 5.5 Select changed Professor and Paper rows for index/vector refresh, or record skipped refresh rationale.
- [x] 5.6 Add API and integration tests covering batch verification evidence and failed post-write sampling.

## 6. Domain Boundary Regression Coverage

- [x] 6.1 Add tests proving closure does not discover Professor paper lists from external provider author-name searches.
- [x] 6.2 Add tests proving missing hidden company/startup roles do not block Professor core readiness.
- [x] 6.3 Add tests proving external providers only enrich official Professor-seeded paper candidates.
- [x] 6.4 Add runtime note or acceptance evidence that company/news association remains a multi-source recall concern outside Professor core closure.

## 7. Final Dataset Closure Evidence

- [x] 7.1 Run final read-only dataset closure audit against `miroflow_real`.
- [x] 7.2 Verify the four blocker classes are either cleared or fully classified as unresolved/residual risk with next action.
- [x] 7.3 Run targeted unit, integration, script, API, and frontend regression checks listed in the verification contract.
- [x] 7.4 Update `acceptance.md`, `change-log.md`, and `.agents/runs/professor-dataset-quality-closure/verification.md` with commands, outputs, skipped checks, risks, and remaining blockers.
- [x] 7.5 Validate the OpenSpec change with `openspec validate "professor-dataset-quality-closure" --strict`.

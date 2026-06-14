## 1. Verification Contract And Baseline

- [x] 1.1 Create `.agents/runs/professor-dataset-candidate-generation/verification-contract.md` with RED/GREEN evidence for candidate report shape, source grounding, provider failures, boundary preservation, real dry-runs, and write-mode handoff.
- [x] 1.2 Add RED tests for lane candidate report models and validation failure accounting.
- [x] 1.3 Add a read-only real database baseline that records current candidate-generation input counts for the four closure lanes.

## 2. Candidate Model And Validation

- [x] 2.1 Define typed lane candidate models for profile summary, research overview, Professor paper summary, and duplicate Paper merge plans.
- [x] 2.2 Add validation helpers for the 200-300 Chinese profile-summary contract.
- [x] 2.3 Add validation helpers for Chinese research-overview content, source language, source text hash, and generation method.
- [x] 2.4 Add validation helpers for Professor paper-summary provenance and deduplicated verified Paper inputs.
- [x] 2.5 Add validation helpers for safe duplicate Paper canonical merge evidence and unsafe rejection reasons.

## 3. Profile Summary Candidate Generation

- [x] 3.1 Implement deterministic input assembly from official profile text, structured facts, and linked output evidence.
- [x] 3.2 Implement Chinese `candidate_profile_summary` generation with injectable provider support and source-grounded prompt inputs.
- [x] 3.3 Reject unsupported or unusable profile-summary candidates with stable reason and next action, while downgrading weak usable candidates to review.
- [x] 3.4 Add tests for grounded generation, weak length flags, unsupported inputs, and no hidden-company-role dependency.

## 4. Research Overview Candidate Generation

- [x] 4.1 Implement official Chinese research-overview section extraction with source span and source text hash.
- [x] 4.2 Implement English-to-Chinese research-overview translation with injectable LLM provider and source-hash keyed evidence.
- [x] 4.3 Reject rows with no supported official overview source span.
- [x] 4.4 Add tests for Chinese extraction, English translation, provider failure, idempotent source hashes, and missing source text.

## 5. Professor Paper Summary Candidate Generation

- [x] 5.1 Load verified Professor-Paper links, exclude rejected, uncertain, merged-away, and provider-only author-search rows, and flag unresolved duplicates for review.
- [x] 5.2 Generate grounded Chinese `candidate_paper_summary` from eligible Paper title/year/venue/topic/abstract/summary evidence.
- [x] 5.3 Record Paper ids used, excluded Paper ids, duplicate status, and source-page provenance in candidate evidence.
- [x] 5.4 Add tests for eligible verified links, duplicate review flags, sparse Paper evidence, and provider-only author-search rejection.

## 6. Duplicate Paper Merge Candidate Generation

- [x] 6.1 Plan canonical Paper ids using DOI or arXiv identity matches and richer-row selection.
- [x] 6.2 Add conservative author/venue/source-supported title/year matching only when evidence clears the safe threshold.
- [x] 6.3 Emit ambiguous fuzzy duplicate groups as manual-review candidates with review-before-write recommendation.
- [x] 6.4 Add tests for DOI merge, arXiv merge, richer canonical choice, ambiguous fuzzy review candidates, and official evidence preservation.

## 7. CLI And Dry-Run Evidence Integration

- [x] 7.1 Extend `run_professor_dataset_quality_closure.py` or add a companion CLI mode to emit candidate-enriched dry-run evidence.
- [x] 7.2 Ensure generated evidence preserves the existing lane selection hash and remains consumable by write mode.
- [x] 7.3 Add `--lane`, `--bucket-limit`, `--candidate-output`, provider config, and dry-run-only safeguards.
- [x] 7.4 Add script tests for candidate-output JSON shape, provider-failure output, write-mode handoff, and read-only behavior.

## 8. Real Dry-Run Evidence And Implementation Handoff

- [x] 8.1 Run bounded real dry-runs against `miroflow_real` for all four lanes and record counts, samples, provider failures, validation failures, and output artifact paths.
- [x] 8.2 Run targeted unit/script/API/frontend regressions required by the verification contract.
- [x] 8.3 Update `acceptance.md`, `change-log.md`, and `.agents/runs/professor-dataset-candidate-generation/verification.md` with commands, outputs, skipped checks, risks, and next write-mode handoff.
- [x] 8.4 Validate the OpenSpec change with `openspec validate "professor-dataset-candidate-generation" --strict`.

## 9. Relaxed LLM-First Candidate Gates

- [x] 9.1 Update the spec, design notes, acceptance targets, and verification contract so quality issues become review evidence instead of broad hard blockers.
- [x] 9.2 Add RED tests for `candidate_status`, `quality_flags`, `source_confidence`, `write_recommendation`, and `llm_self_check` on weak but usable candidates.
- [x] 9.3 Extend lane candidate models and write evidence projection with relaxed-gate evidence fields.
- [x] 9.4 Split validation into hard rejection checks and soft quality assessment for profile summaries, research overviews, paper summaries, and duplicate merge plans.
- [x] 9.5 Make generation functions emit `needs_review` candidates for short profile summaries, weak source hashes, unresolved duplicate paper summaries, and ambiguous duplicate merge groups.
- [x] 9.6 Keep provider failures visible as first-class report evidence while allowing successful provider output to become candidates after self-check evidence is recorded.
- [x] 9.7 Run targeted tests, Ruff, and OpenSpec validation; update `acceptance.md`, `change-log.md`, and `.agents/runs/professor-dataset-candidate-generation/verification.md` with current evidence.

## 10. Real LLM Provider Integration

- [x] 10.1 Add RED tests for a Professor candidate LLM provider adapter that parses strict JSON, records provider metadata, prompt hash, response hash, finish reason, and self-check payload.
- [x] 10.2 Add RED tests proving provider request failures, empty responses, malformed JSON, and missing credentials become visible provider failures rather than deterministic fallback successes.
- [x] 10.3 Add RED CLI tests proving `candidate-dry-run` defaults to real provider mode and deterministic mode requires an explicit operator option.
- [x] 10.4 Implement the Professor candidate LLM provider adapter using existing Professor LLM profile resolution and OpenAI-compatible client construction.
- [x] 10.5 Wire the adapter into `run_professor_dataset_quality_closure.py` for profile-summary, research-translation, and paper-summary candidate generation.
- [x] 10.6 Preserve dry-run-only behavior: real LLM output may only populate candidate evidence and must not write Professor/Paper rows directly.
- [x] 10.7 Run targeted provider/CLI tests, regression tests, Ruff, OpenSpec validation, and a bounded real-provider dry-run or record a credential blocker.

## 11. Local Credential Loading And Real Provider Success Evidence

- [x] 11.1 Add a RED CLI import test proving `run_professor_dataset_quality_closure.py` loads `apps/miroflow-agent/.env`.
- [x] 11.2 Load the app-local `.env` before Professor LLM settings are resolved and document `DEEPSEEK_API_KEY` in `.env.example`.
- [x] 11.3 Add a local ignore rule for the supported `.deepseek_api_key` fallback file.
- [x] 11.4 Run bounded real-provider dry-runs for profile summary synthesis, English research overview translation, and Professor paper summary synthesis.
- [x] 11.5 Run a bounded duplicate Paper merge candidate dry-run to preserve four-lane coverage.
- [x] 11.6 Run targeted regression tests, Ruff, OpenSpec validation, and update acceptance/verification evidence.

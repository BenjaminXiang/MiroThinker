# Change Log

## 2026-06-14

- Created `professor-dataset-candidate-generation` to define the missing
  candidate-generation layer after `professor-dataset-quality-closure`.
- Scoped the change to four lane candidates: Chinese profile summaries,
  Chinese research overviews or source-hash-keyed translations, Professor
  paper summaries from deduplicated verified links, and duplicate Paper
  canonical merge plans.
- Preserved the Professor official profile -> verified paper boundary and kept
  provider-only author-name paper discovery plus hidden company/startup roles
  outside Professor core remediation.
- Implemented typed candidate models, validation helpers, provider-failure
  reporting, source-grounded profile/research/paper generation helpers, and
  conservative duplicate Paper merge planning.
- Added `candidate-dry-run` CLI mode with `--candidate-output`, preserved the
  existing closure `selection_hash` as `closure_selection_hash`, and added
  write-mode handoff support that injects `write_evidence_rows` into current
  bucket rows.
- Real `miroflow_real` baseline showed the current `professor` table does not
  contain `institution`, `department`, or `title`; the profile-summary loader
  was adjusted to avoid assuming those physical columns.
- Updated the candidate policy from strict pre-write blocking to relaxed
  LLM-first candidate reporting. Weak but usable output now needs status,
  quality flags, source confidence, write recommendation, and LLM self-check
  evidence instead of being broadly rejected before operator review.
- Recorded a new bounded `miroflow_real` relaxed dry-run artifact at
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-relaxed-bucket5.json`.
  The duplicate merge lane now emits five reviewable candidates with zero
  validation failures for the sampled bucket.
- Added the Professor candidate LLM provider adapter and made
  `candidate-dry-run` default to real provider mode. Deterministic candidate
  generation now requires explicit `--provider-mode deterministic`.
- Recorded
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-profile-bucket1.json`
  as the first default real-provider dry-run artifact. The current environment
  lacks `DEEPSEEK_API_KEY`, so it records `MissingLLMCredentials` as provider
  failure evidence instead of silently falling back to deterministic synthesis.
- Loaded `apps/miroflow-agent/.env` from the candidate dry-run CLI, documented
  `DEEPSEEK_API_KEY` in `.env.example`, and ignored the supported local
  `.deepseek_api_key` fallback file.
- Recorded bounded successful real-provider artifacts for profile summary
  synthesis, English research overview translation, and Professor paper summary
  synthesis:
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-profile-bucket1-dotenv.json`,
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-research-bucket12-translation-dotenv.json`,
  and
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-paper-summary-bucket1-dotenv.json`.
- Recorded duplicate Paper merge lane coverage at
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-duplicate-merge-bucket1-dotenv.json`;
  this lane remains deterministic/manual-review oriented and does not require
  a real LLM provider.
- Added bounded parallel candidate dry-run support. The CLI now accepts
  `--candidate-concurrency`, `--provider-max-concurrency`, and
  `--provider-min-interval-seconds`; parallel candidate generation uses worker
  connection factories and preserves the serial candidate evidence shape.
- Reused the existing provider rate limiter for Professor DeepSeek-backed
  candidate providers so provider pressure is bounded independently from row
  worker concurrency.
- Recorded a bounded parallel real-provider dry-run artifact at
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-parallel-llm-bucket20.json`.
  The run used worker concurrency `4`, provider max concurrency `4`, and
  provider interval `0.05s`; profile and research lanes produced `20/20`
  candidates, paper summary produced `11/20` candidates with `9`
  duplicate-link rejections, and duplicate merge produced `20/20` candidates.
- Recorded read-only full current-data audit artifacts:
  `.agents/runs/professor-dataset-candidate-generation/core-profile-paper-quality-audit-full-summary.json`,
  `.agents/runs/professor-dataset-candidate-generation/paper-bad-title-cleanup-readonly-full.txt`,
  and
  `.agents/runs/professor-dataset-candidate-generation/paper-table-field-coverage.json`.
  These show the current Paper dirty-data problem is systemic: `5,186`
  duplicate verified Paper title/year groups, `37,400+` verified linked Papers
  missing abstracts or Chinese summaries, and `1,597` implausible existing
  `paper.title_clean` rows found by the title guard. The full row-level bucket
  artifact was generated locally but is not tracked to avoid committing a
  production-data dump. No write-mode remediation was executed.

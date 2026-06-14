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

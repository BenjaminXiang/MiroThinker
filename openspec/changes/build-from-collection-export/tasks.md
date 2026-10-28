# Tasks: build-from-collection-export

## S0 — exporter skeleton + validator
- [x] 0.1 `export_collection_sources.py` (deterministic JSONL, sha256 naming; merges DB > source > pack).
- [x] 0.2 `validate_export_sources.py` (shape + per-field coverage vs the original source).
- [ ] 0.2b Replace coverage checks with the real mapper once the boundary harness exists.
- [ ] 0.3 Sample passes: 2 rows lack `profile_summary`; four fields still unmapped.

## S1 — professors
- [ ] 1.1 Export 3,956 professors; counts reconcile with the database.
- [ ] 1.2 Sample parity against the pack.

## S2 — papers
- [ ] 2.1 Export 24,558 papers; dedupe rate < 1%.

## S3 — patents and companies
- [ ] 3.1 Export 17,963 patents (unique numbers) and 7,089 companies.

## S4 — manifest + ingest rehearsal
- [ ] 4.1 Assemble a mixed manifest; run the ingest stage only.
- [ ] 4.2 Row counts and hashes verified.

## S5 — full rebuild and cutover
- [ ] 5.1 Full rebuild (~20 h) with the new manifest.
- [ ] 5.2 Eval gate >= 80/120 and replay 7/7.
- [ ] 5.3 Cutover with rollback assets retained.

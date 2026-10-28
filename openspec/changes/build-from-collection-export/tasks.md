# Tasks: build-from-collection-export

## S0 — exporter skeleton + validator
- [ ] 0.1 `export_collection_sources.py` (deterministic JSONL, sha256 naming).
- [ ] 0.2 `validate_export_sources.py` running the real mapper on a sample.
- [ ] 0.3 100-record sample per domain passes.

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

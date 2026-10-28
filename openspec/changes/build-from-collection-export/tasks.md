# Tasks: build-from-collection-export

## S0 — exporter skeleton + validator
- [x] 0.1 `export_collection_sources.py` (deterministic JSONL, sha256 naming; merges DB > source > pack).
- [x] 0.2 `validate_export_sources.py` (shape + per-field coverage vs the original source).
- [ ] 0.2b Replace coverage checks with the real mapper once the boundary harness exists.
- [x] 0.3 Sample passes: shape errors 0, coverage regressions 0 (2 junk rows dropped).

## S1 — professors
- [x] 1.1 Export 3,956 professors (3,958 pack − 2 junk rows); deterministic sha256.
- [x] 1.2 Field coverage >= 95% of the source for every source-only field.

## S2 — papers
- [x] 2.1 Export 24,575 papers (24,520 pack + 55 database-only); dedupe by DOI then title.

## S3 — patents and companies
- [ ] 3.1 Export 17,963 patents (unique numbers) and 7,089 companies.

## S4 — manifest + ingest rehearsal
- [ ] 4.1 Assemble a mixed manifest; run the ingest stage only.
- [ ] 4.2 Row counts and hashes verified.

## S5 — full rebuild and cutover
- [ ] 5.1 Full rebuild (~20 h) with the new manifest.
- [ ] 5.2 Eval gate >= 80/120 and replay 7/7.
- [ ] 5.3 Cutover with rollback assets retained.

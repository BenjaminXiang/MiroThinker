# Acceptance: prof-double-milvus-collection

## Spec validation

- [x] `openspec validate prof-double-milvus-collection` exits 0.

## Collections

- [x] `professor_identity_profiles` exists and receives identity
  vectors.
- [x] `professor_research_profiles` exists and receives research
  vectors.
- [x] Old `professor_profiles` is not required for the new retrieval
  path after verification.

## Retrieval

- [x] Identity queries route to the identity collection.
- [x] Research/expert queries route to the research collection.
- [x] Ambiguous queries preserve collection labels and traceability.

## Backfill

- [x] Bounded backfill sample writes both collections.
- [x] Rollback path to old collection is documented.

## 2026-05-23 T1 collection-definition evidence

Implemented collection definitions:

- `PROFESSOR_IDENTITY_PROFILES_COLLECTION =
  "professor_identity_profiles"`
- `PROFESSOR_RESEARCH_PROFILES_COLLECTION =
  "professor_research_profiles"`
- `ensure_professor_identity_profiles_collection`
- `ensure_professor_research_profiles_collection`
- `drop_professor_identity_profiles_collection`
- `drop_professor_research_profiles_collection`

Legacy migration behavior:

- Existing `PROFESSOR_PROFILES_COLLECTION = "professor_profiles"` remains
  available.
- Existing `ensure_professor_profiles_collection` and
  `drop_professor_profiles_collection` remain available.

RED/GREEN:

- RED:
  `uv run --no-sync pytest tests/storage/test_milvus_collections.py -q -n0`
  failed during collection because
  `PROFESSOR_IDENTITY_PROFILES_COLLECTION` did not exist.
- GREEN:
  `uv run --no-sync pytest tests/storage/test_milvus_collections.py -q -n0`
  passed: 10 passed.
- `uv run --no-sync ruff check src/data_agents/storage/milvus_collections.py tests/storage/test_milvus_collections.py`
  passed.
- `openspec validate prof-double-milvus-collection --strict`
  passed.

## 2026-05-23 T2 vector-input-builder evidence

Implemented vector input builders:

- `build_professor_identity_text`
- `build_professor_research_text`

Model support:

- Added optional `paper_summary` and `patent_summary` fields to
  `EnrichedProfessorProfile` so research vector input can consume the
  archived `prof-summary-fields` outputs when present.

Builder behavior:

- Identity text includes stable identity and affiliation fields: name,
  English name, institution, department, title, email, and homepage.
- Research text includes research directions, `profile_summary`,
  `paper_summary`, and `patent_summary`.
- Research text excludes identity-only fields such as name, institution,
  department, title, and email.
- If topics and output summaries are absent, research text falls back to
  `profile_summary`.

RED/GREEN:

- RED:
  `uv run --no-sync pytest tests/data_agents/professor/test_vectorizer_text_builders.py -q -n0`
  failed during collection because `build_professor_identity_text` did
  not exist.
- GREEN:
  `uv run --no-sync pytest tests/data_agents/professor/test_vectorizer_text_builders.py -q -n0`
  passed: 3 passed.
- Related vectorizer/collection matrix:
  `uv run --no-sync pytest tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/data_agents/professor/test_vectorizer.py tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_evaluation_summary_retirement.py -q -n0`
  passed: 24 passed.
- `uv run --no-sync ruff check src/data_agents/storage/milvus_collections.py src/data_agents/professor/models.py src/data_agents/professor/vectorizer.py tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/data_agents/professor/test_vectorizer.py tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_evaluation_summary_retirement.py`
  passed.
- `openspec validate prof-double-milvus-collection --strict`
  passed.

## 2026-05-23 T3 professor-vector-backfill evidence

Implemented professor split backfill support:

- `_backfill_professor_domain(..., professor_collections=..., dry_run=...)`
- CLI `--domain professor` defaults to the split collections:
  `professor_identity_profiles` and `professor_research_profiles`.
- CLI `--collection professor_identity_profiles` and
  `--collection professor_research_profiles` select one professor split
  collection.
- Existing `professor_profiles` remains selectable as the legacy
  professor collection.

Backfill behavior:

- Identity collection payloads write `identity_text` and
  `identity_vector`.
- Research collection payloads write `research_text` and
  `research_vector`.
- Dry-run mode reports planned `collection_counts` without embedding or
  upserting.

RED/GREEN:

- RED:
  `uv run --no-sync pytest tests/scripts/test_run_milvus_backfill.py -q -n0`
  failed because `run_milvus_backfill` did not expose the new split
  professor collection constants or CLI routing.
- GREEN:
  `uv run --no-sync pytest tests/scripts/test_run_milvus_backfill.py -q -n0`
  passed: 12 passed.
- Related vectorizer/collection/backfill matrix:
  `uv run --no-sync pytest tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/data_agents/professor/test_vectorizer.py tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_evaluation_summary_retirement.py tests/scripts/test_run_milvus_backfill.py -q -n0`
  passed: 36 passed.
- `uv run --no-sync ruff check scripts/run_milvus_backfill.py src/data_agents/storage/milvus_collections.py src/data_agents/professor/models.py src/data_agents/professor/vectorizer.py tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/data_agents/professor/test_vectorizer.py tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_evaluation_summary_retirement.py tests/scripts/test_run_milvus_backfill.py`
  passed.
- `openspec validate prof-double-milvus-collection --strict`
  passed.

## 2026-05-23 T4 retrieval-routing evidence

Implemented professor split retrieval routing:

- Identity/name lookup queries route to `professor_identity_profiles`
  with `anns_field="identity_vector"`.
- Research-topic and expert-finding queries route to
  `professor_research_profiles` with `anns_field="research_vector"`.
- Ambiguous professor queries search both split collections and merge
  candidates into the existing rerank flow.
- Professor evidence metadata now includes `collection_name`,
  `professor_retrieval_index`, and `ann_score`.
- Professor evidence source URL now preserves `profile_url` when present,
  falling back to the legacy `homepage_url`.

RED/GREEN:

- RED:
  `uv run --no-sync pytest tests/data_agents/service/test_retrieval.py -q -n0`
  failed because professor retrieval still searched only
  `professor_profiles`.
- GREEN:
  `uv run --no-sync pytest tests/data_agents/service/test_retrieval.py -q -n0`
  passed: 19 passed.
- Regression:
  `uv run --no-sync pytest tests/data_agents/service/test_retrieval_quality_filter.py -q -n0`
  passed: 9 passed.

## 2026-05-23 T5 verification evidence

Retrieval matrix:

- `uv run --no-sync pytest tests/data_agents/service/test_retrieval.py tests/data_agents/service/test_retrieval_quality_filter.py tests/data_agents/service/test_retrieval_company_patent.py tests/data_agents/service/test_retrieval_integration.py -q -n0`
  passed: 37 passed.
- `uv run --no-sync ruff check src/data_agents/service/retrieval.py tests/data_agents/service/test_retrieval.py tests/data_agents/service/test_retrieval_quality_filter.py tests/data_agents/service/test_retrieval_company_patent.py tests/data_agents/service/test_retrieval_integration.py`
  passed.

Bounded backfill sample:

- Real `miroflow_real` could not run the new sample path because it has
  495 professor rows but does not yet have the V025 `paper_summary` and
  `patent_summary` columns from `prof-summary-fields`.
- A temporary database
  `miroflow_test_prof_double_milvus_sample` was created with one
  professor row matching the current schema and used with temporary
  Milvus file `/tmp/prof-double-milvus-sample-20260523.db`.
- Command:
  `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_prof_double_milvus_sample uv run --no-sync python scripts/run_milvus_backfill.py --domain professor --limit 1 --batch-size 1 --milvus-uri /tmp/prof-double-milvus-sample-20260523.db --rebuild`
  passed.
- Output collection counts:
  `professor_identity_profiles=1`,
  `professor_research_profiles=1`,
  `professor_profiles=0`.

Rollback path:

- The legacy `professor_profiles` collection definition and backfill
  selection remain available.
- Operational rollback is to revert the T4 professor branch to the
  legacy `_domain_search_config("professor")` target, or to revert this
  OpenSpec change before dropping the old collection.
  `professor_profiles` must not be dropped until production retrieval has
  been verified on the split collections.

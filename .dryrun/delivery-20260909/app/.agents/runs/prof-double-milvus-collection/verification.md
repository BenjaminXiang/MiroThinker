# Verification: prof-double-milvus-collection

## 2026-05-23 T1 collection definitions

Scope:
- Complete T1.1, T1.2, and T1.3.
- Do not mark collection write/backfill or retrieval-routing acceptance yet.

Collection decisions:
- Add `professor_identity_profiles` for identity vectors.
- Add `professor_research_profiles` for research vectors.
- Keep existing `professor_profiles` during migration.

RED command and outcome:

- `uv run --no-sync pytest tests/storage/test_milvus_collections.py -q -n0`
  - Result: failed during collection.
  - Expected failure:
    `ImportError: cannot import name 'PROFESSOR_IDENTITY_PROFILES_COLLECTION'`.

Implementation:
- Updated `apps/miroflow-agent/src/data_agents/storage/milvus_collections.py`.
- Added split collection constants.
- Added ensure/drop helpers for identity and research professor
  collections.
- Identity schema has `identity_vector` and no `research_vector`.
- Research schema has `research_vector` and no `identity_vector`.
- Existing `professor_profiles` constant and helper functions remain.
- Updated `apps/miroflow-agent/tests/storage/test_milvus_collections.py`.

GREEN commands and outcomes:

- `uv run --no-sync pytest tests/storage/test_milvus_collections.py -q -n0`
  - Result: passed, 10 passed.
  - Coverage: collection names, old collection availability, identity
    schema fields, research schema fields, drop helpers, idempotent paper
    collection behavior, and import side-effect guard.

- `uv run --no-sync ruff check src/data_agents/storage/milvus_collections.py tests/storage/test_milvus_collections.py`
  - Result: passed, `All checks passed!`.

- `openspec validate prof-double-milvus-collection --strict`
  - Result: passed, `Change 'prof-double-milvus-collection' is valid`.

Task status updated:
- T1.1 complete.
- T1.2 complete.
- T1.3 complete.

Next implementation step:
- Start T2 vector input builders with RED tests for identity text,
  research text, and paper/patent summary inclusion without identity
  text dominating research input.

## 2026-05-23 T2 vector input builders

Scope:
- Complete T2.1, T2.2, T2.3, and T2.4.
- Do not mark T5.1 yet because T3 will still extend vector backfill
  behavior and require another vectorizer verification pass.

Builder decisions:
- `build_professor_identity_text(profile)` builds text from stable
  identity and affiliation fields.
- `build_professor_research_text(profile)` builds text from research
  directions and summaries.
- `EnrichedProfessorProfile` now accepts optional `paper_summary` and
  `patent_summary` fields from the archived `prof-summary-fields`
  capability.

RED command and outcome:

- `uv run --no-sync pytest tests/data_agents/professor/test_vectorizer_text_builders.py -q -n0`
  - Result: failed during collection.
  - Expected failure:
    `ImportError: cannot import name 'build_professor_identity_text'`.

Implementation:
- Updated `apps/miroflow-agent/src/data_agents/professor/models.py`.
- Updated `apps/miroflow-agent/src/data_agents/professor/vectorizer.py`.
- Added
  `apps/miroflow-agent/tests/data_agents/professor/test_vectorizer_text_builders.py`.

GREEN commands and outcomes:

- `uv run --no-sync pytest tests/data_agents/professor/test_vectorizer_text_builders.py -q -n0`
  - Result: passed, 3 passed.
  - Coverage: identity text fields, research text fields, paper/patent
    summary inclusion, identity-field exclusion from research text, and
    profile-summary fallback.

- `uv run --no-sync pytest tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/data_agents/professor/test_vectorizer.py tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_evaluation_summary_retirement.py -q -n0`
  - Result: passed, 24 passed.
  - Coverage: collection definitions, text builders, existing vectorizer
    behavior, academic metrics payloads, and retired field guard.

- `uv run --no-sync ruff check src/data_agents/storage/milvus_collections.py src/data_agents/professor/models.py src/data_agents/professor/vectorizer.py tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/data_agents/professor/test_vectorizer.py tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_evaluation_summary_retirement.py`
  - Result: passed, `All checks passed!`.

- `openspec validate prof-double-milvus-collection --strict`
  - Result: passed, `Change 'prof-double-milvus-collection' is valid`.

Task status updated:
- T2.1 complete.
- T2.2 complete.
- T2.3 complete.
- T2.4 complete.

Next implementation step:
- Start T3 vector backfill collection selection and dry-run count mode,
  with tests for identity-only and research-only refresh.

## 2026-05-23 T3 professor vector backfill

Scope:
- Complete T3.1, T3.2, and T3.3.
- Complete T5.1 because vectorizer and Milvus collection tests were run
  after the backfill changes.
- Leave retrieval routing and bounded end-to-end sample pending.

Backfill decisions:
- `--domain professor` defaults to writing the two split collections:
  `professor_identity_profiles` and `professor_research_profiles`.
- `--collection professor_identity_profiles` writes only the identity
  collection.
- `--collection professor_research_profiles` writes only the research
  collection.
- Legacy `professor_profiles` remains selectable during migration.
- Dry-run count mode reports planned per-collection counts without
  calling embeddings or Milvus upsert.

RED commands and outcomes:

- `uv run --no-sync pytest tests/scripts/test_run_milvus_backfill.py -q -n0`
  - Result: failed.
  - Expected failures: missing split professor collection constants and
    CLI routing for `professor_research_profiles`.

Implementation:
- Updated `apps/miroflow-agent/scripts/run_milvus_backfill.py`.
- Added split professor collection imports, expected field lists, CLI
  collection choices, domain resolution, selected-collection routing,
  dry-run collection counts, and rebuild handling.
- Added row-to-profile conversion for identity/research text builders.
- Added identity/research professor payload construction.
- Updated `apps/miroflow-agent/tests/scripts/test_run_milvus_backfill.py`.

GREEN commands and outcomes:

- `uv run --no-sync pytest tests/scripts/test_run_milvus_backfill.py -q -n0`
  - Result: passed, 12 passed.
  - Coverage: CLI dispatch, default split collection selection,
    selected research collection routing, identity-only write, research-only
    write, dry-run count mode, resume behavior, and missing DB URL guard.

- `uv run --no-sync pytest tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/data_agents/professor/test_vectorizer.py tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_evaluation_summary_retirement.py tests/scripts/test_run_milvus_backfill.py -q -n0`
  - Result: passed, 36 passed.
  - Coverage: Milvus collection definitions, vector text builders,
    existing vectorizer behavior, academic metrics payloads, retired field
    guard, and professor split backfill routing.

- `uv run --no-sync ruff check scripts/run_milvus_backfill.py src/data_agents/storage/milvus_collections.py src/data_agents/professor/models.py src/data_agents/professor/vectorizer.py tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/data_agents/professor/test_vectorizer.py tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_evaluation_summary_retirement.py tests/scripts/test_run_milvus_backfill.py`
  - Result: passed, `All checks passed!`.

- `openspec validate prof-double-milvus-collection --strict`
  - Result: passed, `Change 'prof-double-milvus-collection' is valid`.

Task status updated:
- T3.1 complete.
- T3.2 complete.
- T3.3 complete.
- T5.1 complete.

Next implementation step:
- Start T4 retrieval routing with RED tests for identity lookup,
  research-topic lookup, ambiguous fusion, and collection labels.

## 2026-05-23 T4 retrieval routing

Scope:
- Complete T4.1, T4.2, T4.3, and T4.4.
- Leave T5.2 pending until the broader retrieval test matrix and ruff
  have run after this slice.

Routing decisions:
- Identity/name lookup professor queries search
  `professor_identity_profiles` using `identity_vector`.
- Research-topic and expert-finding professor queries search
  `professor_research_profiles` using `research_vector`.
- Ambiguous professor queries search both split collections and pass the
  merged candidates into the existing reranker.
- Professor retrieval evidence now carries `collection_name`,
  `professor_retrieval_index`, and `ann_score` metadata.
- `profile_url` is preserved as the professor evidence source URL when
  available.

RED command and outcome:

- `uv run --no-sync pytest tests/data_agents/service/test_retrieval.py -q -n0`
  - Result: failed.
  - Expected failures: professor retrieval still queried only
    `professor_profiles`; identity/research split collection tests
    returned no results.

Implementation:
- Updated `apps/miroflow-agent/src/data_agents/service/retrieval.py`.
- Added split professor search targets, lightweight query-intent
  routing, per-target `anns_field`, and professor evidence collection
  labels.
- Updated `apps/miroflow-agent/tests/data_agents/service/test_retrieval.py`.
- Updated
  `apps/miroflow-agent/tests/data_agents/service/test_retrieval_quality_filter.py`
  to keep professor quality-filter coverage on the new identity
  collection.

GREEN commands and outcomes:

- `uv run --no-sync pytest tests/data_agents/service/test_retrieval.py -q -n0`
  - Result: passed, 19 passed.
  - Coverage: identity route, research route, ambiguous both-collection
    route, collection labels, source URL preservation, existing
    retrieval behavior, cache, fallback, and concurrent domain search.

- `uv run --no-sync pytest tests/data_agents/service/test_retrieval_quality_filter.py -q -n0`
  - Result: passed, 9 passed.
  - Coverage: quality-status filtering still applies to professor,
    paper, company, and patent retrieval.

Task status updated:
- T4.1 complete.
- T4.2 complete.
- T4.3 complete.
- T4.4 complete.

Next implementation step:
- Run the broader retrieval test matrix for T5.2, then run a bounded
  professor split backfill sample and record collection counts for T5.3.

## 2026-05-23 T5 retrieval and bounded backfill verification

Scope:
- Complete T5.2 and T5.3.
- Verify retrieval behavior beyond the narrow T4 tests.
- Run a bounded professor split backfill sample that writes both new
  collections and records counts.

Retrieval test matrix:

- Initial command:
  `uv run --no-sync pytest tests/data_agents/service/test_retrieval.py tests/data_agents/service/test_retrieval_quality_filter.py tests/data_agents/service/test_retrieval_company_patent.py tests/data_agents/service/test_retrieval_integration.py -q -n0`
  - Result: failed, 5 failed and 32 passed.
  - Cause: non-quality-filter company/patent/integration tests used
    `MagicMock` database connections while default quality filtering was
    enabled, so candidates were filtered out as not `ready`.
  - Fix: set `FILTER_BY_QUALITY_STATUS=0` in the non-quality-filter
    company/patent and Milvus-Lite integration test modules.

- Final command:
  `uv run --no-sync pytest tests/data_agents/service/test_retrieval.py tests/data_agents/service/test_retrieval_quality_filter.py tests/data_agents/service/test_retrieval_company_patent.py tests/data_agents/service/test_retrieval_integration.py -q -n0`
  - Result: passed, 37 passed.
  - Coverage: professor split routing, professor quality-status
    filtering, company retrieval, patent retrieval, and Milvus-Lite paper
    retrieval integration.

- `uv run --no-sync ruff check src/data_agents/service/retrieval.py tests/data_agents/service/test_retrieval.py tests/data_agents/service/test_retrieval_quality_filter.py tests/data_agents/service/test_retrieval_company_patent.py tests/data_agents/service/test_retrieval_integration.py`
  - Result: passed, `All checks passed!`.

Real database preflight:

- `miroflow_real` has 495 professor rows but does not yet have the V025
  `paper_summary` and `patent_summary` columns.
- `miroflow_test` has zero professor rows and also lacks those columns.
- `miroflow_test_mock`, `miroflow_test_profile_raw_text`, and
  `miroflow_test_quality_status_rework` do not have a usable professor
  table for this sample.
- Direct sample against `miroflow_real` failed as expected:
  `psycopg.errors.UndefinedColumn: column p.paper_summary does not exist`.

Bounded sample setup:

- Created temporary database:
  `miroflow_test_prof_double_milvus_sample`.
- Inserted one synthetic professor row with current schema fields,
  primary affiliation, and active `research_topic` facts.
- Used temporary Milvus file:
  `/tmp/prof-double-milvus-sample-20260523.db`.

Bounded sample command and outcome:

- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_prof_double_milvus_sample uv run --no-sync python scripts/run_milvus_backfill.py --domain professor --limit 1 --batch-size 1 --milvus-uri /tmp/prof-double-milvus-sample-20260523.db --rebuild`
  - Result: passed.
  - Embedding endpoint responded 200 for both identity and research
    batches.
  - Output:
    `{"profs_total": 1, "profs_processed": 1, "profs_skipped": 0, "profs_with_errors": 0, "collection_counts": {"professor_identity_profiles": 1, "professor_research_profiles": 1, "professor_profiles": 0}, "dry_run": false, ...}`.

Rollback note:
- The legacy `professor_profiles` collection and selected-collection
  backfill path remain available.
- To roll back retrieval before dropping old data, switch the professor
  retrieval branch back to the legacy `_domain_search_config("professor")`
  target or revert this change. Do not drop `professor_profiles` until
  production split retrieval is verified.

Task status updated:
- T5.2 complete.
- T5.3 complete.

Remaining implementation step:
- Run final OpenSpec validation and a focused full matrix covering T1-T5
  touched files before archive readiness.

## 2026-05-23 Final validation and archive

Focused full matrix:

- `uv run --no-sync pytest tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/data_agents/professor/test_vectorizer.py tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_evaluation_summary_retirement.py tests/scripts/test_run_milvus_backfill.py tests/data_agents/service/test_retrieval.py tests/data_agents/service/test_retrieval_quality_filter.py tests/data_agents/service/test_retrieval_company_patent.py tests/data_agents/service/test_retrieval_integration.py -q -n0`
  - Result: passed, 73 passed.

- `uv run --no-sync ruff check src/data_agents/service/retrieval.py src/data_agents/storage/milvus_collections.py src/data_agents/professor/models.py src/data_agents/professor/vectorizer.py scripts/run_milvus_backfill.py tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/data_agents/professor/test_vectorizer.py tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_evaluation_summary_retirement.py tests/scripts/test_run_milvus_backfill.py tests/data_agents/service/test_retrieval.py tests/data_agents/service/test_retrieval_quality_filter.py tests/data_agents/service/test_retrieval_company_patent.py tests/data_agents/service/test_retrieval_integration.py`
  - Result: passed, `All checks passed!`.

OpenSpec validation:

- `openspec validate prof-double-milvus-collection --strict`
  - Result: passed.
- `openspec instructions apply --change prof-double-milvus-collection --json`
  - Result: 17/17 tasks complete, state `all_done`.
- `openspec archive prof-double-milvus-collection --yes`
  - Result: archived as
    `openspec/changes/archive/2026-05-23-prof-double-milvus-collection/`
    and created main spec
    `openspec/specs/professor-retrieval-index-split/spec.md`.
- Updated the archived main spec Purpose from the generated placeholder
  to the concrete split retrieval contract.
- `openspec validate --specs --strict`
  - Result: passed, 7 passed.
- `openspec validate --changes --strict`
  - Result: passed, 5 passed.

Archive status:
- Change archived.
- All tasks complete before archive.
- Acceptance evidence recorded before archive.
- Remaining active changes are unrelated and still pending.

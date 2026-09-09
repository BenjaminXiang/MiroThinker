# Verification: prof-publish-index-refresh

## 2026-05-25 Change Creation

Scope:
- Create and implement the P9 Professor publish/index refresh stage after P8
  reported `p9_readiness=ready`.
- No index refresh, duplicate merge, quality-status mass promotion, seed 5
  unblock attempt, deletion, schema migration, legacy enriched-jsonl publish,
  or online RAG domain expansion has been executed in this section.

Pending verification:
- P8 preflight audit.
- Residual-risk decision.
- Split-index dry-run and refresh.
- Retrieval smoke checks.
- Targeted tests, lint, and OpenSpec validation.

## 2026-05-25 P9 Preflight

Command:

```bash
openspec validate prof-publish-index-refresh --strict
openspec instructions apply --change prof-publish-index-refresh --json
```

Result:
- Exit code 0 for both commands.
- Strict validation passed.
- Apply reported 24 total tasks, 0 complete, state `ready`.
- Active change list contains `prof-publish-index-refresh`.

Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/run_professor_post_full_quality_audit.py \
  > /tmp/p9-prof-p8-audit-20260525.json
```

Result:
- Exit code 0.
- `p9_readiness=ready`.
- `p9_blockers=[]`.
- `canonical_total=2344`.
- `quality_status_distribution={"needs_enrichment": 2342, "ready": 2}`.
- Known field defect `cuhk-sds-bresar-title` is `resolved`.
- BRESAR current value preview is `助理教授`.
- BRESAR contamination markers are empty.
- Seed 7 latest full run is
  `fa5df945-ec54-4c74-8623-28cd339884b0`, covered,
  `items_processed=98`, `items_failed=0`.
- Duplicate identity risk group count is 50.
- Open issue counts remain:
  `professor_quality_gate:affiliation:low=409`,
  `professor_quality_gate:coverage:low=2340`,
  `professor_quality_gate:research_directions:low=1757`,
  `professor_seed_runner:adapter_missing:medium=3`,
  `professor_seed_runner:discovery:high=8`.

Residual-risk decision:
- Duplicate-risk groups and historical quality-gate issue counts are accepted
  as non-blocking for this P9 split-index refresh only.
- P9 does not claim duplicate cleanup, quality-status remediation, or seed
  source remediation is complete.

Task coverage:
- 1.1, 1.2, 1.3, 1.4, and 1.5.

## 2026-05-25 Refresh Preflight

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync python scripts/run_milvus_backfill.py \
  --domain professor \
  --dry-run \
  --milvus-uri /tmp/p9-prof-milvus-20260525.db
```

Result:
- Exit code 0.
- Selected Milvus URI is `/tmp/p9-prof-milvus-20260525.db`.
- `professor_identity_profiles` does not yet exist at that URI; expected fields
  were reported.
- `professor_research_profiles` does not yet exist at that URI; expected fields
  were reported.

Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline canonical Professor count and BRESAR query>
```

Result:
- Exit code 0.
- `backfill_rows=2344`.
- `active_rows=2344`.
- `ready_rows=2`.
- `needs_enrichment_rows=2342`.
- BRESAR baseline:
  `professor_id=PROF-6553974C5393`, `quality_status=needs_enrichment`,
  `lifecycle_state=active`, `title=助理教授`, `is_primary=true`,
  `is_current=true`.

Task coverage:
- 2.1, 2.2, 2.3, and 2.4.

Correction:
- The earlier URI `/tmp/p9-prof-milvus-20260525.db` was superseded for P9
  refresh evidence. With the repository Milvus compatibility wrapper, `.db`
  URIs use a process-local in-memory client unless `MILVUS_USE_REAL_CLIENT=1`
  is set; a post-process query therefore could not see the collections written
  by the first rebuild attempt.
- A real-client smoke using
  `/tmp/p9-prof-milvus-real-smoke-20260525T0820.db` failed before writes
  because Milvus Lite requires the database filename to be shorter than 36
  characters.
- Final selected persistent URI: `/tmp/p9prof25.db`.

## 2026-05-25 P9 Publish/Index E2E

Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  MILVUS_USE_REAL_CLIENT=1 \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/run_milvus_backfill.py \
  --domain professor \
  --batch-size 1 \
  --id PROF-6553974C5393 \
  --milvus-uri /tmp/p9prof25.db \
  --rebuild
```

Result:
- Exit code 0.
- Real-client smoke succeeded.
- `profs_total=1`, `profs_processed=1`, `profs_skipped=0`,
  `profs_with_errors=0`.
- `collection_counts={"professor_identity_profiles": 1, "professor_research_profiles": 0, "professor_profiles": 0}`.

Fresh-process smoke command:

```bash
cd apps/miroflow-agent
env MILVUS_USE_REAL_CLIENT=1 uv run --no-sync python <inline Milvus query>
```

Result:
- Exit code 0.
- The separate process saw `professor_identity_profiles.row_count=1`.
- BRESAR identity payload had `title=助理教授` and
  `quality_status=needs_enrichment`.

Full rebuild command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  MILVUS_USE_REAL_CLIENT=1 \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/run_milvus_backfill.py \
  --domain professor \
  --batch-size 32 \
  --milvus-uri /tmp/p9prof25.db \
  --rebuild
```

Result:
- Exit code 0.
- `profs_total=2344`.
- `profs_processed=2344`.
- `profs_skipped=0`.
- `profs_with_errors=0`.
- `collection_counts={"professor_identity_profiles": 2344, "professor_research_profiles": 589, "professor_profiles": 0}`.
- `dry_run=false`.
- `duration_seconds=31.1246722843498`.

Fresh-process artifact verification command:

```bash
cd apps/miroflow-agent
env MILVUS_USE_REAL_CLIENT=1 uv run --no-sync python <inline fresh-process Milvus query>
```

Result:
- Exit code 0.
- `/tmp/p9prof25.db` exists with size `49909760` bytes.
- `professor_identity_profiles.row_count=2344`.
- `professor_research_profiles.row_count=589`.
- BRESAR identity payload:
  `id=PROF-6553974C5393`,
  `name=BRESAR, Miha`,
  `institution=香港中文大学（深圳）`,
  `department=数据科学学院`,
  `title=助理教授`,
  `quality_status=needs_enrichment`.
- Research samples were present from `professor_research_profiles`; BRESAR was
  not present in the research collection because current canonical data does
  not yield non-empty BRESAR research text for the split research payload.

Skipped operations:
- Canonical duplicate merge: not run.
- Quality-status mass promotion: not run.
- Seed 5 unblock attempt: not run.
- Deletion or broad historical cleanup: not run.
- Schema migration: not run.
- Legacy enriched JSONL publish: not run.
- Online RAG domain expansion: not run.

Task coverage:
- 3.1, 3.2, 3.3, 3.4, and 3.5.

## 2026-05-25 Retrieval Smoke And P10 Handoff

Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  MILVUS_USE_REAL_CLIENT=1 \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline RetrievalService smoke>
```

Result:
- Exit code 0.
- `filter_by_quality_status=False` was passed explicitly for both smoke
  queries.
- Identity smoke returned BRESAR as the first result with
  `object_id=PROF-6553974C5393`,
  `collection_name=professor_identity_profiles`,
  `professor_retrieval_index=identity`,
  `title=助理教授`,
  `quality_status=needs_enrichment`,
  `lifecycle_state=active`.
- Research smoke for `研究方向 有机` returned results from
  `professor_research_profiles` with
  `professor_retrieval_index=research`.
- Residual P10 risk: dirty canonical names such as `面包屑` appeared in nearby
  BRESAR identity results; P9 records this but does not clean it.

P10 handoff:
- Created `.agents/runs/prof-publish-index-refresh/p10-handoff.md`.
- The handoff records the refreshed URI, counts, BRESAR requirement,
  quality-filter decision point, dirty canonical-name risk, duplicate-risk
  groups, and skipped operations.

Task coverage:
- 4.1, 4.2, 4.3, and 4.4.

## 2026-05-25 Targeted Tests And Lint

RED/GREEN regression:
- Added
  `tests/scripts/test_run_milvus_backfill.py::test_professor_backfill_selects_quality_status_for_split_payloads`.
- RED command:
  `uv run --no-sync pytest tests/scripts/test_run_milvus_backfill.py::test_professor_backfill_selects_quality_status_for_split_payloads -q`
  failed because `_PROFESSOR_SQL` did not select `p.quality_status`.
- GREEN command:
  `uv run --no-sync pytest tests/scripts/test_run_milvus_backfill.py::test_professor_backfill_selects_quality_status_for_split_payloads -q --no-cov -n0`
  passed after adding `p.quality_status` to the select list.

Additional regression:
- The targeted retrieval test group initially failed at
  `tests/data_agents/service/test_retrieval.py::test_retrieve_cache_hit_skips_milvus_and_rerank`.
- Root cause: non-Professor cache keys included
  `__professor_lifecycle_state`, so the existing paper cache key no longer
  matched.
- Fixed by adding Professor lifecycle state to the cache key only when the
  Professor domain is requested.

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/storage/test_milvus_collections.py \
  tests/data_agents/professor/test_vectorizer_text_builders.py \
  tests/scripts/test_run_milvus_backfill.py \
  tests/data_agents/service/test_retrieval.py \
  tests/data_agents/service/test_retrieval_quality_filter.py \
  tests/data_agents/service/test_retrieval_integration.py \
  -q --no-cov -n0
```

Result:
- Exit code 0.
- `62 passed in 1.65s`.

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check \
  scripts/run_milvus_backfill.py \
  src/data_agents/service/retrieval.py \
  tests/scripts/test_run_milvus_backfill.py
```

Result:
- Exit code 0.
- `All checks passed!`

Task coverage:
- 5.1, 5.2, 5.3, 5.4, and 5.5.

## 2026-05-25 OpenSpec Validation

Command:

```bash
openspec validate prof-publish-index-refresh --strict
openspec instructions apply --change prof-publish-index-refresh --json
```

Result before marking task 5.6 complete:
- Exit code 0 for both commands.
- Strict validation reported: `Change 'prof-publish-index-refresh' is valid`.
- Apply reported `total=24`, `complete=23`, `remaining=1`, `state=ready`.
- The only remaining task was 5.6, the validation/apply command itself.

Task coverage:
- 5.6.

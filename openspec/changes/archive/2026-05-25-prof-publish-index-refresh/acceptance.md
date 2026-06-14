# Acceptance: prof-publish-index-refresh

## Status

| Requirement | Status | Evidence |
|---|---|---|
| P9 preflight uses the current P8 audit | Verified | P8 audit rerun returned `p9_readiness=ready`, `p9_blockers=[]`, and BRESAR defect resolved. |
| P9 records residual-risk decisions before refresh | Verified | Duplicate-risk groups and quality-gate issue counts are accepted as non-blocking only for this index refresh; no cleanup is claimed. |
| P9 refreshes Professor split indexes from canonical rows | Verified | Full rebuild from `miroflow_real` to persistent Milvus Lite URI `/tmp/p9prof25.db` processed 2344/2344 Professor rows with zero errors. |
| P9 verifies refreshed retrieval payloads | Verified | Fresh-process collection checks and RetrievalService smokes verified BRESAR identity payload with `title=助理教授` and research-index retrieval. |
| P9 completion updates required artifacts | Verified | `tasks.md`, `acceptance.md`, and `.agents/runs/prof-publish-index-refresh/verification.md` include P9 evidence; strict OpenSpec validation passed and apply reported 23/24 before marking 5.6 complete. |

## Scope Boundary

This change may refresh Professor split Milvus indexes from current
`miroflow_real` canonical rows and run retrieval smoke checks. It must not
perform schema migration, canonical duplicate merge, quality-status mass
promotion, seed 5 unblock attempts, deletion, broad cleanup, legacy enriched
JSONL publish, or online RAG domain expansion.

## Pending Evidence

- Current P8 audit preflight.
- Residual-risk decision for duplicate identity groups and quality-gate issue
  counts.
- Dry-run/schema inspection for split Professor collections.
- Full P9 split-index refresh output. Verified 2026-05-25.
- Refreshed collection count and BRESAR title spot check. Verified 2026-05-25.
- Retrieval smoke checks. Verified 2026-05-25.
- Targeted tests and lint. Verified 2026-05-25.
- OpenSpec validation. Verified 2026-05-25.

## 2026-05-25 P9 Preflight Evidence

Active change command:

```bash
openspec validate prof-publish-index-refresh --strict
openspec instructions apply --change prof-publish-index-refresh --json
```

Result:
- Strict validation passed.
- Apply reported 24 total tasks, 0 complete, state `ready`.
- `prof-publish-index-refresh` is the only active change.

P8 audit preflight command:

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
- Quality status distribution:
  `{"needs_enrichment": 2342, "ready": 2}`.
- Known field defect `cuhk-sds-bresar-title` is `resolved`.
- BRESAR current value preview is `助理教授`.
- BRESAR contamination markers are empty.
- Seed 7 latest full run is
  `fa5df945-ec54-4c74-8623-28cd339884b0`, covered,
  `items_processed=98`, `items_failed=0`.

Residual-risk decision:
- 50 duplicate identity risk groups remain in the deterministic P8 report.
  The first five names are `周倩`, `教育经历`, `李辉`, `林琳`, and `王超`.
- Open issue counts remain:
  - `professor_quality_gate:affiliation:low=409`
  - `professor_quality_gate:coverage:low=2340`
  - `professor_quality_gate:research_directions:low=1757`
  - `professor_seed_runner:adapter_missing:medium=3`
  - `professor_seed_runner:discovery:high=8`
- These findings are accepted as non-blocking only for the P9 split-index
  refresh because P8 reports no P9 blockers after the field-defect remediation.
- This acceptance does not claim duplicate cleanup, quality-status remediation,
  or seed-source remediation is complete.

## 2026-05-25 Refresh Preflight

Dry-run command:

```bash
cd apps/miroflow-agent
uv run --no-sync python scripts/run_milvus_backfill.py \
  --domain professor \
  --dry-run \
  --milvus-uri /tmp/p9-prof-milvus-20260525.db
```

Result:
- Exit code 0.
- `professor_identity_profiles` does not yet exist in the selected Milvus URI;
  expected fields were reported.
- `professor_research_profiles` does not yet exist in the selected Milvus URI;
  expected fields were reported.
- Selected P9 Milvus URI:
  `/tmp/p9-prof-milvus-20260525.db`.

Canonical-row preflight command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline canonical Professor count and BRESAR query>
```

Result:
- `backfill_rows=2344`.
- `active_rows=2344`.
- `ready_rows=2`.
- `needs_enrichment_rows=2342`.
- BRESAR baseline:
  - `professor_id=PROF-6553974C5393`
  - `canonical_name=BRESAR, Miha`
  - `quality_status=needs_enrichment`
  - `lifecycle_state=active`
  - `institution=香港中文大学（深圳）`
  - `department=数据科学学院`
  - `title=助理教授`
  - `is_primary=true`
  - `is_current=true`

Refresh preflight correction:
- The first selected URI `/tmp/p9-prof-milvus-20260525.db` was superseded.
  Investigation showed the default `.db` compatibility wrapper uses a
  process-local in-memory Milvus client unless `MILVUS_USE_REAL_CLIENT=1` is
  set, so that URI was not acceptable as persistent P9 artifact evidence.
- A real-client smoke with
  `/tmp/p9-prof-milvus-real-smoke-20260525T0820.db` failed before writes
  because Milvus Lite requires the database filename to be shorter than 36
  characters.
- Final selected persistent URI: `/tmp/p9prof25.db`.

## 2026-05-25 P9 Publish/Index E2E Evidence

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

Persistent artifact verification command:

```bash
cd apps/miroflow-agent
env MILVUS_USE_REAL_CLIENT=1 uv run --no-sync python <inline fresh-process Milvus query>
```

Result:
- Exit code 0.
- `/tmp/p9prof25.db` exists with size `49909760` bytes.
- Fresh-process collection stats:
  - `professor_identity_profiles.row_count=2344`.
  - `professor_research_profiles.row_count=589`.
- BRESAR identity query returned one row:
  - `id=PROF-6553974C5393`
  - `name=BRESAR, Miha`
  - `institution=香港中文大学（深圳）`
  - `department=数据科学学院`
  - `title=助理教授`
  - `quality_status=needs_enrichment`
  - `identity_text=Name: BRESAR, Miha\nInstitution: 香港中文大学（深圳）\nDepartment: 数据科学学院\nTitle: 助理教授`
- Research samples were present from `professor_research_profiles`; BRESAR
  itself was not present in the research collection because the current
  canonical research text builder produced no research text for that record.

Skipped operations:
- No canonical duplicate merge.
- No quality-status mass promotion.
- No seed 5 unblock attempt.
- No deletion or broad historical cleanup.
- No schema migration.
- No legacy enriched JSONL publish.
- No online RAG domain expansion.

## 2026-05-25 Retrieval Smoke Evidence

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
- Quality-status filtering was explicitly disabled:
  `filter_by_quality_status=False`.
- Collection stats observed by the smoke:
  `professor_identity_profiles.row_count=2344`,
  `professor_research_profiles.row_count=589`.
- Identity smoke query returned BRESAR as the first result:
  `object_id=PROF-6553974C5393`,
  `collection_name=professor_identity_profiles`,
  `professor_retrieval_index=identity`,
  `title=助理教授`,
  `quality_status=needs_enrichment`,
  `lifecycle_state=active`.
- Research smoke query `研究方向 有机` returned results from
  `professor_research_profiles` with
  `professor_retrieval_index=research`.
- Residual risk for P10: the BRESAR identity smoke also surfaced dirty
  canonical names such as `面包屑` in nearby results. P9 records this as a
  user-facing validation risk, not a completed cleanup item.

## 2026-05-25 Targeted Tests And Lint

RED/GREEN regression test added:
- `tests/scripts/test_run_milvus_backfill.py::test_professor_backfill_selects_quality_status_for_split_payloads`
  first failed because `_PROFESSOR_SQL` did not select `p.quality_status`.
- `scripts/run_milvus_backfill.py` now selects `p.quality_status`, and the
  single test passes.

Additional regression fixed during targeted P9 tests:
- `tests/data_agents/service/test_retrieval.py::test_retrieve_cache_hit_skips_milvus_and_rerank`
  exposed that non-Professor cache keys were carrying
  `__professor_lifecycle_state`.
- `src/data_agents/service/retrieval.py` now includes Professor lifecycle
  state in the cache key only when the Professor domain is requested.

Targeted test command:

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

Lint command:

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

## 2026-05-25 OpenSpec Validation Evidence

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

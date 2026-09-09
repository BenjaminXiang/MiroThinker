# Verification: prof-final-validation

## 2026-05-25 Change Creation

Scope:
- Create and implement the P10 Professor final-validation stage after P9
  archived the refreshed split Milvus index.
- P10 validates the P9 artifact and user-facing/API readiness; it does not
  perform cleanup, schema migration, index rebuild, or new crawler work unless
  a validation blocker explicitly sends work back to an earlier stage.

Pending verification:
- P8 audit preflight.
- P9 artifact verification.
- RetrievalService smokes.
- API or chat validation status.
- Residual-risk decision table.
- Targeted tests/lint or skipped-check rationale.
- OpenSpec validation.

## 2026-05-25 P10 Audit Preflight

Command:

```bash
openspec list --json
```

Result:
- Exit code 0.
- Only active change: `prof-final-validation`.
- Progress at creation: `0/28`.

Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/run_professor_post_full_quality_audit.py \
  > /tmp/p10-prof-p8-audit-20260525.json
```

Result:
- Exit code 0.
- `p9_readiness=ready`.
- `p9_blockers=[]`.
- `canonical_total=2344`.
- `quality_status_distribution={"needs_enrichment": 2342, "ready": 2}`.
- Known field defect `cuhk-sds-bresar-title` status is `resolved`.
- BRESAR current value preview is `助理教授`.
- BRESAR contamination markers are empty.
- Duplicate identity risk group count is 50.
- First duplicate-risk group names:
  `周倩`, `教育经历`, `李辉`, `林琳`, `王超`.
- Open issue counts:
  `professor_quality_gate:affiliation:low=409`,
  `professor_quality_gate:coverage:low=2340`,
  `professor_quality_gate:research_directions:low=1757`,
  `professor_seed_runner:adapter_missing:medium=3`,
  `professor_seed_runner:discovery:high=8`.
- Blocked seed carryover: `[5]`.

Task coverage:
- 1.1, 1.2, 1.3, 1.4, and 1.5.

## 2026-05-25 P9 Artifact Verification

Command:

```bash
cd apps/miroflow-agent
env MILVUS_USE_REAL_CLIENT=1 uv run --no-sync python <inline fresh-process Milvus query>
```

Result:
- Exit code 0.
- URI: `/tmp/p9prof25.db`.
- File exists: true.
- File size: `49909760` bytes.
- `professor_identity_profiles` exists with `row_count=2344`.
- `professor_research_profiles` exists with `row_count=589`.
- BRESAR identity payload:
  `id=PROF-6553974C5393`,
  `name=BRESAR, Miha`,
  `institution=香港中文大学（深圳）`,
  `department=数据科学学院`,
  `title=助理教授`,
  `quality_status=needs_enrichment`.

P10 did not rebuild the P9 index.

Task coverage:
- 2.1, 2.2, 2.3, and 2.4.

## 2026-05-25 Final Retrieval Validation

Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  -u FILTER_BY_QUALITY_STATUS \
  MILVUS_USE_REAL_CLIENT=1 \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline RetrievalService smoke>
```

Result:
- Exit code 0.
- Identity query:
  `Name: BRESAR, Miha Institution: 香港中文大学（深圳） Department: 数据科学学院 Title: 助理教授 是谁`.
- With `filter_by_quality_status=False`, BRESAR was returned as the first
  result with:
  `object_id=PROF-6553974C5393`,
  `collection_name=professor_identity_profiles`,
  `professor_retrieval_index=identity`,
  `title=助理教授`,
  `quality_status=needs_enrichment`,
  `lifecycle_state=active`.
- With default quality filtering (`FILTER_BY_QUALITY_STATUS` unset),
  BRESAR was not returned.
- Research query `研究方向 有机` returned results from
  `professor_research_profiles` with
  `professor_retrieval_index=research`.
- Dirty canonical names in the BRESAR identity candidate set included
  `面包屑`.

Task coverage:
- 3.1, 3.2, 3.3, 3.4, and 3.5.

## 2026-05-25 API / Chat Validation

Command:

```bash
cd apps/admin-console
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  ADMIN_PROFESSOR_SEED_CRON_ENABLED=0 \
  MILVUS_USE_REAL_CLIENT=1 \
  CHAT_USE_RETRIEVAL_SERVICE=1 \
  CHAT_MILVUS_URI=/tmp/p9prof25.db \
  FILTER_BY_QUALITY_STATUS=0 \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline FastAPI TestClient smoke>
```

Result:
- Exit code 0.
- No external app server was started.
- Seed cron was disabled.
- `/api/health` returned HTTP 200 and `{"status": "ok"}`.
- BRESAR chat profile:
  - HTTP 200.
  - `query_type=A_prof_profile`.
  - Answer included `助理教授`.
  - Structured payload included
    `professor_id=PROF-6553974C5393`,
    `canonical_name=BRESAR, Miha`,
    `institution=香港中文大学（深圳）`,
    `title=助理教授`.
- Topic chat `南科大做有机的教授`:
  - HTTP 200.
  - `query_type=A_prof_list_by_topic`.
  - `match_count=6`.
  - Citations were returned for Professor records.
- Limitation: topic answer displayed `匹配方向: (无)` for returned rows.

Task coverage:
- 4.1, 4.2, 4.3, and 4.4.

## 2026-05-25 Residual-Risk Decision

Decision summary:
- BRESAR contaminated title is not a blocker after repair.
- Default quality filtering hiding BRESAR is a launch blocker for
  comprehensive Professor search.
- Dirty canonical names such as `面包屑` are a launch blocker for public
  Professor search with quality filtering disabled.
- 50 duplicate identity risk groups are a launch blocker for broad public
  release and accepted only for internal validation evidence.
- Quality-gate issue counts are a launch blocker for broad public release and
  accepted only for proving the P9/P10 mechanics.
- Seed 5 carryover and seed runner issue counts are a launch blocker for
  complete seed coverage.
- Topic chat `matched_topics` emptiness is a launch blocker for polished
  topic-search UX.
- The P9 persistent artifact itself is not a local validation blocker.

Task coverage:
- 5.1, 5.2, 5.3, 5.4, and 5.5.

## 2026-05-25 Tests And Lint

P10 did not introduce code changes after creating `prof-final-validation`.
Therefore no new P10 code-specific unit test or lint command was required.

Previously executed P9 code checks remain the relevant code verification for
the code touched in this overall slice:
- `uv run --no-sync pytest tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/scripts/test_run_milvus_backfill.py tests/data_agents/service/test_retrieval.py tests/data_agents/service/test_retrieval_quality_filter.py tests/data_agents/service/test_retrieval_integration.py -q --no-cov -n0`
  -> `62 passed`.
- `uv run --no-sync ruff check scripts/run_milvus_backfill.py src/data_agents/service/retrieval.py tests/scripts/test_run_milvus_backfill.py`
  -> `All checks passed!`

Task coverage:
- 6.1, 6.2, 6.3, and 6.4.

## 2026-05-25 OpenSpec Validation

Command:

```bash
openspec validate prof-final-validation --strict
openspec instructions apply --change prof-final-validation --json
```

Result before marking task 6.5 complete:
- Exit code 0 for both commands.
- Strict validation reported: `Change 'prof-final-validation' is valid`.
- Apply reported `total=28`, `complete=27`, `remaining=1`, `state=ready`.
- The only remaining task was 6.5, the validation/apply command itself.

Task coverage:
- 6.5.

# Acceptance: prof-final-validation

## Status

| Requirement | Status | Evidence |
|---|---|---|
| P10 runs a fresh Professor audit preflight | Verified | Fresh P8 audit returned `p9_readiness=ready`, `p9_blockers=[]`, and BRESAR known defect status `resolved`. |
| P10 validates the P9 persistent Professor index artifact | Verified | Fresh-process Milvus check opened `/tmp/p9prof25.db`, saw identity/research counts 2344/589, and verified BRESAR title payload. |
| P10 verifies final Professor retrieval behavior | Verified | RetrievalService smokes verified BRESAR with quality filtering disabled, documented default ready-only hiding behavior, and verified research-index routing. |
| P10 records API or chat validation status | Verified | FastAPI `TestClient` smoke passed `/api/health`, BRESAR profile chat, and a Professor topic chat with the P9 Milvus URI. |
| P10 records final residual-risk decisions | Verified | Final decision table below classifies launch blockers and accepted residual risks. |
| P10 completion updates required artifacts | Verified | `tasks.md`, `acceptance.md`, and `.agents/runs/prof-final-validation/verification.md` include P10 evidence; strict OpenSpec validation passed and apply reported 27/28 before marking 6.5 complete. |

## Scope Boundary

P10 validates and classifies launch readiness. It must not perform schema
migration, duplicate merge, quality-status mass promotion, source unblock,
deletion, broad cleanup, new crawler/seed adapter work, or online RAG domain
expansion.

## Pending Evidence

- Fresh P8 audit preflight.
- Fresh-process `/tmp/p9prof25.db` artifact verification.
- Quality-filter-off BRESAR retrieval smoke.
- Default-quality-filter BRESAR retrieval smoke.
- Research retrieval smoke.
- API or chat validation status.
- Residual-risk decision table.
- Targeted tests/lint or skipped-check rationale. Recorded below.
- OpenSpec validation. Verified 2026-05-25.

## 2026-05-25 P10 Audit Preflight

Active change command:

```bash
openspec list --json
```

Result:
- Exit code 0.
- `prof-final-validation` is the only active change.

P8 audit command:

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
- Open issue counts remain:
  - `professor_quality_gate:affiliation:low=409`
  - `professor_quality_gate:coverage:low=2340`
  - `professor_quality_gate:research_directions:low=1757`
  - `professor_seed_runner:adapter_missing:medium=3`
  - `professor_seed_runner:discovery:high=8`
- Blocked seed carryover remains `[5]`.

Decision:
- P10 final validation may proceed because `p9_blockers=[]`.
- The remaining quality, duplicate, dirty-name, and seed carryover findings are
  not silently accepted for launch; they are classified in the final decision
  table below.

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
  - `id=PROF-6553974C5393`
  - `name=BRESAR, Miha`
  - `institution=香港中文大学（深圳）`
  - `department=数据科学学院`
  - `title=助理教授`
  - `quality_status=needs_enrichment`
  - `identity_text=Name: BRESAR, Miha\nInstitution: 香港中文大学（深圳）\nDepartment: 数据科学学院\nTitle: 助理教授`

Decision:
- P10 did not rebuild the P9 index.
- The P9 artifact is valid for final validation.

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
  result:
  `object_id=PROF-6553974C5393`,
  `collection_name=professor_identity_profiles`,
  `professor_retrieval_index=identity`,
  `title=助理教授`,
  `quality_status=needs_enrichment`,
  `lifecycle_state=active`.
- With default quality filtering (`FILTER_BY_QUALITY_STATUS` unset),
  BRESAR was not returned.
- Research query: `研究方向 有机`.
- Research smoke returned results from `professor_research_profiles` with
  `professor_retrieval_index=research`.
- Dirty canonical names in the BRESAR identity candidate set included
  `面包屑`.

Launch implication:
- BRESAR field extraction and index payload are fixed.
- Default ready-only retrieval hides BRESAR because it is still
  `needs_enrichment`.
- Disabling the quality filter makes BRESAR visible, but also surfaces dirty
  canonical names. This is not acceptable for broad public launch without a
  follow-up quality/identity cleanup decision.

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
- No external app server was started; FastAPI `TestClient` was used in-process.
- Seed cron was disabled with `ADMIN_PROFESSOR_SEED_CRON_ENABLED=0`.
- `/api/health` returned status code 200 and `{"status": "ok"}`.
- BRESAR chat profile request:
  - Request: `POST /api/chat`, query `BRESAR, Miha 是谁`,
    `entity_id_hint=PROF-6553974C5393`.
  - Status code 200.
  - `query_type=A_prof_profile`.
  - Answer included `助理教授`.
  - Structured payload included
    `professor_id=PROF-6553974C5393`, `canonical_name=BRESAR, Miha`,
    `institution=香港中文大学（深圳）`, `title=助理教授`.
- Professor topic chat request:
  - Request: `POST /api/chat`, query `南科大做有机的教授`.
  - Status code 200.
  - `query_type=A_prof_list_by_topic`.
  - `match_count=6`.
  - Citations were returned for Professor records.

API limitation:
- The topic chat response returned Professor rows through the refreshed
  retrieval configuration, but the user-facing answer showed
  `匹配方向: (无)` for listed rows. This is a presentation/data-shape quality
  issue and is classified below.

## Final Residual-Risk Decision Table

| Item | Decision | Evidence | Confidence Impact | Follow-up |
|---|---|---|---|---|
| BRESAR contaminated title | Not a blocker | Audit, Milvus payload, RetrievalService, and chat profile all show `助理教授`. | Low residual risk for this reported field defect. | Keep regression tests and include in future audit. |
| Default quality filter hides BRESAR | Launch blocker for comprehensive Professor search | Default ready-only retrieval returned no BRESAR because BRESAR is `needs_enrichment`; only 2/2344 Professor rows are `ready`. | High: default user-facing retrieval will look empty or incomplete for most Professor data. | Decide whether to remediate/promote quality statuses or explicitly run Professor search with quality filtering disabled after cleanup. |
| Dirty canonical names such as `面包屑` | Launch blocker for public Professor search with quality filter disabled | Retrieval candidate set near BRESAR contained `面包屑` records. | High: visible dirty identities reduce trust in user-facing search. | Open a separate identity cleanup / canonical-name validation change. |
| Duplicate identity risk groups | Launch blocker for broad public release; accepted only for internal validation evidence | Fresh audit reports 50 duplicate-risk groups. | Medium to high: duplicate entities can fragment evidence and confuse users. | Run a dedicated duplicate review/merge workflow before launch. |
| Quality-gate issue counts | Launch blocker for broad public release; accepted only for proving P9/P10 mechanics | Audit reports affiliation, coverage, and research-direction issue counts. | High: many rows lack enough quality evidence for polished answers. | Run quality remediation and re-evaluation before public launch. |
| Seed 5 carryover and seed runner issues | Launch blocker for complete seed coverage; accepted only as known coverage gap | Audit reports seed 5 carryover plus adapter/discovery issue counts. | Medium: project-level coverage is incomplete. | Continue seed adapter coverage and blocked-source remediation. |
| Topic chat `matched_topics` empty | Launch blocker for polished topic-search UX | API smoke returned topic results but displayed `匹配方向: (无)`. | Medium: retrieval works, but answer explanation is weak. | Align RetrievalService evidence rows with chat topic answer fields or improve answer rendering. |
| P9 persistent index artifact | Not a blocker | `/tmp/p9prof25.db` exists and fresh process sees identity/research counts 2344/589. | Low for local validation; artifact is temp-path based. | For deployment, define a durable serving URI and backfill promotion process. |

Final P10 validation decision:
- The P0-P10 execution and validation path is complete enough to close the
  staged validation workflow.
- The Professor domain is not ready for broad public launch without follow-up
  cleanup/remediation changes for quality filtering, dirty canonical names,
  duplicate-risk groups, quality-gate issues, and seed coverage gaps.

## 2026-05-25 Tests And Lint

P10 did not introduce code changes after creating `prof-final-validation`.
Therefore no new P10 code-specific unit test or lint command was required.

Relevant code changes discovered and fixed during P9 were already covered by:
- `uv run --no-sync pytest tests/storage/test_milvus_collections.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/scripts/test_run_milvus_backfill.py tests/data_agents/service/test_retrieval.py tests/data_agents/service/test_retrieval_quality_filter.py tests/data_agents/service/test_retrieval_integration.py -q --no-cov -n0`
  -> `62 passed`.
- `uv run --no-sync ruff check scripts/run_milvus_backfill.py src/data_agents/service/retrieval.py tests/scripts/test_run_milvus_backfill.py`
  -> `All checks passed!`

## 2026-05-25 OpenSpec Validation Evidence

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

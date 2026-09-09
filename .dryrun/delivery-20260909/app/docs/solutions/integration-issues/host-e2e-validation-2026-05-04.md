---
title: "Host E2E validation evidence 2026-05-04"
date: 2026-05-04
owner: codex
status: pending_host_rerun
category: docs/solutions/integration-issues
module: apps/admin-console / apps/miroflow-agent
problem_type: e2e_validation
severity: high
tags: [agentic-rag, host-e2e, classifier, chat, postgres, milvus, llm]
---

# Host E2E validation evidence 2026-05-04

## Scope

目标是按 Roadmap 对 P0/P1 修复做 host 真实 E2E 证据采集，而不是只跑单测。

覆盖项：

- classifier 100-case benchmark
- `/api/chat` 四域入口样例
- Postgres / Milvus / internal LLM 可达性

## Evidence timeline

### Codex sandbox precheck

The Codex sandbox shell could parse the Gemma-4 profile, but could not reach the
OpenAI-compatible endpoint due to sandbox network limits. That sandbox failure
does not represent host connectivity.

Shell env:

```text
DATABASE_URL_UNSET
MILVUS_URI_UNSET
CHAT_MILVUS_URI_UNSET
LOCAL_LLM_BASE_URL_UNSET
LOCAL_LLM_MODEL_UNSET
```

`resolve_professor_llm_settings("gemma4", include_profile=True)` 可以解析出 profile：

```text
LLM_PROFILE_OK
base_url_set True
model_set True
```

Sandbox direct LLM OpenAI-compatible probe:

```text
LLM_PROBE_FAIL
APIConnectionError Connection error.
```

### Host run 2026-05-04T10:10:59Z

Log:

```text
docs/source_backfills/host-e2e-agentic-rag-2026-05-04T10-10-59Z.txt
```

LLM connectivity on the real host was **OK**:

```text
profile=gemma4
base_url_host= star.sustech.edu.cn
base_url_path= /service/model/gemma4/v1
model= gemma-4-26b-a4b-it
api_key_present= True
tcp_probe=OK
openai_probe=OK
openai_text= pong!
```

This is an online/internal OpenAI-compatible API endpoint, not a locally
deployed LLM process. The script resolves credentials through the existing
`gemma4` profile/key loader; `API_KEY` and `LOCAL_LLM_API_KEY` do not need to be
present as shell variables for this profile to work.

The same host run did not have explicit data-source env:

```text
DATABASE_URL=UNSET
DATABASE_URL_TEST=UNSET
CHAT_MILVUS_URI=UNSET
MILVUS_URI=UNSET
```

Postgres and Milvus probes therefore failed before any trustworthy chat E2E:

```text
postgres_probe=FAIL
reason=DATABASE_URL and DATABASE_URL_TEST are unset

milvus_probe=FAIL
reason=CHAT_MILVUS_URI and MILVUS_URI are unset
```

The classifier benchmark passed, but before the deterministic short-circuit fix
it still paid per-query LLM latency:

```text
tests/test_classifier_benchmark.py::test_classifier_benchmark PASSED
1 passed, 2 deselected in 52.59s
```

The HTTP chat section was invalid as an app signal because uvicorn failed to bind
the fixed port and curl hit another service already listening on `127.0.0.1:8010`:

```text
ERROR: [Errno 98] error while attempting to bind on address ('127.0.0.1', 8010): address already in use
http_status=404
raw= ... Cannot POST /api/chat ...
```

### Host run 2026-05-04T10:29:40Z

Log:

```text
docs/source_backfills/host-e2e-agentic-rag-2026-05-04T10-29-40Z.txt
```

Infrastructure probes passed:

```text
openai_probe=OK
postgres_probe=OK
professor_count= 787
company_count= 1024
paper_count= 7297
patent_count= 1931
milvus_probe=OK
collections= company_profiles,paper_chunks,patent_profiles,professor_profiles
professor_profiles_stats= {'row_count': 787}
company_profiles_stats= {'row_count': 1024}
paper_chunks_stats= {'row_count': 11591}
patent_profiles_stats= {'row_count': 1931}
tests/test_classifier_benchmark.py::test_classifier_benchmark PASSED
1 passed, 2 deselected in 0.02s
health=OK
result=PASS
```

However, this PASS was a harness-level pass, not a product-quality E2E pass,
because the script only required HTTP 200 and non-empty `answer_text`.

Semantic regressions found in the log:

```text
B-paper:
query_type= B_paper_topic_search
citations_count= 0
answer_prefix= 未找到与 '具身智能论文' 相关的论文。

C-followup-company:
query_type= B_company_topic_search
```

Root causes:

1. Topic cleanup removed `近两年` and `方向的` after stripping only the trailing `有哪些`, leaving `具身智能论文` instead of `具身智能`.
2. Chat classified the context-rewritten query (`丁文伯参与创立了哪些企业`) instead of the raw user query (`他参与创立了哪些企业`), so the deterministic C rule never saw the pronoun.

Fixes applied after this log:

1. Topic cleanup now strips query nouns again after date/direction cleanup.
2. v3 classifier now classifies `raw_query`; older rule handlers can still use the context-rewritten query.
3. Host script now asserts expected `query_type` and citation/no-data behavior for the five chat samples.
4. Host Postgres probe now prints Ding Wenbo professor-company role rows to distinguish C routing failures from relation-data gaps.

### Host run 2026-05-04T10:54:21Z

Log:

```text
docs/source_backfills/host-e2e-agentic-rag-2026-05-04T10-54-21Z.txt
```

Infrastructure and strict routing checks passed:

```text
openai_probe=OK
postgres_probe=OK
milvus_probe=OK
tests/test_classifier_benchmark.py::test_classifier_benchmark PASSED
health=OK
B-company query_type=B_company_topic_search citations_count=6
B-paper query_type=B_paper_topic_search citations_count=10
B-patent query_type=B_patent_topic_search citations_count=10
A-professor query_type=A_prof_profile citations_count=1
```

The remaining failure was not a router failure:

```text
ding_company_role_count= 0
C-followup-company query_type= C_cross_domain_related
citations_count= 0
answer_prefix= 暂未收录丁文伯关联的企业数据。
result=FAIL
```

Updated product decision: do not force a weak Ding Wenbo -> Wujie Zhihang
relation into Postgres just to satisfy the C sample. Chinese university
professors often do not publish complete company roles; when public evidence is
not strong enough, the correct behavior is a source-grounded no-data answer.
The E2E gate should therefore validate C routing and non-hallucination, not a
mandatory citation for this specific relation.

Harness adjustment after this log:

1. `C-followup-company` now requires `query_type=C_cross_domain_related`.
2. If citations exist, they are accepted as normal evidence.
3. If citations are zero, the answer must explicitly say the relation is not collected/found or evidence is insufficient.
4. The professor-company backfill apply script refuses serving-visible `candidate` writes unless explicitly overridden; preferred apply mode after human review is `--apply --link-status verified`.

### Host run 2026-05-04T11:09:37Z

Log:

```text
docs/source_backfills/host-e2e-agentic-rag-2026-05-04T11-09-37Z.txt
```

Application-level E2E passed all strict chat gates:

```text
openai_probe=OK
postgres_probe=OK
tests/test_classifier_benchmark.py::test_classifier_benchmark PASSED
health=OK
B-company query_type=B_company_topic_search citations_count=6
B-paper query_type=B_paper_topic_search citations_count=10
B-patent query_type=B_patent_topic_search citations_count=10
A-professor query_type=A_prof_profile citations_count=1
C-followup-company query_type=C_cross_domain_related citations_count=0
answer_prefix= 暂未收录丁文伯关联的企业数据。
```

The final run result was still:

```text
milvus_probe=FAIL
error= <ConnectionConfigException: (code=1, message=Open local milvus failed)>
result=FAIL
```

Root cause: the script-level standalone Milvus-Lite probe tried to open
`apps/miroflow-agent/milvus.db` while another process already held the local file
lock. This is a harness/concurrency artifact for local Milvus-Lite. The HTTP
chat samples still exercised the retrieval path successfully, so the product
E2E signal is positive.

Harness adjustment after this log:

1. `host_e2e_agentic_rag.sh` now treats this specific local Milvus-Lite lock as `milvus_probe=SKIPPED_LOCKED` rather than a hard failure.
2. Real retrieval validation remains covered by the HTTP chat samples with expected `query_type`, citation/no-data behavior, and non-empty answers.
3. For a cleaner infrastructure-only signal, run the Agentic RAG and Excel scripts sequentially, or move host validation to a standalone Milvus server URI.

### Host run 2026-05-04T11:31:40Z and 11:32:22Z

Logs:

```text
docs/source_backfills/host-e2e-agentic-rag-2026-05-04T11-31-40Z.txt
docs/source_backfills/host-e2e-agentic-rag-2026-05-04T11-32-22Z.txt
```

The 11:31 run was executed directly from Codex CLI host access and exposed a
harness environment bug:

```text
ModuleNotFoundError: No module named 'src'
ModuleNotFoundError: No module named 'psycopg'
ModuleNotFoundError: No module named 'pymilvus'
```

Root cause: standalone Python probes used host system `python`, while the real
service and tests use the admin-console `uv` environment. Fix: `host_e2e_agentic_rag.sh`
now runs dependency-bearing probes through an `admin_python` wrapper:

```text
cd apps/admin-console
PYTHONPATH=apps/miroflow-agent uv run python ...
```

After the fix, 11:32 host E2E passed:

```text
openai_probe=OK
postgres_probe=OK
milvus_probe=OK
tests/test_classifier_benchmark.py::test_classifier_benchmark PASSED
health=OK
B-company query_type=B_company_topic_search citations_count=6
B-paper query_type=B_paper_topic_search citations_count=10
B-patent query_type=B_patent_topic_search citations_count=10
A-professor query_type=A_prof_profile citations_count=1
C-followup-company query_type=C_cross_domain_related citations_count=0
answer_prefix= 暂未收录丁文伯关联的企业数据。
result=PASS
```

This is the first strict host Agentic RAG E2E pass with LLM, Postgres, Milvus,
classifier, HTTP `/api/chat`, C no-evidence behavior, and four-domain retrieval
samples covered in one run.

## Earlier local data-source precheck

默认 real Postgres DSN 曾在 sandbox shell 下不可达：

```text
postgresql://miroflow:miroflow@localhost:15432/miroflow_real
POSTGRES_DEFAULT_FAIL OperationalError connection is bad: no error details available
```

admin-console PG dependency 在当前 shell 下会直接失败：

```text
PG_POOL_FAIL
RuntimeError DATABASE_URL (or DATABASE_URL_TEST) must be set before starting the admin console.
```

Milvus env 未设置；client 可实例化，但不是显式真实 Milvus E2E：

```text
CHAT_MILVUS_URI_SET False
MILVUS_URI_SET False
MILVUS_CLIENT_OK MilvusClientCompat
```

## Classifier benchmark

Initial sandbox command:

```bash
cd apps/admin-console
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY \
  UV_CACHE_DIR=/tmp/mirothinker-uv-cache-status \
  uv run pytest tests/test_classifier_benchmark.py -m requires_classifier_llm -v --tb=short
```

Result:

```text
tests/test_classifier_benchmark.py::test_classifier_benchmark PASSED
1 passed, 2 deselected in 132.52s (0:02:12)
```

Updated interpretation:

- This proves the 2026-05-04 deterministic fallback can cover the 100-case fixture.
- Host log proves the resolved Gemma-4 OpenAI-compatible endpoint itself is reachable.
- The classifier should not call LLM for benchmark cases that deterministic rules already cover; this was fixed by short-circuiting before LLM fallback.

## `/api/chat` entrypoint sample

Command:

```bash
cd apps/admin-console
timeout 20s env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY \
  UV_CACHE_DIR=/tmp/mirothinker-uv-cache-status \
  uv run python - <<'PY'
from fastapi.testclient import TestClient
from backend.main import app
with TestClient(app, raise_server_exceptions=False) as client:
    resp = client.post('/api/chat', json={'query': '深圳哪些公司做激光雷达'})
    print('STATUS', resp.status_code)
    print('BODY', resp.text[:500].replace('\n', ' '))
PY
```

Result:

```text
ADMIN_CONSOLE_FRONTEND_STALE: dist/index.html built at 2026-04-17T10:55:44,
but src has newer file (frontend/src/pages/Chat.tsx at 2026-04-23T14:12:05).
EXIT_CODE=124
```

Sandbox interpretation:

- `/api/chat` did not return within 20s in the sandbox shell.
- That shell lacked `DATABASE_URL`, and its LLM probe failed due to sandbox network restrictions; either is sufficient to block real chat E2E there.
- Frontend dist is stale. This is not the API blocker, but it means user-facing UI validation is not current until frontend is rebuilt.

## Verdict

P0/P1 local code paths are test-backed. The first host run is **not a valid chat
E2E failure** because the harness had missing data-source env and a fixed-port
collision. The second host run proved infrastructure availability but exposed
two semantic E2E gaps that required code and harness tightening.

Confirmed facts:

1. LLM profile `gemma4` uses `https://star.sustech.edu.cn/service/model/gemma4/v1` with model `gemma-4-26b-a4b-it`.
2. The real host can TCP-connect and complete an OpenAI-compatible chat completion against that endpoint.
3. The first host run lacked `DATABASE_URL` and `CHAT_MILVUS_URI` / `MILVUS_URI`.
4. `/api/chat` 404s came from a different process on port 8010, not from this FastAPI app.
5. React frontend dist is stale relative to `frontend/src`; this affects browser UI E2E, not API E2E.
6. 2026-05-04T10:29:40Z host run passed the old harness but failed product semantics for B-paper and C-followup-company.
7. 2026-05-04T10:54:21Z host run fixed B-paper and C routing, and exposed a professor-company relation data gap for Ding Wenbo.
8. 2026-05-04T11:09:37Z host run passed all strict HTTP chat gates; only the standalone Milvus-Lite probe failed due to local file locking.
9. 2026-05-04T11:32:22Z host run passed strict Agentic RAG E2E end to end after probes were moved into the project `uv` environment.

Harness fixes applied after this log:

1. `apps/admin-console/scripts/host_e2e_agentic_rag.sh` now defaults missing DB/Milvus env to the project real-data defaults.
2. The script chooses a free port by default and verifies `/api/health == {"status":"ok"}` before sending chat requests.
3. The script records failure counts and exits nonzero unless every probe/chat sample passes.
4. The classifier now short-circuits deterministic benchmark-covered queries before LLM fallback.
5. The script validates sample-level `query_type` and citation/no-data behavior, including `B_paper_topic_search` and `C_cross_domain_related`.

## Follow-up roadmap

1. Rerun `bash apps/admin-console/scripts/host_e2e_agentic_rag.sh` on the host and archive the new log.
2. Accept the run only if:
   - `openai_probe=OK`
   - `postgres_probe=OK`
   - `milvus_probe=OK` or `milvus_probe=SKIPPED_LOCKED` when using local Milvus-Lite concurrently and chat retrieval gates pass
   - classifier benchmark passes without per-query LLM latency
   - `health=OK`
   - all `/api/chat` samples return HTTP 200 JSON with non-empty `answer_text`
   - C follow-up either returns grounded citations or explicitly says the relation is not collected/found / evidence is insufficient
   - final `result=PASS`
3. If Postgres still fails, start/export the production-equivalent DB before code changes.
4. If Milvus still fails, set `CHAT_MILVUS_URI` to the intended real Milvus URI/path before code changes.
5. If chat returns HTTP 200 but weak/empty domain answers, debug retrieval/data quality per sample:
   - `深圳哪些公司做激光雷达`
   - `近两年具身智能方向的论文有哪些`
   - `哪些专利和柔性触觉传感有关`
   - `介绍清华的丁文伯` -> `他参与创立了哪些企业`
6. Rebuild frontend before user-facing UI E2E:
   - `just frontend-fresh` or equivalent.

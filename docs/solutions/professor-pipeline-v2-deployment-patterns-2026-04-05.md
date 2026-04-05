---
title: Professor pipeline v2 deployment patterns and infrastructure lessons
date: 2026-04-05
category: docs/solutions
module: apps/miroflow-agent/src/data_agents/professor
problem_type: implementation_pattern
component: professor_pipeline_v2, vectorizer, search_service
severity: high
applies_when:
  - Building data agent pipelines that publish to the shared DataSearchService
  - Using Milvus Lite for local vector storage
  - Connecting to internal embedding endpoints with API key auth
  - Converting domain-specific enriched profiles to ReleasedObject format
  - Running data collection behind corporate proxies
tags: [professor, pipeline-v2, milvus-lite, embedding, search-service, proxy, domain-suffixes]
---

# Professor pipeline v2 deployment patterns and infrastructure lessons

## Context

On April 5, 2026, the professor enrichment pipeline v2 was deployed end-to-end, processing 3274 professors from 7 Shenzhen universities into both a professor-specific Milvus collection (4096-dim Qwen3-Embedding-8B) and the shared DataSearchService stores (SQLite + hash-based 64-dim Milvus). Several infrastructure and integration issues were discovered and resolved during deployment.

## Guidance

### 1. Milvus Lite only supports AUTOINDEX, not HNSW

When using Milvus Lite (file-based, no server), the only supported index types are `FLAT`, `IVF_FLAT`, and `AUTOINDEX`. Attempting to create an `HNSW` index produces:

```
MilvusException: invalid index type: HNSW, local mode only support FLAT IVF_FLAT AUTOINDEX
```

**Fix:** Always use `AUTOINDEX` for Milvus Lite. It automatically selects the best available index for the data size.

```python
index_params.add_index(
    field_name="profile_vector",
    index_type="AUTOINDEX",  # NOT "HNSW"
    metric_type="COSINE",
)
```

### 2. Embedding model IDs must match exactly

The Qwen3-Embedding-8B endpoint at `172.18.41.222:18005` requires the exact HuggingFace model ID format. Using a short name returns 404:

- `qwen3-embedding-8b` -> 404 Not Found
- `Qwen/Qwen3-Embedding-8B` -> 200 OK

**Fix:** Always query the `/v1/models` endpoint first to discover the exact model ID, then use that in embedding requests.

### 3. Internal embedding endpoints require API key auth

The sglang-hosted embedding endpoint requires `Authorization: Bearer <key>` headers. Without auth, requests return 401 Unauthorized.

**Fix:** Pass the API key through the config chain: `PipelineV2Config.embedding_api_key` -> `EmbeddingClient(api_key=...)` -> `headers["Authorization"]`.

### 4. Domain suffix list must cover all university variants

When converting enriched professors to `ProfessorRecord`, the contract requires at least one `official_site` evidence item. Evidence URLs are classified as official/public based on domain suffix matching. Missing domains cause silent validation failures.

Universities with multiple domain variants:
- **HIT Shenzhen**: `hitsz.edu.cn` (Shenzhen campus) AND `hit.edu.cn` (main campus) — many professor profile URLs use the main campus domain
- **PKU Shenzhen**: `pkusz.edu.cn` (Shenzhen) AND `pku.edu.cn` (main campus) — some ECE professors have `ece.pku.edu.cn` URLs
- **SUAT Shenzhen**: `suat-sz.edu.cn` — not intuitive, easy to miss

**Fix:** When adding new universities, check all evidence URLs to discover domain variants. The set should include both campus-specific and main-campus domains.

### 5. Dual-store architecture: professor-specific vs shared

The system has two vector storage paths:
1. **Professor-specific**: `ProfessorVectorizer` with real Qwen3-Embedding-8B (4096-dim), dual vectors (profile + direction), stored in a dedicated Milvus collection
2. **Shared**: `MilvusVectorStore` with hash-based embeddings (64-dim), single vector, used by `DataSearchService`

Both are needed: the professor-specific collection provides high-quality semantic search, while the shared stores integrate with the cross-domain `DataSearchService` that the Agentic RAG agent uses.

**Publishing flow:**
```
EnrichedProfessorProfile
  -> ProfessorVectorizer (professor-specific Milvus, 4096-dim)
  -> ProfessorRecord -> ReleasedObject -> SqliteReleasedObjectStore + MilvusVectorStore (shared, 64-dim)
```

### 6. Corporate proxy causes SSL failures for external HTTPS sites

The environment has HTTP_PROXY/HTTPS_PROXY set to `http://100.64.0.15:7893`, which causes SSL handshake failures (`[SSL: UNEXPECTED_EOF_WHILE_READING]`) for many university websites.

**Mitigation:** Use the fetch cache at `logs/debug/professor_fetch_cache/` which stores HTML from previous successful crawls. The cache uses SHA256(url) filenames and contains 3754+ cached pages. The pipeline's `fetch_html_with_fallback` checks cache before making HTTP requests.

### 7. uv package manager fails with SUSTech PyPI mirror SSL issues

`uv run` fails when the SUSTech PyPI mirror (`mirrors.sustech.edu.cn/pypi`) has SSL certificate problems. This blocks all `uv sync` and `uv run` operations.

**Workaround:** Use `.venv/bin/python` directly instead of `uv run` for script execution:

```bash
# Instead of:
uv run python scripts/run_professor_enrichment_v2_e2e.py

# Use:
.venv/bin/python scripts/run_professor_enrichment_v2_e2e.py
```

### 8. setuptools 82+ drops pkg_resources, breaking milvus-lite

`milvus-lite` imports `pkg_resources` at module level. setuptools 82.0.1 removed this module.

**Fix:** Pin setuptools to a version that still includes pkg_resources:

```bash
uv pip install "setuptools==74.1.3"
```

## Files involved

- `src/data_agents/professor/vectorizer.py` — Embedding client + Milvus vectorization
- `src/data_agents/professor/pipeline_v2.py` — V2 pipeline orchestrator
- `src/data_agents/storage/milvus_store.py` — Shared hash-based vector store
- `src/data_agents/storage/sqlite_store.py` — Shared SQLite released object store
- `src/data_agents/service/search_service.py` — DataSearchService for Agentic RAG
- `scripts/run_professor_publish_to_search.py` — Bridge script: enriched -> shared stores
- `scripts/run_professor_enrichment_v2_e2e.py` — Full pipeline E2E runner

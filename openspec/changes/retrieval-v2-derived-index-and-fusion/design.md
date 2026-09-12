# Design: retrieval-v2-derived-index-and-fusion

> Standard change. Sources: `retrieval-review.md` §4/§6/§10/§11 (measured
> reviews), zvec-grep source recon 2026-09-12 (subagent report, facts cited
> inline), feasibility probes run against the sealed run14 pack 2026-09-12.

## Facts

**Our side (measured).**

- 47,071 lookup documents; lexical lane = substring scan, live wall
  0.9-3.6s; exact 0.12-0.55s; vector 3.2-5.4s; web 6.9-11.2s (turn-debug
  probe, 2026-09-12). TTFT r4 all ≤24.5s after LAT-1/LAT-3.
- Fusion = 1:1 local/web positional interleave
  (`knowledge_serving_isolated.py:2583-2588`); no RRF anywhere.
- `StructuredConstraints` = 3 fields; `geography` zero consumers.
- P2 baseline (generalization r5): lidar off-category 25/64 and 18/64,
  storage 9/56; drone 0/37-63; medical 0/43.
- Pack documents are cached in-process (`_BOUND_DOCUMENT_CACHE`) and the
  lookup view carries a prebuilt name index (AQ-S7) — the per-request cost
  is the per-document matching loop, not SQLite reads.

**zvec-grep (source-recon facts, for the reject decision).**

- BM25/FTS lives inside `@zvec/zvec` — the Node binding to
  `alibaba/zvec` (C++ in-process engine; FTS added v0.5.0; jieba tokenizer
  chosen for CJK). k1/b are not exposed by the FTS path.
- RRF: **k=60, no per-channel weights**, two levels (single-plan recall
  traces; cross-query-group fusion); tie-break by string id.
- Retrieval unit = file fragments (code symbols / Markdown sections /
  3600-char text chunks) with file+range; no Python API; daemon exposes
  streamable-HTTP MCP only (no REST search).
- Incremental = changed-path diff (size+mtime fast path → sha256), only
  changed files re-extracted/re-embedded; freshness = per-hit
  fresh/possibly_stale from indexedTime vs mtime.
- The underlying store DOES ship PyPI wheels (`zvec` 0.7.0, cp312
  manylinux x86_64 verified).

## Options considered

| Option | Verdict |
|---|---|
| A. Adopt zvec-grep as a sidecar (Node + MCP) | **Rejected.** File/chunk unit vs our typed entities + lineage; data must be exported to files and re-synced per pack rebuild; Node runtime; field-level filters and record lineage would be rebuilt outside our guarantees. |
| B. Re-implement the three mechanisms in our stack (SQLite FTS5 + jieba; facets; RRF; page cache) | **Chosen.** Measured feasibility above; stdlib SQLite (no new native dep), one small pure-Python dependency (jieba), persisted derived artifact we can hash/verify, candidate lineage preserved. |
| C. Import `zvec` (Python wheels) for lexical+vector | **Deferred hedge.** Would add a second native engine beside Milvus Lite with opaque BM25 tuning and a data migration; revisit only if FTS5 saturates or the vector side outgrows Milvus Lite. |

## Step 1 — Derived lexical index

**Artifact layout (outside the sealed pack).**

```
/var/tmp/mirothinker-data-v2/derived/lexical/<release_id>/lexical.sqlite3
/var/tmp/mirothinker-data-v2/derived/lexical/<release_id>/manifest.json
```

manifest = `{schema_version, release_id, pack_lookup_sha256, build_tool_version,
jieba_dict_sha256, doc_count, token_count, built_at}`; the loader refuses an
artifact whose pack sha / release id / schema version differ from the bundle
(same fail-closed posture as the existing pack authority checks).

**FTS5 schema.**

```sql
CREATE VIRTUAL TABLE doc_fts USING fts5(
  name,            -- display name + name forms (weight 8)
  tags,            -- industry/tech tags, product names, aliases (weight 4)
  body,            -- profile summary / abstract / claims (weight 1)
  tokenize='unicode61'
);
CREATE TABLE doc_map(doc_id INTEGER PRIMARY KEY, canonical_object_id TEXT,
                     domain TEXT, lookup_document_id TEXT);
CREATE TABLE doc_facet(doc_id INTEGER, facet TEXT, value TEXT);  -- step 2
```

Segmentation contract (both build and query side, enforced by one function):
`jieba.cut_for_search` with the entity name-form user dictionary loaded
(AQ-S7 `_entity_name_forms` + `_compact_company_alias`, ~17.5k entries),
tokens stripped; queries are OR-joined so a multi-term query is a ranked
sample, never an AND filter. Ranking = `ORDER BY bm25(doc_fts, 8.0, 4.0, 1.0)`.

**Query construction (measured correction, 2026-09-12).** FTS5's own
tokenizer treats a raw quoted CJK run as ONE token, so the MATCH expression
must be built from the segmented tokens: phrase = quoted tokens joined by a
space (`"储能" "电池"`), OR = quoted tokens joined by `OR`. The naive raw
phrase `"储能电池"` returned **0** hits against the built index while the
segmented phrase returns 114; the same asymmetry makes the adjacency pass
exclude 激光设备-style documents for 激光雷达 (66 phrase hits vs 128 OR).
The lane runs **phrase-first, then OR fill** when the adjacency pass is
thinner than the window floor — the precision pass plus the recall pass.

**Serving integration.** `LexicalIndex.search(query, domains, top_k, mode)`
returns `(lookup_document_id, bm25_score)`; the lane reconstructs candidates
through the existing `_candidate_from_document` path so evidence items, claim
bindings, lineage hashes and citations stay byte-identical in shape, and the
BM25 order is preserved by keeping `raw_score` flat (downstream stable sorts
carry the lane rank). Both lexical adapters — the isolated one and the
serving pack one that the live composite actually runs — call one shared
helper (`iso._indexed_lexical_lane_result`), so the two paths cannot drift;
the substring lane stays below as the fallback (switch off, artifact absent
or unbound, or an empty index result). Switch:
`CANONICAL_V2_LEXICAL_INDEX=1` (+ `CANONICAL_V2_LEXICAL_INDEX_ROOT`).

## Step 2 — Facets (structured filter channel)

`doc_facet` rows: `domain`, `industry`, `tech_tag`, `geography`
(registered-address city, reusing AQ-S8's witness), `founded_year`,
`quality_tier`. `StructuredConstraints` gains consumers that translate plan
slots into facet predicates; the geography filter in particular moves from a
name heuristic to the typed field. Facet counts are returned for the trace.

## Step 3 — RRF fusion

Replace the interleave with RRF over each lane's ordered candidate list:
`score(d) = Σ_lanes 1/(k + rank_lane(d))`, k=60, unweighted first (matching
zvec-grep's own default), deterministic tie-break `(score desc,
canonical_object_id asc)`. The local/web quota semantics survive as optional
per-lane weights (`w_lane`, default 1.0) and as a post-fusion disclosure
rule, never as positional interleave. The fusion receipt records the
per-lane ranks used.

## Step 4 — Page cache + freshness

- `web_page_cache(url TEXT PRIMARY KEY, day TEXT, text TEXT, fetched_at)`
  in the existing web-lane SQLite; TTL = same day (mirrors the view cache);
  cache hits recorded in the web lane trace.
- Freshness: pack `as_of` + web snapshot timestamps render as a one-line
  "数据截至 …" footer; turn trace gains a `freshness` field.

## Step 5 — Incremental refresh (staged, after acceptance)

Diff `(canonical_object_id, content_sha256)` against the artifact manifest;
FTS delete/insert only for changed docs; full rebuild stays the boring path
and the only one wired into the release cycle initially.

## Verification surface

- Deterministic modules (tokenization, index search, facets, RRF): unit +
  contract tests (RED first).
- Retrieval behavior: generalization probes (P2 off-category, P1/P3),
  workbook testset (g2/g5), replay gate (zero new signatures), TTFT probe,
  and the offline latency harness for lane-level numbers.
- Baselines frozen in `.agents/runs/retrieval-v2-derived-index-and-fusion/
  verification-contract.md` (same-day dual-run differentials required).

## Risks and rollback

| Risk | Mitigation |
|---|---|
| Tokenization drift between build and query | One shared `segment()` function; the build records the dict hash; tests pin the matrix (2/3-char, mixed, alias, name form) |
| Index staleness vs pack | Manifest binds pack sha + release id; loader refuses mismatch; fallback lane |
| RRF changes long-standing answer shapes | Switch-gated; same-day differential (generalization + testset + replay) before default-on |
| Derived artifact leaks into the sealed pack | Artifact path outside the pack root; sealed-pack integrity untouched; add a guard test |
| jieba memory/latency in the serving process | Measured: dict load ~1.2s, query ~1ms; loaded lazily with the index; switch off = old lane |

## Field contract (Step 0.3)

Sources are the pack lookup documents' `lookup_content` JSON
(company/professor/paper/patent). Index columns and facets:

| column / facet | fields |
|---|---|
| `name` (weight 8) | `name`, `normalized_name`, `title`, `canonical_name_zh`, derived name forms (AQ-S7 `_entity_name_forms`) |
| `tags` (weight 4) | `aliases[]`, `industry.name`, `industry_tags[].name`, `tech_tags[].name`, `products[].name`, paper `venue.name`/`authors[]`, patent `applicants[]`/`inventors[]` |
| `body` (weight 1) | `profile_summary`, `product_description`, `technology_route_summary` (+ `_supplementary.technology_route_summary[]`), `summary_text`, `team_description` |
| facet `domain` | document domain |
| facet `industry` | `industry.name` |
| facet `tech_tag` | `tech_tags[].name` |
| facet `geography` | city derived from `registered_address` / `geography.name` (AQ-S8 witness) |
| facet `founded_year` | `founded_at` year (4-digit) |
| facet `quality_tier` | `quality_status` |
| **never indexed** (hashes/decisions/lineage) | `content_sha256`, `catalog_content_sha256`, `identity_decision_id`, `inclusion_decision_id`, `field_lineage`, `evidence[].assertion_id`, `id`, `canonical_identity_id` |

The never-indexed list is enforced by construction: the column builder reads
only the whitelisted keys above (a test pins that no hash-shaped token
appears in the index).

## Step 1 exit review (2026-09-13) — the lane is off by default; Step 1b is the design

**Measured outcome of the Step 1 design above.** The lane is fast (select +
build 0.056-0.710 s on four real turns vs 1.13-3.71 s for the substring lane,
zero fallbacks) and TTFT is unchanged (the lane is not on the critical path:
web 6.9-11.2 s, vector 3.2-5.4 s). But substituting the lane's output for the
substring lane's output regressed quality, and the strongest oracle caught it:

- replay gate 3 failures (`G3_person_pronoun` T2 person scope;
  `G7_enumeration` 2/3 repeats missing 优必选);
- testset g2 2/3 (`entity` layer missing 开普勒/九号) and g5 1/2;
- attribution: the harness id-level window diff and the live answer's
  off-category names match one-for-one.

Root cause: the F1 category recall is a tuned semantic — bigram term matching,
field tiers (industry x8 / tags x4 / product x2 / summary x1), a min-score
gate, displayed-entity constraints. Tokenisation + BM25 + a 128-document
window is a *different* semantic: narrower for exact tokens (misses 优必选 via
智能), wider for generic terms (floods on 论文), and its truncation drops
tier-tagged companies. **The index must generate candidates for a relevance
reranker; it must not replace recall semantics.**

Deployment state: `CANONICAL_V2_LEXICAL_INDEX=0` (systemd drop-in
`lexical-index.conf`), baseline behaviour restored; artifact retained.

## Step 1b — index as candidate generator + relevance rerank

Target shape (unchanged):

```text
query residue (content terms, stop-phrase stripped)
  → index recall: phrase pass ∪ OR pass over the residue terms, pool = 2-4x
    the request window (cap ~512)
  → relevance rerank: cross-encoder or embedding score over the pool
      cross-encoder: Qwen3-Reranker-8B  (served, :18006)
      embedding:     Qwen3-Embedding-8B (served, :18005; the vector lane's model)
  → top-window by rerank score (ties broken by canonical id, deterministic)
  → fall-through: if the window is not a superset of the substring lane's
    recall for category queries, return None and keep the substring lane
```

### Model endpoints (owner-provided 2026-09-13, both measured live)

| Endpoint | Model | Protocol | Measured |
|---|---|---|---|
| `http://100.64.0.27:18006` | `qwen3-reranker-8b` (cross-encoder) | `POST /v1/rerank` | 3 docs 52 ms, 64 docs 236 ms, 128 docs 208 ms |
| `http://100.64.0.27:18005` | `Qwen/Qwen3-Embedding-8B` (4096-dim) | `POST /v1/embeddings` | 3 docs 56 ms, 64 docs 433 ms |

Both require `Authorization: Bearer <key>`; the credential is held only in the
0600 key file `/home/longxiang/.config/mirothinker/rerank-api-key` (shared by
both endpoints) and is never written into a unit file, doc, log or command
line. `max_model_len` is 32,768 on both.

### Step 1b(a) — cross-encoder relevance rerank (implemented 2026-09-13)

What landed: `canonical_v2/rerank_client.py` (stdlib `urllib.request`, no new
dependency) + serving wiring in `knowledge_serving_isolated.py`.

- Transport contract: `POST {base}/v1/rerank` with `query`, `documents`,
  `model`, `top_n`; the response is accepted only when every returned
  `results[].index` is in range, unique and carries a finite numeric
  `relevance_score`. Missing/duplicate/out-of-range index, non-numeric or
  NaN/inf score, HTTP failure and timeout all raise one error type
  (`RerankUnavailable`).
- Serving semantics: the model reorders **inside the existing buckets** — the
  mixed/local/Web/other balance and the pre-existing order semantics are
  preserved; candidates beyond `CANONICAL_V2_RERANK_MAX_DOCUMENTS` (128) keep
  their stable input order and are placed after the scored ones.
- Fallback: no configuration → the old path runs untouched; any
  `RerankUnavailable` → `_deterministic_serving_rerank()` for that turn.
- Config: `CANONICAL_V2_RERANK_BASE_URL`, `_MODEL`, `_API_KEY`,
  `_API_KEY_FILE`, `_TIMEOUT_SECONDS`, `_MAX_DOCUMENTS`, `_DEBUG`. The
  resolved config is cached per process (change the env → restart, or clear the
  cache in tests). Logging carries endpoint, model, document count and duration
  only — never the query text, candidate text or the key.
- Deployment: systemd drop-in
  `canonical-v2-backend.service.d/rerank.conf` (parked as `.pending` = OFF).
  The switch is `switch_rerank.sh on|off|stub` in the run directory.

Still open in Step 1b (not implemented, do not report as done): the wide pool
(1b.1), the embedding-scored path (1b.2), the substring superset guard (1b.3)
and the four-oracle exit gate (1b.4). Step 1b(a) is a *reranking* change only:
it cannot recover a candidate that recall never generated (evidence: 优必选
enters `recalled_handles` in 4/15 live turns and `committed_names` in 0/15).

**Why the rerank is the right tool here.** The failures are ordering and
window-composition failures, not candidate-generation failures: 开普勒/九号
were generated but out-ranked; 优必选 was not generated at all (fix that with a
wider pool plus a bigram-aware recall path, then let the reranker order the
pool). The current `_serving_reranker` is a deterministic bucket sorter
(`mixed/local/web` positional balance; every local candidate carries
`raw_score=1.0`), so it cannot separate relevant from irrelevant local hits —
replacing that with a model score is the owner-directed change.

**Exit criteria (all four, same day, before default-on).**

1. replay gate: zero new signatures — measured against the **same-day OFF
   runs**, not the historical `replay-post-lat3` (Web lane + LLM synthesis make
   a cross-day ALL-PASS baseline invalid; 2026-09-13 OFF runs failed
   G3+G4 and G3+G7 respectively).
2. testset: g2 3/3, g5 2/2 (completeness not worse).
3. generalization P2 not worse than the same-day OFF measurement
   (2026-09-13 OFF: lidar 38/40, storage 47, drone 46/63/35, medical 47).
4. harness: lane cost < 1 s on the four turns and the window a superset of the
   substring lane's recall (id-level, offline proof).

**Measured 2026-09-13 (live ON vs OFF, same pack, index lane off, ON proven by
the endpoint's request counter +128/turn).** Replay: clean — ON's single
failure is `G3_person_pronoun`, which fails identically in both OFF runs with
the same assertion and the same `query_type` (`canonical_v2:A:answer`), i.e. a
deterministic pre-existing defect, not a rerank signature. Testset: red,
1/5 vs OFF 4/5 (g2 collapses 3/3 → 0/3). Generalization: on-category coverage
down (drone 46→30, 64→59, 35→33; medical 47→39) with off-category up
(lidar 25→20, 23→19; storage 8→5) — a precision-for-recall trade the customer's
ask does not accept. TTFT: 11.6-23.8 s, all under the 30 s ceiling (model cost
208 ms at the 128-document cap). Verdict: fail-safe, but **not default-on**.

**Mechanism to instrument before the next attempt.** The cross-encoder reads
`display_name（domain）` plus evidence snippets only. An entity whose match is a
typed field with a thin profile (九号: `industry=机器人`, nearly every other
field empty) renders a near-empty document, so the model cannot see what the
deterministic tier score encodes (industry ×8 / tags ×4 / product ×2 / text ×1).
The symptom (九号 and the drone-class companies leaving the committed window)
fits, but the decisive evidence — pre-rerank position, post-rerank position and
document length per struct-field-matched entity per turn — is not yet captured.
Consequence for 1b.2/1b.3: the model score must **augment** the structural
prior (blend or quota inside the commit window) and the superset guard must
cover the commit axis, not only recall generation.

**Superset check (step 4) is the safety net for the class of failure we just
hit**: it is a deterministic offline comparison on the frozen turn set
(`step1_lane_query_ab.py` extended to diff lane windows by canonical id), so a
future regression in this class cannot reach the answer path unnoticed.

**Facets (Step 2) ordering note.** Facets narrow by typed fields (geography,
industry, tag); the evidence above says the lexical lane must not be the
mechanism that narrows a category query. Keep Step 2 independent: facet
predicates filter the fused pool, and their acceptance remains the live
geography-narrowing turns.

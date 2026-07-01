# Retrieval reach gaps — FM4 (cross-domain paper→professor) & FM5 (strict name matching): first-principles solution analysis

> Type: reusable technical lesson / solution exploration (NOT a behavior contract).
> Date: 2026-07-01. Parent: `docs/superpowers/specs/2026-07-01-retrieval-gap-closure-design.md`.
> Code anchors verified against current HEAD. Numbers from Phase-1 oracles.

## 1. Problem (measured)

Two recall-logic gaps where the answer entity IS in the DB but the recall path cannot reach it:

- **FM5** — "深圳法本信息科技有限公司的产品特点以及团队介绍" → `query_type=unknown`, 0/1 (法本信息技术
  missed). Company `法本信息技术` (COMP-d5c254c49820) is in the DB, `ready`. Oracle case 51.
- **FM4** — "有哪些做具身智能和灵巧手的教授" → 0/4 (柯文德/任尔夫/王强/刘桂良 missed). 12 professors with
  embodied/dexterous papers exist (3367 active professors, 2843 with paper links). Oracle case 50.

End-to-end recall with both cases: 11/24 (46%).

## 2. First-principles root cause: recall REACH is too narrow

Both gaps share one root: **the recall path's reach cannot surface an entity that is in the DB
and relevant**, because reach is narrowed two ways —

1. **Name matching is strict and un-normalized** (FM5): the query's surface-form name is matched
   as-is (exact / full-string substring) against `canonical_name` + `aliases` only. Entity names
   have many surface forms (legal suffixes 有限公司/科技/集团; region prefixes; registered vs
   canonical vs aliases); strict matching misses any variant.
2. **Recall is per-domain-isolated with no cross-domain traversal** (FM4): a topic query routes
   to ONE domain; `retrieve(professor)` is pure vector on `professor_profiles`; the cross-domain
   graph (paper→professor via `professor_paper_link`) is never traversed on the recall path,
   even though the SQL is already written.

First principle: **recall should reach any in-DB relevant entity via (a) normalized name matching
and (b) cross-domain graph traversal.** Both are half-built today; each needs one wire-up.

## 3. FM5 — code-grounded analysis

Three layers compound (all verified):

### 3a. Rule classifier has no pattern for "X公司的产品/团队" → falls to LLM → unknown
`_classify_query_by_rules` (`apps/admin-console/backend/api/chat.py:412-511`). The A-company rule
(line 499-507) matches only `有哪些专利|有什么专利|有哪些机器人产品|有哪些科研成果`; the A-name rule
(line 508-511) matches `^(介绍)?\s*[一-鿿A-Za-z0-9]{2,12}\s*(是谁|的相关信息)$`. A query
phrased "X公司的产品特点以及团队介绍" matches NEITHER → falls through to `_classify_query_with_llm`
(line 582) → LLM times out or returns None → `query_type=unknown`.

### 3b. `_extract_a_name(company)` does not strip "的产品特点/团队介绍"
`apps/admin-console/backend/api/chat.py:402-409`. The suffix-strip regex (line 405) is a fixed
allowlist: `有哪些专利|有什么专利|的技术实力怎么样|在深圳的科创业务介绍|公司画像|有哪些机器人产品|
的核心技术|有哪些科研成果|的专利布局|公司的技术方向|相关信息`. It does NOT include `的产品特点|团队介绍|
产品|团队|介绍|概况|简介`. So even if routed to A-company, the extracted name is the WHOLE query
string "深圳法本信息科技有限公司的产品特点以及团队介绍".

### 3c. `lookup_company` matches strict + ignores `registered_name`
`apps/admin-console/backend/services/chat_context.py:118-205`. Core matching (line 195-200):
```sql
WHERE c.identity_status != 'inactive'
  AND (c.canonical_name = %s                              -- exact full name
       OR jsonb_exists(COALESCE(c.aliases,'[]'::jsonb), %s)  -- exact alias array element
       OR c.canonical_name ILIKE %s)                       -- %full name% substring
```
with `like = f"%{name}%"` (line 119). For the un-stripped long name, all three miss: canonical
"法本信息技术" neither equals nor contains "深圳法本信息科技有限公司的产品特点以及团队介绍". And the
WHERE does not check `registered_name` at all (the column exists — `company.registered_name` —
and likely holds the full legal name "深圳法本信息科技有限公司").

**Confirmation by contrast:** case #21 "华力创科学...的相关信息" → `unknown` but 1/1 OK, because
"的相关信息" IS stripped by `_extract_a_name` (line 405) → name="华力创科学..." → `canonical_name
ILIKE '%华力创科学...%'` matches. So the `unknown` path DOES attempt `lookup_company`; exact/short
names hit, variants miss. FM5 is purely a name-matching gap, not a gate gap.

## 4. Move B — name normalization + fuzzy matching (fixes FM5)

### 4a. Broaden `_extract_a_name(company)` suffix stripping
`chat.py:405` — extend the regex to strip profile-attribute suffixes:
```python
company = re.sub(
    r"(有哪些专利|有什么专利|有哪些机器人产品|有哪些科研成果|"
    r"的技术实力怎么样|在深圳的科创业务介绍|公司画像|的核心技术|"
    r"的专利布局|公司的技术方向|相关信息|"
    r"的产品特点|团队介绍|产品特点|团队|产品|介绍|概况|简介|"
    r"基本信息|详细信息|产品信息|怎么样|如何)$",
    "",
    company,
)
```
This turns "深圳法本信息科技有限公司的产品特点以及团队介绍" → "深圳法本信息科技有限公司".

### 4b. Normalize + broaden `lookup_company`
`chat_context.py:118-205`. Two changes:
1. **Normalize the name to core** before matching: strip region prefix (深圳/北京/...) + legal
   suffix (有限公司/股份有限公司/科技/集团/控股/公司). "深圳法本信息科技有限公司" → core "法本信息".
2. **Add `registered_name` to the WHERE** and **use the normalized core for the ILIKE**:
```python
core = _normalize_company_name(name)   # strip region + legal suffix
like = f"%{core}%"
# WHERE ... AND (
#   c.canonical_name = %s OR c.registered_name = %s
#   OR jsonb_exists(COALESCE(c.aliases,'[]'::jsonb), %s)
#   OR c.canonical_name ILIKE %s OR c.registered_name ILIKE %s
# )
```
Now `canonical_name ILIKE '%法本信息%'` matches "法本信息技术" (canonical contains core); and
`registered_name` (full legal name) gives a second exact/substring channel.

### 4c. (Optional) trigram fallback for near-misses
If 4a+4b still miss, add a `pg_trgm` similarity OR-branch (`similarity(c.canonical_name, %s) >
0.5`) as a last resort, flagged low-confidence for the reranker. Requires the `pg_trgm` extension
and an index for performance.

### 4d. Risks
- **Over-matching**: "法本信息" may also match a different "法本电子" (COMP-e5756d07c503). Mitigate:
  prefer exact-core > substring > trigram; keep `LIMIT 10`; the reranker + `_company_clarification`
  (chat.py:2695) disambiguate when multiple match. Use the precision oracle to catch false matches.
- No schema change (reuses `canonical_name`/`registered_name`/`aliases`).

## 5. FM4 — code-grounded analysis

### 5a. `retrieve(professor)` is pure vector, no paper reverse-lookup
`apps/miroflow-agent/src/data_agents/service/retrieval.py:317-447`. Professor recall = vector ANN
on `professor_profiles` collection; `_object_sql("professor")` (line 564-571) fetches fields BY
`professor_id`. There is no step that takes recalled paper_ids and reverse-looks-up their author
professors. Professor `profile_summary` often does not emphasize the topic the way paper titles
do, so professor vector recall by topic is weak — the root of case 50's 0/4.

### 5b. The cross-domain paper→professor SQL is ALREADY BUILT — just not invoked on recall
`retrieval.py:597-646`. `_related_sql` (line 597-609) maps all 8 cross-domain pairs; in particular
`("paper","professor") → _paper_professors_sql` (line 600, 631-646):
```sql
SELECT prof.*, ppl.link_status, ppl.topic_consistency_score, ppl.match_reason
  FROM professor_paper_link ppl
  JOIN professor prof ON prof.professor_id = ppl.professor_id
 WHERE ppl.paper_id = %s
   AND ppl.link_status = 'verified'
   AND prof.identity_status = 'resolved'
 ORDER BY ppl.topic_consistency_score DESC NULLS LAST, prof.canonical_name ASC
 LIMIT %s
```
This is exactly the paper→professor rescue SQL. It is exposed via `get_related_objects` (the
public method that calls `_related_sql`). It is simply NOT called on the topic recall path.

### 5c. Topic queries route to single-domain company recall
`chat.py:4399` sets `query_type=f"B_{target_domain}_topic_search"`; the B path recalls companies.
`_lookup_cross_domain_evidence` (chat.py:1892, the professor+paper+company concurrent fan-out)
fires only for `D_cross_domain_topic`/`D_narrowing` (chat.py:4469/4498), NOT for `B_`. So a topic
query never reaches professor recall, and even if it recalled papers, the paper→professor link
would not be traversed.

## 6. Move C — cross-domain rescue + topic multi-domain fan-out (fixes FM4)

### 6a. Invoke `get_related_objects(paper→professor)` after topic paper recall
After the topic path recalls papers (paper_ids), call:
```python
professors = retrieval_service.get_related_objects(
    source_domain="paper", target_domain="professor",
    object_ids=recalled_paper_ids, limit=per_paper_cap,
)
```
and merge as professor evidence. The SQL (5b) is already written and already filters to
`link_status='verified'` + `identity_status='resolved'` + orders by `topic_consistency_score`.
This is the cheapest reach-extension: **no new SQL, one wire-up call.**

### 6b. Route topic queries to multi-domain fan-out (not just company)
Extend the B/topic path to recall company + paper + professor concurrently (reusing the
`ThreadPoolExecutor(max_workers=3)` pattern from `_lookup_cross_domain_evidence`, chat.py:1897),
then apply 6a's paper→professor rescue on the paper results. For a "具身智能" topic this surfaces
companies (vector) + papers (vector) + professors (rescued from papers via the link) — the 12
ground-truth professors become reachable.

### 6c. Risks
- **Rescued-professor volume**: all authors of all recalled papers can be many. Mitigate:
  `topic_consistency_score` ordering + `LIMIT` per paper + the reranker + `final_top_k` cap
  (already in place).
- **Latency**: one extra `get_related_objects` call (SQL, fast) per topic query; the latency
  oracle (p95 5.71s) has headroom under the 6s SLO.
- **Precision**: rescued professors may be loosely related (a co-author on one topic paper).
  Mitigate: the reranker + precision oracle; optionally weight by `topic_consistency_score` and
  number of topic papers per professor.

## 7. Sequencing

- **B first** (FM5): isolated to `_extract_a_name` + `lookup_company`; low blast radius (only
  entity-name company queries); no schema change; immediately fixes case 51 and the whole class
  of company-name-variant queries.
- **C second** (FM4): bigger (topic multi-domain fan-out + wire-up), but the rescue SQL already
  exists; highest recall-axes impact (unblocks topic→professor). Independent of B — can be a
  parallel follow-on change.

## 8. Out of scope (not first-principles-logic-solvable here)

- **FM3** (cross-filter professor routing): already DELIVERED — #19 routes to
  `B_semantic_topic_search` (not `unknown`); the 0/2 is data-blocked (许晋诚/陈功 not ingested).
  Logic layer has no gap; ingest fixes it.
- **FM1a** (6 absent entities): data coverage is a multiplicative factor on recall — not
  salvageable by retrieval logic. Separate ingest workstream (`fm1a-ingest-decision.md`).
- **web-augment** (Serper 403): credential defect, not logic. `add-web-augment` workstream.

## 9. Verification (when implemented)

- B: oracle case 51 flips 0/1 → 1/1 (法本信息技术 recalled); add a few more variant-name cases
  (公司/有限公司/科技 suffixes) to lock the normalization. Precision oracle watches for false matches.
- C: oracle case 50 flips 0/4 → ≥2/4 (柯文德/任尔夫 rescued via paper→professor); latency oracle
  confirms p95 still ≤ 6s; precision oracle labels rescued professors for relevance.

Both moves are eval-gated (CLAUDE.md §14.7) — the recall/precision/latency oracles are the
RED→GREEN oracle, not unit tests alone.

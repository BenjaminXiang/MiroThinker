# Retrieval-Generation Gaps — Systematic Root-Cause Map (2026-07-02)

> A first-principles root-cause analysis of every gap surfaced this round, organized by ROOT
> CAUSE (not symptom). Each root cause manifests as multiple gaps; fixing the symptom without
> the root means new query forms / new data keep hitting it.

## The root causes (7 themes)

### A. Classifier is a brittle pattern-list + non-deterministic LLM fallback
- **Manifests**: FM5 (法本 "X公司的产品特点/团队" — no rule), qid11 (bare English paper title —
  rules are CJK-centric: 论文 prefix / 的作者 suffix), qid14 (multi-clause — _extract_a_name
  assumes single-clause), FM3 (cross-filter attribute-AND-attribute).
- **Why**: the rule classifier enumerates CJK query patterns deterministically, but query
  surface-form is infinite. Rules miss variants (English, multi-clause, profile attributes);
  the LLM fallback is non-deterministic → intermittent mis-refuse (qid11 routed correctly 3/3
  after the rule, but was 0/2 under LLM). One root → 4 gaps.
- **Patches shipped**: FM5/qid11/qid14 rules added (eval-verified). FM3 delivered.
- **Root remains**: the pattern-list + LLM-fallback architecture. New query forms will keep
  falling through. **Principled fix**: normalization-first routing (normalize the query →
  entity type + intent, not pattern-match) OR a trained classifier; reduce LLM-fallback
  dependence.

### B. Recall is per-domain-isolated — doesn't traverse the entity graph
- **Manifests**: FM4 (professor not recalled for topic; paper→professor link EXISTS in
  `get_related_objects`/`_paper_professors_sql` but not invoked on the topic path; topic
  queries route to ONE domain).
- **Why**: `retrieve(professor)` is pure vector on `professor_profiles`; topic queries route to
  a single domain; the cross-domain graph (professor↔paper↔company↔patent, with links + SQL)
  exists in the data but the recall path doesn't traverse it. Single-hop single-domain lookup.
- **Patches shipped**: FM4 rescue (wire `get_related_objects(paper→professor)` on the topic
  path, ranked by topic-paper-count).
- **Root remains**: single-hop architecture. The rescue is ONE wire-up (paper→professor);
  paper→company, company→patent, etc. aren't wired on recall. **Principled fix**: graph-aware
  multi-hop recall (traverse the entity graph from recalled seeds, not just one domain's vector).

### C. Entity name matching is rigid (no normalization)
- **Manifests**: FM5 (`lookup_company` exact + full-string substring, ignored `registered_name`,
  no core normalization — "法本信息科技有限公司" didn't match "法本信息技术").
- **Why**: entity names have many surface forms (有限公司/科技/集团 suffixes, region prefixes,
  registered vs canonical vs aliases); matching was exact/substring only.
- **Patches shipped**: FM5 (`_normalize_company_name` strip region+suffix → core +
  `registered_name` in WHERE).
- **Root remains**: company fixed; professor/paper name matching may have the same root (not
  investigated — e.g., professor canonical_name vs aliases, paper title variants). **Principled
  fix**: normalized + fuzzy/trigram matching across all entity types (Move B).

### D. Data collected but not retrieval-ready (quality-gate + embedding gaps)
- **Manifests**: FM4 GT-4 papers (`needs_enrichment`, NULL `abstract_clean`, not embedded),
  GT-4 professors (`needs_review`/`needs_enrichment`, NULL metrics, not embedded), FM1b (普渡/
  深南电路 ready+embedded but broad profile), the ~70-75% of papers/professors not-ready.
- **Why**: the pipeline collects but doesn't fully promote-to-ready + embed. Sub-causes:
  - **D1 (paper)**: needs `abstract_clean` (NULL) → external-source backfill (Crossref/OpenAlex/
    arXiv). summary_zh then promotable.
  - **D2 (professor)**: needs `h_index`/`citation_count` (from OpenAlex) + `patent_summary`.
  - **D3 (embedding)**: not-ready → not embedded in Milvus → not vector-retrievable. (Ready-
    but-unembedded also possible.)
- **Patches shipped**: 4-5 papers through the full chain (abstract→summary→promote→embed);
  embed worked with backend up (milvus single-writer over-cautious).
- **Root remains**: ~70-75% of papers/professors still not-ready. **Principled fix**: complete
  the promote+embed pipeline at scale (chain works; needs D1/D2 sources + scale).

### E. External data-source throttling (environmental — blocks D1 + D2)
- **Manifests**: D1 (paper abstracts: OpenAlex 503 sustained, arXiv 429), D2 (professor
  metrics: h_index/citation_count from OpenAlex — same throttling). Crossref title-search
  worked (salvaged 4 papers) but 429'd mid-run.
- **Why**: this host is rate-limited by OpenAlex/arXiv/Semantic Scholar. NOT a code defect.
- **One environmental cause → multiple data-readiness manifestations** (paper abstracts +
  professor metrics both blocked by OpenAlex). **Principled fix**: rotate IP / polite-pool
  (mailto) / wait out the throttle / use cached or local sources. The chain is ready; the
  sources are throttled.

### F. Data collection gaps (not collected at all — separate from readiness D)
- **Manifests**: FM1a (6 absent entities: 云迹/九号/擎朗/嘉立创/许晋诚/陈功 — 0 rows).
- **Why**: the collection pipeline didn't ingest these.
- **Principled fix**: ingest workstream (separate from D's "already-collected but not ready").
- **Status**: out of scope (user scoped to "already-collected").

### G. Eval/harness + GT-labeling gaps (the measurement itself)
- **Manifests**: multi-turn coref (qid2/4/10/12 — eval sends standalone, no session_id →
  SessionContext never fires), L3 variance (qid11/17/20 swing run-to-run — LLM synthesis+judge),
  GT-draft mismatches (qid24 web-drafted required ≠ DB patents; qid27 GT-4 are data-blocked),
  env-truth (58%/Serper-dead false reading — FIXED: eval_env.sh loads backend keys).
- **Why**: eval harness is single-turn + LLM-judge; GT generation (web+LLM) doesn't match DB
  content.
- **Patches shipped**: env-truth fixed; L1 labeling pass (16 LLM-drafted); L3 judge calibrated.
- **Root remains**: multi-turn harness (model sessions); L3 stability (averaged runs / stronger
  judge); DB-grounded GT labeling. **Principled fix**: session-aware harness; L3 averaging;
  DB-grounded GT.

## The systemic insight: A+B+C+D are INTERLOCKED, E blocks the D fix

- **FM4 is a convergence of 3 roots**: A (topic→professor routing) + B (no cross-domain
  traversal) + D (professor not-ready/not-embedded). Fixing any one alone wouldn't unblock
  qid27 — the rescue (B-fix) needs the professors ready+embedded (D), and the routing (A) to
  reach professor recall.
- **E (throttling) blocks both D1 (paper abstracts) AND D2 (professor metrics)** — one
  environmental cause, multiple data-readiness manifestations. The data-enhancement chain
  (abstract→summary→promote→embed) is PROVEN end-to-end; the blocker is E (OpenAlex/arXiv
  throttling), not the chain logic.
- **A+B+C (logic roots) were PATCHED at the symptom level** (rules added, one rescue wired,
  company name-normalized). The roots (pattern-list classifier, single-hop recall, rigid
  matching) remain — new query forms / new entity types will keep hitting them. The principled
  fixes (learning router, graph-aware recall, normalized matching) are architectural.
- **D (data-readiness) is the biggest recall ceiling** (~70-75% not-ready). The chain is ready;
  scaling it + resolving E is the durable lever — bigger than any single logic patch.

## Status summary

| Root cause | Fixed (symptom) | Root remains? | Principled fix |
|---|---|---|---|
| A. Brittle classifier + LLM fallback | FM5/qid11/qid14 rules | yes | normalization-first / trained router |
| B. Per-domain-isolated recall | FM4 rescue (1 wire-up) | yes | graph-aware multi-hop recall |
| C. Rigid name matching | company (FM5) | yes (professor/paper?) | normalized+fuzzy all types |
| D. Data not retrieval-ready | 4-5 papers through chain | yes (~70-75%) | scale promote+embed pipeline |
| E. External throttling | — | yes (environmental) | rotate IP/polite-pool/cache |
| F. Collection gaps (FM1a) | — | yes (out of scope) | ingest workstream |
| G. Eval/harness/labeling | env-truth, L1 draft, L3 calib | yes | session harness, L3 avg, DB-GT |

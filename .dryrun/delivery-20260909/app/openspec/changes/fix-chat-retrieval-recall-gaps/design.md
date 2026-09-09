# Design: fix-chat-retrieval-recall-gaps

> Eval-first (CLAUDE.md §14.7). RED = baseline 58% (`eval_recall_chat.py`, measured this round,
> synthesis off, Serper 403 → web dead); GREEN = recall ≥ 58% (current-HEAD) with no passing
> case regressed. Diagnosis: `.agents/runs/retrieval-generation-alignment/diagnosis-baseline.md`.

## FM1b — recall candidate window (DELIVERED as hybrid RRF; candidate_limit reverted)

**Root cause (verified):** `candidate_limit=30` cuts deep candidates, but raising it (30→64) was
eval-NEUTRAL and reverted — the reranker still does not reliably promote broad-profile entities
(普渡 rerank-rank-10 over the full pool). The delivered lever is **hybrid RRF**
(`_hybrid_rrf_select`, `retrieval.py:242`): lexical coverage fuses vector-rerank + keyword ranks
so deep-but-lexically-relevant entities enter the window via a second signal.

**Web-search augmentation** was a second recall lever (commit `1fb6449`), but it is OUT of this
change: Serper now returns `403 Unauthorized`, so web contributes 0 to the measured 58%. Web is
split to `add-web-augment` (its own contract + the Serper fix). The deeper profile-quality
layer (broad summaries) is also out of scope (mitigated via RRF, not redone).

## FM3 — cross-filter professor routing

**Root cause:** `_classify_query_by_rules` returns `None` for attribute-AND-attribute queries
("毕业于X，且...专注Y的企业家"), and the LLM classifier either times out or returns None
→ endpoint falls to `unknown` refuse. No recall attempted.

**Fix (DELIVERED, data-blocked):** a rule/classifier target recognizing the cross-filter
professor pattern (school/origin + field/topic → type B, domain professor) reaches professor
Milvus recall. Acceptance = routing-reachable; #19 recall is bound by ingest (许晋诚/陈功 absent).

## FM4 — cross-domain paper→professor reverse-lookup (KNOWN GAP, measured, deferred)

**Root cause (verified 2026-07-01):** the DB has 3367 active professors (2843 with paper links);
12 have embodied/dexterous papers (柯文德/任尔夫/王强/刘桂良...). So professor data IS present —
NOT an FM1a data gap. The gap is recall logic, three layers: (1) topic queries route to
`B_company_topic` (company-only recall); `_lookup_cross_domain_evidence` (professor+paper+company
concurrent) only fires for `D_` queries (chat.py:4469/4498), not `B_`; (2) `retrieve(professor)`
is pure `professor_profiles` vector (retrieval.py:564+), not reverse-looking-up authors from
recalled papers; (3) the cross-domain SQL `_paper_professors_sql` exists in `get_related_objects`
(retrieval.py:599-604, via `professor_paper_link`) but is NOT invoked on the topic/professor
recall path.

**Measured (oracle case 50):** forced-domain professor recall for "有哪些做具身智能和灵巧手的
教授" = **0/4** (柯文德/任尔夫/王强/刘桂良 all missed; recalled-top4 are generic "Research
direction"/"Profile summary" snippets). The gap is now counted (it was previously invisible —
#34's `required` was company-only).

**Scope this round:** recorded + measured, NOT implemented. Implementation (wire paper→professor
reverse-lookup into the topic/professor recall path, and/or extend FM3 routing to route
topic→professor) is a separate recall-logic slice — deferred to a follow-on change (like
FM1a/web-augment). FM3's region+domain topic→professor routing is the same class as #19's
person-attribute routing.

## FM5 — clear single-company query misclassified `unknown` (KNOWN GAP, measured, deferred)

**Root cause (verified 2026-07-01, user badcase):** query "深圳法本信息科技有限公司的产品特点以及团队介绍"
routes to `query_type=unknown` (the clarify/refuse path), even though the company IS in the DB
(`法本信息技术`, COMP-d5c254c49820, `ready`). The classifier's company-name lookup is too strict:
the query name "法本信息科技有限公司" does not exact/ILIKE-match the DB canonical "法本信息技术"
(suffix differs: 科技有限公司 vs 技术), so the name-lookup misses → classifier falls to `unknown`.
NOT a data gap; a name-variant-matching gap.

**Measured (oracle case 51):** end-to-end `/api/chat` returns `query_type=unknown`, 0 candidates
→ 0/1 (法本信息技术 missed). The gap is now counted.

**Scope this round:** recorded + measured, NOT implemented. Implementation (fuzzy/substring/
trigram company-name matching, or alias expansion) is a separate classifier slice — deferred.
Risk: over-matching (false company matches) — needs precision care + eval.

## Verification surface (eval-first)
| Surface | What it proves | RED/oracle |
|---|---|---|
| `eval_recall_chat.py` (end-to-end /api/chat, synthesis off) | required-entity recall | baseline 58% (measured) |
| `eval_recall.py` (forced-domain) | isolates raw recall per domain | per-domain hit |
| `tests/scripts` + existing chat tests | no routing regression | green |

Deterministic-ish (retrieval + rules); the LLM-classifier branch is eval-first (§14.7).

## Risk
- FM3 rule may over-trigger (route non-cross-filter to professor). Mitigation: tight pattern +
  eval (precision on other cases unchanged).
- FM1a (data) is NOT addressed — recall ceiling stays bounded for #4/#13 until ingest.
- Web-augment (Serper 403) is NOT addressed here — split to `add-web-augment`.

## Out of scope
FM1a ingest; web-search augmentation (Serper); generation/streaming/AnswerGenerator;
embedding/profile rework; A–G enum; `_VALID_DOMAINS`; `_is_indexable_paper`; evidence shape.

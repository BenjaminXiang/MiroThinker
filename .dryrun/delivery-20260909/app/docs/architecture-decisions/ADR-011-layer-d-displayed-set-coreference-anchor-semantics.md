# ADR-011: Layer D multi-turn context — displayed-set coreference + anchor semantics

- **Date:** 2026-07-09
- **Status:** Accepted (grilling-validated, pre-implementation)
- **Related:** `docs/superpowers/specs/2026-07-07-retrieval-generation-rebuild-design.md` (Layer D, Slice 4 — this ADR details it); ADR-009/010 (Layer C precision, upstream of D); root `CONTEXT.md` (ubiquitous language this ADR fixes)
- **Contract:** to be carried by an OpenSpec change (openspec/ now exists; behavior-affecting per CLAUDE.md §8)

## Context

Multi-turn correctness factors as `referent-resolution × operation-capability × (single-turn factors)`.
A follow-up = (referent R, operation O). Referents: R1 single entity, R2 result set, R3 constraint
frame, R4 answer text. Operations: O1 profile, O2 filter, O3 cross-domain traversal, O4 attribute
aggregation, O5 constraint re-query.

Code-verified gaps (chat.py, chat_context.py): set referents 上述/这些/他们 resolve to nothing
(`_PRONOUN_DOMAIN_MAP` is single-entity only); `_handle_d_narrowing` locks same-domain;
`get_related_objects` is single-source; the classifier's C-route examples are all single-entity, so
"上述教授参与的企业" silently degrades to *one arbitrary professor's* companies. Hardest evidence:
the product's own suggested-followup chips (看看这些教授的论文 / 上述哪些在深圳 / 这些公司有哪些专利,
chat.py:3933-3966) are not matched by any routing layer — **the UI promises follow-ups the backend
cannot honor**.

## Scope decision

Layer D = **set coreference + set operations** (R2 row: resolve, filter, traverse, fetch member
attributes) + R1 regression. R2×O4 splits: D resolves the set and fetches member data; **Layer A
owns aggregation/comparison expression**. R3 (constraint re-query, "那广东的呢") and R4 (answer-text
deixis, "第二个是谁") are deferred — they need new state (constraint-frame / answer-structure
memory), a different foundation from R1/R2 which only need resolution+operations over existing
`last_result_set`.

## Decisions

### 1. Result set = what the user SAW (displayed), not what retrieval returned

`result_ids_by_domain` currently ingests all `retrieval_evidence` (cap 100) while the answer shows
~10 — so 上述 can resolve to entities the user never saw, breaking the word's semantics and §5
audit traceability ("where did you mention that?").

**Decision:** the result set captures only displayed entities (answer list + citations). Recall of
undisplayed-but-relevant entities is Layer C's job (ranking/display policy), not something D
compensates for by secretly remembering more. Mitigation for the lost recall: answers may state
"以上筛选基于上轮展示的 N 个结果".

Trade-off accepted: lower narrowing recall in exchange for a coherent user mental model and clean
per-answer audit trails. **Surprising without context** because the code deliberately stops
harvesting evidence it already has.

### 2. Anchor semantics: list answers create NO single-entity anchors

Today every list citation is pushed onto the `entities` stack, so "他" after a 10-professor list
resolves to an arbitrary member (last pushed) — silently wrong. **Decision:** the anchor stack
holds only entities the user individually focused on (profile answer, disambiguation pick, explicit
naming). Sets live in `last_result_set`; anchors in `entities`; R1/R2 separation mirrored in state.
Singular pronoun + no anchor + live set in that domain → deterministic clarification listing the
members (a guess is luck; clarification is honest and costs one turn).

### 3. Routing: hybrid, A-G semantics unchanged

No new top-level query class (§5 invariant; "D-route gains set-coref, not new query classes").
A thin **rule layer guarantees** chip texts and explicit set-words (上述/这些/他们) route
deterministically; the LLM classifier gains an orthogonal `referent: "set" | "entity"` output (plus
set examples) to catch paraphrases ("他们都开了哪些公司"). `C + referent=set` → batch traversal;
`C + referent=entity` → existing single-entity path. Explicit set-word beats classifier; neither
present → single-entity (conservative status quo). **Every chip string must be rule-hit — locked by
a routing-matrix test** so UI promises stay honored.

### 4. Set traversal: loop over `get_related_objects`, target-centric render

Batch = chat-layer loop over the existing retrieval-service `get_related_objects` (NOT the HTTP
endpoint variant, which mis-buckets professors into `papers`; retrieval.py:524 returns clean rows).
Per-member limit natural (5), each call auditable, no new windowed `ANY(%s)` SQL for ≤10-member
sets. Result is a **member-target bipartite mapping** kept whole in `structured_payload` (§5);
rendering dedups by target with back-links. Default projection **target-centric** (the
interrogative falls on the target domain); 分别 in the query switches to member-centric. Answers
MUST carry a coverage statement ("10 位中 4 位有企业关联记录…其余 6 位暂无") distinguishing no-data
from not-searched; candidate links shown but labeled; `role_type` surfaced.

### 5. Narrowing: three mechanisms by predicate type

- **Chip predicates** (region/institution, year/recency, grant status, applicant type — a closed
  table): fetch member rows by ID, deterministic Python predicate, per-member explainable verdicts.
  Not semantic retrieval — embeddings carry no "granted-status" semantics; that mismatch is why
  topic-∩-set alone was rejected as the sole mechanism.
- **Open predicates** ("引用量超1000", "偏硬件的", qid5's 机械臂按电梯): deterministic fetch of full
  member rows → **LLM per-member structured verdict** `{member_id, verdict, evidence_field, quote}`,
  fully audit-logged — same pattern as Layer A Step-1 relevance judgment (LLM judges on grounded
  evidence; never selects retrieval).
- **Topic narrowing** ("其中做大模型的"): existing `retrieve(topic) ∩ set` unchanged.

Unknown-vs-unsatisfied distinguished in answers (empty field → 信息缺失, not counted as 不满足).

### 6. Degradation: deterministic base is self-sufficient, LLM is an enhancement layer

`CHAT_QUERY_CLASSIFIER=off`: chips + explicit set-words still route (rule layer); paraphrases fall
through to status-quo new-query handling (no guessing). `CHAT_LLM_SYNTHESIS=off`: open-predicate
narrowing degrades to `retrieve(topic) ∩ set` labeled "按语义相关性筛选"; deterministic rendering is
the final answer; traversal/chip-narrowing/clarification unaffected. Off-state determinism is the
unit-test surface; full-on is the eval surface. Verdict model follows Layer A's selection
(deepseek-v4-pro; accuracy > latency >> cost — not reopened).

### 7. Verification (GREEN)

Multi-turn eval runner (session-sticky via `miroflow_chat_session` cookie, proxy vars unset) over
`turn_group`-linked golden conversations: the **8 existing follow-up cases in test_cases.yaml**
(currently skipped by `is_head_turn`) + ~6 synthesized dialogs covering R2×O3 traversal, bare 他们,
list-then-他 clarification, empty-set/domain-mismatch clarification, a 3-turn chain
(教授→上述教授的企业→这些公司的专利), and the chip routing matrix. RED baseline archived before
implementation. **Accept line: ≥12/14 multi-turn pass AND zero single-turn regression (19-case set,
esp. qid14/17) AND chip routing matrix fully green.**

## Alternatives rejected

- **Set = full retrieved evidence (status quo):** breaks 上述 semantics + audit; recall belongs to C.
- **Pure-rule routing:** cannot cover paraphrases; chips-only honesty. Pure-classifier: single point
  of failure, env-off leaves chips broken. Hybrid keeps the guarantee where we control the strings.
- **New batch SQL with per-source window:** complexity without need at set size ≤10.
- **LLM guess for post-list 他:** silent wrong answers; clarification is deterministic and cheap.
- **Semantic retrieval for structured predicates (已授权 etc.):** mechanism mismatch, unexplainable.

## Known limitations

- Narrowing/traversal operate on ≤ displayed-set size (~10); truncation is declared in the answer.
- R3/R4 referents unsupported this slice (deferred, separate state model).
- Open-predicate verdicts inherit LLM variance — bounded by structured output + audit log + the
  2-case tolerance in the accept line.

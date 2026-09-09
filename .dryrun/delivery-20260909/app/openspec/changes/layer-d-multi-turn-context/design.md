# Design: layer-d-multi-turn-context

> Full decision record with rejected alternatives and evidence:
> `docs/architecture-decisions/ADR-011-layer-d-displayed-set-coreference-anchor-semantics.md`.
> This design maps those decisions onto the code and defines the verification surface.
> Requirements live in `specs/chat-multi-turn-context/spec.md`.

## Context

Current state (code-verified 2026-07-09):

- `SessionContext.last_result_set` (chat.py:1933) exists, cap 100, but is populated by
  `result_ids_by_domain` (chat_context.py:41) from ALL `retrieval_evidence` — not just
  displayed entities — and its only consumer is same-domain narrowing.
- `_PRONOUN_DOMAIN_MAP` (chat.py:1892) covers singular pronouns only; 上述/这些/他们 resolve
  to nothing. Every list citation is pushed onto the `entities` anchor stack, so 他 after a
  list resolves to an arbitrary member.
- `looks_like_narrowing_query` (chat_context.py:21) is a line-anchored prefix regex; chip
  texts like 看看这些教授的论文 fall through to a global new query.
- `_handle_d_narrowing` (chat.py:4947) locks `latest_result_domain()` — never cross-domain;
  its only mechanism is `retrieve(topic) ∩ set`.
- `_build_c_type_response` (chat.py:3390) is single-entity; the classifier's C-route
  examples are all single-entity.
- Two relation lookups exist: retrieval-service `get_related_objects` (retrieval.py:524,
  clean rows, 8 domain pairs) and the HTTP endpoint variant (domains.py:2255) which
  mis-buckets paper→professor results into `papers`. Only the former is usable here.
- Eval: `eval_full_testset.py` sends head-turns only; the 8 follow-up golden cases in
  `test_cases.yaml` (turn_group-linked) are skipped. No session-sticky runner exists.

Constraints: CLAUDE.md §5 invariants (A-G semantics unchanged, deterministic auditable
retrieval, evidence traceability, no schema change); Route-C principle (LLM judges on
grounded evidence, never selects retrieval); §8 requires eval-first GREEN for multi-turn
chat work.

## Goals / Non-Goals

**Goals:**

- Set coreference over displayed result sets; set narrowing (3 predicate mechanisms); set
  cross-domain traversal with member-target mapping answers; honest clarification on
  ambiguity; chip texts honored end-to-end; chained follow-ups; defined degradation;
  session-sticky multi-turn eval with RED baseline.

**Non-Goals:**

- R3 constraint re-query (那广东的呢) and R4 answer-text deixis (第二个是谁) — separate
  state models, deferred.
- New A-G query classes; new domains; schema/migration changes; agentic retrieval.
- Improving retrieval recall (Layer C owns ranking/display; D never compensates by
  remembering undisplayed evidence).

## Decisions

Numbered decisions, each with locus in code. Alternatives and evidence: ADR-011.

### D1. Displayed-set semantics for `last_result_set`

`result_ids_by_domain` narrows its sources to answer-displayed entities + citations;
`retrieval_evidence` harvesting is removed. Call sites in `_record_and_return` pass the
displayed subset. Answers over sets may append "以上基于上轮展示的 N 个结果".

### D2. Anchor discipline + clarification

`_record_and_return` stops pushing list citations onto `entities`; pushes happen only for
profile/disambiguation/explicit-naming answers. New guard: singular pronoun + no anchor +
non-empty same-domain set → deterministic clarification response listing members (new
`query_type="D_clarification"` is NOT added — reuse the existing clarification response
shape under the current query_type taxonomy to keep A-G untouched).

### D3. Hybrid routing with `referent` field

- Rule layer (chat_context.py): set-word detector (上述/这些/他们 + domain-worded forms) and
  an operation splitter (narrow vs traverse vs attribute) that MUST match every chip string
  emitted by `_suggested_followups` — locked by a routing-matrix unit test enumerating the
  chip strings.
- Classifier: prompt gains 2-3 set examples and an output field `referent: "set"|"entity"`;
  C + referent=set → batch traversal path; C + referent=entity → existing single-entity
  path. Parsing tolerates the field's absence (older prompt cache, off switch).
- Precedence (deterministic): explicit set-word > singular pronoun > classifier referent >
  status quo.

### D4. Batch traversal = loop over retrieval-service `get_related_objects`

New chat-layer helper `_batch_related_objects(source_domain, source_ids, target_domain,
per_source_limit=5)`: loops members (set size ≤ displayed ~10), calls
`get_retrieval_service().get_related_objects` per member, assembles the member-target
mapping. No new windowed SQL; each call independently auditable. The domains.py HTTP
variant is not touched. Truncation (set larger than cap) is declared in the answer.

### D5. Member-target mapping render

Deterministic renderer builds: target-centric projection (default; dedup targets, keep
back-links, role_type + link_status labels) or member-centric (分别 in query). Coverage
statement always. Full mapping into `structured_payload` (§5 traceability). When synthesis
is on, the rendered structure is the evidence for LLM phrasing; when off, it IS the answer.

### D6. Narrowing mechanism selection

Predicate classifier (deterministic, ordered): chip-predicate table hit → per-member Python
predicate on rows fetched by ID (region/institution, year/recency, grant status, applicant
type — field mapping per domain); else if synthesis on → LLM per-member structured verdict
`{member_id, verdict, evidence_field, quote}` (same grounded-judgment pattern as Layer A
Step-1; model per Layer A selection: deepseek-v4-pro lane); else → existing
`retrieve(topic) ∩ set` labeled 按语义相关性筛选. Unknown (empty field) reported as 信息缺失,
never counted as failing.

### D7. Chaining

Traversal/narrowing answers push their displayed output entities as the new result set in
the output domain (existing `push_result_set` mechanics; the displayed-set discipline of D1
applies).

### D8. Verification surface (per repo design rules)

- **Scenario eval (primary GREEN)**: new session-sticky runner
  `apps/admin-console/scripts/eval_multi_turn.py` — groups `test_cases.yaml` by
  `turn_group`, replays each conversation over HTTP with a fixed `miroflow_chat_session`
  cookie, scores per-turn required/forbidden/coverage + routing assertions. Proxy vars
  unset (project memory); read-only against the live backend (Milvus single-writer safe).
  Golden set: 8 existing follow-up cases + ~6 synthesized dialogs (traversal, bare 他们,
  list-then-他 clarification, empty-set clarification, 3-turn chain, chip matrix).
  RED baseline archived to `.agents/runs/layer-d-multi-turn-context/` before
  implementation. Oracle strength: strong for routing/membership assertions (deterministic
  IDs), moderate for answer coverage (term overlap).
- **Unit/contract tests**: routing matrix (every chip string → expected path), set-word
  precedence, predicate table per domain, projection renderers, anchor discipline,
  displayed-set capture — all with `CHAT_LLM_SYNTHESIS=off CHAT_QUERY_CLASSIFIER=off`
  (mock boundary = LLM lanes + retrieval service, consistent with existing test style).
- **Not unit-tests-alone**: per repo rule for chat/routing work, acceptance is the eval
  line: ≥12/14 multi-turn AND zero single-turn regression (19-case set, esp. qid14/17) AND
  chip matrix green.

## Risks / Trade-offs

- [Displayed-set narrows recall of set operations] → deliberate (ADR-011 D1): coherence and
  §5 audit beat recall; recall belongs to Layer C. Answers may state the basis-set size.
- [LLM verdict variance on open predicates] → structured output + per-member audit in
  `structured_payload` + the 2-case tolerance in the accept line; degradation path exists.
- [Classifier prompt change perturbs existing routing] → referent is an additive orthogonal
  field; parser tolerates absence; single-turn 19-case non-regression is a hard gate; the
  intent-benchmark CI gate (ADR-008) covers classifier drift.
- [Anchor discipline changes existing behavior (list→他 now clarifies)] → user-approved in
  grilling; qid14/17 profile-flows unaffected (verified in eval).
- [Loop-per-member latency on traversal] → set ≤ ~10, per-call SQL is indexed by link
  tables; accuracy > latency per rebuild design. If needed later, parallelize the loop —
  not a blocker now.
- [Two routing layers drift apart] → the chip-matrix unit test pins the rule layer; the
  eval pins end-to-end; both run in CI.

## Migration Plan

Pure application-code change; no schema, no data migration. Deploy = normal backend
release. Rollback = revert commit(s). Session objects persisted with the old (wide)
`last_result_set` semantics remain valid — model_post_init caps them; first new turn
overwrites per-domain sets. Env kill-switches provide operational fallback without deploy.

## Open Questions

None blocking — all decision points were resolved in the grilling session (scope, set
semantics, routing, projection default, narrowing mechanisms, anchor discipline, GREEN
line ≥12/14, degradation). Deferred by decision (not open): R3/R4 referents, numeric
comparison predicates in the chip table (first version relies on the open-predicate LLM
path for those).

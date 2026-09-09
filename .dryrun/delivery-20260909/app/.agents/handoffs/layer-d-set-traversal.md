# Handoff — layer-d-multi-turn-context, set cross-domain traversal (group 3 rule-routing + group 4 execution)

> Claude → Codex. One Ready slice. Groups 2 (coref) Accepted; this delivers end-to-end
> **set cross-domain traversal**. Routing-without-execution would be a half-state, so the
> rule-layer detector and the traversal executor ship together.

## Contract

- OpenSpec: `openspec/changes/layer-d-multi-turn-context/` — specs requirements "Follow-up
  routing is hybrid…" (rule-layer part), "Set cross-domain traversal produces a
  member-target mapping answer", "Set operations chain".
- Verification contract: `.agents/runs/layer-d-multi-turn-context/verification-contract.md`.
- RED evidence this slice fixes: `red-notes.md` **M1** (traversal hijacked by narrowing:
  S1-F, S5-F1, S5-F2, S6C-F), **M3** (bare 他们: S2-F), **M4** (chip → unknown: S6A-F).
  Narrowing-mechanism cases (qid4/10, S6B) and clarification cases stay as-is (later groups).
- ADR-011 D3 (rule layer), D4 (batch traversal), D5 (mapping render), D7 (chaining).
  Glossary: root `CONTEXT.md` (member-target mapping, coverage statement).

## Why rule-layer only (classifier `referent` field DEFERRED)

Every golden traversal case is rule-coverable (explicit domain words: 企业/论文/专利 ≠ source).
The classifier `referent` field is paraphrase-robustness only — not a prerequisite for any
golden case. Deferring it keeps this slice from perturbing A–E routing (ADR-008 benchmark
risk). It becomes its own tiny follow-up. Do NOT touch `_CLASSIFIER_SYSTEM` in this slice.

## Scope

### A. Operation detector (pure, services/chat_context.py)
New `detect_set_operation(query, source_domain) -> ("traverse", target_domain) | ("narrow", None)`:
- Scan the query for domain words (教授/老师/学者→professor; 公司/企业→company; 论文/文章→paper; 专利→patent).
- Collect the set of domains referenced EXCLUDING `source_domain`.
- If exactly one other domain → `("traverse", that_domain)`. If ≥2 others → treat as narrow
  (ambiguous multi-domain is D-route territory, out of scope; fall through). If none →
  `("narrow", None)`.
- Pure function; unit-test the matrix (incl. source-word-present-but-not-target cases like
  上述教授的研究方向 → narrow).

### B. Dispatch wiring (api/chat.py, in `chat()`)
Insert AFTER the group-2 clarification guard (chat.py ~5110) and BEFORE
`looks_like_narrowing_query` (~5115):
```
set_referent = detect_set_referent(query)            # group 2
resolved = session.resolve_set_referent(set_referent) if set_referent else None
if set_referent is not None and resolved is None:
    <group-2 clarification>                           # already present
if resolved is not None:
    op = detect_set_operation(query, resolved[0])
    if op[0] == "traverse":
        return _handle_set_traversal(resolved[0], resolved[1], op[1])
# ... existing looks_like_narrowing_query / _handle_d_narrowing unchanged ...
```
This kills M1: traversal queries no longer reach `_handle_d_narrowing`.

### C. Batch traversal executor (api/chat.py)
New `_handle_set_traversal(source_domain, source_ids, target_domain)`:
- Cap `source_ids` to displayed-set size (≤10); if larger, truncate and note it.
- Loop members → `get_retrieval_service().get_related_objects(source_domain=…, source_id=mid,
  target_domain=target_domain, limit=5)`. Catch per-member errors (log, continue). This is
  the retrieval-SERVICE variant (apps/miroflow-agent/.../retrieval.py:524) — NOT the HTTP
  endpoint in domains.py (it mis-buckets professors into `papers`).
- Assemble member-target mapping: list of `{member_id, member_label, targets: [chat_row…]}`
  preserving order; members with zero targets kept (marked 暂无).
- `query_type="C_cross_domain_related"` (NO new A-G class; matches fixture expectations).

### D. Renderer (deterministic; api/chat.py or chat_context.py)
- Default **target-centric**: dedup targets by id across members; each target line shows
  label + back-links (which members, role_type, link_status label: verified/candidate).
- **Member-centric** when query contains 分别: per member, list its targets.
- **Coverage statement mandatory**: "上轮 N 位{source label}中，M 位有{target label}关联记录，
  共涉及 K 个{target label}。其余 (N−M) 位暂无收录。" (exact counts from the mapping).
- `role_type` + `link_status` surfaced (verified shown plainly, candidate labeled 候选).
- When `CHAT_LLM_SYNTHESIS=on`: feed the rendered mapping as evidence to the existing
  synthesis lane for phrasing (do NOT change the synthesis prompt contract). When off: the
  deterministic render IS the answer.

### E. Preserve link metadata
`_related_row_to_chat_row` (chat.py:3287) currently drops `role_type`/`link_status`/
`match_reason`. Extend it to include them as optional fields when present (additive — the
single-entity C path at `_build_c_type_response` is unaffected). The renderer reads them.

### F. Chaining (spec "Set operations chain")
Build `ChatCitation`s for the displayed (deduped, capped) targets. `_record_and_return`
→ `result_ids_by_domain` harvests target IDs from citations → `push_result_set(target_domain,
…)`. Verify: S5 3-turn chain — turn-3 这些公司有哪些专利 resolves source=company (from turn-2
targets), traverses to patent.

### G. structured_payload shape (so eval set_derived + chaining assertions pass)
```
{
  "source_domain", "source_ids": [...prior member ids...],
  "target_domain",
  "member_target_mapping": [{member_id, member_label, targets:[…]}],
  "retrieval_evidence": [target chat rows],   # also feeds citations via list keys
}
```
`source_ids` present ⇒ eval `_set_derived_assertion` passes (source ids ⊆ prior basis, none
outside). Target ids in citations ⇒ next-turn chaining resolves correctly.

### H. Tests (new tests/test_chat_set_traversal.py, env off)
- Operation detector matrix (traverse vs narrow, source-word-exclusion, multi-domain→narrow).
- `_handle_set_traversal` with mocked `get_related_objects`: target-centric + member-centric
  render, coverage statement counts, empty-member marking, role_type/link_status labels,
  candidate labeling.
- Chaining: result_set updated to target domain; a second mocked turn resolves source=target.
- set_derived payload shape (source_ids present).
- `CHAT_LLM_SYNTHESIS=off` deterministic render is the answer.

## Non-goals (hard boundaries)

- NO classifier prompt/schema changes (`_CLASSIFIER_SYSTEM` untouched).
- NO narrowing-mechanism changes (`_handle_d_narrowing` body unchanged; narrow cases stay red).
- NO anchor-stack changes (group 6).
- NO fixture / eval-runner edits.
- Do NOT run the multi-turn eval or restart the backend (Claude runs eval at review; backend
  on :18188 is live — leave it).

## Environment

Unit tests: `cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
all_proxy ALL_PROXY no_proxy NO_PROXY && UV_CACHE_DIR=/tmp/mirothinker-uv-cache uv run
--no-sync pytest tests/test_chat_set_traversal.py tests/test_chat_set_coreference.py
tests/test_chat_d_narrowing.py tests/test_chat_c_handler.py tests/test_chat_session_persistence.py -q`
(+ any other test you find touching `get_related_objects`/`_build_c_type_response`).

## Candidate criteria

- All listed unit tests green; full chat suite no new failures.
- Diff confined to: services/chat_context.py (detector), api/chat.py (dispatch + executor +
  renderer + `_related_row_to_chat_row` extension + payload), new test file.
- Report: exact commands + output, files changed, any spec-vs-code discrepancy.

## Next owner

Claude review → eval (expect S1-F/S2-F/S5-F1/S5-F2/S6A-F/S6C-F → OK or substantially fixed;
single-turn 19-case zero regression) → Accept ⇒ group 5 (narrowing mechanisms) Ready.

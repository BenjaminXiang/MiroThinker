# Handoff — layer-d-multi-turn-context, task group 1: multi-turn eval runner + RED baseline

> Claude → Codex. One Ready slice. Do NOT touch production chat code in this slice —
> this group builds the measurement harness and archives the failing baseline only.

## Contract

- OpenSpec change: `openspec/changes/layer-d-multi-turn-context/` (proposal, design,
  specs/chat-multi-turn-context/spec.md, tasks.md — this slice = tasks 1.2–1.4)
- Verification contract: `.agents/runs/layer-d-multi-turn-context/verification-contract.md`
  (RED/GREEN definitions; this slice PRODUCES the RED artifact)
- Decision record: `docs/architecture-decisions/ADR-011-layer-d-displayed-set-coreference-anchor-semantics.md`
- Glossary: root `CONTEXT.md`

## Scope (tasks 1.2–1.4)

1. **`apps/admin-console/scripts/eval_multi_turn.py`** — session-sticky multi-turn eval:
   - Load `apps/admin-console/tests/fixtures/test_cases.yaml`; group cases by `turn_group`;
     order head-turn first, follow-ups after (yaml order within group).
   - Replay each group as ONE conversation: same `miroflow_chat_session` cookie for all
     turns of the group (fresh cookie per group). POST /api/chat per turn, sequential.
   - Score follow-up turns: required_entities hit, forbidden_entities violation, coarse
     answer coverage (reuse `_terms`/`_hit` helpers style from `eval_full_testset.py`),
     PLUS routing assertions when the case declares them (see synthesized cases below):
     expected `query_type`, and set-membership checks against `structured_payload`
     (e.g. traversal targets must be set-derived — check the mapping/evidence IDs).
   - Output JSON: per-case rows (qid, turn_group, query, scores, query_type,
     routing-assertion results, failure notes) + summary (pass/fail per case, totals).
     Default out: `.agents/runs/layer-d-multi-turn-context/red-baseline-<date>.json`.
   - CLI mirrors `eval_full_testset.py` (`--base http://localhost:18188`, `--out`).
2. **Synthesized golden dialogs** — add ~6 multi-turn conversations. Put them in a sibling
   fixture `apps/admin-console/tests/fixtures/multi_turn_cases.yaml` (do NOT edit
   test_cases.yaml — it mirrors the source xlsx). Schema: same fields as test_cases.yaml
   plus optional `expected_query_type` and `expected_set_derived: true` (routing
   assertions), `turn_group` linking. Cover exactly:
   - S1 R2×O3 traversal: 有哪些做具身智能和灵巧手的教授 → 上述教授参与的企业
     (expect: set-derived companies, coverage statement; today expected FAIL)
   - S2 bare-pronoun traversal: same head → 他们发表了哪些论文 (today expected FAIL)
   - S3 list-then-singular clarification: professor list → 他的论文是哪些
     (expect clarification, not an arbitrary member; today expected FAIL)
   - S4 empty-set/domain-mismatch: company list head → 上述教授参与的企业
     (expect clarification, no global re-search; today expected FAIL)
   - S5 3-turn chain: 教授列表 → 上述教授参与的企业 → 这些公司有哪些专利
     (turn 3 must operate on turn 2's displayed companies; today expected FAIL)
   - S6 chip routing rows: send the exact chip strings 看看这些教授的论文 /
     上述哪些在深圳 / 这些公司有哪些专利 / 上述哪些已授权 after suitable heads; assert
     routing (query_type/behavior), not answer quality. (today expected FAIL/partial)
   Required/forbidden entities for S1/S2/S5: derive from live DB relations of the head
   query's displayed set — keep them minimal (1-2 required each) and verifiable via
   `professor_company_role` / link tables; if the live set is too thin, mark the case
   routing-assertion-only (no entity requirements) rather than inventing golds.
3. **RED baseline run** (task 1.4): with the backend UP, run the runner over ALL groups
   (8 yaml follow-ups + 6 synthesized), archive JSON to
   `.agents/runs/layer-d-multi-turn-context/red-baseline-<date>.json`, and write
   per-case failure modes to `.agents/runs/layer-d-multi-turn-context/red-notes.md`
   (which layer each failure maps to: routing / coref / traversal / anchor).

## Non-goals (hard boundaries)

- NO edits to `backend/api/chat.py`, `services/chat_context.py`, classifier prompts, or
  any production behavior — measurement only.
- NO edits to `test_cases.yaml`.
- NO Milvus refresh / writes — the runner is read-only HTTP.
- Do not chase making cases pass; RED is the deliverable.

## Environment (per project memory — critical)

```
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
export no_proxy=localhost,127.0.0.1,::1
```
Backend must be UP (default base http://localhost:18188). If it is not running, report and
stop — do not start/restart services yourself.

## Acceptance for THIS slice (Candidate criteria)

- Runner runs clean end-to-end over all 14 groups; JSON + notes archived.
- Session stickiness proven: per-group cookie reused (visible in code + at least one group
  where turn-2 behavior differs from sending the same query standalone — e.g. qid12
  这论文的链接 resolves the anchor).
- Exact commands + output snippets recorded in the report.
- No production-code diffs (`git status` clean outside scripts/, fixtures
  multi_turn_cases.yaml, and .agents/runs/layer-d-multi-turn-context/).

## Next owner after this slice

Claude review (Accept/Revise/Reject) → then task group 2 (displayed-set semantics) becomes
Ready.

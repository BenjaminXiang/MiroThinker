# Proposal: enforce-never-refuse-contracts

> Phase 2 of Epic `fix-round-1-serving-pipeline` (opened 2026-08-18, under the
> user's full-autonomy grant; agent-governed per AGENTS.md §3).
> Human docs: plan `docs/plans/2026-08-17-systematic-fix-round-1.md` ·
> log `docs/plans/2026-08-17-systematic-fix-round-1-log.md`.
> Behavior-affecting: YES. Capability: `canonical-v2-chat`.

## Why

Three verbatim-transcript defect forms share one root: the answer layer is
allowed to ship refusals, deflections, and world-negative claims that the
evidence does not support.

- **P2 (G2)**: bare-name first answers ship refusal-form text
  ("未找到/暂无公开的详细运营信息" family) even though the entity IS known
  to the system; the existing last-resort fallback
  (`_soft_fallback_answer_text`) is itself a refusal shape ("暂未能确认…
  可以换个角度继续提问") with no subject, no confirmed facts, no named gap.
- **P5 (G4)**: patent-scoped answers deflect to external databases
  ("建议访问国家知识产权局…" family) when the local patent relation is
  empty — presenting a data-coverage gap as if the information did not exist.
- **P4 wording (G3)**: "这一机构名称" style template phrases ship
  entity-less answers.
- **2.2 semantics**: a web-lane outage (all providers failed) must be stated
  as 网络检索暂不可用 — NEVER as 未找到该机构 (a negative factual claim
  about the world). Phase 1 made lane failure VISIBLE in the trace; this
  change makes the ANSWER state it.

## What Changes

1. **Never-refuse fallback contract (2.1)**: `_soft_fallback_answer_text`
   rewritten to the contract form — subject name in the first sentence, what
   IS confirmed, the specific gap named as a coverage fact, an actionable
   next step. Never "换个角度" brush-offs, never subject-less refusals.
2. **Deflection guard (2.1)**: new deterministic post-guard — answers
   matching external-database deflection patterns (国知局/PatSnap/Incopat/
   专利数据库/检索平台 suggestions) over a turn with zero patent evidence are
   rewritten to the gap-naming form (anchor named, coverage gap stated, local
   confirmed facts kept).
3. **Lane-failure semantic correction (2.2)**: when the turn's evidence
   traces show the web lane unavailable (all provider attempts errored or
   timed out) the answer MUST carry 网络检索暂不可用 and keep
   local/cached/prior evidence; negative world claims (未找到该机构/无相关
   信息) over such turns are rewritten. RED: fault-injected empty web lane
   over a web-only subject (same harness as Phase 1 RED-4).
4. **Subject-carrying answers (wording)**: rewritten fallbacks always name
   the active anchor (or the query's named subject when no anchor exists).
5. **Synthesis prompt contract**: prose-renderer prompt gains the same
   three rules (no refusal-form endings, no external deflection, lane
   outage wording) so the LLM path produces compliant text natively; the
   deterministic guards remain the enforcement backstop.

Out of scope: subject-layer fixes (P1/P3/P4 root causes — Phase 3), data
coverage (P5/P8 root — Phase 4/5), enumeration coverage statements (land with
Phase 5 fetch where enumeration evidence actually changes).

## Impact

- `apps/admin-console/backend/services/canonical_v2_chat.py` — fallback text,
  new guards in `_map_response` path.
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
  — prose renderer prompt contract line(s).
- Tests: admin-console guard unit tests (hermetic fakes) + replay/fault
  evidence per verification contract.

# Source Links: close-retrieval-generation-contract

## Behavior and data contracts

- `docs/Data-Agent-Shared-Spec.md` — structured, traceable, source-grounded cross-domain evidence.
- `docs/Agentic-RAG-PRD.md` — authoritative explicit-title local miss invokes real-time external
  fallback; this Epic preserves it with separate Web provenance and truthful outcomes.
- `docs/index.md` — authority map for current versus legacy/partial documentation.
- `openspec/changes/close-retrieval-generation-contract/specs/chat-grounded-answer-contract/spec.md`
- `openspec/changes/close-retrieval-generation-contract/specs/paper-retrieval-quality/spec.md`
- `openspec/changes/close-retrieval-generation-contract/specs/paper-index-parity/spec.md`

## Predecessor change records (Candidate)

- `openspec/changes/fix-paper-topic-query-classification/`
- `openspec/changes/wire-professor-paper-list-traversal/`
- `openspec/changes/fix-professor-ambiguity-intro-rule/`

These records show the local repairs but do not override this Epic's canonical end-to-end gates.
Their Candidate verification contracts/evidence live under matching
`.agents/runs/{fix-paper-topic-query-classification,wire-professor-paper-list-traversal,fix-professor-ambiguity-intro-rule}/`.

## Accepted eligibility behavior dependency

- `openspec/changes/make-partial-papers-retrievable/specs/data-quality-gating/spec.md` — the pure
  canonical eligibility/rich-text predicate remains the sole retrieval-readiness authority. Slice F
  records versioned reconciliation observations and MUST NOT create a second persisted readiness
  signal.
- `openspec/changes/make-partial-papers-retrievable/specs/agentic-rag-retrieval/spec.md` — accepted
  partial-rich vector admission and presentable snippet chain.
- `openspec/changes/make-partial-papers-retrievable/tasks.md` — its unmeasured D3 task is explicitly
  dispositioned to this Epic's stricter Slice F all-paper/exact-chunk reconciliation.

## Modified in-verification dependency

- `openspec/changes/sigs-official-publications-to-paper-domain/` — retains its unique official-
  publication ingest capability, but its historical exact-title title-only exclusion and ready-first
  topic fallback are superseded by C0/D1. Normal archive is blocked on aligned Task 5.20.

## Current implementation/evaluation evidence to inspect per slice

- `apps/admin-console/backend/api/chat.py` — routing, retrieval payload, evidence prompt, synthesis,
  citations, response serialization, and outcome behavior.
- `apps/admin-console/frontend/src/pages/Chat.tsx` — citation numbering and source rendering.
- `apps/admin-console/backend/static/chat.html` and `apps/admin-console/backend/main.py` — the
  currently served `/chat` consumer/route that must migrate or be explicitly redirected.
- `apps/admin-console/scripts/eval_recall.py` — retrieval cases and historical token oracle.
- `apps/admin-console/scripts/eval_recall_chat.py` — response-wide recall scoring seam.
- `apps/admin-console/scripts/eval_true_accuracy.py` — existing generation semantic-judge leg.
- `apps/admin-console/tests/test_paper_retrievability.py` — current regression coverage.
- `apps/miroflow-agent/src/data_agents/service/retrieval.py` — paper retrieval, relations, and
  candidate behavior.
- Paper canonical/link storage and Milvus publisher/backfill code discovered from the current tree
  during Slice F; exact paths and schemas must be bound in that slice before editing.

## Existing run evidence

- `.agents/runs/paper-retrievability-baseline/slice-contract.md`
- `.agents/runs/paper-retrievability-baseline/baseline-summary.md`
- `.agents/runs/paper-retrievability-baseline/type2-prof-papers-fix.md`
- `.agents/runs/paper-retrievability-baseline/type4-classifier-fix.md`
- `.agents/runs/retrieval-generation-alignment/` — historical baseline JSON files; only artifacts
  committed to the target change may be treated as fixed evidence.

## Audit snapshot

- Code checkpoint: `c0f3db2` on `feat/professor-retrievability`.
- Design decisions: 2026-07-10 retrieval/generation grilling session, captured in this change's
  `proposal.md` and `design.md`.
- The proposal-time database counts in `verification.md` are observations, not normative constants.

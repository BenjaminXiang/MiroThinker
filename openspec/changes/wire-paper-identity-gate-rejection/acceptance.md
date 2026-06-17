# Acceptance — wire-paper-identity-gate-rejection

> Each acceptance item maps to a requirement/scenario in `specs/paper-identity-status/spec.md`. Evidence lives under `.agents/runs/wire-paper-identity-gate-rejection/`. Mark Met / Partial / Unmet with the artifact or the specific gap.

## A1. Rejection guard correctness (spec: "LLM same-person-gate rejection transitions identity_status")
- **A1.1** `decide_identity_status_rejection` returns `reject` only when (no verified link AND `prof_page_only`); `no_change` otherwise. — Met via `tests/data_agents/paper/test_identity_status_writer.py` (RED→GREEN).
- **A1.2** On `--apply`, only qualifying papers transition to `identity_status='rejected'`; a remaining `verified` link or non-prof-page-only source ⇒ no change. — Met via scan script test + bounded-apply run artifact.

## A2. Reversibility (spec: "Identity-status rejection is reversible")
- **A2.1** `restore_identity_status` restores the exact `prior_identity_status` and resolves the `pipeline_issue` when a `verified` link is re-established. — Met via unit test.
- **A2.2** The rejection path does NOT set `quality_status='rejected'` (no terminalization). — Met via unit test asserting `quality_status` unchanged.

## A3. Dry-run + independent flag (spec: "scan is dry-run by default behind an independent flag")
- **A3.1** Default invocation writes nothing and emits JSONL + counts. — Met via script test + real dry-run artifact.
- **A3.2** `PAPER_IDENTITY_GATE_ENABLED` falsy ⇒ scan skips gate and writes; flag is read in the script and is independent of `NAME_IDENTITY_GATE_ENABLED` / `paper_collector.identity_gate_enabled`. — Met via script test.

## A4. Retrieval effect (spec: "Rejected or merged papers are excluded from retrieval")
- **A4.1** A `rejected` paper is not indexable (`_is_indexable_paper`); after Milvus re-backfill, a rejected paper no longer returns in retrieval. — Met via `_is_indexable_paper` unit test + post-backfill spot-check artifact.

## A5. Evidence + run_id (spec: "Rejections carry evidence and run_id")
- **A5.1** Each applied rejection has a stage-`identity_gate` `pipeline_issue` row (or JSONL entry) with gate confidence, reasoning, source spans, and `run_id`. — Met via writer unit test + apply-run artifact.

## A6. Baseline / blast-radius discipline
- **A6.1** An eligibility baseline (count of prof-page-only papers with no verified link) is recorded before any `--apply`, and the applied reject count is compared to it. — Met via `eligibility-baseline.json` + dry-run counts.

## Out of scope (explicitly not accepted here)
- Promotion of ~7,297 `unverified` rows (→ W0a/W2a source-gap).
- Cleanup of dead `apply_identity_gate_reevaluation` (→ Gap A).
- Gate threshold/semantics changes.

## Skipped / deferred checks
- Host real-LLM E2E on the full unverified population (cost/blast-radius) — replaced by bounded-slice apply (6.2). Flag default stays conservative until operator signs off on the dry-run counts.

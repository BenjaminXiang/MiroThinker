# Source Links — wire-paper-identity-gate-rejection

> Per CLAUDE.md §14.3 (touch-to-promote). Legacy docs / code consulted and what was extracted into the new `paper-identity-status` capability spec.

## Consulted legacy sources

- **`docs/plans/2026-06-16-dirty-data-gap-closure-portfolio.md` (W0b card, §0.2 root-cause E1)** — extracted the E1 gap framing; the card's original premise (that `apply_identity_gate_reevaluation` is the target) was **corrected** during refinement (it conflated three mechanisms — see change-log). The portfolio W0b card is updated to the Gap B definition (task 7.4).
- **Root-cause investigation 2026-06-16 (prof→paper dirty data, lanes 1–4)** — established: LLM gate writes only `professor_paper_link.link_status`, never `paper.identity_status`; `identity_status` is set by identifier resolution + dedup; Milvus `_is_indexable_paper` already excludes `rejected`/`merged`; the ~7,297 `unverified` is an identifier-resolution (source-gap) issue, not an identity-gate issue.
- **`docs/solutions/data-quality/name-identity-gate-round-7-17-2026-04-18.md`** — extracted the flag-separation lesson (one miscalibrated gate must not null a whole column irreversibly; split the flags) and the precision-first, fail-safe-to-reject principle. Confirms W0b's risk profile is lower than the professor name-gate (reversible status vs irreversible column overwrite).
- **`scripts/run_name_identity_scan.py`** — extracted the dry-run-default / `--apply` / JSONL / `_ScanStats` scan pattern to mirror.
- **`professor/name_identity_gate.py`** + **`professor/canonical_writer.py:920-967`** — extracted the script-side flag pattern (`NAME_IDENTITY_GATE_ENABLED`) and on-reject behavior (null field) as the contrast W0b deliberately avoids (status transition only).

## Code anchors extracted into the design

- `professor/paper_identity_gate.py::batch_verify_paper_identity` — the reused LLM gate (threshold 0.8, fail-safe-to-reject, ORCID shortcut). Unchanged by this change.
- `scripts/run_identity_verify_candidate_links.py` — the decision flow reused (writes `professor_paper_link.link_status`); W0b adds the row-level `identity_status` consequence.
- `scripts/run_paper_title_enrichment_backfill.py:1085-1106` (`_reject_implausible_paper`) — extracted the `prof_page_only` guard pattern mirrored by `decide_identity_status_rejection`.
- `paper/milvus_backfill.py:178-181` (`_is_indexable_paper`) — the retrieval-eligibility filter the rejection transition leverages (unchanged).
- `alembic/versions/V020_add_identity_status_paper_patent.py` — the `identity_status` column + allowed values reused (no migration).

## What was NOT migrated
- `apply_identity_gate_reevaluation` (`paper/quality_promotion.py:212-238`) is explicitly out of scope (dead `quality_status` path, Gap A). Not promoted into the capability spec.

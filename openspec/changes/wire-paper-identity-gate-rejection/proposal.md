## Why

Paper rows whose **every** professor attribution is rejected by the LLM same-person gate still reach retrieval, because `paper.identity_status` is never set from the gate — the gate only writes `professor_paper_link.link_status`. So wrong-attribution papers (same-name, not same-person) remain indexed in Milvus and surface to users. This is root-cause **E1** from the professor→paper dirty-data investigation (2026-06-16): the LLM verdict is computed but never promoted to the row-level status that retrieval honors. Closing it removes the dominant "dirty data that looks clean" leakage on the professor→paper route and gives operators a reversible, evidence-backed lever to remove wrong-attribution papers from search.

This change is **behavior-affecting** (changes which paper rows are eligible for retrieval). The behavior contract is owned by the new capability `paper-identity-status`.

## What Changes

- **NEW behavior**: when the LLM same-person gate (`professor/paper_identity_gate.batch_verify_paper_identity`, run via `run_identity_verify_candidate_links.py`) rejects a `professor_paper_link`, **and** the paper then has **no remaining `verified` links** **and** `canonical_source='prof_page_only'`, the paper's `identity_status` transitions to `rejected`. The existing `paper/milvus_backfill._is_indexable_paper` filter already excludes `identity_status in {rejected, merged}`, so such rows drop out of retrieval with no Milvus code change.
- **NEW script** `scripts/run_paper_identity_scan.py`, mirroring `scripts/run_name_identity_scan.py`: dry-run by default, `--apply` to write, JSONL per-row decisions, and `_ScanStats`-style counts (`examined / rejected / unchanged / flipped_back`).
- **NEW independent env flag** `PAPER_IDENTITY_GATE_ENABLED`, read in the **script** (not the module), separate from `NAME_IDENTITY_GATE_ENABLED` and the professor `paper_collector` `identity_gate_enabled` — operators can kill this gate alone without losing other protection (lesson from `name-identity-gate-round-7-17`).
- **Reversibility**: a re-scan after a `verified` link is restored flips `identity_status` back to its prior value. The rejection path sets `identity_status` only; it **does not** terminalize `quality_status` (reject → `needs_review`-style human queue, not auto-delete).
- **Non-destructive**: status transitions only; no irreversible column overwrite (contrast with the professor name-gate footgun of nulling `canonical_name_en` via `ON CONFLICT DO UPDATE`).

## Capabilities

### New Capabilities
- `paper-identity-status`: the lifecycle of `paper.identity_status` transitions and their effect on retrieval eligibility (Milvus). Baselines the existing identifier-resolution/dedup-driven transitions (`unverified` default; `confirmed` via DOI/arXiv/OpenAlex resolution; `merged`/`rejected` via prof-page-only dedup) and adds the new LLM-same-person-gate-driven rejection transition.

### Modified Capabilities
<!-- none — no existing spec's requirements change -->

## Impact

- **Affected code**: new `apps/miroflow-agent/scripts/run_paper_identity_scan.py`; a rejection writer guarded by "no remaining verified links AND `canonical_source='prof_page_only'`" (mirrors `_reject_implausible_paper` at `scripts/run_paper_title_enrichment_backfill.py:1085-1106`); env flag wiring. Reuses the existing LLM gate `professor/paper_identity_gate.batch_verify_paper_identity` and the `run_identity_verify_candidate_links.py` decision flow; does **not** modify the gate itself.
- **Retrieval**: `paper/milvus_backfill._is_indexable_paper` is **unchanged** (already honors `identity_status in {rejected, merged}`); the effect is that more rows are *correctly* excluded. Requires a Milvus re-backfill for the change to take effect on already-indexed rows.
- **Storage**: V020 `paper.identity_status` column — **no migration** (existing column, existing allowed values `{confirmed, unverified, rejected, merged}`).
- **Evidence/provenance**: each rejection carries the gate decision (confidence, reasoning, source spans) recorded in scan JSONL and (on `--apply`) a `pipeline_issue` row; `run_id` traceability preserved.
- **No public API change**; serialized formats unchanged; classifier A–G semantics and `_VALID_DOMAINS` untouched.

## Non-goals

- Does **not** touch `apply_identity_gate_reevaluation` (paper/quality_promotion.py:212-238) — that dead `quality_status`-path function is a separate cleanup (Gap A).
- Does **not** promote the ~7,297 `unverified` rows — those lack a resolved identifier (DOI/arXiv/OpenAlex) and are a source-gap / `doi_verify` problem, re-routed to W0a/W2a of the portfolio plan.
- Does **not** auto-merge title+year-only duplicate groups or change dedup anchors.
- Does **not** change the LLM gate's threshold (0.8) or its fail-safe-to-reject semantics.

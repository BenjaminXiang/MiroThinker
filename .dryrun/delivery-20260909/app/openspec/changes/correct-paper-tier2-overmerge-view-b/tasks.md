# Tasks: correct-paper-tier2-overmerge-view-b

## 0. Verification contract (§14.7)
- [x] 0.1 `.agents/runs/correct-paper-tier2-overmerge-view-b/verification-contract.md` —
      deterministic SQL/storage; RED = fake-conn unit tests for `flip_paper_canonical` + the Tier-3
      candidate-SQL exclusion; GREEN = unit tests pass + operational dry-run/apply #1 + retrieval
      spot-check. Full Superpowers TDD allowed (deterministic).

## 1. Flip primitive + script + tests (Codex)
- [x] 1.1 EDIT `src/data_agents/paper/dedup_merge.py`: add
      `flip_paper_canonical(conn, *, old_canonical, new_canonical, run_id, *, merge_reason=…,
      evidence_source=…) -> dict` per spec (alias reverse → promote journal / demote conf →
      un-reject journal link / reject conf link; idempotent detect-and-skip; reuses
      `upsert_paper_merge_alias` / `require_real_run_id`).
- [x] 1.2 NEW `scripts/run_paper_overmerge_flip.py`: mirror `run_paper_exact_title_dedup`
      conventions; stricter `--confirm-real-db` gate (block ANY `miroflow_real` access without it,
      per `run_merge_duplicate_professors.py:202-208`); `--group` repeatable; `--dry-run` prints the
      4-step plan + link disposition; `--apply` calls `flip_paper_canonical` + `backfill_paper_chunks(
      paper_ids=[C,J])`; `run_id` via `open_pipeline_run` / `close_pipeline_run`.
- [x] 1.3 NEW `tests/scripts/test_run_paper_overmerge_flip.py` (fake-conn): alias reversed;
      journal link un-rejected with clean evidence (no migration suffix); conf link rejected;
      status swapped; idempotent no-op; contaminated suffix lands on the rejected conf link.

## 2. Tier-3 criterion (Codex)
- [x] 2.1 EDIT `scripts/run_paper_exact_title_dedup.py` candidate SQL: add the DOI-conflict
      exclusion (≥2 distinct publisher DOIs → exclude; whitelist `10.48550/arxiv.`, `10.2139/ssrn.`,
      `10.5194/egusphere-` preprint prefixes).

## 3. Operational apply #1 (Claude, localhost DB)
- [x] 3.1 `--dry-run --group PAPER-3E13FAE7D789`: print plan + link disposition; user confirms.
      (Dry-run clean: `false_action_count=0`; plan + link disposition match the spec.)
- [x] 3.2 Apply: flip #1 via `flip_paper_canonical` directly (DB flip only — Milvus refresh
      unnecessary; J's chunks present from pre-merge indexing). Recorded `evidence.md`.
- [x] 3.3 Retrieval spot-check: online `/api/chat` → J (`PAPER-64D7A39FC25B`) returned (A_paper_profile,
      ×3); C absent; J indexable=True, C indexable=False.

## 4. #7 review + governance (Claude)
- [x] 4.1 #7: DB abstracts for NYAS 2007 vs CTO 2008 are near-identical (same content + 5 authors) →
      same review article published twice → current merge is correct View-B; **no flip**. Recorded in
      `acceptance.md`.
- [x] 4.2 #13 deferral rationale recorded (no retrieval impact; journal not ready; no abstract).
- [x] 4.3 `openspec validate correct-paper-tier2-overmerge-view-b --strict` exits 0.
- [x] 4.4 Ledger: in-implementation → in-verification.

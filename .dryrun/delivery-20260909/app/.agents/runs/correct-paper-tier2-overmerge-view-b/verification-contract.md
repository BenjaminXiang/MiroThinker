# Verification Contract — correct-paper-tier2-overmerge-view-b

Per CLAUDE.md §14.7. Created BEFORE production-code edits.

## Classification
- Behavior-affecting: YES (narrows the Tier-2 candidate criterion; mutates `paper` /
  `paper_merge_alias` / `professor_paper_link` for group #1).
- Weight: Standard (bounded — 1 group flip + 1 candidate-SQL clause).
- Module class: deterministic SQL / storage adapter / tool wrapper — full Superpowers TDD ALLOWED.

## RED artifact (the oracle)
Fake-conn unit tests (`tests/scripts/test_run_paper_overmerge_flip.py`):
- flip reverses the alias (journal→conf deleted, conf→journal written);
- journal link un-rejected with clean evidence (`match_reason` has no migration suffix);
- conf link rejected; the conf's migrated `; exact_title_dedup:<journal>` suffix lands on the
  rejected (hidden) row, NOT on the visible journal link;
- paper status swapped (journal `confirmed/ready`, conf `merged/rejected`);
- idempotent re-run = no-op (zero counts);
- Tier-3 candidate-SQL exclusion: a DOI-conflict group is absent from candidates; a
  preprint↔published group is present.

## GREEN
All RED unit tests pass + `ruff check` / `ruff format` clean + the operational dry-run prints the
#1 plan + apply #1 produces the documented post-state + retrieval spot-check (journal rank 0, conf
absent).

## Allowed Superpowers mode
Full TDD (deterministic storage adapter / tool wrapper). No eval-first requirement — this is NOT
agentic/RAG/routing/prompt/policy work.

## Operational boundary (Claude-owned, NOT Codex)
- localhost `miroflow_real` dry-run / apply, Milvus refresh (`backfill_paper_chunks`), retrieval
  spot-check.
- Proxy vars unset for localhost; `--confirm-real-db` required for any `miroflow_real` access.
- #7 abstract fetch + human decision; #13 deferral documentation.

# Verification Contract — merge-paper-exact-title-duplicates

> CLAUDE.md §14.7. Created before handing behavior-affecting implementation to Codex.

## Change
- **change-id:** `merge-paper-exact-title-duplicates`
- **capability:** `paper-dedup` (new)
- **weight:** Standard (CLAUDE.md §8)
- **type:** Behavior-affecting — data-mutation backfill (merges 2,135 paper rows → 804 canonicals; mutates `paper.identity_status` / `paper.quality_status` / `paper_merge_alias` / `professor_paper_link`).
- **determinism:** Fully deterministic. No LLM in the merge path. Candidate selection = SQL (exact case-insensitive title + single author list). Canonical pick = deterministic ranking (identifier-bearing > richest fields > lowest `paper_id`). Merge = 4-step SQL reusing proven Stage-A primitives. The only empirical/oracle surface is the pilot adversarial title-match (false-merge guard).

## Classification
Deterministic data-mutation backfill reusing existing storage primitives (`upsert_paper_merge_alias`, `professor_paper_link` upsert, `paper` UPDATE). NOT agentic RAG/chat/routing/prompt/policy — no eval-first requirement. Falls under §14.7: "Deterministic modules, storage adapters, tool wrappers may use full Superpowers TDD when RED = unit/contract tests."

## RED artifact (what must fail first)
1. **Unit tests** — fake/mock connection, NO real DB. Pattern: `tests/scripts/test_run_paper_title_enrichment_backfill.py` (`FakeConnection`/`FakeCursor` dispatching on SQL prefixes + recording `statements`/`commits`/`rollbacks`; script imported via `importlib.util.spec_from_file_location` so privates are testable; rows built by plain `_row()` dict-builders, no factories).
   - **canonical pick**: identifier-bearing member wins; tie-break richest-fields (abstract/summary_zh/venue/year populated count); final tie-break lowest `paper_id`.
   - **link-migration-before-reject ORDER**: for each non-canonical member, `INSERT INTO professor_paper_link … ON CONFLICT (professor_id, paper_id)` (migrate) statements precede `UPDATE professor_paper_link SET link_status='rejected' …` for the same `old_paper_id` (no attribution loss).
   - **idempotent re-run**: a second run over an already-merged group is a no-op — candidate SQL excludes `identity_status in ('rejected','merged')`; `uq_paper_merge_alias_old_paper` ON CONFLICT; `link_status != 'rejected'` guard on the reject UPDATE.
   - **merged row excluded from candidate SQL**: a row already `identity_status='merged'` is not re-selected as a candidate.
2. **Pilot adversarial title-match** (operational, gated): for the `--limit 50` sample, every member title vs canonical title similarity ≥ 0.99; **0 false-merges or STOP**. Saved to `.agents/runs/merge-paper-exact-title-duplicates/pilot.jsonl`.

## GREEN (definition of done)
- Unit tests above pass (fake-conn layer).
- Pilot dry-run `--limit 50`: 0 false-merges; report saved to `pilot.jsonl`.
- Full `--apply` over all 804 groups: `paper_merge_alias` rows written + links migrated + **0 ready degraded** (no `quality_status='ready'` row moves to non-ready as a side effect); exact counts recorded.
- Retrieval spot-check (task 3.2): for sampled merged groups, the canonical carries all migrated professor links; merged rows excluded from `_is_indexable_paper` (`identity_status='merged'`).
- `openspec validate merge-paper-exact-title-duplicates --strict` exits 0.

## Allowed Superpowers mode
Full Superpowers TDD (RED→GREEN→REFACTOR) is permitted for the script + helper + unit tests (tasks 1.1–1.3), because RED = unit/contract tests on a deterministic module. NOT permitted: TDD choosing its own RED artifact independently — the RED is fixed above (§14.7 / CLAUDE.md §11). The operational apply (tasks 2.1, 3.1, 3.2) is NOT TDD — it is gated execution with empirical spot-checks, run by Claude against the local DB.

## Invariants preserved (do not weaken)
- **Attribution / evidence shape**: migrate links BEFORE reject; on upsert preserve `link_status`/evidence columns/`evidence_page_id`; carry `run_id`.
- **`upsert_paper_merge_alias` idempotency** via `uq_paper_merge_alias_old_paper`.
- **`_is_indexable_paper` filter unchanged** (`identity_status not in {rejected,merged}` AND `quality_status=='ready'`); merged rows auto-excluded — no Milvus re-index needed for the merged members (canonical, if ready, already indexed).
- No change to: `quality_status` enum, A–G classification, `_VALID_DOMAINS`, evidence shape, any serialized public format, Alembic history.
- **Reversible**: `paper_merge_alias` allows un-merge (clear alias + un-reject links + restore `identity_status`).

## Reconciliation notes (resolved — NOT in the change docs)
- `merge_reason='exact_title_dedup'`, `evidence_source='exact_title+author_list'` (design.md §3 / spec.md).
- `rejected_reason='merged_into_canonical:<canonical_paper_id>'` (spec.md line 29 + design.md §3) — NOT Stage-A's legacy `merged_into_resolved_paper:` prefix.
- The extracted helper `merge_paper_into_canonical` MUST **drop** the Stage-A `_mark_page_only_merged` guard `canonical_source='prof_page_only'` — Tier-2 merges members of all `canonical_source` values.
- Identifier columns on `paper` used for "identifier-bearing" canonical pick: `doi`, `arxiv_id`, `openalex_id`, `semantic_scholar_id`.
- `upsert_paper_merge_alias` takes a **dataclass** `PaperMergeAliasInput(old_paper_id, canonical_paper_id, merge_reason, evidence_source=None, run_id=None)` — not loose kwargs. Module not re-exported from `storage/postgres/__init__.py`; import the module directly.

## Primitives & paths (grounded 2026-06-29)
- `upsert_paper_merge_alias` + `resolve_canonical_paper_id` — `src/data_agents/storage/postgres/paper_merge_alias.py`.
- Stage-A inlined pattern (lift source for the helper) — `scripts/run_paper_title_enrichment_backfill.py:502-533` (orchestration) + privates `:909-1057`.
- `open_pipeline_run` / `close_pipeline_run` / `require_real_run_id` / `DRY_RUN_SENTINEL_RUN_ID` — `src/data_agents/storage/postgres/pipeline_run.py` (`:51`,`:85`,`:38`,`:35`). `run_kind="backfill_real"`.
- `_is_indexable_paper` — `src/data_agents/paper/milvus_backfill.py:178-181`. Alias-exclusion SQL pattern — `src/data_agents/paper/source_gap_audit.py:215-218`.
- Candidate SQL (grounded: 804 groups / 2,135 rows) — `design.md §1`.
- DB conn: `resolve_dsn` from `src/data_agents/storage/postgres/connection.py` + `psycopg.rows.dict_row`.
- Test template — `tests/scripts/test_run_paper_title_enrichment_backfill.py`; merge-alias unit tests — `tests/storage/test_paper_merge_alias_storage.py`.

## Out of scope
Tier 3 (7,923 divergent-author groups → `duplicate-paper-review-workflow`); enum / `_is_indexable_paper` change; re-resolution; A–G; `_VALID_DOMAINS`; evidence shape.

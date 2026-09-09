# Handoff: merge-paper-exact-title-duplicates (Tier-2 paper dedup script)

- **change-id:** `merge-paper-exact-title-duplicates` (OpenSpec, spec-driven, Standard weight, status `proposed`)
- **verification-contract:** `.agents/runs/merge-paper-exact-title-duplicates/verification-contract.md` — READ FIRST; it fixes the RED/GREEN and the allowed Superpowers mode.
- **source docs:** `openspec/changes/merge-paper-exact-title-duplicates/{proposal,design,specs/paper-dedup/spec,tasks}.md`
- **slice scope:** tasks 1.1, 1.2, 1.3 ONLY (script + shared helper + unit tests). Operational pilot/apply (tasks 2.x, 3.x) are Claude-owned — do NOT run them.
- **Codex role:** production-code builder. Claude designs/reviews.

## What to build

### 1.1 — NEW `apps/miroflow-agent/scripts/run_paper_exact_title_dedup.py`
Tier-2 paper dedup backfill. For each candidate group (exact case-insensitive title + single author list, not rejected/merged), pick a canonical and merge every other member into it.

- **Candidate SQL** — exactly `design.md §1` (grounded 2026-06-29: 804 groups, 2,135 rows; sizes {2:326, 3:431, 4:46, 6:1}; 725/804 identifier-bearing). Re-run must be a no-op because the SQL excludes `identity_status in ('rejected','merged')`.
- **Canonical pick** (deterministic, `design.md §2`): member with a non-null identifier (`doi`/`arxiv_id`/`openalex_id`/`semantic_scholar_id`) > most-populated fields (`abstract_clean`/`summary_zh`/`venue`/`year`) > lowest `paper_id`.
- **Per non-canonical member** — call the new helper `merge_paper_into_canonical(...)` (task 1.2); strict order migrate→alias→reject→mark, each in its own step, commit per group (mirror Stage-A `_process_rows:502-533`).
- **CLI** (match `run_paper_title_enrichment_backfill.py` conventions, adapted per `tasks.md §1.1`):
  - `--dry-run` (default, no writes) / `--apply` (wet) / `--confirm-real-db` (borrow from `scripts/run_merge_duplicate_professors.py:83-84`, required to gate `--apply` against the real DB).
  - `--limit N` (cap groups; used by the pilot `--limit 50`).
  - `--json-output` → `print(json.dumps(report, ensure_ascii=False, default=str))` to stdout (machine-readable); else human-readable summary.
  - `run_id` via `open_pipeline_run(conn, run_kind="backfill_real", run_scope={...}, triggered_by=...)` on wet run; dry-run uses the sentinel `f"dry-run-{uuid4()}"` (do NOT call `open_pipeline_run` in dry-run). `require_real_run_id(run_id, writer_name=...)` after opening.
  - On exit: `close_pipeline_run(conn, run_id, status=..., items_processed=..., items_failed=...)` + `conn.commit()`; on exception: rollback + `close_pipeline_run(status="failed", error_summary={"message": str(exc)})`.
  - **Adversarial title-match** (pilot gate): in dry-run, for every group compute each member title vs canonical title similarity; report any with sim < 0.99 as a `false_merge_risk` entry. Use a simple deterministic similarity (e.g. normalized Levenshtein ratio or token-sort cosine — pick one, document it); STOP signal = `report["false_merge_count"] > 0`.
  - DB conn: `resolve_dsn` from `src.data_agents.storage.postgres.connection` + `psycopg.rows.dict_row`; `_APP_ROOT = Path(__file__).resolve().parents[1]`; `load_dotenv(_APP_ROOT / ".env")`; `sys.path.insert(0, str(_APP_ROOT))` before `src.*` imports.
- **report dict** fields: `groups_total`, `rows_total`, `groups_processed`, `members_merged`, `links_migrated`, `merge_aliases_written`, `old_links_rejected`, `ready_degraded` (MUST be 0), `false_merge_count`, `false_merge_risk` (list), `run_id`, `mode` (dry-run/apply).

### 1.2 — NEW `apps/miroflow-agent/src/data_agents/paper/dedup_merge.py`
Shared helper — **extract** the Stage-A inlined pattern (it is NOT reusable today; the Stage-A privates are scoped to `canonical_source='prof_page_only'`).

```python
def merge_paper_into_canonical(conn, *, old_paper_id, canonical_paper_id, run_id, *,
                               merge_reason="exact_title_dedup",
                               evidence_source="exact_title+author_list",
                               rejected_reason_prefix="merged_into_canonical") -> dict:
    """Migrate old member's professor_paper_links onto canonical, write merge_alias,
    reject old links, mark old merged. Returns per-member counts."""
```
- Lift the 4 steps from `scripts/run_paper_title_enrichment_backfill.py:909-1057` (`_upsert_migrated_link`, `_write_merge_alias`, `_reject_old_links`, `_mark_page_only_merged`).
- **CRITICAL reconciliation (do NOT copy blindly):**
  - **Drop** the `_mark_page_only_merged` guard `WHERE canonical_source = 'prof_page_only'` — Tier-2 merges members of ALL `canonical_source` values. The mark-merged UPDATE must be `WHERE paper_id = old AND paper_id != canonical` (no `canonical_source` filter).
  - `rejected_reason` = `f"{rejected_reason_prefix}:{canonical_paper_id}"` → `merged_into_canonical:<canonical>` (NOT Stage-A's `merged_into_resolved_paper:`).
  - `_write_merge_alias` calls `upsert_paper_merge_alias(conn, PaperMergeAliasInput(old_paper_id=..., canonical_paper_id=..., merge_reason=merge_reason, evidence_source=evidence_source, run_id=require_real_run_id(run_id, writer_name="merge_paper_into_canonical")))`. `PaperMergeAliasInput` is the frozen dataclass from `src.data_agents.storage.postgres.paper_merge_alias`; the module is NOT re-exported from `storage/postgres/__init__.py` — import the module directly.
  - `_upsert_migrated_link`: upsert each `professor_paper_link` onto canonical with `ON CONFLICT (professor_id, paper_id) DO UPDATE` preserving `link_status`/evidence columns/`evidence_page_id`, set `rejected_at=NULL, rejected_reason=NULL`, `run_id=COALESCE(EXCLUDED.run_id, professor_paper_link.run_id)`. Use `verified_by='rule_auto'`, `verified_at=datetime.now(UTC)`. Match-reason suffix `f"; exact_title_dedup:{old_paper_id}"`.
  - **Order is load-bearing**: migrate → alias → reject → mark (migrate BEFORE reject, or attribution is lost). Do NOT reorder.
  - Idempotency is free via `uq_paper_merge_alias_old_paper` (ON CONFLICT) + `link_status != 'rejected'` guard on the reject UPDATE + candidate SQL exclusion.

### 1.3 — Unit tests (fake-conn layer; pattern `tests/scripts/test_run_paper_title_enrichment_backfill.py`)
- Import the script via `importlib.util.spec_from_file_location` so privates are testable; build rows with plain `_row()` dict-builders (no factories, no real DB).
- Cases (RED per verification-contract):
  - canonical pick: identifier-bearing wins over richer-but-no-id; tie-break richest-fields; final tie-break lowest `paper_id`.
  - migrate-before-reject ORDER: assert `INSERT INTO professor_paper_link …` statements for `old_paper_id` precede `UPDATE professor_paper_link … rejected …` for the same id.
  - idempotent re-run: second `merge_paper_into_canonical` call is a no-op (alias ON CONFLICT; reject UPDATE affects 0 rows after first run).
  - merged row excluded from candidate SQL: a row pre-set `identity_status='merged'` is absent from candidate output.
- Also add an integration test ONLY if trivial via `tests/postgres/conftest.py` `pg_conn` (per-test BEGIN/rollback, refuses `miroflow_real`) — optional; the fake-conn layer is the required RED.

## Do-not rules
- Do NOT run the operational pilot/apply (tasks 2.x/3.x) — Claude owns localhost DB execution.
- Do NOT change `quality_status` enum, `_is_indexable_paper`, A–G, `_VALID_DOMAINS`, evidence shape, any serialized format, or Alembic history.
- Do NOT add an LLM/semantic step to the merge path — deterministic only. The adversarial title-match similarity is a simple string metric, not an LLM call.
- Do NOT weaken attribution: migrate before reject; preserve evidence on upsert.
- Do NOT modify `run_paper_title_enrichment_backfill.py` to extract — COPY the pattern into the new helper; leave Stage-A intact (its `prof_page_only` scoping is correct for its purpose).
- Keep changes scoped to the two NEW files + the NEW test file. No edits to existing production modules except reading their public API.

## Checks to run (report output)
```bash
cd apps/miroflow-agent
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
uv run ruff check scripts/run_paper_exact_title_dedup.py src/data_agents/paper/dedup_merge.py tests/scripts/test_run_paper_exact_title_dedup.py
uv run ruff format scripts/run_paper_exact_title_dedup.py src/data_agents/paper/dedup_merge.py tests/scripts/test_run_paper_exact_title_dedup.py
uv run pytest tests/scripts/test_run_paper_exact_title_dedup.py tests/storage/test_paper_merge_alias_storage.py -n0
```
(Localhost proxy vars MUST be unset or loopback is hijacked — project memory.)

## Done criteria
- All RED unit tests pass (fake-conn layer); `ruff check`/`format` clean.
- `--dry-run --limit 50` runs WITHOUT writes and emits the report dict including `false_merge_count` (Claude will run the real pilot against the local DB; Codex only needs the dry-run path to be wired and unit-tested).
- Idempotent re-run verified by test.
- No production module edited except the two NEW files + NEW test file.

## Report back
- Files created (paths) + line counts.
- `ruff` + `pytest` output (pass/fail counts).
- The chosen adversarial-similarity metric + why.
- Any deviation from this handoff (with reason).

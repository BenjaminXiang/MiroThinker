# Handoff: correct-paper-tier2-overmerge-view-b (Codex build slice)

- **change-id:** `correct-paper-tier2-overmerge-view-b` (OpenSpec Lite, spec-driven, Standard, status `in-implementation`)
- **verification-contract:** `.agents/runs/correct-paper-tier2-overmerge-view-b/verification-contract.md` — READ FIRST (RED/GREEN + allowed Superpowers mode).
- **source docs:** `openspec/changes/correct-paper-tier2-overmerge-view-b/{proposal,specs/paper-dedup/spec,tasks,acceptance}.md`
- **slice scope:** tasks 1.1, 1.2, 1.3, 2.1 ONLY (flip helper + flip script + unit tests + Tier-3 candidate-SQL clause). Operational dry-run/apply (#1), Milvus refresh, retrieval spot-check, #7 review, governance (tasks 3.x, 4.x) are Claude-owned — do NOT run them.
- **Codex role:** production-code builder. Claude designs/reviews.

## Context (grounded 2026-06-30 against `miroflow_real`)

`merge-paper-exact-title-duplicates` (applied 2026-06-29) auto-merged 921 exact-title + identical-author-list
groups. Post-acceptance audit: 7 are conference↔journal over-merges (two distinct publications sharing
exact title + authors, different DOIs). User decision: **View B** — keep the **journal** version as
the visible canonical, hide the conference version. DB re-scan narrows the work to **1 flip
(group #1)** + a **prospective Tier-3 criterion** (DOI-conflict groups excluded from future Tier-2).

Group #1: conference canonical `PAPER-3E13FAE7D789` (LNCS 2019, `confirmed/ready`, retrievable) ↔
journal `PAPER-64D7A39FC25B` (JLAMP 2021, `merged/rejected`, hidden, has arXiv 1805.10073). Prof
`PROF-ADE0D71E527F` is the only linked professor; its 2 link rows are:
- `prof→PAPER-3E13FAE7D789` (C, canonical): `link_status='verified'`,
  `match_reason='homepage_title_resolution; exact_title_dedup:PAPER-64D7A39FC25B'` (J's evidence
  migrated onto C — the "contaminated" side).
- `prof→PAPER-64D7A39FC25B` (J, merged): `link_status='rejected'`,
  `match_reason='homepage_title_resolution'` (J's OWN clean evidence, intact, just rejected).

So the flip is mechanically clean: un-reject J's link (clean evidence surfaces), reject C's link
(contamination becomes invisible on the hidden C). **No attribution loss.**

## What to build

### 1.1 — EDIT `apps/miroflow-agent/src/data_agents/paper/dedup_merge.py`

Add `flip_paper_canonical` next to the existing `merge_paper_into_canonical`. Reuse the module's
existing imports (`upsert_paper_merge_alias`, `PaperMergeAliasInput`, `require_real_run_id`) and
helpers (`_required_str`, `_optional_str`).

```python
def flip_paper_canonical(
    conn: Any,
    *,
    old_canonical: str,           # the conference paper to DEMOTE (currently canonical)
    new_canonical: str,           # the journal paper to PROMOTE (currently merged)
    run_id: UUID | str,
    merge_reason: str = "exact_title_dedup_canonical_correction",
    evidence_source: str = "conf_journal_extension_view_b",
) -> dict[str, int]:
    """Reverse a conf↔journal Tier-2 over-merge: promote the journal, demote the conference.

    Idempotent: if alias old_canonical→new_canonical already exists AND old_canonical is already
    'merged', return zero counts. Otherwise, in order: reverse alias, promote/demote papers,
    un-reject journal link, reject conference link. Returns per-step counts.
    """
```

Steps (each a simple `conn.execute`; commit is the SCRIPT's responsibility, not the helper's —
mirror `merge_paper_into_canonical` which does not commit):
1. **Idempotency check**: fetch `old_canonical` paper; if `identity_status='merged'` AND an alias
   `old_canonical→new_canonical` exists → return `_empty_flip_counts()`.
2. **Alias reverse**:
   - `DELETE FROM paper_merge_alias WHERE old_paper_id=%s AND canonical_paper_id=%s AND merge_reason='exact_title_dedup'` (old=J=`new_canonical`, canonical=C=`old_canonical`) — remove the wrong-direction alias.
   - `upsert_paper_merge_alias(conn, PaperMergeAliasInput(old_paper_id=old_canonical, canonical_paper_id=new_canonical, merge_reason=merge_reason, evidence_source=evidence_source, run_id=require_real_run_id(run_id, writer_name="flip_paper_canonical")))` (idempotent via `uq_paper_merge_alias_old_paper`).
3. **Paper status**:
   - `UPDATE paper SET identity_status='confirmed', quality_status='ready', run_id=%s, updated_at=now() WHERE paper_id=%s` (promote J=`new_canonical`).
   - `UPDATE paper SET identity_status='merged', quality_status='rejected', run_id=%s, updated_at=now() WHERE paper_id=%s` (demote C=`old_canonical`).
4. **Links**:
   - `UPDATE professor_paper_link SET link_status='verified', rejected_at=NULL, rejected_reason=NULL, run_id=%s, updated_at=now() WHERE paper_id=%s AND link_status='rejected'` (un-reject J's links — `paper_id=new_canonical`). Capture rowcount as `links_restored`.
   - `UPDATE professor_paper_link SET link_status='rejected', rejected_at=now(), rejected_reason=%s, run_id=%s, updated_at=now() WHERE paper_id=%s AND link_status!='rejected'` with `rejected_reason=f"merged_into_canonical:{new_canonical}"` (reject C's links — `paper_id=old_canonical`). Capture rowcount as `links_rejected`.

Return `{"aliases_deleted", "aliases_written", "papers_promoted", "papers_demoted", "links_restored", "links_rejected"}`. Validate both ids are non-empty distinct strings (reuse `_required_str`; raise `ValueError` if equal, like `merge_paper_into_canonical` does).

### 1.2 — NEW `apps/miroflow-agent/scripts/run_paper_overmerge_flip.py`

Mirror `scripts/run_paper_exact_title_dedup.py` conventions (read it first):
- `_APP_ROOT = Path(__file__).resolve().parents[1]`; `load_dotenv(_APP_ROOT / ".env")`; `sys.path.insert(0, str(_APP_ROOT))` before `src.*` imports (lines 16-19).
- DB: `resolve_dsn` from `src.data_agents.storage.postgres.connection` + `psycopg.rows.dict_row` (lines 22, 73-74).
- CLI: mutex `--dry-run`/`--apply` (dest="mode"); `--confirm-real-db` (store_true); `--group` (**repeatable**, `action="append"`, the conference canonical paper_id to demote); `--json-output` (store_true); `--database-url`.
- **Stricter gate** (from `run_merge_duplicate_professors.py:202-208`): block ANY `miroflow_real` access without `--confirm-real-db` (this mutates real data — gate even dry-run). Use a `_REAL_DB_NAME` constant.
- `run_id`: dry-run → `f"dry-run-{uuid4()}"` (NO `open_pipeline_run`); apply → `open_pipeline_run(conn, run_kind="backfill_real", run_scope={"task":"paper_overmerge_flip","groups":args.group,"mode":args.mode}, triggered_by="paper_overmerge_flip")` → `require_real_run_id(run_id, writer_name="run_paper_overmerge_flip")` → `conn.commit()`; on success `close_pipeline_run(conn, run_id, status=..., items_processed=..., items_failed=...)` + `conn.commit()`; on exception rollback + `close_pipeline_run(status="failed", error_summary={"message": str(exc)})`. (Mirror lines 375-423.)

For each `--group <conf_paper_id>`: resolve the group via `paper_merge_alias` — find the alias where `canonical_paper_id = <conf>` and `merge_reason='exact_title_dedup'`; the `old_paper_id` of that alias is the journal `new_canonical`. (Exactly one such alias per group, per the DB state.) If none found, report and skip.

- **Dry-run**: for each group, print (and collect into the report dict) the 4-step plan + the exact `professor_paper_link` rows it will touch: `(professor_id, paper_id, current link_status → new link_status, match_reason)`. Emit `false_action_count=0` if every J link is currently `rejected` and every C link is currently non-`rejected` (the expected pre-flip state); else flag. No writes.
- **Apply**: call `flip_paper_canonical(conn, old_canonical=<conf>, new_canonical=<journal>, run_id=run_id)` per group; `conn.commit()` per group; then call `backfill_paper_chunks(conn, milvus_client, embedding_client, paper_ids=[<conf>, <journal>])` (from `src.data_agents.paper.milvus_backfill`) to refresh Milvus (it deletes conf chunks — merged — and indexes journal — ready — in one call; respects `_is_indexable_paper`). Construct `milvus_client` + `embedding_client` the same way `run_milvus_backfill.py` does (read that script for the exact construction; do not invent).
- **report dict** fields: `groups_total`, `groups_processed`, `aliases_deleted`, `aliases_written`, `papers_promoted`, `papers_demoted`, `links_restored`, `links_rejected`, `milvus_refreshed`, `false_action_count`, `run_id`, `mode`.

### 1.3 — NEW `apps/miroflow-agent/tests/scripts/test_run_paper_overmerge_flip.py`

Fake-conn layer (pattern: `tests/scripts/test_run_paper_title_enrichment_backfill.py` and the merge
change's `tests/scripts/test_run_paper_exact_title_dedup.py`). Import `dedup_merge` directly
(`from src.data_agents.paper.dedup_merge import flip_paper_canonical`) so the helper is unit-tested
without the script. Use a fake-conn that records executed SQL (statements + params) and serves
`fetchone`/`fetchall` from scripted rows. No real DB. Cases (RED per verification-contract):
- **alias reversed**: after flip, a `DELETE FROM paper_merge_alias … WHERE old=J AND canonical=C` precedes an upsert of `C→J`; assert both recorded.
- **J link un-rejected, clean evidence retained**: the `UPDATE … link_status='verified' … WHERE paper_id=J` is recorded; the J link row's `match_reason` is the unsuffixed `homepage_title_resolution` (unchanged — the UPDATE does not touch match_reason).
- **C link rejected, contaminated suffix stays on the hidden row**: the `UPDATE … link_status='rejected' … WHERE paper_id=C` is recorded; C's `match_reason` (with the `; exact_title_dedup:J` suffix) is NOT on the J link.
- **status swapped**: J `confirmed/ready`, C `merged/rejected` UPDATEs recorded.
- **idempotent no-op**: prime the fake-conn so `old_canonical` is already `merged` and alias `C→J` exists → `flip_paper_canonical` returns all-zero counts and records NO DELETE/UPDATE.
- **invalid args**: `old_canonical == new_canonical` raises `ValueError`.

### 2.1 — EDIT `apps/miroflow-agent/scripts/run_paper_exact_title_dedup.py` candidate SQL (lines 78-91)

Add the Tier-3 DOI-conflict exclusion to the `HAVING` clause. After the existing
`HAVING count(DISTINCT lower(coalesce(p.authors_display,''))) = 1`, add:

```sql
  AND count(DISTINCT nullif(p.doi,''))
    - count(DISTINCT CASE WHEN p.doi LIKE '10.48550/arxiv.%'
                           OR p.doi LIKE '10.2139/ssrn.%'
                           OR p.doi LIKE '10.5194/egusphere-%'
                          THEN nullif(p.doi,'') END) <= 1
```

Rationale (in a code comment): ≥2 distinct publisher DOIs = likely distinct publications (conf↔journal
extension) → route to Tier-3 review, not auto-merge; preprint DOIs (arxiv/ssrn/egusphere) are
whitelisted so legit preprint↔published pairs stay Tier-2. **Prospective only** — does not alter
already-merged groups.

## Do-not rules
- Do NOT run the operational pilot/apply/Milvus (#1) — Claude owns localhost DB execution.
- Do NOT change `quality_status` enum, `_is_indexable_paper`, A–G, `_VALID_DOMAINS`, evidence shape,
  any serialized format, or Alembic history.
- Do NOT add an LLM step — deterministic SQL only.
- Do NOT modify `run_paper_title_enrichment_backfill.py` or the existing `merge_paper_into_canonical`.
- Keep changes scoped to: EDIT `dedup_merge.py` (add fn only), NEW script, NEW test, EDIT candidate
  SQL clause. No other production-module edits.
- Do NOT construct the Milvus client ad hoc — copy the construction from `run_milvus_backfill.py`.

## Checks to run (report output)
```bash
cd apps/miroflow-agent
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
uv run ruff check scripts/run_paper_overmerge_flip.py src/data_agents/paper/dedup_merge.py tests/scripts/test_run_paper_overmerge_flip.py scripts/run_paper_exact_title_dedup.py
uv run ruff format scripts/run_paper_overmerge_flip.py src/data_agents/paper/dedup_merge.py tests/scripts/test_run_paper_overmerge_flip.py
uv run pytest tests/scripts/test_run_paper_overmerge_flip.py tests/scripts/test_run_paper_exact_title_dedup.py -n0
```
(Localhost proxy vars MUST be unset — project memory. The fake-conn tests need no network.)

## Done criteria
- All RED unit tests pass (fake-conn); `ruff check`/`format` clean; the existing
  `test_run_paper_exact_title_dedup.py` still passes (the SQL clause change must not break it).
- `--dry-run --group PAPER-3E13FAE7D789` runs WITHOUT writes and emits the report dict including
  the 4-step plan + link disposition (Claude runs the real dry-run; Codex only needs the path wired
  + unit-tested).
- Idempotent re-run verified by test.
- No production module edited except the additions above.

## Report back
- Files created/edited (paths) + line counts.
- `ruff` + `pytest` output (pass/fail counts).
- The exact Milvus client + embedding_client construction you copied (file:line).
- Any deviation from this handoff (with reason).

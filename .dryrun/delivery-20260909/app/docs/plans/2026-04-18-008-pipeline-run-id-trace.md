# Round 7.16 — Pipeline run_id trace (write-side provenance)

**Date:** 2026-04-18
**Status:** Planning (implementation deferred — large scope)
**Parent:** `docs/plans/2026-04-18-005-data-quality-guards-and-identity-gate.md` §§ "Round 7.16 deferred"

## 1. Problem

`pipeline_run` table exists (1 row today in `miroflow_real`) but NO other table records which run produced which row. Operators can't answer:

- "Which writes came from the 2026-04-18 run vs earlier?"
- "A batch looks corrupted — what rows must we revert?"
- "Round 7.17 name-gate just nulled 182 `canonical_name_en` values — what was the pre-nulling state we can restore if the gate mis-calibrates?"

Every data-quality retrospective so far (Rounds 7.6/7.8/7.9/7.10'/7.13/7.14/7.15/7.17) has had to reason about pollution without a run boundary. Adding `run_id` lets future rounds do precise rollbacks instead of full-table reprocess.

## 2. Scope

**In:**
- Migration V007 adds `run_id uuid REFERENCES pipeline_run(run_id) ON DELETE SET NULL` to:
  - `professor`
  - `professor_affiliation`
  - `professor_fact`
  - `professor_paper_link`
  - `paper`
  - `patent`
  - `source_page`
- Index on `run_id` for each table (for rollback queries).
- Backfill: generate one synthetic `pipeline_run` row labeled "pre-trace legacy" (status='succeeded', run_kind='legacy_backfill'), assign its run_id to every pre-existing row.
- Writers thread `run_id` through every insert / upsert path.
- Entrypoints (`pipeline_v3`, `run_real_e2e_professor_backfill`, etc.) create a new `pipeline_run` row at start, pass its `run_id` to all writers, close it at end.

**Out:**
- Read-side query API for "find all writes by run_id". Grep the table; don't build another endpoint yet.
- Automatic rollback tool. Reversal is a one-off ops action; build the query when needed.
- Run-level metrics table beyond what `pipeline_run` already has (`items_processed`, `items_failed`).

## 3. Design

### 3.1 Migration V007

```sql
-- Backfill row must exist first so we can set NOT NULL cleanly
INSERT INTO pipeline_run (run_id, run_kind, status, started_at, finished_at, triggered_by)
VALUES (
  '00000000-0000-0000-0000-000000000001'::uuid,
  'legacy_backfill',
  'succeeded',
  '2026-04-18 00:00:00+00',
  '2026-04-18 00:00:00+00',
  'round_7_16_migration'
) ON CONFLICT DO NOTHING;

-- One column per affected table; default + backfill + NOT NULL in three steps
-- (see plan §3.3 for the "safe under concurrent writes" order)
ALTER TABLE professor ADD COLUMN run_id uuid REFERENCES pipeline_run(run_id) ON DELETE SET NULL;
UPDATE professor SET run_id = '00000000-0000-0000-0000-000000000001' WHERE run_id IS NULL;
-- NOT NULL would break writes that haven't been wired yet — leave nullable until
-- Phase 2 confirms all writers pass run_id.
CREATE INDEX CONCURRENTLY idx_professor_run_id ON professor(run_id);

-- Repeat for professor_affiliation, professor_fact, professor_paper_link,
-- paper, patent, source_page.
```

### 3.2 Write-path wiring

Every writer gets a new `run_id: UUID | None = None` kwarg, added at the INSERT/UPSERT site:

```python
# canonical_writer._upsert_professor_row
def _upsert_professor_row(conn, *, professor_id, enriched, primary_page_id,
                         name_identity_gate=None, run_id: UUID | None = None) -> bool:
    ...
    conn.execute(
        "INSERT INTO professor (..., run_id) VALUES (..., %s)"
        "ON CONFLICT (professor_id) DO UPDATE SET ..., run_id = EXCLUDED.run_id",
        (..., run_id),
    )
```

Thread `run_id` through:
- `write_professor_bundle` (public entry) → `_upsert_professor_row`, `_upsert_affiliation`, `_upsert_fact`, `_upsert_professor_paper_link`.
- `paper/canonical_writer.upsert_paper` → paper row.
- Similar for patent, company.

Nullable column + `None` default keeps legacy callers working; new callers pass `run_id` explicitly.

### 3.3 Entrypoint wiring

`pipeline_v3.run_professor_pipeline_v3`:
```python
async def run_professor_pipeline_v3(config):
    run_id = uuid4()
    with psycopg.connect(...) as conn:
        conn.execute(
            "INSERT INTO pipeline_run (run_id, run_kind, started_at, triggered_by, run_scope) "
            "VALUES (%s, 'professor_v3', now(), %s, %s::jsonb)",
            (run_id, triggered_by, json.dumps({"seed_doc": str(config.seed_doc), "limit": config.limit})),
        )
    try:
        result = await _actual_work(config, run_id=run_id)
        _mark_run_succeeded(conn, run_id, result.report)
    except Exception as exc:
        _mark_run_failed(conn, run_id, exc)
        raise
```

Backfill script (`run_real_e2e_professor_backfill`) same pattern.

### 3.4 Safe migration order

Adding NOT NULL to 7 tables while writes happen = deadlock risk. Order:

1. Add nullable `run_id` column (no lock beyond brief metadata).
2. Backfill with legacy run_id via `UPDATE ... WHERE run_id IS NULL` in batches of 10k.
3. `CREATE INDEX CONCURRENTLY` on `run_id`.
4. Deploy code that passes `run_id` on all new writes.
5. (Optional, Phase 3) After code is fully deployed and no NULL writes in a week, `SET NOT NULL` in a separate migration.

Phase 5 is not part of this round.

## 4. TDD spec

- `tests/data_agents/professor/test_canonical_writer_run_id.py` — assert `run_id` gets written to every affected table.
- `tests/migrations/test_migration_v007.py` — assert legacy backfill row exists, all pre-existing rows have run_id.
- `tests/integration/test_pipeline_v3_run_id.py` — full pipeline run creates exactly one pipeline_run row, all produced rows carry that run_id.

## 5. Rollback path

`rollback_run.py` (not part of this round, but documented):
```python
def rollback_run(conn, run_id):
    """Roll back all writes from a given pipeline_run.

    Deletes from professor_paper_link, professor_fact, professor_affiliation,
    professor, paper, patent, source_page where run_id = $1.
    Does NOT delete from pipeline_run; that row stays as audit.
    """
```

## 6. Non-goals

- Transactional guarantees that one run = one DB transaction. A single run can span many transactions (e.g. per-professor savepoints). `run_id` is a tag, not a transaction boundary.
- Upstream source tracking (seed file hash, discovery URLs). That's `source_row_lineage` / `source_page`'s job; `run_id` only answers "which Python process produced this".

## 7. Estimated delta

| Artifact | Size |
|---|---|
| alembic/versions/V007_add_run_id_trace.py | ~100 LOC |
| scripts/backfill_run_id.py | ~50 LOC |
| canonical_writer.py changes | ~40 LOC (one param + 5 insert sites) |
| paper/canonical_writer.py changes | ~20 LOC |
| pipeline_v3.py entrypoint wiring | ~30 LOC |
| run_real_e2e_professor_backfill.py entrypoint wiring | ~15 LOC |
| tests | ~300 LOC |

Total ~555 LOC. Medium scope. Suitable for one focused session.

## 8. Known risks

- **Orphan `pipeline_run` rows** if the entrypoint crashes between INSERT and the finishing update. Ops concern only; status stays `running` forever. Mitigation: sweep for stale 'running' rows older than 24h, mark as 'failed_timeout'.
- **Schema blowup** on 7 tables × ~millions of rows for the backfill `UPDATE`. Batch in 10k chunks; acceptable downtime is zero for miroflow_real (current scale <1M rows total).
- **FK to pipeline_run ON DELETE SET NULL**: if someone drops a pipeline_run row (shouldn't happen), affected rows lose their tag. Acceptable — we keep the data, just lose provenance.

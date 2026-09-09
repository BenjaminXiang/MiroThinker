# Evidence — correct-paper-tier2-overmerge-view-b (View B flip)

> Change in-implementation → in-verification. Claude-owned operational evidence (tasks 3.x, 4.x).
> All counts DB-grounded against `miroflow_real` (localhost:15432); proxy vars unset. Online
> retrieval verified via the running admin-console backend (port 18188).

## Scope (DB-grounded 2026-06-30)

Of the 7 conference↔journal over-merges found in the post-acceptance audit of
`merge-paper-exact-title-duplicates`, only **group #1** has a retrieval impact (the rest are either
already journal-canonical (#2/#3/#6/#9), have no retrieval impact (#13 — neither version ready), or
need human review (#7)). **#1 flipped; #7 pending review; #13 deferred; #2/#3/#6/#9 no-op.**

## Group #1 — flip applied (run via `flip_paper_canonical` directly)

`flip_paper_canonical(old_canonical=PAPER-3E13FAE7D789 [conf LNCS 2019], new_canonical=PAPER-64D7A39FC25B [journal JLAMP 2021, arXiv 1805.10073])` under `open_pipeline_run(run_kind="backfill_real", triggered_by="paper_overmerge_flip")` + `close_pipeline_run(status="succeeded")`.

**Why direct (not `run_paper_overmerge_flip.py --apply`):** the script's `--apply` bundles a
`backfill_paper_chunks` Milvus refresh against `apps/miroflow-agent/milvus.db`, which is held
exclusively by the running admin-console backend's milvus-lite subprocess (PID 2640707, single-writer).
The DB flip was applied non-disruptively via the helper; the Milvus refresh turned out to be
**unnecessary** (J's chunks were still present from pre-merge indexing — verified by the online
retrieval spot-check below).

### Flip counts
```json
{"aliases_deleted": 1, "aliases_written": 1, "papers_promoted": 1, "papers_demoted": 1, "links_restored": 1, "links_rejected": 1}
```

### Post-state (DB-verified)
| Check | Result |
|---|---|
| alias | `old=PAPER-3E13FAE7D789 → canonical=PAPER-64D7A39FC25B`, reason `exact_title_dedup_canonical_correction` (wrong-direction `J→C` deleted) ✓ |
| paper status | J `confirmed/ready`; C `merged/rejected` ✓ |
| `prof→J` link | `verified`, `rejected_reason=NULL`, `match_reason='homepage_title_resolution'` (**clean, no migration suffix**) ✓ |
| `prof→C` link | `rejected`, `rejected_reason='merged_into_canonical:PAPER-64D7A39FC25B'`, `match_reason='homepage_title_resolution; exact_title_dedup:PAPER-64D7A39FC25B'` (**contaminated suffix stays on the hidden C row**) ✓ |
| `_is_indexable_paper` | J indexable=`True`; C indexable=`False` ✓ |
| retrieval candidate SQL (`identity_status!='rejected' AND quality_status!='rejected'`) | includes J, excludes C ✓ |

### Retrieval spot-check (online `/api/chat`, port 18188)
- Query `"Deadlock-Freedom of Parametric Component-Based Systems 论文"` → routed `A_paper_profile` →
  returned **`PAPER-64D7A39FC25B` (J) ×3**; **`PAPER-3E13FAE7D789` (C) absent**. ✓
- Confirms J's Milvus chunks are present (pre-merge indexing; the merge change did no Milvus delete)
  and C is hidden by the Postgres `quality_status='rejected'` filter. **No Milvus refresh required.**

## Unit tests (Codex slice, independent Claude re-run)
- `uv run pytest tests/scripts/test_run_paper_overmerge_flip.py tests/scripts/test_run_paper_exact_title_dedup.py -n0` → **14 passed** (8 new flip/Tier-3 + 6 existing dedup still green).
- `uv run ruff check` → clean.

## Tier-3 criterion (prospective, task 2.1)
`run_paper_exact_title_dedup.py` candidate SQL now excludes groups with ≥2 distinct **publisher**
DOIs (whitelisting `10.48550/arxiv.`, `10.2139/ssrn.`, `10.5194/egusphere-` preprint prefixes).
Unit tests verify: a publisher-DOI-conflict group is excluded; a preprint↔published pair stays
eligible. **Prospective only** — does not alter the 921 already-merged groups.

## Milvus refresh — intentionally NOT performed
The real `paper_chunks` index (`apps/miroflow-agent/milvus.db`) is held exclusively by the running
admin-console backend. The online retrieval spot-check confirmed J is already retrievable (chunks
present from pre-merge indexing) and C is hidden — so a refresh is **not required for correctness**.
If J had been absent from retrieval, the remediation would be: stop the backend, run
`run_paper_overmerge_flip.py --apply` (which refreshes Milvus), restart. Not needed here.

## #7 — pending human review
`PAPER-0A3117FF4FC6` (NYAS 2007, doi `10.1196/annals.1402.081`) vs `PAPER-5F47A16E07AD` (Cells
Tissues Organs 2008, doi `10.1159/000151747`) — both journals, different publishers, 1 year apart.
Metadata alone cannot distinguish dual-publication (View B keep-one) from two distinct papers
(un-merge to two). Decision recorded in `acceptance.md` once the user rules.

## #13 — deferred
`PAPER-7A80609AE22B` (LNCS conf 2008, `confirmed/partial`, not retrievable) vs `PAPER-9B500BAC9CB5`
(Formal Methods 2010, `merged`, no abstract). Flip has zero retrieval impact (neither version ready;
journal version also lacks abstract). Deferred until the journal version is enriched.

## Artifacts
- `src/data_agents/paper/dedup_merge.py` — `flip_paper_canonical` (+ helpers).
- `scripts/run_paper_overmerge_flip.py` — flip CLI (`--dry-run`/`--apply`/`--confirm-real-db`/`--group`).
- `tests/scripts/test_run_paper_overmerge_flip.py` — 8 fake-conn tests.
- `scripts/run_paper_exact_title_dedup.py` — Tier-3 DOI-conflict exclusion in candidate SQL.

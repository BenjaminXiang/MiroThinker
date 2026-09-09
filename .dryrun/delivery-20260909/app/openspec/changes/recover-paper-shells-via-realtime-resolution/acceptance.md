# Acceptance: recover-paper-shells-via-realtime-resolution

A change is accepted only when ALL of the following hold.

## Ingest-fix contract
- [ ] Default ingest (cap=None) resolves an un-cached publication in realtime →
      no `prof_page_only` shell created merely because the title was un-cached.
- [ ] Explicit `--external-resolution-max-per-professor=N` still honored (N+1th
      → cache_only allowed for bulk fast-mode).
- [ ] None-safe: `effective=None` does not break the budget comparison.

## Re-resolution (Stage A)
- [ ] Pilot (500 shells) yield recorded (≈77% expected); rate-limits/workers
      tuned before the full run.
- [ ] Full run: resolved count recorded; resolved shells enriched (DOI/abstract)
      + merged into canonical via `paper_merge_alias`; professor links
      re-pointed.
- [ ] 0 `ready` papers degraded; idempotent re-run (via `title_resolution_cache`).

## summary_zh (Stage B)
- [ ] `summary_zh` generated only for resolved papers (with abstract); no
      boilerplate injection (sample spot-check).
- [ ] No `summary_zh` fabricated for unresolved shells.

## Ready + retrieval (Stage C)
- [ ] Recovered papers (full ready criteria) promoted to `ready`.
- [ ] Newly-ready papers indexed in `paper_chunks` (targeted rebackfill).
- [ ] Retrieval spot-check: ≥20 newly-recovered papers retrievable (self@rank0/1).

## Residual (Stage D)
- [ ] Post-Stage-A unresolved shells documented as a bounded residual; they
      remain not-`ready` (excluded from retrieval); no fabrication.

## Code quality / invariants
- [ ] No schema migration; `paper`/`paper_merge_alias`/`paper_full_text` reused.
- [ ] No enum/gate change; no `summary_zh` fabrication; no A–G / `_VALID_DOMAINS`
      / evidence-shape change.
- [ ] `uv run pytest` green (new tests + regression); `just lint` clean.
- [ ] `openspec validate recover-paper-shells-via-realtime-resolution --strict`
      exits 0.

## Evidence to report
- Pilot yield + Stage A/B/C counts (under `.agents/runs/recover-paper-shells-via-realtime-resolution/`).
- Retrieval spot-check results.
- Ingest-fix + residual-marker test output.

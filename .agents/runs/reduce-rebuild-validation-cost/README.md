# Evidence root: reduce-rebuild-validation-cost

Change: `openspec/changes/reduce-rebuild-validation-cost/` (Standard, status
**proposed** — registered 2026-09-14, implementation not started).

Human-side evidence for this change lives in one analysis doc:

- `docs/plans/2026-09-14-rebuild-cost-analysis.md`
  - §5 / §7 — Python-side per-entity full scans (identity validator) + fix direction;
  - §11 / §11.1 / §11.2 — PG-layer deferred-trigger hot spot, `EXPLAIN ANALYZE`
    (42.8 ms/row), and the measured 12h40m decision-batch `COMMIT`;
  - §12 — over-design review: four checkable criteria, minimal design (§12.4),
    acceptance line (§12.5);
  - §13 / §13.2 — release-contract review, sealer phase timings
    (`envelope_validate 2071.098s`), minimal design (§13.4), acceptance (§13.5).

This directory receives the verification artefacts when implementation starts:
`verification-contract.md`, `verification.md`, per-phase rebuild timings, and the
equivalence digests required by `acceptance.md` A1–A7.

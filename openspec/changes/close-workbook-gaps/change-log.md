# Change Log: close-workbook-gaps

## 2026-09-10 — Change opened

- Opened under the system-completion plan approved 2026-09-10
  (P1 functional completeness first, P2 delivery second).
- Scope: 16-item workbook gap list (evidence doc
  `docs/plans/2026-09-09-testset-baseline-and-repair-plan.md` §九),
  stages B (serving-line fixes) and C (data groundwork).
- B1 designed in full (design.md); B2–C5 recorded as stubs to be filled at
  slice start.
- User directives baked in: simple path first; audit/proof layers frozen;
  thin-load/direct-scan instead of assembly-contract repair (risk R1).

## 2026-09-10 — B1 round 1: port landed, design revised (two upstream gates)

- Port of the G3-simple scan landed as commit `b20161d` (+79 lines) with an
  added path-eligibility guardrail (source block `790f4d1` re-admitted
  excluded endpoints — same defect confirmed present in the data line;
  **follow-up: back-port the guardrail to the data line**).
- g17-t1 stayed RED: the ported function is unreachable on the s12f pack.
  Evidence in `.agents/runs/close-workbook-gaps/verification-b1.md`:
  Gate A (planner binding: patterns miss "有哪些专利" shape + pack aliases
  lack the bare short name) and Gate B (dispatch routes company→patent to
  `_source_bound_relationship_candidates` because s12f has 0
  relationship-scoped eligibility rows; positive control 普渡 = 17
  candidates proves the lane machinery works).
- design.md §B1 revised: Gate A fix (patterns + derived short-name channel
  with uniqueness guard), Gate B fix (shared `_direct_patent_applicant_scan`
  helper called from the source-bound path — dispatch re-routing rejected
  because it would regress 普渡), B1c (relationship-lane citations).
- Replay jitter documented (7/7, 6/7, 6/7 across identical code; failing
  signatures all pre-existing in historical logs; ported code unreachable
  on this pack). Interim acceptance policy recorded in design.md; jitter
  fix queued as `harden-serving-test-harness` A3.4.
- Tasks B1.3–B1.5 added; B1.1 marked done.

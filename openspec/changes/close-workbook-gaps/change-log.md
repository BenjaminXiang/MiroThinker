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

## 2026-09-10 — B1 round 2: Gates A/B + citation floor landed; Gate C found

- Round 2 landed on `codex/canonical-v2-s12a-ready` (source in auto
  snapshot `1860b8c`, tests `673edb7`): Gate A binds the bare short name
  ("优必选有哪些专利" → `company-c-64e631c0e0cd9e91d032d209`) through the
  `_compact_company_alias` channel — the originally sketched possessive
  pattern extension was correctly skipped (the short-name channel covers
  it, and the extension would mis-fire on "…的竞争对手有哪些专利");
  Gate B unions `_direct_patent_applicant_scan` into
  `_source_bound_relationship_candidates` (优必选: 48 candidates = 58
  bindings − 10 path-eligibility exclusions); B1c emits
  `local-source-<sha>` citation cards for URL-less relationship evidence.
  Positive control 普渡 end-to-end green: 17 candidates → 16 CN numbers +
  16 local cards (archive `pudu-answer-r2.json`).
- g17-t1 stayed RED at a third, deeper gate: `_apply_constraints`
  (knowledge_read.py:6174) derives `displayed_entity_witness_ids` only from
  relationship projection traces; scan items carry a typed claim binding
  and no trace (by design), so the `displayed_entity_set` slot rejects all
  48. Minimal repro:
  `.agents/runs/close-workbook-gaps/repro_constraint_gate_scan_items.py`.
- Mechanism verified line-by-line before designing the fix: witness ids are
  consumed solely by the `displayed_entity_set` branch (geography /
  exact-identifier slots use claim-subject / identity paths); the answer
  selector already admits these candidates via `_claim_binding_binds_anchor`
  (knowledge_serving_isolated.py:5678); `_apply_constraints` is shared by
  the main read flow (:7961) and the release-bound relationship validator
  (knowledge_read_isolated.py:6118), so one edit keeps both consistent.
- design.md §B1 revision 2 adds the Gate C fix (claim-binding witness
  branch mirroring the selector's value-endpoint semantics) with rejected
  alternatives and the round-3 test matrix; task B1.6 added.

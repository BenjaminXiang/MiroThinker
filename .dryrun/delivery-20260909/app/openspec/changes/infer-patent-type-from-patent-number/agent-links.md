# Agent Links — infer-patent-type-from-patent-number

> Per CLAUDE.md §14.4. Roles, skills, and verification boundary for this change.

## Roles (CLAUDE.md §1)
- **Claude (designer/reviewer):** the DB-grounded feasibility investigation
  (source-xlsx header inspection + patent_number kind-code scan) that scoped
  this change to the feasible, no-new-data path; this OpenSpec change; and
  post-implementation review against the contract.
- **Codex (implementer):** owns the `tasks.md` slices — `type_inference.py`,
  the canonical-path wiring, the dry-run, the bounded backfill, the Milvus
  rebackfill, and the retrieval spot-check evidence. Reports back per slice.

## Related changes
- `unify-data-quality-gating` (sibling, 2026-06-26) — owns the paper write-path
  gate + Milvus rebackfill discipline; this change is the patent analogue
  (fill the upstream field so the existing gate promotes to ready → retrievable).
  Independent code paths; either may land first.
- `wire-professor-patent-inventor-linking` (R17) — **not viable** until patent
  inventor data is sourced (separate, data-blocked). This change does not
  unblock it; it only unblocks patent `ready`/retrievability.

## Skills used
- `openspec-propose` — generated this change's artifacts.
- `superpowers:test-driven-development` — drives the deterministic unit/contract
  slices (RED → GREEN) per the verification contract.
- `pattern-repair` — the cross-domain "collected but not retrievable" framing
  that surfaced patent 0/11,408 as a systemic retrieval gap.

## Verification boundary (CLAUDE.md §14.7)
- `.agents/runs/infer-patent-type-from-patent-number/verification-contract.md`
  (task 1.1) classifies the change as **behavior-affecting but deterministic at
  the new-code surface** (pure `patent_number` function; no LLM, no network).
  RED = unit + contract tests + read-only dry-run; GREEN = tests pass +
  dry-run "11,408 partial→ready, 0 ready degraded" + bounded backfill +
  Milvus rebackfill.
- Superpowers TDD may drive the deterministic slices; it MUST NOT alter the
  gate, the enum, the no-enrichment constraint, or add a patent API.
- The dry-run "0 ready degraded" + 100%-type-coverage assertions are
  stop-and-report hard gates.

## Dispatch
- One active writer (Codex) per slice (CLAUDE.md §11). Slice order follows
  `tasks.md` groups 1 → 5.
- Claude reviews each slice against `acceptance.md` before the next.

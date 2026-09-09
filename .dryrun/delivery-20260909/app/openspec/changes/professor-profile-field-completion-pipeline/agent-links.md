# Agent Links — professor-profile-field-completion-pipeline

> Per CLAUDE.md §14.4.

## Roles (CLAUDE.md §1)
- **Claude (designer/reviewer):** field-completeness diagnosis, this OpenSpec change (architecture + per-field chain), post-slice review.
- **Codex (implementer):** owns the `tasks.md` slices (audit, L4/L3/L2/L1, closure, tests). Reports per slice.

## Skills used
- `pattern-repair` (root-cause framing — single-source completion is the systemic defect).
- `superpowers:writing-plans` (gap-analysis + seed-checklist companion docs).
- `openspec-propose` (this change's artifacts).

## Verification boundary (CLAUDE.md §14.7)
- `.agents/runs/professor-profile-field-completion-pipeline/verification-contract.md` (task 1.1): deterministic surface = source-chain dispatcher + closure + audit → unit/contract RED; L2 (LLM) + L3 (OpenAlex/ORCID) + L4 (crawl) real-runs are acceptance evidence, not RED. Superpowers TDD drives deterministic slices; must not weaken `professor-profile-field-extraction-integrity` or evidence/run_id.

## Dispatch
- Epic-shaped: L2/L3/L4 are independent subsystems → may split into child changes (§design Open Questions). Single active writer (Codex) per slice (CLAUDE.md §11). Slice order: 1 (audit) → 2 (L4) → 3 (L3) → 4 (L2) → 5 (L1) → 6 (dispatcher/closure) → 7 (tests) → 8 (evidence/acceptance/ledger).

# .agents/runs/ (per-change execution workspace)

This directory is the **execution workspace** for OpenSpec changes, introduced in Phase 0 under CLAUDE.md §14.4 and AGENTS.md §15.

## Layout

```text
.agents/runs/<change-id>/
├── implementation-plan.md      Claude-owned executable plan (slices, file-level scope, TDD steps)
├── verification-contract.md    pre-implementation RED/GREEN contract and Superpowers mode
├── slices/                     per-slice notes
│   ├── 001-<slug>.md
│   └── 002-<slug>.md
├── handoff.md                  short-form Codex handoff; cross-reference also lives in .agents/handoffs/<slug>
├── verification.md             executed commands, outputs, and skipped-check rationale
└── review.md                   Claude review notes; cross-reference also lives in .agents/reviews/<slug>
```

The `<change-id>` is the same identifier used in `openspec/changes/<change-id>/`.

## Authority

`.agents/runs/<change-id>/` is an **execution artifact**. It may narrow the implementation slice but **cannot override** OpenSpec or the legacy behavior baseline (CLAUDE.md §14.1).

If implementation reveals the OpenSpec change is wrong, update OpenSpec first (`proposal.md`, `specs/`, `tasks.md`, `change-log.md`), then update the execution plan here.

`verification-contract.md` is written before production-code edits for behavior-affecting work. It decides what RED is, what GREEN means, and whether Superpowers TDD, eval-first, trace-debug-first, or baseline-only execution is allowed. Superpowers may execute the discipline, but must not independently choose the RED artifact.

## Relationship to existing `.agents/` subdirectories

- `.agents/handoffs/<slug>.md` — short-form, single-slice handoffs; remain in use; reference the change-id in the header.
- `.agents/reviews/<slug>.md` — review notes; remain in use; reference the change-id in the header.
- `.agents/specs/` — frozen legacy (see `.agents/specs/README.md`).
- `.agents/skills/` — repeatable workflows; unchanged.
- `.agents/runs/` — this directory; per-change execution workspace.

## Phase scope

Phase 0 introduces this directory and README. Actual `<change-id>` subdirectories are created as the first OpenSpec changes are proposed in Phase 1+.

# .agents/specs/ (legacy, frozen)

This directory is **frozen as legacy** under CLAUDE.md §14.5 and AGENTS.md §15.5.

## Do not create new files here.

The Claude-owned design-contract role previously held by `.agents/specs/<date>-<slug>.md` has been split:

- **Behavior contract** → `openspec/changes/<change-id>/specs/`
- **Technical design** → `openspec/changes/<change-id>/design.md`
- **Execution detail** (slices, file-level scope, TDD steps) → `.agents/runs/<change-id>/`

## Existing files

The dated `.md` files in this directory remain as **historical context only**. They may be consulted when investigating prior design decisions or when migrating a capability into OpenSpec (touch-to-promote, CLAUDE.md §14.3), but they are not authoritative.

When a future change touches a capability covered by an existing legacy file:

1. Promote durable behavior into `openspec/specs/<capability>/spec.md` per CLAUDE.md §14.3.
2. Record the extraction in `openspec/changes/<change-id>/source-links.md`.
3. Leave the original legacy file in place until the Phase 1 cleanup decision.

## Phase scope

Phase 0 only adds this README and freezes the directory. Moving, renaming, or rewriting individual `.agents/specs/<date>-<slug>.md` files is **deferred to Phase 1+** and requires its own OpenSpec change.

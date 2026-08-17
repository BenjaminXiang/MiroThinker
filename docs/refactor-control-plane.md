# Refactor Control Plane

This document defines how large-scale refactors are prepared, executed, verified, and reviewed in this repo.

Root instructions stay compact:

- `CLAUDE.md` defines Claude orchestration, phase ownership, review, and handoff policy.
- `AGENTS.md` defines Codex implementation, verification, reporting, and stop conditions.
- This document defines the detailed refactor control loop.

## First principles

A large refactor must preserve behavior unless an approved OpenSpec change explicitly changes behavior.

The refactor workflow must provide:

1. Baseline behavior evidence.
2. Clear owner per phase.
3. Small implementation slices.
4. Regression resistance.
5. Reversible diffs.
6. Verification evidence.
7. Claude review decisions: Accept / Revise / Reject.
8. Portfolio cleanup so unfinished work does not accumulate.

## Phase owners

- Claude owns clarification, architecture pressure-testing, refactor contracts, Codex handoffs, review decisions, and archive readiness.
- Codex owns one approved Ready slice at a time, including implementation, test updates, verification evidence, and reporting.
- OpenSpec owns behavior contracts and behavior changes.
- Superpowers owns implementation discipline: planning, TDD where appropriate, systematic debugging, and verification-before-completion.
- Matt skills own pre-spec grilling, domain modeling, codebase design, handoff quality, and test design review.

## Default quality chain

For non-trivial refactor or implementation work:

```text
Matt grill-with-docs
  -> clarify goal, scope, risks, and edge cases

OpenSpec / refactor-contract
  -> define what is correct and what must remain unchanged

Matt codebase-design
  -> check seams, interfaces, adapters, and slice boundaries

Codex
  -> implement exactly one Ready slice

Superpowers
  -> enforce execution and verification discipline

Matt test-design-review
  -> prevent tests from only asserting implementation details

Claude review
  -> Accept / Revise / Reject

Portfolio / archive
  -> prevent unfinished task inventory from accumulating

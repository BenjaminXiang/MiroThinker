# ADR-013: Canonical V2 uses hybrid enumeration coverage

- **Date:** 2026-07-13
- **Status:** Accepted and carried by the active OpenSpec change
- **Related:** `CONTEXT.md` (Enumeration policy, Enumeration coverage report); OpenSpec
  `rebuild-canonical-v2-knowledge-platform`; Tasks 8.6-8.8 and 9.5-9.8
- **Contract:** carried by the active OpenSpec change before S8 query-orchestration
  implementation

## Context and decision

Questions such as “有哪些” range from finite database traversals to open-world market landscapes.
A bounded candidate set or Top-K cannot by itself establish that a list is complete, while forcing
clarification before every list query would make ordinary discovery unnecessarily costly.

Canonical V2 will therefore use a hybrid enumeration policy:

- `exhaustive_bounded` applies only when the plan names a finite universe and the route can account
  for every eligible member;
- `required_members` applies when the user or an accepted case contract names entities that must be
  checked and either included with evidence or reported with a specific unsupported/omission reason;
- `representative` is the default for an open-world list without a bounded universe or required-member
  contract, and the answer must not imply exhaustiveness.

Every list answer carries an enumeration coverage report naming the mode, scope, as-of boundary,
checked/eligible/retrieved/displayed accounting, omissions and unknowns, and continuation state. A
materially ambiguous scope may still trigger clarification, but clarification is not the universal
default.

## Consequences

- The typed retrieval plan needs an explicit enumeration policy; evidence sufficiency must evaluate
  the policy rather than treating a non-empty candidate list as complete.
- The answer/session contract must retain the displayed set and coverage report without turning
  undisplayed candidates into set referents.
- Acceptance cases need machine-readable required members, forbidden members, scope, as-of, and
  coverage mode. Aggregate key-point scores cannot mask a failed required member or a false
  exhaustiveness claim.
- This ADR records the product decision but does not itself modify OpenSpec behavior requirements;
  the active V2 change remains the behavior owner.

## Alternatives rejected

- **Always clarify before searching:** precise but adds a mandatory turn even when representative
  discovery is useful and honest.
- **Always return representative Top-N:** simple but cannot satisfy bounded exhaustive or named
  required-member questions and encourages false completeness claims.

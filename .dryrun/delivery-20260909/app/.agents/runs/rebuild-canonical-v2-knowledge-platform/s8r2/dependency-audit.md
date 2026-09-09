# S8R2 Dependency Audit — 2026-07-19T20:24:02Z

## Outcome

The next smallest independently testable Task 8.3 relationship family is one release-scoped,
displayed-Company-to-Patent applicant traversal:

```text
planner path:       company_has_patent / company_to_patent / company -> patent
canonical relation: patent_has_applicant@canonical-v2-relationship-v1
execution:          reverse traversal from the accepted Company applicant to the Patent
```

This single mapping is Ready to specify. Aggregate Task 8.3 closure is not Ready because OpenSpec
does not yet contain the complete planner-path-to-canonical-relation closure matrix. S8R2 must not
check Task 8.3 or claim aggregate relationship-lane coverage.

## Why this mapping is already authoritative

- The active query spec permits an exhaustive applicant-to-Patent universe only when that universe
  is finite and accepted; otherwise it requires representative enumeration, which S8R2 selects.
- Accepted Task 6 catalog evidence uniquely maps `traversal_scenario.company_to_patent` to
  `patent_has_applicant`, marks the direction `supported`, fixes Patent-to-applicant canonical
  orientation, and forbids interpreting applicant as owner or assignee.
- The Accepted planner contract already permits exactly
  `company_has_patent / company_to_patent / company -> patent`.
- S8L2 already binds contextual displayed IDs into exact structured constraints and rejects a
  protected displayed-set mismatch.
- S7K is a generic exact-pair publication interface. Its Technology pair is a positive fixture,
  not an interface restriction. A clean S8R2-owned combined-registry Company/Patent graph is a new
  valid input to that Accepted interface, not an unaccepted predecessor.

## Ranked alternatives

1. `company_to_patent` is source-supported, has one exact canonical type, needs no internal public
   domain, and has an existing typed planner path.
2. Professor-to-Paper is source-supported but carries attribution-versus-existence and same-name
   identity invariants.
3. Person-backed Company-team/Paper-author/Patent-inventor traversal spans three roles plus
   resolved/unresolved Person boundaries.
4. Multi-route Technology comparison has the closest current trace shape but the Accepted positive
   fixture publishes only one route.
5. Professor/Company and Professor/Patent directions remain evidence-limited; reverse
   Company-to-Technology is not explicitly required and risks promoting Product evidence.

## Dependency decision

S8R2 depends on Accepted S6 catalog/relationship semantics, S7 candidate/index/release authority,
S7K generic relationship-pair authority, S8P2 planning, S8E1 composition, S8L2 displayed-set
binding, and S8R1 relationship replay/postvalidation mechanics. S2C3C2 still gates only reviewed
calibration and claim-level oracle execution, not this deterministic release-bound predecessor.

Durable sources for this decision are:

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/evidence-first-query-orchestration/spec.md`
  (structured paths, applicant-to-Patent enumeration, and traceability);
- `apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/domain-catalog-v1.json`
  (`patent_has_applicant` and `traversal_scenario.company_to_patent`);
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s7k-release-scoped-relationship-publication-authority-correction.md`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s8l2-release-scoped-displayed-set-structured-lookup-green.md`; and
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s8r1-release-scoped-technology-relationship-traversal.md`.

No code, tests, OpenSpec task checkbox, external store, provider, source, pointer, Commit, Push, PR,
Archive, promotion, or Cutover changed during this audit.

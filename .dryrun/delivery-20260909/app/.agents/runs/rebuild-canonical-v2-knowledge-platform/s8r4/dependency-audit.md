# S8R4 Dependency Audit — 2026-07-20

## Outcome

The next smallest independently testable Task 8.3 slice is one release-scoped displayed-Paper-to-
Professor attribution traversal:

```text
planner path:       professor_authored_paper / paper_to_professor / paper -> professor
canonical relation: professor_attributed_to_paper@canonical-v2-relationship-v1
execution:          inverse traversal from one accepted displayed Paper to accepted Professors
```

This mapping is Ready to specify. Aggregate Task 8.3 closure is not Ready: S8R2 and S8R3 execute two
of the eight public cross-domain directions, while S8R4 adds only the supported inverse of S8R3.
Task 8.3 SHALL remain unchecked and the formal ledger SHALL remain `56/80` after S8R4.

## Authoritative denominator and remaining paths

The OpenSpec verification contract, Accepted path-eligibility policy, catalog scenarios, and product
PRD agree on eight public cross-domain directions. S8R2 owns Company-to-Patent and S8R3 owns
Professor-to-Paper. The six directions not yet executed through public `KnowledgeRead.execute` are:

| Direction | Canonical relationship family | Catalog evidence outcome |
|---|---|---|
| Paper-to-Professor | `professor_attributed_to_paper` inverse | `supported` |
| Patent-to-Company | `patent_has_applicant` forward | `supported` |
| Professor-to-Company | `professor_company_role` forward | `insufficient_evidence` |
| Company-to-Professor | `professor_company_role` inverse | `insufficient_evidence` |
| Professor-to-Patent | inventor/listing evidence family | `insufficient_evidence` |
| Patent-to-Professor | inventor/listing evidence family inverse | `insufficient_evidence` |

S8R1 Technology-to-Company is an internal auxiliary-domain-to-public-domain traversal and does not
consume one of these eight public directions.

## Why Paper-to-Professor is next

- The Accepted Task 6 catalog explicitly marks `paper_to_professor` as `supported` and binds it to
  the same `professor_attributed_to_paper@canonical-v2-relationship-v1` authority as S8R3.
- Accepted path eligibility already replays both `professor_to_paper` and `paper_to_professor`
  against the same relationship decision. S8R3 already verifies both endpoint requests/results.
- The frozen S9M multi-turn RED uses a Professor-to-Paper turn followed by Paper-to-Professor;
  S8R4 therefore removes a real downstream read dependency without inventing new product semantics.
- Patent-to-Company is also supported, but its applicant role must remain distinct from owner,
  assignee, inventor, and generic organization relations. It is the preferred next slice after S8R4.
- Professor/Company directions need exact-role evidence recollection, and Professor/Patent still has
  a real semantic split between verified inventor evidence and a Professor page merely listing a
  Patent. Neither is appropriate for this minimal slice.

## Planner and canonical-predicate boundary

`professor_authored_paper` remains the accepted planner alias. It is not a canonical predicate. The
new inverse direction SHALL emit only the canonical claim
`Professor --professor_attributed_to_paper--> Paper`, even though the displayed Paper is the query
source and the returned candidate is the Professor. It SHALL NOT infer `paper_has_author`, claim
unconditional authorship, reverse the canonical predicate, or infer an edge from author names,
PaperAuthor subobjects, internal Person identities, ORCID/name matches, or projected ID lists.

## Feasibility and implementation boundary

- Reuse the existing public `KnowledgeRead.execute` interface, release bundle, and single
  `create_isolated_relationship_lookup_adapter` factory.
- Preserve S8R1/S8R2/S8R3 literal and serialized contracts. Add a dedicated inverse trace rather
  than mutating the Accepted S8R3 discriminator or field semantics.
- Make planner endpoint validation direction-aware with the finite key
  `(relationship_type_id, direction)` so one planner alias can safely support both directions.
  Preserve current error categories for unknown type, unsupported direction, and endpoint drift.
- Reuse the exact S8R3 relationship assertion, source assignments, decision/current projection,
  retained evidence, public endpoints, and dual endpoint eligibility authority entirely in memory.
- Return only Professor candidates. The displayed Paper is a protected source witness; Web evidence
  cannot manufacture that witness or a Professor-Paper relationship claim. Legitimate same-
  Professor Web evidence may fuse and satisfy Professor-scoped constraints.
- Own one exact vertical RED/GREEN scenario in
  `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`.

Two independent read-only audits selected this slice and found no unresolved product or
architecture decision. S2C3C2 continues to gate only reviewed calibration and acceptance-oracle
execution, not this deterministic release-replay slice.

## Durable sources

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md` — Task 8.3;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md` — all-eight-
  directions denominator;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/evidence-first-query-orchestration/spec.md`;
- `apps/miroflow-agent/src/data_agents/canonical_v2/path_eligibility.py`;
- `apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/domain-catalog-v1.json`;
- `docs/Agentic-RAG-PRD.md`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s8r3-release-scoped-displayed-professor-paper-traversal.md`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s9m-multiturn-red.md`.

No code, test, OpenSpec checkbox, external store, provider, source, pointer, Commit, Push, PR,
Archive, promotion, or Cutover changed during this audit.

# S8R3 Dependency Audit — 2026-07-19T22:31:15Z

## Outcome

The next smallest independently testable Task 8.3 relationship family is one release-scoped,
displayed-Professor-to-Paper attribution traversal:

```text
planner path:       professor_authored_paper / professor_to_paper / professor -> paper
canonical relation: professor_attributed_to_paper@canonical-v2-relationship-v1
execution:          forward traversal from one accepted displayed Professor to accepted Papers
```

This mapping is Ready to specify. Aggregate Task 8.3 closure is not Ready: S8R3 covers one public
relationship family only and SHALL NOT check Task 8.3 or claim complete relationship-lane coverage.

## Why the mapping is authoritative

- The Accepted planner contract already permits exactly
  `professor_authored_paper / professor_to_paper / professor -> paper`.
- The Accepted Task 6 catalog uniquely maps `traversal_scenario.professor_to_paper` to
  `professor_attributed_to_paper@canonical-v2-relationship-v1`, fixes Professor-to-Paper canonical
  orientation, requires `professor_page_or_identity_attribution_assertion`, and permits no role.
- The same catalog explicitly separates attribution metadata from a business role, separates an
  attribution decision from Paper existence, and limits the same-name gate to Person identity.
- Accepted path eligibility already evaluates both `professor_to_paper` and
  `paper_to_professor` against the same canonical relationship decision.
- S7K is a generic exact-pair publication interface. A clean S8R3-owned Professor/Paper graph is a
  new valid input, not a new release schema or an unaccepted predecessor.
- S8R2 already established omission-preserving enumeration policy, source-side displayed-set
  authority, release replay, open-world coverage, and hostile postvalidation mechanics.

## Planner-name boundary

`professor_authored_paper` is the existing planner path name. It is not the canonical predicate and
does not authorize a `paper_has_author` edge or an unconditional authorship statement. S8R3 SHALL
emit only `professor_attributed_to_paper`, backed by an accepted current canonical attribution and
its retained evidence. It SHALL NOT infer that attribution from a PaperAuthor, an internal Person,
a same-name match, or a projected `professor_ids` value without the accepted relationship chain.

## Feasibility decision

- Reuse the existing public `KnowledgeRead.execute` interface and the single
  `create_isolated_relationship_lookup_adapter` factory.
- Keep S8R2's literal Company/Patent/applicant trace unchanged. Add one dedicated Professor/Paper
  trace variant and deepen only package-private traversal/replay helpers.
- Reuse the current Professor and Paper projections, shared relationship assertion/assignment/
  decision chain, dual endpoint path eligibility, candidate/index/release bundle, Web fusion, and
  coverage machinery.
- Own one exact vertical RED/GREEN scenario in
  `test_internal_reference_projection_contract.py`; no external provider or physical store is
  required.

Three independent pre-draft read-only audits found no unresolved product or architecture decision.
Independent Ready reviews closed at `2026-07-19T22:53:22Z` with zero open Critical/Important; the
final contract review reports `C=0/I=0/M=0/YAGNI=0`. Existing focused relationship/path tests
passed. S2C3C2 still gates only reviewed calibration and claim-level acceptance-oracle execution,
not this deterministic slice.

## Dependencies

S8R3 depends on Accepted S6 catalog/relationship/path semantics, S7 candidate/index/release
authority, S7K generic relationship-pair authority, S8P2 planning, S8E1 composition, S8L2
displayed-set binding, S8R1 replay/postvalidation, and S8R2 public source-witness/enumeration
mechanics.

Durable sources:

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/evidence-first-query-orchestration/spec.md`;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/paper-identity-status/spec.md`;
- `apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/domain-catalog-v1.json`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s7k-release-scoped-relationship-publication-authority-correction.md`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s8r2-release-scoped-displayed-company-patent-traversal.md`.

No code, test, OpenSpec checkbox, external store, provider, source, pointer, Commit, Push, PR,
Archive, promotion, or Cutover changed during this audit.

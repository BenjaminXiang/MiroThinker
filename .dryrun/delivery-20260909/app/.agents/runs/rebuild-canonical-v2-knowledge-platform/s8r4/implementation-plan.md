# S8R4 Release-scoped Displayed Paper-to-Professor Traversal Implementation Plan

> **For agentic workers:** use `superpowers:test-driven-development` for RED/GREEN and
> `superpowers:verification-before-completion` before Candidate/Accepted claims. One writer owns the
> two production modules and the vertical owner test. Do not Commit.

**Goal:** Execute one displayed Paper-to-Professor attribution traversal from an exact S7K release
graph through the existing public `KnowledgeRead.execute` interface.

**Architecture:** Deepen the existing single relationship adapter with a direction-aware finite
planner mapping and one dedicated inverse trace. Reuse S8R3's exact relationship authority replay,
but keep the displayed Paper as a protected source witness and return a Professor candidate while
preserving the canonical Professor-to-Paper claim orientation.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, uv, Ruff, Pyright, OpenSpec.

---

## Status

Accepted at `2026-07-20T08:53:38Z` after Candidate verification and independent final review
reported `C=0/I=0/M=0/YAGNI=0`. Task 8.3 remains unchecked and the formal ledger remains `56/80`.

## File map

- Modify `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`:
  one exact S8R4 vertical owner reusing the smallest S8R3 fixture surface.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`: direction-aware
  planner endpoints, exact inverse path constant, dedicated trace, returned-Professor validation,
  source-side Paper witness, and unchanged S8R1/S8R2/S8R3 serializers.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`: exact inverse
  path dispatch, in-memory shared-authority replay, and release pre/postvalidation.
- Update only S8R4 run/receipt/evidence plus existing portfolio/change-log/agent-links/status
  summaries after acceptance. Keep `tasks.md` and `acceptance.md` unchanged.

## Task 1: Freeze Ready

- [x] Independently review contract semantics, planner compatibility, deep-module boundary, and
  RED/hostile matrix.
- [x] Repair Critical/Important only; record Minor/YAGNI without adding gates. The lean merged review
  returned `C=0/I=0/M=0/YAGNI=0`; no repair was required.
- [x] Mark contract/plan Ready only after zero open Critical/Important; record UTC timestamp and
  exact reviewed Specified hashes; run strict OpenSpec (`2026-07-20T07:25:40Z`; valid).

## Task 2: Add and observe one exact RED

- [x] Add `_MissingS8R4PaperProfessorTraversal` and `_s8r4_public_relationship_contract()` requiring
  `LocalPaperProfessorRelationshipTrace` with exact `paper_professor_relationship_traversal` /
  `relationship` discriminators. Acquire `tmp_path` and `monkeypatch` only after the seam check.
- [x] Add the exact strict-xfail owner:

```python
@pytest.mark.xfail(
    raises=_MissingS8R4PaperProfessorTraversal,
    reason="S8R4 RED: exact Paper-to-Professor traversal seam is absent",
    strict=True,
)
def test_s8r4_executes_release_scoped_paper_to_professor_attribution_traversal(
    request: pytest.FixtureRequest,
) -> None:
    read_module, relationship_factory, release_factory = (
        _s8r4_public_relationship_contract()
    )
    tmp_path = request.getfixturevalue("tmp_path")
    monkeypatch = request.getfixturevalue("monkeypatch")
```

- [x] Reuse a clean Professor/Paper candidate/index/release graph with one shared source assertion,
  two canonical assignments, one accepted decision/current projection, one retained reference, and
  exact directional eligibility for both endpoints. Build an inverse plan with domains
  `("professor",)`, displayed Paper authority, and exact `paper_to_professor` path.
- [x] Freeze the positive trace/claim/coverage plus bounded zero/negative matrix: authoritative
  zero; no edge; wrong canonical family; rejected/non-current edge; excluded/limited endpoints;
  zero max; wrong type/direction/endpoints/release/evidence/assignment/time; multi-retained-reference
  omission; later/earlier query; source Paper Web witness; fabricated Web relationship claim;
  hostile delegate output; relationship path/lane drift before Web; and zero physical reads.
- [x] Add legitimate same-Professor Web fusion with a Professor exact identifier and one Paper-only
  negation term. Relationship source evidence must neither satisfy nor reject Professor-scoped
  constraints.
- [x] Run the exact normal RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r4_executes_release_scoped_paper_to_professor_attribution_traversal -q
```

Expected: exactly one strict xfail at `_MissingS8R4PaperProfessorTraversal` and no fixture/effect
acquisition before the sentinel.

Observed: `61 deselected, 1 xfailed in 2.51s`.

- [x] Run the exact forced RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider --runxfail \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r4_executes_release_scoped_paper_to_professor_attribution_traversal -q
```

Expected: exactly one failure at `_MissingS8R4PaperProfessorTraversal`, before `tmp_path`,
`monkeypatch`, release construction, Web, or adapter execution.

Observed: `1 failed, 61 deselected in 1.21s`; the only failure was the exact missing
`LocalPaperProfessorRelationshipTrace` sentinel before fixture acquisition.

## Task 3: Carry the inverse request and trace contract

- [x] Replace the planner's one-direction-per-type lookup with an exact finite mapping keyed by
  `(relationship_type_id, direction)`. Preserve the existing error categories and add
  `_PAPER_TO_PROFESSOR_QUERY_PATH` without changing accepted constants or serialized payloads.
- [x] Permit omission-preserving `relationship_enumeration_policy` only for the new exact path in
  addition to S8R2/S8R3. Require exact plan/policy/as-of identity.
- [x] Add `LocalPaperProfessorRelationshipTrace` with the contract's exact fields, literals,
  sorted/unique rules, empty roles, content-bound IDs, canonical claim orientation, displayed Paper
  authority, and returned Professor candidate semantics. Do not mutate/reuse S8R3's discriminator.
- [x] Extend trace union, locator, local item/candidate validation, protected-source constraint
  witness, fusion ownership, and coverage accounting for the inverse variant.
- [x] Remove the xfail only once the exact seam exists; run the focused test and record the next
  genuine RED before implementing the adapter branch.

Observed: the next real RED was the exact unsupported inverse relationship request path after the
trace seam and release fixture existed.

## Task 4: Implement exact inverse traversal

- [x] Add one exact inverse branch inside the existing adapter and factory. Do not add a registry,
  public interface, storage seam, or second factory.
- [x] Select only accepted current
  `professor_attributed_to_paper@canonical-v2-relationship-v1` whose canonical Paper target equals
  the displayed Paper and whose Professor source has an accepted public projection.
- [x] Replay the exact projection candidate, shared assertion, source/target assignments, decision
  input/outcome/decision/current projection, retained reference, both endpoint projections, empty
  roles, observed-at semantics, and both direction-bound eligibility pairs.
- [x] Preserve canonical claim orientation:

```text
subject   = canonical:professor:<returned-professor-id>
predicate = professor_attributed_to_paper
value     = canonical:paper:<displayed-paper-id>
```

- [x] Emit deterministic Professor candidates, union visible endpoint limitations, add only the
  exact later-snapshot quality flag, and then apply `max_candidates`. The Paper eligibility request
  remains the authority for `confirmed|unverified`; Professor status remains `None`.
- [x] Prove no `paper_has_author`, PaperAuthor/name/ORCID/internal-Person/ID-list, Web, or physical-
  store bypass. Preserve open-world omission for a structurally valid but unsupported multi-
  reference relationship.

## Task 5: Extend release-bound postvalidation

- [x] Before delegate/Web effects, validate one displayed Paper/protected set, exact inverse path,
  enumeration, as-of, release, output domain, and presence of the relationship lane.
- [x] Replay the expected inverse output after execution and require exact top-level/fused evidence,
  candidate traces, local trace ownership, constraint receipts, canonical handle, and open-world
  coverage.
- [x] Reject missing/extra/altered/fabricated attribution, endpoint/status/request/result/release/
  direction/decision crosswires, assignment/evidence crosswires, cross-lane ID reuse, displayed
  Paper Web witness, non-local Professor-Paper claims, and forged exhaustive coverage.
- [x] Allow legitimate same-Professor Web fusion. Only local inverse relationship evidence may
  satisfy `displayed_entity_set`; all other constraints apply to the returned Professor.
- [x] Run focused S8R4 GREEN with warnings as errors and record the exact count/time.

Observed final: `1 passed, 61 deselected in 38.63s`. The owner covers exact Canonical Web evidence,
an Accepted `web_candidate` evidence-subject alias, canonical/web-only/unknown-kind crosswires, and
release-bound claim-subject rejection.

## Task 6: Verify and accept

- [x] Run the exact S8R1 literal plus S8R1/S8R2/S8R3/S8R4 matrix.
- [x] Run exact S7K/S8P1/S8P2/S8E1/S8L2/S8R predecessor owners and complete relevant relationship,
  path-eligibility, release, planning, and physical/release-owner tests.
- [x] Run the complete no-external Canonical V2 suite; Ruff check/format-check; Pyright; changed-file
  compile; strict OpenSpec; diff/untracked whitespace; offline lock/wheel/source parity; cache/wheel
  cleanup; frozen-target checks; and secret/forbidden-marker scans.
- [x] Write Candidate receipt/evidence, obtain independent zero-Critical/Important implementation
  and evidence reviews, then mark Accepted and synchronize portfolio/plan/change-log/agent-links.
  Keep Task 8.3 unchecked and the formal ledger `56/80`.

Observed final verification: exact relationship matrix `5 passed, 57 deselected in 158.00s`;
complete no-external Canonical V2 `349 passed, 141 skipped, 3 intentional hostile-serializer
warnings in 192.94s`; complete Ruff/format, changed-file compile, complete Canonical V2 Pyright,
strict OpenSpec, whitespace, package/source parity, frozen-source, and forbidden-action checks pass.

## Invariants

- Planner alias never becomes a canonical predicate or unconditional authorship fact.
- Inverse execution does not reverse the canonical claim orientation.
- Attribution rejection does not alter Paper or Professor existence.
- S8R1/S8R2/S8R3 serialized contracts and hashes remain exact.
- No online canonical mutation, physical relationship read, original source write, provider call in
  required checks, external promotion, or cutover.

## Rollback note

Before acceptance, revert only S8R4-owned additions in the two read modules, owner test, and S8R4
artifacts. No migration, pointer, release, source, or external target rollback is required.

# S8R3 Release-scoped Displayed Professor-to-Paper Traversal Implementation Plan

> **For agentic workers:** use `superpowers:test-driven-development` for RED/GREEN and
> `superpowers:verification-before-completion` before Candidate/Accepted claims. One writer owns the
> two production modules and the vertical test. Do not Commit.

**Goal:** Execute one displayed Professor-to-Paper attribution traversal from an exact S7K release
graph through the existing public `KnowledgeRead.execute` interface.

**Architecture:** Deepen the existing relationship adapter. Reuse S8R2's omission-preserving
enumeration and displayed-source mechanics, but preserve S8R2's literal trace by adding a dedicated
Professor/Paper trace. Replay the shared source relationship assertion, canonical assignments,
decision, current projection, retained evidence, and dual endpoint eligibility entirely in memory.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, uv, Ruff, Pyright, OpenSpec.

## File map

- Modify `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`:
  one exact S8R3 vertical owner and the smallest explicit attribution fixture extension.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`: exact path constant,
  dedicated trace, source-side Professor witness, and traced-output validation.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`: exact path
  dispatch, in-memory shared-decision replay, and release pre/postvalidation.
- Update S8R3 receipt/evidence after Candidate review; keep `tasks.md` and `acceptance.md` unchanged.

## Task 1: Freeze Ready

- [x] Independently review contract semantics/deep-module boundary, implementation feasibility, and
  test matrix.
- [x] Repair Critical/Important only; record Minor/YAGNI without adding gates.
- [x] Mark contract/plan Ready only after zero open Critical/Important, record timestamp and hashes,
  and run strict OpenSpec (`2026-07-19T22:53:22Z`; final contract review
  `C=0/I=0/M=0/YAGNI=0`).

## Task 2: Add and observe one exact RED

- [x] Add `_MissingS8R3ProfessorPaperTraversal` and a contract helper requiring the dedicated trace
  symbol/discriminator. Acquire `tmp_path` and `monkeypatch` only after the seam check.
- [x] Add the exact strict-xfail marker and lazy-fixture function header:

```python
@pytest.mark.xfail(
    raises=_MissingS8R3ProfessorPaperTraversal,
    reason="S8R3 RED: exact Professor-to-Paper traversal seam is absent",
    strict=True,
)
def test_s8r3_executes_release_scoped_professor_to_paper_attribution_traversal(
    request: pytest.FixtureRequest,
) -> None:
    read_module, relationship_factory, release_factory = (
        _s8r3_public_relationship_contract()
    )
    tmp_path = request.getfixturevalue("tmp_path")
    monkeypatch = request.getfixturevalue("monkeypatch")
```
- [x] Build a clean Professor/Paper candidate/index/release graph with one explicit shared source
  relationship assertion, two canonical assignments, one accepted canonical decision/current
  projection, retained evidence registry reference, and two directional eligibility results.
- [x] Freeze positive trace/claim/coverage and bounded zero/negative matrix: authoritative zero,
  no-edge, same Person/PaperAuthor only, rejected/non-current, endpoint excluded/limited, max zero,
  wrong path/type/explicit release binding/evidence/assignment/role, time drift, Web source-witness
  injection, hostile delegate output, and zero physical relationship reads. Add one legitimate
  same-Paper Web fusion
  with a Paper-target exact identifier and one Professor-only negation term; relationship source
  evidence must neither satisfy nor reject the Paper-scoped constraint.
- [x] Add one exact Paper `domain_identity_status` crosswire: trace status must equal the paired
  accepted Paper `PathEligibilityRequest.projection.domain_identity_status`; do not infer it from a
  limitation code.
- [x] Run the exact normal RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r3_executes_release_scoped_professor_to_paper_attribution_traversal -q
```

Expected: exactly `1 xfailed` at `_MissingS8R3ProfessorPaperTraversal`.
Observed: `60 deselected, 1 xfailed in 2.06s` at the exact sentinel.

- [x] Run the exact forced RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider --runxfail \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r3_executes_release_scoped_professor_to_paper_attribution_traversal -q
```

Expected: exactly `1 failed` at `_MissingS8R3ProfessorPaperTraversal` before fixture/effect
acquisition.
Observed: `1 failed, 60 deselected in 1.15s`; failure was only the exact sentinel before
`tmp_path`/`monkeypatch` acquisition.

## Task 3: Carry the exact request and trace contract

- [x] Add `_PROFESSOR_TO_PAPER_QUERY_PATH` without changing existing path constants or serializers.
- [x] Copy `relationship_enumeration_policy` only for this exact path in addition to S8R2; require
  exact representative policy/plan/as-of identity and preserve S8R1/S8R2 literal hashes.
- [x] Add the contract's exact `LocalProfessorPaperRelationshipTrace` field set, discriminator,
  prefixes, sorted/unique rules, empty roles, and hash exclusions. Bind the full shared assertion/
  assignment/decision/current/retained-evidence/endpoint-eligibility chain and exact attribution
  claim without requiring a public-domain `SourceAssertion` alias.
- [x] Extend locator, evidence-item, candidate, constraint-witness, fusion, and ownership validation
  for the new trace. Only its displayed Professor may satisfy `displayed_entity_set`; all other
  constraints apply to the returned Paper.
- [x] Remove the xfail marker once the exact seam exists and observe the next real RED:
  `relationship request path is unsupported` (`1 failed, 60 deselected in 4.14s`, at the exact
  isolated request dispatch after the real release fixture was built).

## Task 4: Implement exact forward traversal

- [x] Add one exact public-path branch inside the existing adapter. Do not create a registry or new
  factory.
- [x] Resolve only current accepted
  `professor_attributed_to_paper@canonical-v2-relationship-v1` whose Professor source equals the
  displayed witness and whose Paper target is an accepted public projection.
- [x] Replay candidate, shared assertion, both assignments, decision input, outcome, shared decision,
  current projection, retained evidence plus public endpoint projections, empty roles, attribution
  metadata, and both endpoint eligibility results exactly.
- [x] Pair each Professor/Paper endpoint result with its exact accepted index request, replay that
  request through `PathEligibilityEngine`, require Professor status `None`, and copy Paper
  `confirmed|unverified` status directly from the paired Paper request into the trace.
- [x] Emit deterministic Paper candidates/claims, sorted limitation/freshness flags, then apply
  `max_candidates`. Cover confirmed and unverified/limited Paper outcomes. Preserve the contract's
  valid-zero/error distinction, including bare current-release-unknown IDs as zero.
- [x] Prove no `paper_has_author`, Person/name/ORCID, `professor_ids`, Web, or physical-store bypass.
- [x] Support exactly one retained assertion reference/no artifacts for this minimal slice. Omit a
  valid multi-reference relation as an open-world unsupported member without corrupting the release
  or claiming exhaustive coverage.
- [x] Scope non-displayed constraints to the returned Paper identity/Paper-scoped evidence even
  after Web fusion; Professor relationship evidence participates only in relationship support and
  the explicit displayed-set witness.

## Task 5: Extend release-bound postvalidation

- [x] Prevalidate exact source/protected set, path, enumeration, as-of, release, and domain before
  delegate/Web effects.
- [x] Replay expected S8R3 output after execution and require exact top-level/fused evidence,
  candidate traces, local trace ownership, constraint receipts, no auxiliary trace, canonical
  handle, and open-world coverage.
- [x] Recheck the paired Professor/Paper eligibility requests/results and reject a trace status or
  request/result/release/projection/direction/decision crosswire.
- [x] Reject missing/extra/altered/fabricated attribution, one S8R3-specific assignment/evidence
  crosswire, cross-lane ID reuse, Professor Web witness, and forged exhaustive coverage while
  allowing legitimate same-Paper Web fusion. Rely on Accepted S6/S7K owners for their full hostile
  matrices rather than copying them.
- [x] Run focused S8R3 GREEN: exactly one pass (`1 passed, 60 deselected in 49.51s`, warnings as errors).

## Task 6: Verify and accept

- [x] Run S8R1 literal + S8R1 + S8R2 + S8R3 exact matrix (`4 passed, 57 deselected`).
- [x] Run exact S7K/S8P1/S8P2/S8E1/S8L2/S8R predecessors (`9 passed, 52 deselected`).
- [x] Run complete physical/release owner, relationship/path/release owners, all KnowledgeRead/query
  planning owners, and complete no-external Canonical V2 suite.
- [x] Run complete Ruff, format `--check`, Pyright, changed-file compile, strict OpenSpec,
  diff/untracked whitespace, offline lock/wheel/source parity, cleanup, frozen-target checks, and
  secret scan.
- [x] Write Candidate receipt/evidence, obtain independent zero-Critical/Important review, then mark
  Accepted and synchronize evidence. Keep Task 8.3 unchecked and formal ledger `56/80`.

## Invariants

- Planner alias does not become canonical predicate or authorship fact.
- Attribution rejection does not alter Paper existence.
- S8R1/S8R2 serialized contracts and hashes remain exact.
- No online canonical mutation, physical relationship read, original source write, or external
  promotion.

## Rollback note

Before acceptance, revert only S8R3-owned additions in the two read modules, owner test, and S8R3
artifacts. No migration, pointer, release, source, or external target rollback is required.

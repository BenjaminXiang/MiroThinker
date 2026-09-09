# Slice Contract: s8l1-release-scoped-exact-lookup-green

## Status

Accepted at `2026-07-16T05:31:12Z`. Exact RED returned `1 xfailed`; forced `--runxfail` returned one
direct `_MissingIsolatedKnowledgeReadModule` failure before the lazy physical fixture was acquired.
GREEN returned `1 passed`; the shared S7/S8 file returned `43 passed, 2 skipped`, the existing
KnowledgeRead owner matrix returned `16 passed`, and complete no-external Canonical V2 returned
`331 passed, 141 skipped, 0 xfailed` with three existing hostile-model serialization warnings.
Complete static/strict/package/source gates passed. The merged review found three Important
query/domain/exclusion gaps; each received an exact regression and targeted repair, and re-review
closed all three with zero new Critical/Important. One naming Minor and one redundant-check YAGNI
remain recorded and nonblocking. The secret-free receipt is under the S8L1 run directory.

The design gate's two predecessors are resolved: Accepted S7I
retains exact-path eligibility outcome/limitations, and this contract binds the reader to the full
Accepted `IsolatedReleaseBundle` rather than trusting a raw same-release target. Task 8.3,
aggregate S8, and the formal ledger remain unchecked at 55/80.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `8.3` (release-scoped exact-lookup predecessor only; remains unchecked)
- Depends on: Accepted S7E lookup/index projection and safe readback, Accepted S7F/S7H release
  parity/publication semantics, Accepted S7I lookup eligibility-lineage correction, and Accepted
  S8RG synthetic `KnowledgeRead` mechanics
- Independent-start authority: this slice uses only a serviceable typed `PublishedRelease`, one
  immutable `IsolatedReleaseBundle`, and the real read-only S7 lookup reader. It does not use the
  pending S2C claim-level corpus as an acceptance oracle.

## Goal

Add one package-internal factory:

```python
create_isolated_exact_lookup_adapter(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
) -> Callable[[LaneRequest], RetrievalLaneResult]
```

The returned adapter shall:

1. Revalidate same-class bundle and publication values and reject before lookup I/O unless the
   publication has one of the two serviceable `PublishedRelease` states (`active` or `rolled_back`)
   and canonical/published/index/bundle/target release identities are exactly equal. A
   `rolled_back` value represents the prior release restored as current by the Accepted S7
   publication contract.
2. Invoke the real `read_isolated_lookup_documents` boundary, which validates the target marker,
   receipt, immutable SQLite readback, manifests, document identities, and release, then require
   exact equality with `release_bundle.index_result.lookup_documents` before mapping any candidate.
3. Expose only `public_domain` Professor, Company, Paper, and Patent lookup documents. Internal
   Person/Technology documents remain available to the later internal-reference adapter and never
   masquerade as a fifth public domain.
4. Match the unique validated exact-lane query text against accepted canonical IDs, full names/
   titles/aliases, and typed identifiers while retaining `query_view` as the view identity. Honor
   target public domains, protected exact-name/identifier slots, displayed-set/excluded-term
   constraints, and the plan candidate bound; other constraints remain visible on `LaneRequest`
   for their existing central owner.
5. Return `RecallCandidate` values through the existing exact lane, with local evidence and a typed
   projection trace binding the bundle target/marker, build manifest, index result, document,
   canonical object, release, projection/schema/policy and eligibility decision, lookup/source
   hashes, publication verification, source evidence, candidate ID, and evidence ID.

## Non-goals

- No structured, lexical, vector, relationship, internal Person/Technology, Web, supplemental, or
  provider production adapter; no multi-view alias/domain rewrite execution beyond the already-
  validated unique exact `LaneQuery`; no full Task 8.3 or aggregate S8 acceptance.
- No second `KnowledgeRead` service/factory, generic storage repository, query parser, global exact-
  field registry, ranking framework, cache, persistence, migration, database/index/source write, or
  release-pointer operation.
- No reviewed S2C case replay, real-provider threshold/latency/cost claim, HTTP/admin/session wiring,
  Commit, Push, PR, archive, promotion, or Cutover.

## Allowed scope

- Add `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` for the exact
  adapter only.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` only to add an optional
  typed local projection trace to `EvidenceItem`; validate lane-query uniqueness/release/lane
  ownership; pass its executable text plus existing plan domains/protected slots/structured
  constraints/candidate bound through `LaneRequest`; and retain all existing serialized fixtures by
  defaults.
- Modify `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`
  only to extract the existing S7E real-target setup into one module-scoped fixture, keep the S7E
  assertions independent, and add one S8L1 vertical public-behavior group using that same real
  target. The shared request may use S7I's already-Accepted helper option to materialize one visible
  exact-path limitation; no S7 assertion is removed or weakened. The import occurs before lazy
  fixture acquisition so RED does not perform the costly build.
- Add this Slice Contract and its implementation plan. Update existing verification/change-log/
  agent-links/portfolio/mainline-plan evidence only after Candidate review. `tasks.md` and
  `acceptance.md` remain unchanged.

## Interface and compatibility constraints

- The public `KnowledgeRead.execute(RetrievalPlan) -> EvidenceSet` and
  `create_ephemeral_knowledge_read(...)` signatures remain unchanged. The new factory is package-
  internal and composes through `lane_adapters={"exact": adapter}`.
- `LaneRequest.query_view` remains the existing view identity (`view:original`) and candidate trace
  behavior remains unchanged. `LaneRequest.query_text` carries the unique matching `LaneQuery` text,
  or the original query only when the plan has no lane query for that lane. Duplicate, cross-release,
  or non-plan lane queries fail plan validation.
- Existing `EvidenceItem` construction/JSON round trips remain valid because local projection trace
  is optional with a `None` default. New exact-adapter evidence must carry the trace.
- Public lookup content is revalidated as the matching typed domain projection and must bind the
  document object/release/domain/source-projection hash before candidate construction. Every local
  trace and evidence/candidate ID is content-bound, and `KnowledgeRead` cross-validates item object,
  domain, lane, release, snippet hash, claim binding, candidate origin evidence, eligibility flags,
  and trace IDs at the adapter trust boundary.
- Input models and reader outputs are revalidated at trust boundaries; malformed, cross-wired,
  non-serviceable-state, unsafe, or cross-release input fails closed rather than degrading to empty
  success. Valid `rolled_back` current-release values remain readable.

## Forbidden changes

- Any production file other than `knowledge_read.py` and the new isolated adapter; any migration,
  provider, S7 builder/reader/publication behavior, Accepted assertion value, public domain list,
  Product-capability relationship, or original/retained index target.
- Test-local adapter implementation, monkeypatched positive readback, copied portable lookup binary,
  imported private helper from another test module, weakened S7 assertion, broad exception masking,
  `importorskip`, runtime `pytest.xfail`, live network/credential use, or URL/source-path identity.
- Rejecting a valid `rolled_back` publication, reading a cross-release publication, returning
  internal auxiliary documents on the exact public lane, trusting a raw target or physical scalar
  metadata without bundle/typed-content binding, or inventing source authority/claims absent from
  the lookup projection.

## Expected unchanged behavior

- The existing S7E real readback test retains its current assertions and uses the same real marked
  target, Milvus-Lite build, SQLite lookup readback, active-pointer neutrality, and original-Milvus
  hash check; setup ownership moves to a shared fixture and one S7I-Accepted exact limitation is
  included so S8 can prove its visible propagation through a physical read.
- All 16 Accepted S8RG KnowledgeRead owner groups remain GREEN. S9/S10 and original PostgreSQL,
  Milvus, forensic sources, candidate/index state, and active pointers remain unchanged.
- Before GREEN, the new vertical group is exactly one strict xfail and forced execution exposes one
  exact missing-target sentinel without acquiring the physical fixture. After GREEN, it passes
  without xfail/skip and complete no-external Canonical V2 gains exactly one passing group.

## Required checks

- RED: focused normal execution is exactly `1 xfailed`; `--runxfail` is exactly one failure caused
  by `_MissingIsolatedKnowledgeReadModule` for the absent exact target module, and the lazy shared
  physical fixture is not acquired.
- GREEN: focused S8L1 execution is exactly `1 passed`. It proves real marked-target readback and
  exact bundle snapshot parity, active-release equality, exact lane-request propagation, name/
  identifier/domain/bound behavior, candidate/evidence/projection trace identity, eligibility
  limitation retention, internal-auxiliary exclusion, cross-release and hostile same-class fail-
  before-read behavior, valid rolled-back service, snapshot mismatch rejection, and unsafe/unmarked
  target refusal.
- The complete shared S7/S8 test file is exactly `43 passed, 2 skipped` under the current no-
  disposable-database environment (S7I baseline `42 passed, 2 skipped` plus one S8L1 group); the
  existing 16-group KnowledgeRead owner matrix remains `16 passed`.
- Complete no-external Canonical V2 is expected to be exactly `331 passed, 141 skipped, 0 xfailed`
  absent concurrent work; any actual count is recorded rather than forced.
- Scoped Ruff check/format, `py_compile`, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, scope/high-confidence-secret/generated-cache, fresh offline wheel content, and
  frozen original-source checks pass.
- One merged independent implementation/test-integrity review ends with zero open Critical/
  Important findings. Minor/YAGNI is recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md` and `agent-links.md`.
- `.agents/portfolio.md` and the current code-grounded mainline plan.
- A secret-free receipt under `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8l1/` with exact
  commands/results, file hashes, review outcome, package/source checks, and next Ready action.

## Stop conditions

- Correct behavior requires changing a public `KnowledgeRead` method, S7 projection/publication
  contract, migration/schema, release pointer, provider, or product semantics not frozen here.
- The real marked lookup target cannot be read without mutating it, or release/marker/content parity
  cannot fail closed before candidate output.
- The shared S7 test loses an Accepted assertion, any existing KnowledgeRead owner regresses, an
  internal auxiliary appears as a public candidate, or a Critical/Important finding remains open.
- The slice would need to claim lane-specific rewrite, full Task 8.3, aggregate S8, or reviewed-corpus
  acceptance rather than this independently observable exact adapter.

## Done means

- The RED group fails for the exact missing boundary, then passes through the real S7 lookup target
  and existing `KnowledgeRead` composition with complete release/projection/evidence traceability.
- All Required checks and one independent review pass with zero open Critical/Important findings;
  evidence and rollback are persisted.
- S8L1 is Accepted as a Task 8.3 predecessor only. Task 8.3 and aggregate S8 remain open, and the
  formal ledger remains exactly 55/80.

## Rollback note

Remove `knowledge_read_isolated.py`, the additive optional trace/request fields, the S8L1 group,
and restore the S7E test's inline fixture setup; then remove only S8L1 evidence/status deltas. No
database, index, source, release pointer, public interface, or task checkbox requires rollback.

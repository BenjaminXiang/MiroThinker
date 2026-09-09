# S8C Aggregate KnowledgeRead Runtime Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` only after this plan becomes Ready. Use
> `superpowers:test-driven-development` for RED/GREEN and
> `superpowers:verification-before-completion` before Candidate/Accepted claims. Steps use checkbox
> syntax for tracking. One writer owns the production composition seam and vertical owner. Do not
> Commit.

**Goal:** Close Tasks 8.3, 8.5, and 8.7 through one real release-bound `KnowledgeRead` composition
while reusing all Accepted retrieval, fusion, Web-handle, sufficiency, enumeration, and supplemental
mechanics.

**Architecture:** Extend the existing isolated-release factory with optional typed pass-through
ports already supported by `create_ephemeral_knowledge_read`. Admit that existing delegate's
lane-free handle replay under the wrapper's exact release binding through one finite validator
branch. Add one vertical integration owner over the final Accepted S8R5 release fixture, then
combine it with the Accepted detailed owner matrix as aggregate runtime evidence. Do not add a new
provider layer or change retrieval/replay algorithms.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, uv, Ruff, Pyright, OpenSpec.

---

## State gate

This plan is **Ready** at `2026-07-20T09:43:54Z` after S8R5 acceptance, strict OpenSpec, and one
lean independent review with `C=0/I=0/M=0/YAGNI=0`. Reviewed Specified hashes are contract
`2b0fc7af1fdfe99131087095ee7eb999c6cb00cb345d9dde7d987242dcee44d5`, plan
`cc9e8033747dfb674fa0022a015c697eb695183c2b3526abd8cef9296e67196c`, and audit
`1f5b5a629e1dc8af207e402a9cabc31c5a41c629259775d101c691d06b958e81`.

- [x] S8R5 Slice Contract says Accepted and its verification receipt says Accepted.
- [x] One lean S8C contract/plan review reports zero open Critical/Important.
- [x] Minor/YAGNI findings are recorded as non-blocking without another review loop.
- [x] Strict OpenSpec validation exits `0`.
- [x] Reviewed Specified contract/plan hashes and a UTC timestamp are recorded in the Ready
  transition.

Execution moved to **In Progress**. The exact seven-port RED passed its contract. A real second RED
then showed that an otherwise-valid handle replay is rejected only after the isolated release
binding makes it planner-owned. At `2026-07-20T10:00:21Z` the writer was paused; the plan was
minimally revised to fix that public-path admission instead of invoking a captured internal
delegate. The displayed-Patent protection correctly excludes an unrelated Web-only group, so S8C
reuses Accepted S8RF handle-creation evidence and proves replay/resolution through the public
release-bound service.

The targeted re-plan review closed its one session-boundary Important and reported `C=0/I=0` at
`2026-07-20T10:10:51Z`. Reviewed pre-recording hashes were contract
`c67b1b92b4665f75f9a73c55e7fc147867581090b5feaafb66038ab2ff23aa74`, plan
`c37f1563aaa6bb4c93e8c1c84b41a5cc34764f4501bf3df81a819cd01579e7a3`, and audit
`685685f2bac5e7931556d320b5ded1a204b4f947128c765653f64a5a2a6bbe9f`.

This plan reached **Candidate** at `2026-07-20T10:49:57Z` and **Accepted** at
`2026-07-20T10:50:22Z`. The final review closed its only TTL-observability Important through the
public negative-TTL probe and reports `C=0/I=0/M=0`. Tasks 8.3/8.5/8.7 close atomically at `59/80`;
Tasks 8.1/8.8 remain open.

S2C is not a Ready gate for S8C. It remains the gate for Task 8.1 calibration and Task 8.8 aggregate
acceptance only. No Commit, Push, PR, Archive, promotion, or Cutover step belongs to this plan.

## File map

- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`: add only the
  optional callback/TTL imports, factory parameters, and delegate pass-through arguments.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`: add only the finite
  planner-owned `handle_replay` validation branch required for public release-bound replay.
- Modify `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`:
  add one strict RED/GREEN S8C release-bound vertical owner reusing the final Accepted S8R5 graph.
- Add `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8c/verification-receipt.json` only after
  Candidate evidence exists.
- Update the S8C audit/contract/plan and existing verification/status artifacts only after evidence.
  Check Tasks 8.3/8.5/8.7 together only at acceptance; leave Tasks 8.1/8.8 open.

## Task 1: Confirm dependencies and freeze Ready

- [x] Read the S8R5 Slice Contract and receipt directly. Stop if either lacks `Accepted` status or
  their final hashes disagree.
- [x] Recheck the current signatures of `create_ephemeral_knowledge_read` and
  `create_isolated_release_knowledge_read`. Confirm the former still owns all seven optional ports
  and the latter still lacks only their pass-through.
- [x] Confirm the four public relationship owner directions are Accepted: Company-to-Patent,
  Patent-to-Company, Professor-to-Paper, and Paper-to-Professor.
- [x] Run:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
```

Expected: exit `0`.

- [x] Complete one lean read-only review of the S8C audit/contract/plan. Repair only open Critical/
  Important findings; record Minor/YAGNI as non-blocking.
- [x] Freeze the reviewed hashes and mark the S8C contract/plan Ready. Do not change production,
  tests, `tasks.md`, or `acceptance.md` in this task.

## Task 2: Write and observe one exact RED

**Test:**
`apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] Add `_MissingS8CAggregateRuntimeClosure` and one seam helper that imports the exact isolated
  read module, resolves `create_isolated_release_knowledge_read`, and inspects its public keyword
  parameters.
- [x] Require exactly these existing composition inputs before acquiring any fixture/effect:

```python
{
    "identity_fuser",
    "reranker",
    "sufficiency_decider",
    "supplemental_search",
    "web_handle_resolver",
    "accepted_identity_lookup",
    "web_handle_ttl",
}
```

- [x] Add one strict-xfail owner named:

```python
def test_s8c_closes_release_bound_knowledge_read_runtime(
    request: pytest.FixtureRequest,
) -> None:
    ...
```

- [x] Resolve the seam before `request.getfixturevalue`, release construction, physical reads,
  embedding, Web calls, or callback invocation.
- [x] Run normal RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8c_closes_release_bound_knowledge_read_runtime -q
```

Expected: exactly `1 xfailed`, zero failures/errors/XPASS.

- [x] Run forced RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider --runxfail \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8c_closes_release_bound_knowledge_read_runtime -q
```

Expected: exactly `1 failed`; the only failure is `_MissingS8CAggregateRuntimeClosure` naming the
missing release-bound port set before any fixture/effect is acquired.

## Task 3: Implement the minimal composition delta

**Production:**
`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`

- [x] Import `timedelta` and the existing request types used only for annotations:
  `IdentityFusionRequest`, `RerankRequest`, `SufficiencyDecisionRequest`, `SupplementalRequest`,
  `WebHandleResolutionRequest`, and `AcceptedIdentityLookupRequest`.
- [x] Extend `create_isolated_release_knowledge_read` with these optional parameters, preserving
  every existing parameter/default and keeping the physical adapter map caller-hidden:

```python
identity_fuser: Callable[[IdentityFusionRequest], object] | None = None
reranker: Callable[[RerankRequest], object] | None = None
sufficiency_decider: Callable[[SufficiencyDecisionRequest], object] | None = None
supplemental_search: Callable[[SupplementalRequest], object] | None = None
web_handle_resolver: Callable[[WebHandleResolutionRequest], object] | None = None
accepted_identity_lookup: Callable[[AcceptedIdentityLookupRequest], object] | None = None
web_handle_ttl: timedelta = timedelta(hours=1)
```

- [x] Pass those seven values unchanged to the existing `create_ephemeral_knowledge_read` call.
  Reuse its validation, content-binding, degradation, and execution behavior. Add no wrapper,
  registry, provider client, fallback, or new public service.
- [x] Do not expose `lane_adapters` or change `_ReleaseBoundKnowledgeRead.execute`. The observed
  integration RED authorizes only the finite planner-owned `handle_replay` branch in
  `knowledge_read.py`; any other shared change requires another stop/re-plan.
- [x] Remove only the S8C strict-xfail marker after the exact seam exists, then rerun the focused
  owner. The expected next failure is an unimplemented vertical assertion/fixture, not a legacy
  contract or unrelated test.

## Task 3B: Observe and close the release-bound replay admission RED

- [x] In the same S8C owner, construct a content-bound `handle_replay` plan using the exact
  `PlanningReleaseBinding` from the Accepted S8R5 plan. Before another production edit, run the
  focused owner and record the only new real RED:

```text
Value error, planner-owned plan has an unsupported interaction mode
```

- [x] Add one explicit `handle_replay` branch to `RetrievalPlan`'s existing planner-owned validator.
  It must require no lanes, `web_required=False`, `freshness_material=False`, disabled Web policy,
  no assessment intent, no material parts, a non-empty `session_id`, and exact equality between that
  ID and every retained/replayed handle's `session_id`, then return the validated model. Reuse the
  existing retained-handle/replay/session/operation fields and execution algorithm; add no field or
  serializer.
- [x] Add negative assertions that a release-bound replay cannot smuggle a lane, Universal Web,
  freshness, assessment, material-part execution, an empty session, or a cross-session handle.
  These fail during model validation before any service effect.

## Task 4: Complete the single release-bound vertical owner

**Test:**
`apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] Reuse the final Accepted S8R5 scenario/authority, isolated release bundle, index request,
  institution catalog, publication, and recorded embedding adapter. Do not create a second
  Company/Patent relationship graph or provider framework.
- [x] Derive one exact release-bound `RetrievalPlan` with all seven lanes:

```python
(
    "exact",
    "structured",
    "lexical",
    "vector",
    "relationship",
    "internal_reference",
    "web",
)
```

  Preserve its `PlanningReleaseBinding`, protected displayed Patent, representative relationship
  enumeration, material parts, constraints, lane-query bindings, and finite budgets. Use the
  Accepted Patent-to-Company path; do not invent another relationship direction.
- [x] Wrap two independent real lane ports with the same bounded `threading.Barrier` pattern already
  used by S8RF, while leaving their actual adapter bodies intact. Assert overlap without asserting
  executor type, worker count, private call order, or wall-clock performance.
- [x] Provide bounded recorded current-Web bytes containing one canonical corroboration candidate
  for the displayed-Patent execution. Assert accepted content hashes/snapshot receipts and
  local/Web source distinction. Reuse the Accepted S8RF matrix for distinct Web-only handle
  creation; the protected displayed-Patent slot must not be weakened to admit an unrelated entity.
- [x] Inject recorded, content-bound callbacks through the release factory:

```text
identity_fuser -> aggregates same accepted identity and retains evidence IDs
reranker -> selects only an existing eligible fused identity
sufficiency_decider -> marks one material part supported and one missing
supplemental_search -> targets only the missing part within the plan budget
web_handle_resolver + accepted_identity_lookup -> resolve one replayed live handle read-only
```

  Assert each request carries the exact release/plan/evidence identity expected by its existing
  model and each recorded proposal is schema/content-bound. Do not assert private helper calls.
- [x] Assert the first execution returns all seven successful lane traces, complete candidate/
  evidence lineage, fusion before constraint/rerank receipts, representative enumeration, updated
  material-part sufficiency, supplemental budget receipt, best-evidence retention, and typed partial
  continuation if a part remains unresolved.
- [x] Execute a second content-bound `handle_replay` plan through the same public release-bound
  service with the original release binding and retained snapshot bytes. Use a recorded handle shape
  from the Accepted S8RF contract; do not capture or invoke the internal delegate. Assert the
  resolution receipt says `read_only=True`, retains original handle/snapshot lineage, and records no
  canonical/source-map/index mutation.
- [x] Assert the isolated target hashes, original Milvus hash, active release pointer snapshot, and
  source inventory are unchanged before/after both executions.
- [x] Run focused GREEN:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -W error \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8c_closes_release_bound_knowledge_read_runtime -q
```

Expected: exactly `1 passed`, no xfail/skip/warning.

## Task 5: Prove aggregate task coverage without duplicating owners

- [x] Run the detailed mechanics owners:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_knowledge_read_retrieval_fusion_contract.py \
  tests/canonical_v2/test_knowledge_read_atomic_green_contract.py \
  tests/canonical_v2/test_knowledge_read_sufficiency_retry_contract.py -q
```

Expected: exit `0`; every selected test passes with no xfail/XPASS. This is the detailed Task
8.3/8.5/8.7 mechanics evidence, including seven-lane overlap, tamper/expiry/read-only resolution,
all enumeration modes, all budget axes, and partial continuation.

- [x] Run the physical/release-bound owners, including the new S8C node:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k 's8e1 or s8l1 or s8l2 or s8l3 or s8v1 or s8v2 or s8ir1 or s8r1 or s8r2 or s8r3 or s8r4 or s8r5 or s8c' -q
```

Expected: exit `0`; every selected S8 node passes with no xfail/XPASS.

- [x] From that result record an explicit mapping showing:

```text
Task 8.3 -> seven release-bound lane traces + Accepted L/V/IR/R physical owners
Task 8.5 -> release-bound port invocation + Accepted fusion/constraint/rerank/handle matrix
Task 8.7 -> release-bound port invocation + Accepted sufficiency/enumeration/budget matrix
```

- [x] Record the four supported public relationship directions and the Accepted zero/gap cases.
  Verify no test or runtime output treats an unsupported/insufficient-evidence direction as a fact.

## Task 6: Run proportional verification and lean review

- [x] Run the complete no-external Canonical V2 command preserved in the latest Accepted S8R5
  receipt. Expected: exit `0`, zero failures; only documented external skips remain.
- [x] Run static checks:

```bash
cd apps/miroflow-agent
uv run ruff check src/data_agents/canonical_v2 tests/canonical_v2
uv run ruff format --check \
  src/data_agents/canonical_v2/knowledge_read_isolated.py \
  tests/canonical_v2/test_internal_reference_projection_contract.py
./.venv/bin/python -m py_compile \
  src/data_agents/canonical_v2/knowledge_read_isolated.py \
  tests/canonical_v2/test_internal_reference_projection_contract.py
```

Expected: every command exits `0`.

- [x] Run the complete Canonical V2 Pyright command/configuration preserved in the Accepted S8R5
  receipt. Expected: `0 errors`.
- [x] Run repository gates:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Expected: both exit `0`.

- [x] Run the established scope, secret, generated-cache, package-content, frozen-source, original
  PostgreSQL/Milvus/source-hash, and no-online-write checks from the Accepted S8R5 receipt. Expected:
  every gate exits `0` and all protected hashes/pointers remain exact.
- [x] Perform one lean implementation/test-integrity review. Repair open Critical/Important only;
  record Minor/YAGNI without another review loop. Rerun the smallest affected checks after any
  repair.

## Task 7: Candidate, Accepted, and ledger closure

- [x] Record exact RED/GREEN commands/results, changed-file hashes, dependency hashes, aggregate
  owner results, static/gate results, protected-source hashes, and review disposition in a new
  `s8c/verification-receipt.json`.
- [x] Mark the S8C contract Candidate only after all required evidence exists. Do not check tasks at
  Candidate.
- [x] Recheck the final diff is limited to the two implementation files plus authorized S8C/status/
  evidence files and contains no Accepted predecessor-slice edit.
- [x] With zero open Critical/Important, mark S8C Accepted and atomically change only Tasks 8.3,
  8.5, and 8.7 from unchecked to checked. Record the formal ledger transition `56/80 -> 59/80` in
  `acceptance.md`, `change-log.md`, `agent-links.md`, verification evidence, portfolio, and current
  convergence/mainline status.
- [x] Explicitly retain Tasks 8.1 and 8.8 as unchecked and state that S2C/calibrated claim-level
  acceptance remains pending. Do not claim aggregate S8 acceptance.
- [x] Run strict OpenSpec and `git diff --check` once more. Expected: both exit `0`.

## Rollback checkpoint

If S8C cannot reach Candidate, remove the new S8C test, revert the optional imports/parameters/
delegate arguments in `knowledge_read_isolated.py`, and remove the finite planner-owned replay
branch from `knowledge_read.py`; leave Tasks 8.3/8.5/8.7 unchecked at `56/80`. If accepted evidence
is later invalidated, revert S8C status/evidence and uncheck those same three tasks. No database,
index, source, provider, release pointer, Commit, Push, PR, Archive, promotion, or Cutover rollback
is required.

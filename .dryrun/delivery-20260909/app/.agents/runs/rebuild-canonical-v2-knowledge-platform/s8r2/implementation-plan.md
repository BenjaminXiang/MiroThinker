# S8R2 Release-scoped Displayed Company-to-Patent Traversal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:test-driven-development` for the
> RED/GREEN sequence and `superpowers:verification-before-completion` before Candidate/Accepted
> claims. Execute inline with one writer because the two production modules and owner test are
> shared with S8R1. Do not Commit.

**Goal:** Execute one displayed Company-to-Patent applicant traversal from an exact S7K release
graph through the existing public `KnowledgeRead.execute` interface.

**Architecture:** Deepen the existing relationship adapter. Structured displayed IDs remain the
source-Company authority; one optional enumeration-policy copy carries scope/as-of/enumeration to
the public-path adapter. The adapter reverse-traverses exact current `patent_has_applicant`
relations, emits a separate canonical public relationship trace, and reuses the release wrapper
for hostile postvalidation without adding a second seam or opening storage.

**Tech Stack:** Python 3.12, Pydantic v2 contracts, pytest, uv, Ruff, Pyright, OpenSpec.

---

## File map

- Modify `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`:
  one S8R2 vertical owner and the smallest default-off Patent applicant fixture input.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`: omission-preserving
  relationship enumeration policy, canonical public relationship trace, source-side displayed-set
  witness, and traced-output validation.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`: exact public
  path dispatch, in-memory reverse traversal, and release pre/postvalidation.
- Update S8R2 receipt/evidence only after Candidate review; keep `tasks.md` and `acceptance.md`
  unchanged.

## Task 1: Review and freeze the Specified contract

- [x] Dispatch independent contract/deep-module and test-feasibility reviews.
- [x] Repair only Critical/Important findings; record Minor/YAGNI without new gates.
- [x] Mark the contract Ready only after all three targeted re-reviews report zero open
  Critical/Important (`2026-07-19T20:58:25Z`; final C=0/I=0/M=0/YAGNI=0).
- [x] Run:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
```

Expected: exit `0`.

## Task 2: Write and observe the exact RED

- [x] Add `_MissingS8R2PublicRelationshipTraversal` and resolve these missing seams before acquiring
  `tmp_path` or `monkeypatch`:

```python
required_lane_fields = {"relationship_enumeration_policy"}
required_symbols = {"LocalCanonicalRelationshipTrace"}
```

- [x] First add `test_s8r1_relationship_request_and_trace_literal_compatibility` and capture the
  current fixed LaneRequest JSON/SHA-256 plus one fixed `LocalRelationshipTrace` JSON/SHA-256. Assert
  the new field name is absent. Run it before production changes:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -W error \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r1_relationship_request_and_trace_literal_compatibility -q
```

Expected: exactly `1 passed`.
- [x] Add the strict marker and lazy fixture order exactly:

```python
@pytest.mark.xfail(
    raises=_MissingS8R2PublicRelationshipTraversal,
    reason="S8R2 RED: exact public relationship traversal seam is absent",
    strict=True,
)
def test_s8r2_executes_release_scoped_company_to_patent_relationship_traversal(
    request: pytest.FixtureRequest,
) -> None:
    read_module, relationship_factory, release_factory = _s8r2_public_relationship_contract()
    tmp_path = request.getfixturevalue("tmp_path")
    monkeypatch = request.getfixturevalue("monkeypatch")
```

- [x] After resolving the missing seams, build a default-off Patent applicant subobject/source
  assertion, a clean combined-registry `patent_has_applicant@v1`
  candidate/assertion/decision/retained-reference set, exact candidate/index/release bundle, and a
  real release-bound planner plan with
  `domains=("patent",)`, one displayed Company, the exact public path, relationship+Web lanes, no
  internal query, and the exact open-world `representative` enumeration shape.
- [x] Freeze positive result/trace/coverage; direct-versus-wrapper source semantics; authoritative-
  zero, valid-source-no-edge, excluded, max-zero, and legacy-zero cases; duplicate/missing/mismatched
  protected sets; path/policy/as-of drift; type/version/orientation/role/candidate/outcome/typed-
  assertion/decision/evidence/projection negatives; Company/Patent excluded and limited cases with
  sorted/unique limitation union; later-snapshot disclosure; hostile source-witness/delegate output;
  and zero physical relationship reads. Reuse existing S6/S7K hostile matrices rather than copy them.
- [x] Run the unchanged S8R1 owner first:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -W error \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r1_release_scoped_technology_relationship_traversal -q
```

Expected: exactly `1 passed`.

- [x] Run normal S8R2 RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r2_executes_release_scoped_company_to_patent_relationship_traversal -q
```

Expected: exactly `1 xfailed` at `_MissingS8R2PublicRelationshipTraversal`.

- [x] Run forced RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider --runxfail \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r2_executes_release_scoped_company_to_patent_relationship_traversal -q
```

Expected: exactly one failure at the missing seam before fixture/effect acquisition.

## Task 3: Carry public relationship policy, trace, and source witness

- [x] Add the single omission-preserving field exactly:

```python
class LaneRequest(_ContentModel):
    relationship_enumeration_policy: EnumerationPolicy | None = None
```

- [x] Extend the LaneRequest serializer to omit `relationship_enumeration_policy` when `None`.
  Populate it only for the exact four-axis S8R2 path. Reject it on another lane/path and require the
  exact representative/open-world shape plus plan/policy/as-of identity. Keep S8R1 and every legacy
  lane byte-identical against the fixed pre-change literals.
- [x] Add `LocalCanonicalRelationshipTrace(path="canonical_relationship_traversal")` as a new union
  variant with the exact lineage fields in the contract, including candidate/outcome/typed assertion,
  policy/protected source, and two direction-bound eligibility pairs. Derive distinct candidate/
  evidence/trace hashes and reject orientation, applicant-role, claim, projection, eligibility, or
  release drift.
- [x] Add explicit locator/item/candidate validation and a narrowly scoped displayed-set witness:
  only a validated canonical-relationship trace may supply its Company ID for
  `displayed_entity_set`; every other constraint still sees the returned Patent. Reject mixed,
  forged, duplicate, unrelated-lane, Web, and untraced witnesses. Do not weaken synthetic
  predecessor compatibility or S8R1.
- [x] Once the missing field/symbol exist, remove the xfail marker and rerun. The next observed RED
  must be the real `relationship request path is unsupported` failure, not another xfail.

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r2_executes_release_scoped_company_to_patent_relationship_traversal -q
```

Expected: exactly `1 failed` at `relationship request path is unsupported`, after which the exact
public-path branch is the only missing behavior.

## Task 4: Implement exact in-memory reverse traversal

- [x] Add exact private constants/branch inside `knowledge_read_isolated.py`; do not introduce a
  one-entry registry:

```python
_COMPANY_TO_PATENT_QUERY_PATH = (
    "company_has_patent",
    "company_to_patent",
    "company",
    "patent",
)
_PATENT_APPLICANT_TYPE = ("patent_has_applicant", "canonical-v2-relationship-v1")
_PATENT_APPLICANT_ROLE = "applicant"
```

- [x] Split request validation by exact Technology versus exact public path behind the same private
  relationship authority. Public validation requires zero relationship-reference queries, one
  displayed Company ID, the exact representative enumeration policy, and matching protected set
  before effects. Freeze the distinct direct-adapter and public-wrapper zero/error matrix.
- [x] Resolve only exact current canonical relations whose Patent source, Company target, applicant
  role, projection candidate, typed assertion/source record, outcome, typed/current decision,
  selected evidence, retained assertion, SourceAssertion/source record, applicant subobject, public
  projections, and both eligibility pairs replay exactly. Company eligibility must bind
  `company_to_patent`; Patent eligibility must bind `patent_to_company`; both bind the current
  decision. Reject owner/assignee/inventor, organization/person applicant, review/invalid outcomes,
  cross-release, and partial/cross-wired evidence.
- [x] Emit deterministic Patent candidates with exact canonical claim orientation, limitations, and
  snapshot flag, then apply `max_candidates`. Sort/deduplicate the two endpoints' limitations. Return
  zero for the contract's authoritative-empty, no-match, excluded, unknown-direct, and max-zero
  cases; reject invalid public-wrapper source authority before effects.
- [x] Keep `create_isolated_relationship_lookup_adapter` as the sole factory and perform no physical
  relationship, lookup, vector, Postgres, Milvus, Web, or provider read.

## Task 5: Extend release-bound pre/postvalidation

- [x] Before delegate/Web execution, verify the public path, displayed/protected source set,
  relationship enumeration policy, plan/policy/as-of identity, representative-only shape, and
  release authority. Unknown public IDs yield local zero; known invalid/missing/duplicate authority
  fails before effects.
- [x] After delegate execution, replay expected public relationship output in memory and require
  exclusive ownership of every expected raw ID, evidence ID, canonical trace, fused Patent identity,
  required quality flag, and canonical handle while allowing unrelated legitimate other-lane
  evidence.
- [x] Build hostile values with `model_validate` and recompute every content-derived identity. Reject
  missing/extra/altered public relationship evidence, auxiliary trace, fused ownership, duplicate
  trace ownership, source-witness inheritance, canonical/Web handle, or a fabricated relation.
- [x] Assert top-level enumeration coverage remains representative/open-world/non-exhaustive with
  continuation required; reject every exhaustive, required-member, or finite-universe policy before
  delegate/Web effects.
- [x] Run focused GREEN:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -W error \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r2_executes_release_scoped_company_to_patent_relationship_traversal -q
```

Expected: exactly `1 passed`.

## Task 6: Proportional regression and verification

- [x] Run exact S7K/S8P1/P2/S8E1/S8L2/S8R1/S8R2 predecessors and record actual counts:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k 'release_bundle_binds_exact_relationship_publication_authority_before_effects or release_scoped_query_planner or s8p2_release_bound_planner or s8e1_release_bound_knowledge_read or release_scoped_structured_lookup or s8r1_release_scoped_technology_relationship or s8r2_executes_release_scoped_company_to_patent_relationship_traversal' -q
```

- [x] Run the complete physical/release owner:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py -q
```

- [x] Run relationship projection plus release-publication owners:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_relationship_projection_contract.py \
  tests/canonical_v2/test_release_publication_interface.py -q
```

- [x] Run all KnowledgeRead/query-planning owners:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_knowledge_read_atomic_green_contract.py \
  tests/canonical_v2/test_knowledge_read_interface.py \
  tests/canonical_v2/test_knowledge_query_planning_contract.py \
  tests/canonical_v2/test_knowledge_read_universal_web_contract.py \
  tests/canonical_v2/test_knowledge_read_sufficiency_retry_contract.py \
  tests/canonical_v2/test_knowledge_read_retrieval_fusion_contract.py -q
```

- [x] Run the complete no-external Canonical V2 suite and record exact pass/skip/warning counts:

```bash
cd apps/miroflow-agent
env \
  -u CANONICAL_V2_TEST_DATABASE_URL \
  -u CANONICAL_V2_TEST_EXPECTED_DATABASE \
  -u CANONICAL_V2_TEST_TARGET_KIND \
  -u CANONICAL_V2_TEST_BACKUP_GATE_ROOT \
  -u ALEMBIC_DATABASE_URL \
  -u ALEMBIC_EXPECTED_DATABASE \
  -u CANONICAL_V2_BACKUP_GATE_ROOT \
  -u DATABASE_URL \
  -u DATABASE_URL_TEST \
  uv run pytest -o addopts='' -p no:cacheprovider tests/canonical_v2 -q
```

- [x] Run complete Ruff, format, and changed-file compile checks:

```bash
cd apps/miroflow-agent
uv run ruff check src/data_agents/canonical_v2 tests/canonical_v2
uv run ruff format --check src/data_agents/canonical_v2 tests/canonical_v2
./.venv/bin/python -m py_compile \
  src/data_agents/canonical_v2/knowledge_read.py \
  src/data_agents/canonical_v2/knowledge_read_isolated.py \
  tests/canonical_v2/test_internal_reference_projection_contract.py
```

- [x] Run complete Canonical V2 Pyright with the same reviewed configuration used by S8R1:

```bash
cd apps/miroflow-agent
./.venv/bin/pyright -p /tmp/s8rg-pyrightconfig.json \
  src/data_agents/canonical_v2 tests/canonical_v2
```

- [x] From the worktree root, run strict OpenSpec and diff checks:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

- [x] Run offline lock/build/source parity. Use a fresh S8R2-owned output directory, record its path,
  wheel SHA-256, entry count, and the two source/entry SHA-256 pairs, then prove no test or `.agents`
  path is packaged:

```bash
cd apps/miroflow-agent
uv lock --check --offline
S8R2_WHEEL_DIR="$(mktemp -d /var/tmp/canonical-v2-s8r2-wheel-XXXXXX)"
uv build --offline --wheel --out-dir "$S8R2_WHEEL_DIR"
S8R2_WHEEL="$(find "$S8R2_WHEEL_DIR" -maxdepth 1 -type f -name '*.whl' -print -quit)"
sha256sum "$S8R2_WHEEL" \
  src/data_agents/canonical_v2/knowledge_read.py \
  src/data_agents/canonical_v2/knowledge_read_isolated.py
unzip -Z1 "$S8R2_WHEEL" > "$S8R2_WHEEL_DIR/entries.txt"
! rg -n '(^|/)(tests|\.agents)/' "$S8R2_WHEEL_DIR/entries.txt"
unzip -p "$S8R2_WHEEL" \
  src/data_agents/canonical_v2/knowledge_read.py \
  > "$S8R2_WHEEL_DIR/knowledge_read.py"
unzip -p "$S8R2_WHEEL" \
  src/data_agents/canonical_v2/knowledge_read_isolated.py \
  > "$S8R2_WHEEL_DIR/knowledge_read_isolated.py"
cmp src/data_agents/canonical_v2/knowledge_read.py "$S8R2_WHEEL_DIR/knowledge_read.py"
cmp src/data_agents/canonical_v2/knowledge_read_isolated.py \
  "$S8R2_WHEEL_DIR/knowledge_read_isolated.py"
sha256sum "$S8R2_WHEEL_DIR/knowledge_read.py" \
  "$S8R2_WHEEL_DIR/knowledge_read_isolated.py"
```

- [x] Re-run the accepted read-only frozen-target checkpoint. Record the exact original Milvus
  SHA-256, `pgtest` paused/running state, volume identity and host port, recovery-lab network/ports/
  restart policy, branch, and HEAD. If an isolated active-pointer DSN is still absent, record that
  the pointer readback remains not applicable; do not connect to or mutate the original target:

```bash
cd /home/longxiang/MiroThinker/.worktrees/canonical-v2-s2
git branch --show-current
git rev-parse HEAD
docker inspect pgtest --format \
  '{{.State.Status}} {{.State.Paused}} {{.State.Running}} {{range .Mounts}}{{.Name}} {{end}}{{json .HostConfig.PortBindings}}'
docker inspect pgtest-recovery-lab-01 --format \
  '{{.HostConfig.NetworkMode}} {{json .HostConfig.PortBindings}} {{.HostConfig.RestartPolicy.Name}}'
sha256sum apps/miroflow-agent/milvus.db
```

Expected: branch `canonical-v2-s2-baseline`, HEAD
`f0e6224e1c675c6d6c58993676783b2fbe0cd8f6`, original Milvus SHA-256
`43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`, `pgtest` paused on volume
`d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`, and recovery lab
network-none/no-port. Record its observed restart policy against the Accepted checkpoint; a missing
named recovery-lab container must be recorded explicitly, not replaced by probing a production-like
target.
- [x] Compare the final slice-owned file set with the Ready checkpoint, scan only that set for
  high-confidence credential assignments and stale S8R2 xfail markers, and inventory newly generated
  cache files. Record exact commands/results in the receipt before cleanup; do not broaden into a
  repository-wide secret dump.
- [x] Record package hashes before removing only S8R2-owned generated outputs.

## Task 7: Independent review and acceptance

- [x] Dispatch independent spec-compliance and code-quality reviews against the Ready contract.
- [x] Close each Critical/Important with an exact review-driven RED, minimal repair, GREEN, and
  targeted re-review. Minor/YAGNI remains nonblocking.
- [x] Rerun every Required check whose input changed and write the secret-free receipt.
- [x] Synchronize acceptance evidence and mark S8R2 Accepted only at zero open Critical/Important.
  Keep Task 8.3, aggregate S8, `tasks.md`, `acceptance.md`, and `56/80` unchanged.
- [x] Return to the outer goal loop; do not mark the persistent goal complete or blocked merely
  because S8R2 is Accepted.

## Rollback checkpoint

Rollback is file-local: remove the optional relationship enumeration policy, canonical trace,
source-witness constraint branch, public relationship branch, one default-off fixture/owner group,
and S8R2 evidence. No schema, stored relation, index, release pointer, task checkbox, or external
target changes.

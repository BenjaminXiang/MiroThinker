# S7I Lookup Eligibility Lineage Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve exact-path eligibility decision/outcome/limitations in every public lookup
document and make lookup manifest parity sensitive to that metadata.

**Architecture:** Extend the existing `LookupProjectionDocument`; do not introduce a second artifact
or query-time policy evaluator. `_lookup_documents` copies the already replay-validated exact path
decision into the document. Existing physical JSON readback carries the fields automatically, while
the manifest hashes each complete normalized document rather than only the embedded projection JSON.

**Tech Stack:** Python 3.12, Pydantic v2 immutable contracts, pytest, Ruff, Pyright, OpenSpec.

---

### Task 1: Add one failing eligibility-lineage regression

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [ ] **Step 1: Let the existing path helper add one exact-path quality signal**

Add `exact_limited_identity_id: str | None = None` to `_public_path_eligibility_pairs` and
`_index_projection_request`. For the selected identity, build one existing
`eligibility_models.QualitySignal` with code `profile_incomplete`, affected path `exact_lookup`, and
one retained field assertion ID. Do not change any other request or default call.

- [ ] **Step 2: Add the focused public-behavior test**

Create `test_lookup_projection_retains_exact_eligibility_lineage_and_manifest_binding`. Build the
resolved-person candidate with `paper-ada` carrying the exact quality signal. For each public lookup
document, find its replayed exact `PolicyDecision` and assert:

```python
document.eligibility_decision_id == decision.decision_id
document.eligibility_outcome == decision.outcome.value
document.eligibility_limitations == decision.limitations
```

Assert the Paper carries `("profile_incomplete",)`. Assert every internal auxiliary document has no
public decision ID, outcome `admitted`, and no limitations. Revalidate a copy with outcome `limited`
and no limitations and require `ValidationError`. Rebuild lookup manifests after changing one valid
limitation string and require the owning manifest content hash to change while document IDs and
embedded `lookup_content_sha256` remain equal.

- [ ] **Step 3: Prove focused RED**

```bash
cd apps/miroflow-agent
uv run pytest -n0 -q --tb=short \
  tests/canonical_v2/test_internal_reference_projection_contract.py::test_lookup_projection_retains_exact_eligibility_lineage_and_manifest_binding
```

Expected: exactly `1 failed` at the missing eligibility field, with no fixture/import/skip/xfail or
unrelated failure.

### Task 2: Persist and content-bind exact eligibility effects

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/index_projection.py`
- Test: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [ ] **Step 1: Extend and validate `LookupProjectionDocument`**

Add required `eligibility_decision_id: NonEmptyStr | None`,
`eligibility_outcome: Literal["admitted", "limited"]`, and
`eligibility_limitations: tuple[NonEmptyStr, ...] = ()`. Sort/uniquify limitations. Require public
documents to carry a decision ID; require internal auxiliaries to carry no decision ID, outcome
`admitted`, and no limitations; require outcome `limited` to carry at least one limitation.

- [ ] **Step 2: Copy the replay-validated exact decision into public documents**

In `_lookup_documents`, set public fields from `lookup.decision_id`, `lookup.outcome.value`, and
`lookup.limitations`. Set internal fields to `None`, `"admitted"`, and `()`.

- [ ] **Step 3: Bind manifest content to the complete document**

Change `_document_content_sha256` to hash each complete `item.model_dump(mode="json")` through the
existing canonical JSON helper before combining deterministic per-document hashes. Do not change
document IDs or `lookup_content_sha256`.

- [ ] **Step 4: Prove focused GREEN and affected S7 regression**

```bash
uv run pytest -n0 -q --tb=short \
  tests/canonical_v2/test_internal_reference_projection_contract.py::test_lookup_projection_retains_exact_eligibility_lineage_and_manifest_binding
uv run pytest -n0 -q --tb=short \
  tests/canonical_v2/test_internal_reference_projection_contract.py
```

Expected: focused `1 passed`; shared file `42 passed, 2 skipped` under the current environment.

### Task 3: Verify and reaccept the correction

**Files:**
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s7i-lookup-eligibility-lineage-correction.md`
- Add after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7i/verification-receipt.json`
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Modify after review: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- Modify after review: `openspec/changes/rebuild-canonical-v2-knowledge-platform/agent-links.md`
- Modify after review: `.agents/portfolio.md`
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/code-grounded-mainline-plan-2026-07-13.md`

- [ ] **Step 1: Run behavior/static/package/source gates**

Run the focused and complete shared S7 owners, S7 release-publication owners, complete no-external
Canonical V2, scoped Ruff check/format, `py_compile`, complete Canonical V2 Pyright, strict OpenSpec,
`git diff --check`, fresh offline wheel content, scope/high-confidence-secret/generated-cache, and
frozen original-target checks. Record actual results.

- [ ] **Step 2: Obtain one merged independent review**

Lock production/test/contract hashes. Review exact decision mapping, public/internal validation,
limited/admitted semantics, manifest mutation sensitivity, physical readback compatibility, test
integrity, and scope. Repair only Critical/Important findings and run one targeted re-review.
Minor/YAGNI remains nonblocking.

- [ ] **Step 3: Persist reacceptance without Git or task actions**

After zero open Critical/Important findings, mark S7I Accepted and update only the listed evidence.
Confirm the formal task ledger remains 55/80; rerun strict OpenSpec and `git diff --check`. Do not
stage, Commit, Push, open a PR, archive, promote, or Cutover.


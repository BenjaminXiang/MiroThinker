# S8L2 Displayed-Set Structured Lookup Implementation Plan

**Goal:** Read exact displayed Canonical IDs through one release-bound structured lane without
inventing a filter language or duplicating the S8L1 physical adapter.

**Architecture:** Generalize only S8L1's package-internal mapping helpers. `LocalProjectionTrace`
gets a default implicit-exact execution lane whose legacy exact ID/hash representation remains
stable; structured traces include their explicit lane and therefore receive distinct candidate and
evidence IDs. The structured factory short-circuits an empty or inconsistent displayed-set request,
then reuses the same guarded bundle read, exact snapshot equality, typed projection validation, and
evidence mapping as exact lookup.

## Task 1: Freeze one lazy vertical RED

- Add one direct-symbol sentinel for missing `create_isolated_structured_lookup_adapter` before
  `request.getfixturevalue("isolated_lookup_target_bundle")`.
- The single test uses a non-name contextual query and displayed Company/Paper IDs, then covers
  empty/mismatched/unknown/internal/cross-domain/bound/exclusion/state/release/snapshot/unmarked
  cases plus exact+structured fusion.
- Run normal and forced focused commands; require `1 xfailed` and one exact sentinel failure.

## Task 2: Generalize local trace identity without changing exact IDs

- Add `execution_lane: Literal["exact", "structured"] = "exact"` to `LocalProjectionTrace`.
- For the default exact lane, compute raw/evidence/content hashes from the prior implicit-exact
  payload so prior serialized exact traces remain valid. For structured, include the explicit lane.
- Require item/candidate/request lanes to equal trace execution lane. Add no other public field.
- Re-run the original S8L1 group and 16 KnowledgeRead owners.

## Task 3: Add the structured factory by reusing S8L1 helpers

- Refactor common same-class publication/bundle validation, physical read/snapshot equality, typed
  projection parsing, full-content exclusion, and candidate mapping inside
  `knowledge_read_isolated.py`; do not change their exact observable results.
- Structured matching requires a non-empty displayed set, exact protected-set agreement when such a
  slot exists, domain membership, exact Canonical membership, excluded-term absence, and the shared
  candidate bound. It does not inspect free query text.
- Remove only the S8L2 xfail wrapper and prove focused GREEN.

## Task 4: Verify, review, and accept without checking Task 8.3

- Run S8L2 focused, original S8L1, the shared file, 16 read owners, and complete no-external suite.
- Run full static/strict/package/source/scope gates and preserve the frozen targets.
- Obtain one independent merged review; repair only Critical/Important and targeted re-review.
- Persist receipt/status evidence. Confirm the task ledger stays 55/80. Do not stage, Commit, Push,
  open a PR, archive, promote, or Cutover.

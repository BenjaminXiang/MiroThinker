# Slice Contract: s2c3c1-human-review-packet

## Status

Accepted at `2026-07-14T18:48:51Z`. S2C3A/S2C3B are Accepted at 47/80; Task 2.8 and aggregate S2C
remain open. S2C3C2 requires authorized external human review/calibration.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `2.8` (external-review preparation only)
- Parent Slice: `s2c3-claim-level-oracle-review`
- Depends on: exact Accepted S2C2 corpus and Accepted S2C3B evaluator

## Goal

Generate one deterministic, content-addressed, no-approval review packet that lets authorized human
reviewers inspect every current case, fill exact review/calibration records, and see every blocked
case as an explicit exclusion candidate without allowing the agent to approve anything.

## Non-goals

- No human decision, reviewer identity invention, judge run, calibration claim, contract status or
  eligibility mutation, exclusion acceptance, Task 2.8 completion, aggregate S2C acceptance, S8/S9,
  live provider, runtime integration, database/index write, or review workflow framework.

## Allowed scope

- One run-local builder, one focused test, and one generated packet under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/`.
- The packet may copy structured contract requirements, case/source/snapshot identities, queries,
  family/accounting labels, and empty exact evaluator review/calibration templates.
- Reference prose/key points may be represented only by their review-only locator/content hash; the
  packet must not copy them into normative fields or prefill a decision.

## Forbidden changes

- Accepted S2C2/S2C3A/S2C3B bytes or semantics, historical S2, human-review labels, reviewer IDs,
  agreement/sample values, claim evidence, runtime/product/provider code, databases, indexes, Task
  2.8, acceptance checkboxes, or external state.

## Required behavior

- Bind the exact Accepted manifest/content/file and all contract/account/snapshot identities before
  output. Account exactly 52 cases once: 29 `pending_user_review` review candidates and 23
  `blocked_missing_evidence` explicit exclusion candidates.
- Each review candidate contains the exact family, contract hash, hard IDs, source snapshot IDs,
  as-of, structured claim/entity/variant/enumeration/stage requirements, plus an exact eight-field
  evaluator review template whose `review_state` and `reviewer_id` are null.
- Each exclusion candidate remains unaccepted and names the existing evidence-gap reason and exact
  identity. It cannot be passed to S2C3B as an accepted review.
- Emit one empty calibration template per pending-review family with the existing minimum sample/
  agreement policy. Model identity remains null/pending external authorization; no measured value,
  reviewer, provider, or calibration result is filled.
- The packet has a canonical self-hash, deterministic bytes, explicit `awaiting_external_human_review`
  state, and contains no `approved` decision or agent/model reviewer substitution.

## Required checks

- Initial focused test records a genuine absent-packet/builder RED, then turns GREEN without weakening
  assertions. Deterministic `--write`/`--check` are byte-identical.
- Accepted S2C remains `16 passed`; historical S2 remains `20 passed`; S2C2 builder `--check` passes.
- Ruff format/check, targeted Pyright, strict OpenSpec, diff/source/scope/secret/cache checks.
- Independent packet/spec review with zero open Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- This Slice and parent status; `change-log.md`, `agent-links.md`, and `.agents/portfolio.md`.
- Task 2.8 and 47/80 remain unchanged.

## Stop conditions

- Packet generation needs an invented reviewer, approval, agreement/sample result, refreshed truth,
  reference prose as oracle, mutation of Accepted artifacts, or a workflow beyond deterministic
  review preparation.

## Done means

- The exact packet is deterministic, complete, unapproved, content-addressed, and independently
  reviewed. S2C3C1 is Accepted; S2C3C2 waits for authorized external human decisions/calibration and
  S2C3C3 later applies the reviewed version and performs aggregate acceptance.

## Acceptance evidence

- Initial RED was exactly `1 xfailed`; forced execution was one direct
  `_MissingHumanReviewPacketBuilder` failure for the exact absent builder. Final focused GREEN is `1
  passed`; combined S2C plus packet is `17 passed`; historical S2 remains `20 passed`.
- Final builder/test/packet file SHA-256 values are respectively
  `6aa0007b1b633e7c7f1443daabcdda2f57c2e34d07da1a62e6db006628778272`,
  `c9939066f5c8aa9c2ab3720bb28b59eef84e4121d23d0e5d014e3de4b3f1b2f4`, and
  `222777219026218d9a6308c62c0238613761ef83ae90497c3a0cfa785bce7d2e`; packet content
  self-hash is `d4aa2a74cd09956f01fcff9b774a55fc0627a412eb604c0de0be46ebd5bf2ffb`.
- The builder uses the fixed Accepted manifest content identity, invokes only the public evaluator
  admission seam, then captures manifest plus all three output byte sequences, compares their hashes
  to the returned artifact identity, and builds only from those same captured bytes.
- Exactly 52 cases are present once: 29 pending review templates, 23 evidence-gap exclusion
  candidates, and 18 family calibration templates. No review is approved; reviewer/model/agreement/
  sample fields remain null/empty and model selection is explicitly pending external authorization.
  Reference prose/key points are absent; only their review-only locator and content hashes remain.
- Deterministic `--write`/`--check`, Ruff format/check, targeted Pyright with zero findings, strict
  OpenSpec, `git diff --check`, source/secret/cache checks pass. Independent final review bound to
  the exact SHAs returned zero Critical/Important/Minor and Accepted only this preparation Slice.
- Accepted S2C2/S2C3 bytes and all external state remain unchanged. No human decision, Task 2.8,
  S2C/S8/S9 acceptance, Commit, Push, PR, archive, or Cutover occurred.

## Rollback note

Delete the review packet builder/test/output and revert evidence. Accepted evaluator/corpus and all
external state remain unchanged.

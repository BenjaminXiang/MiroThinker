# Slice Contract: s2c3c2-external-human-review

## Status

Rejected/Superseded at `2026-07-24` by explicit owner decision. The two-human/per-family-50 policy
below is retained as historical evidence only and MUST NOT be executed or treated as the active Task
2.8 review contract. It is replaced by `s2c3c2-single-human-review-workbench`. Task 2.8 remains
unchecked.

## Supersession reason

The owner simplified the operational review to one attributable human plus one deterministic,
globally five-stratum set of 60 blind calibration labels. Evidence-bounded judging, content identity,
and external human calibration remain required; only the reviewer count and sampling policy changed.
No Accepted v1 packet or corpus byte is changed by this supersession.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `2.8` (human decision/calibration evidence only)
- Parent Slice: `s2c3-claim-level-oracle-review`
- Depends on: Accepted S2C3C1 packet content SHA-256
  `d4aa2a74cd09956f01fcff9b774a55fc0627a412eb604c0de0be46ebd5bf2ffb`

## Goal

Obtain authorized, independently attributable human review decisions for the exact packet and valid
human-agreement evidence for the externally authorized evidence-bounded judge identity, without any
agent/model substituting for a reviewer.

## Required external inputs

- Named human reviewer identities and provenance acceptable to the user/owner; at least two distinct
  humans for every submitted calibration record.
- One explicit decision for each of the 29 review candidates, bound to exact case/contract/hard-ID/
  snapshot/family identities. Approved records use the packet's exact eight-field evaluator shape;
  rejected records remain non-eligible and name a reason.
- An explicit human decision for each of the 23 evidence-gap exclusion candidates, or new reviewed
  claim evidence and a new contract version. A proposed exclusion is not accepted merely because the
  packet generated it.
- Explicit authorization of the real recorded judge model identity, followed by per-relevant-family
  calibration records with at least 50 double-reviewed samples, agreement at least `0.80`, agreement
  no greater than `1.0`, and the exact policy/model/reviewer identities.

## Non-goals

- No agent-generated approval, reviewer impersonation, synthetic/fake judge calibration, source
  refresh, contract application, Task 2.8/S2C acceptance, S8/S9 execution, runtime/database/index
  change, Commit, Push, PR, archive, or Cutover.

## Evidence format

- External decisions/calibrations must be supplied as content-addressable JSON records linked to the
  exact packet identity. Free-form chat approval may authorize the review process but does not by
  itself fabricate a second reviewer or measured calibration result.
- The S2C3B evaluator remains the validation target; S2C3C3 owns applying accepted decisions to a new
  reviewed corpus/manifest version and extending explicit exclusion handling.

## Stop conditions

- Reviewer identity/provenance, a second human, exact decisions, judge authorization, or measured
  calibration evidence is absent.
- Completion would require the agent to infer approval from prior product choices, reference prose,
  model memory, or a generated packet template.

## Done means

- Every exact candidate/exclusion has an attributable human decision; every relevant judged family
  has valid authorized calibration evidence; all records pass structural/content identity checks.
  S2C3C2 becomes Candidate for human-owner confirmation, then S2C3C3 may apply the reviewed version.

## Rollback note

Revoke or remove the external decision package. Accepted code/corpus remains unchanged until S2C3C3
explicitly applies a reviewed version.

# Slice Contract: E — type3-traversal

## Status

Specified — blocked until Slice D is Accepted

## Parent

- OpenSpec change: `openspec/changes/close-retrieval-generation-contract/`
- Depends on: accepted `slices/d-type4-hybrid.md`

## Goal

Implement company-to-professor-to-paper retrieval using explicit strong and secondary relationship
tiers, verified professor-paper edges, and complete two-hop provenance through canonical evidence
and generated disclosure.

## Non-goals

- Populating or correcting company/professor relationship source data.
- Inferring unresolved people or upgrading secondary team links to verified roles.
- Changing Type1/Type2/Type4 ranking or paper index eligibility.
- Embedding ledger, backfill, or bulk index work.

## Allowed scope

- Type3 planner/orchestration, relationship-edge selection, path model, paper deduplication with
  alternate provenance, canonical relationship evidence, and answer disclosure.
- Test-database fixtures for strong, secondary, unresolved, unverified, terminal, and multi-path
  cases.
- Read-only production relationship coverage inspection and a non-mutating remediation worklist;
  no relationship population in this slice.
- Slice-owned API/generation/eval artifacts and status documents.

## Forbidden changes

- Ad-hoc company-name-to-paper text heuristics or unsupported direct company-paper links.
- Treating unresolved `company_team_member` text as a professor ID.
- Treating secondary edges as verified employment or omitting their disclosure.
- Using candidate/unverified/terminal professor-paper links.
- Writing production/business relationship data or broadening to a data-quality workstream.
- Starting Slice F before acceptance.

## Expected unchanged behavior

- Accepted Type1/Type2/Type4 and canonical grounded-answer behavior remains unchanged.
- Existing company profile/team responses remain unchanged outside explicit company-paper intent.
- Canonical relationship tables are read-only.
- No paper index or embedding state changes.

## Required checks

- Frozen fixtures and test-database integration for strong role, resolved secondary team member,
  unresolved name, unverified/terminal paper edge, and one paper reached through multiple paths.
- Current/former/unknown strong-role semantics, latest-snapshot `matched` secondary semantics,
  active node lifecycle, default/max paper pages, strong-first first-10 paths, and path continuation.
- Planner trace asserts exact company/professor/paper and both edge IDs/tier.
- Deduplication test preserves all alternate paths while showing one paper item.
- `/api/chat` integration and structured synthesis prove secondary tier disclosure and strong-tier
  accuracy.
- Negative semantic test prevents “verified company role” claims from secondary evidence.
- Type3 retrieval, returned-item citation, required-intent semantic, unsupported-claim,
  zero-regression, and latency gates.
- Read-only production edge/company/professor/paper coverage counts and explicit mechanism-only or
  production-covered status with remediation owner/worklist.
- Focused lint/type plus strict OpenSpec/diff checks.

## Evidence to update

- Slice E section in `verification.md` and `acceptance.md` with path ID tables, evidence/claims,
  exclusions, alternate paths, semantic output, latency, review, immutable hash, and rollback.
- Tasks/change log/portfolio; make Slice F Ready only after Slice E Accepted.

## Stop conditions

- Slice D is not Accepted.
- Real strong/secondary fixtures cannot be grounded without changing production/business data.
- The schema cannot identify relationship records sufficiently for atomic provenance.
- Correct behavior needs a new relationship tier or product claim absent from the OpenSpec.
- A fix would infer unresolved names or accept unverified paper links.
- Scope becomes a data-population workstream.

## Done means

- Every eligible result is supported by a typed, two-hop, ID-bearing path.
- Strong and secondary tiers remain distinct in retrieval, evidence, and answer.
- Unresolved/unverified paths are excluded and alternate paths survive deduplication.
- Production coverage is quantified; sparse/empty data remains explicitly operationally pending and
  is never described as closed by fixture GREEN.
- All Slice E gates pass; independent review, immutable diff/artifact hash, and Accepted status are
  recorded; an isolated commit is linked only when explicitly authorized.

## Rollback

Disable/revert the Type3 planner diff (or explicitly authorized isolated commit). Canonical data and
index remain untouched, so no data rollback belongs to this slice.
Keep the traversal flag through the observation window; a real E rollback invalidates F/Epic under
the central matrix rather than leaving their prior acceptance usable.

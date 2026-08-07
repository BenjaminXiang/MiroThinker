# Slice Contract: C — deterministic-paper-paths

## Status

Specified — blocked until Slice B is Accepted

Internal checkpoints after unblocking: C0 identity/Type1 -> C1 Type2. C1 cannot become Ready until
C0 is Candidate-reviewed and Accepted with independent Web-fallback rollback evidence.

## Parent

- OpenSpec change: `openspec/changes/close-retrieval-generation-contract/`
- Depends on: accepted `slices/b-grounded-answer.md`

## Goal

Close deterministic professor identity, professor-paper, and exact-title paths: Q004/Q017 profile
entity/endpoint agreement, natural Type1 exact-title resolution, and complete predicate-aware Type2
retrieval through canonical evidence and synthesis.

## Non-goals

- Type4 topic hybrid retrieval, Type3 company traversal, embedding ledger/backfill, or legacy chat
  removal.
- Changing the meaning of unrelated A-G query classes.
- Inventing professor-paper links or accepting unverified/terminal links.

## Allowed scope

- Query normalization/classification wiring required by Q004/Q017 and supported exact-title
  wrappers.
- Exact-title successful-local-miss fallback through the existing Web provider and canonical Web
  evidence/outcome interface; no Type4 topic fallback changes.
- Professor-paper predicate models, verified-link selection, stable pagination, ranking/filter
  helpers, retrieval wiring, and paper-list synthesis/evidence wiring.
- Reuse of the single shared `PaperTopicSearch` interface for Type2 topic intersection; no new topic
  matcher. Slice D may deepen the provider only after C acceptance and must rerun C's topic gates.
- Explicit `PaperTopicSearch.search(predicate, candidate_ids, snapshot_id) -> RetrievalResult` port,
  current-provider production adapter, and deterministic test adapter with canonical IDs/scores/
  lane status; no hidden alternate matcher.
- Slice-owned fixtures/tests/eval artifacts and contract status.

## Forbidden changes

- Global prompt hacks keyed to frozen query text or specific professor/paper names.
- Fixed top-N or database LIMIT behavior presented as a complete Type2 list.
- Type4 vector/lexical fusion, Type3 relations, migrations, canonical data, or index mutation.
- Changing the frozen oracle after seeing candidate output.
- Starting Slice D before acceptance.

## Expected unchanged behavior

- Existing professor profile requests remain profile requests.
- Bare exact-title cases that already pass keep the same target ID and evidence.
- Existing authoritative explicit-title local-miss Web fallback remains available with stronger
  provenance/outcome semantics.
- Non-paper and Type4/Type3 routing/ranking remain unchanged.
- Only active verified professor-paper relationships qualify for local Type2 results.

## Internal checkpoint contracts

### C0 — identity and Type1

- **Status:** Specified; becomes Ready only after Slice B Accepted and before C1 edits.
- **Goal:** close Q004/Q017 professor identity/route/endpoint agreement and natural Type1 exact-title
  resolution, ambiguity/terminal handling, and separately provenanced explicit-title Web fallback.
- **Non-goals:** professor-paper predicates/pages/topic port/synthesis, Type4, Type3, or data/index
  changes.
- **Allowed scope:** qualified-name normalization/classifier wiring, exact-title parsing/canonical-ID
  resolution, existing Web-provider fallback adapter, typed outcomes/evidence, and their tests.
- **Forbidden scope:** query-specific names/titles, rank-guess ambiguity resolution, fabricated local
  IDs, global Web policy changes, Type2 SQL, or a public schema change outside accepted Slice B.
- **Required checks/evidence:** frozen Q004/Q017 gates; title wrapper/same-title/merge/terminal/empty-
  detail matrix; local-hit and local-miss Web success/empty/failure; citation/semantic/regression/
  latency gates; Web-fallback disable/revert drill; review and immutable diff/artifact hash.
- **Stop/rollback:** stop if normalization cannot generalize, the existing Web policy conflicts with
  an authoritative contract, or expected IDs are ambiguous. Revert/disable only C0 routing/title/
  Web wiring while retaining Slice B.

### C1 — Type2

- **Status:** Specified; becomes Ready only after C0 Accepted.
- **Goal:** implement complete verified professor-paper predicates, materialized stable pagination,
  one `PaperTopicSearch` port, and paper-aware canonical synthesis.
- **Non-goals:** changing C0 identity/Web behavior, deepening Type4 provider/ranking, relationship
  ingestion, or data/index mutation.
- **Allowed scope:** predicate/order models, verified-link query, result-set materialization/cursors,
  current-provider/test topic adapters, page evidence, and paper-list synthesis.
- **Forbidden scope:** hidden LIMIT-as-completeness, alternate topic matcher, unverified links,
  post-output oracle changes, or edits to C0 rollout.
- **Required checks/evidence:** all/list/year/range/recent/topic/representative fixtures; default/max/
  null/time/title-sort rules; >one-page and prior-limit targets; public API+synthesis evidence;
  citation/semantic/regression/latency; port fallback/revert drill; review and immutable hash.
- **Stop/rollback:** stop on an ambiguous verified-link universe, missing public contract, or need for
  Type4/data scope. Return the `PaperTopicSearch` adapter and Type2 planner to the prior path and
  revert C1 while retaining accepted C0.

## Required checks

- Q004/Q017 reported-case and sibling matrix: professor-profile classifier/type/name/domain/endpoint,
  professor ID, and citation all exact; no paper predicate is required for those fixtures.
- Natural title matrix: bare, quoted, wrapper suffix, similar-title negative, punctuation/casing
  normalization where supported.
- Same-title active ambiguity, merged-survivor trace, terminal-only miss, and identity-without-detail
  partial-result fixtures.
- Frozen exact-title local-miss fixtures for Web success, successful local+Web empty, and Web
  failure; assert source lane/time, typed outcome, local-ID non-substitution, and latency.
- Test-database Type2 integration for >page-size authors and a target formerly below SQL/answer
  limits; all pages form one exact set without duplicates.
- Type2 all/list, year/range, recent, topic intersection, and representative ranking fixtures.
- Assertions for default/max page sizes, full keyset cursor tuple/snapshot binding, null-year rules,
  bare-recent versus N-year reference year, and representative default/max/order.
- `/api/chat` synthesis-on evidence showing paper titles/page metadata in canonical claims, never
  profile-only output for a paper-list request.
- Frozen Type1/Type2/Q004/Q017 retrieval/citation/semantic/zero-regression hard gates.
- Retrieval p95 <=6s and synthesis p95 <=15s in affected buckets.
- Focused lint/type plus strict OpenSpec/diff checks.

## Evidence to update

- Slice C section in `verification.md` and `acceptance.md` with exact ID sets, pagination proof,
  raw responses, semantic results, latency, review, immutable hashes, and rollback.
- Tasks/change log/portfolio; make Slice D Ready only after Slice C Accepted.

## Stop conditions

- Slice B is not Accepted or canonical evidence cannot express the required results.
- Required semantics need a public API/schema decision absent from the OpenSpec.
- Natural-language parsing cannot generalize beyond frozen strings without a new design decision.
- The verified-link universe is ambiguous or snapshot data contradicts expected IDs.
- Correctness requires Type4, Type3, or data/index scope.

## Done means

- Q004/Q017 pass every identity/route/endpoint/citation gate.
- Supported natural exact-title forms resolve the same canonical ID.
- Exact titles absent locally use truthful separately provenanced Web fallback outcomes and never
  fabricate a canonical local paper ID.
- Type2 exposes complete verified sets through pagination and correctly applies/discloses every typed
  predicate.
- Synthesis answers the paper intent using canonical paper evidence.
- C0 and C1 each have review, immutable diff/artifact hash, checkpoint rollback, and Accepted status;
  isolated commits are linked only when explicitly authorized.
- All Slice C gates pass and Slice C Accepted status is recorded.

## Rollback

Disable/revert C1 independently from C0, or revert C0 routing/title/Web wiring while retaining the
Accepted Slice B contract. Revert an isolated commit only if one was explicitly authorized. No
data/index rollback belongs to this slice. Preserve both C0/C1 flags through the observation window;
a real rollback applies the Epic invalidation matrix before downstream work can remain Accepted.

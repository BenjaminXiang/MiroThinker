# S8X Read-to-Answer Successor Handoff Implementation Plan

## Status

Accepted at `2026-07-20T17:26:45Z`; S8X closes no OpenSpec task and the ledger remains `65/80`.
Final implementation/test-integrity and Candidate-artifact reviews reported
`Critical=0/Important=0`. The traversal replan review
reported `Critical=0/Important=0`; reviewed hashes were audit
`940c94f5a1cfa48e1073ea7d4577c47f49e19505ccb9f7a85dcd24e06786a956`, plan
`faf42b9e456f55f36cd8a954a796a3cd3e55c48ae177334c92b1ade78415a0d8`, and contract
`6c70e29069951c50e7420e9b8330e8c03cbdbe892eb06103b3d9fee0e89044fe`. Do not implement traversal before observed RED. The historical initial review reported
`Critical=0/Important=0`; reviewed hashes were audit
`765024c5fa453f512682b560f3fcf9036a13eff112d4d14c1a281b87070a4a6b`, plan
`54950a4080398c4d9a45388bac1283c990036de0767d1c2daef221e071435d87`, and contract
`08ed4ae5e1b02e8cdb2e5311440fcdab216d78837c357319eab6348625730ea3`.

## Goal

Repair the three proven Read-to-Answer state-contract siblings without changing public fields or
accepted planner/answer semantics.

## Files

- Modify only `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` and
  `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`.
- Create only
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_answer_successor_handoff.py`.
- Add only direct traversal-handoff assertions to the existing S8R2/S8R5/S8R3/S8R4 nodes in
  `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`.
- Update only S8X run/status evidence and its slice contract.

## Steps

1. [x] Obtain one lean Specified review with `Critical=0/Important=0`; record reviewed hashes and
   mark Ready. Minor/YAGNI is non-blocking.
2. [x] Write the initial dedicated owner before production edits. Use the actual public query/read
   factory and actual `create_ephemeral_knowledge_answer` factory in five independent tests. Cover:
   - `evidence_gap` plus second-turn exact option selection;
   - non-enumeration `budget_exhausted` plus second-turn result-set selection;
   - same-subject multi-part is one deterministic positive; missing, duplicated, cross-wired,
     expired/sessionless/snapshotless Web, or multiple-subject authority produces zero candidate;
   - repeated identical authority preserves candidate ID/order while an authority change changes ID;
   - prior-turn poisoned result-set/evidence cannot authorize `current_result_set`; a valid
     current-turn `current_handle` option may remain, including an undisplayed viable alternative;
   - the real blocking planner reaches `_empty`, then the real answer returns
     `clarification_only`, empty claims, zero option, and a conservative request for a
     distinguishing detail without claiming evidenced choices exist;
   - direct Read result passed to Answer without a test-built/copied `EvidenceSet`.
3. [x] Observe five exact REDs caused by absent continuation/blocking materialization.
4. [x] Add one small internal helper in `knowledge_read.py` and invoke it from applicable return
   paths. Add one narrow current-turn authorization guard to the existing
   `knowledge_answer.py::_candidate_offer` boundary; pass current handles/items and only the result
   set newly created during that turn. Preserve models, reasons, operations, planner decisions,
   evidence, and ordering. Candidate IDs/order are content-bound; constraints copy only validated
   protected slots. Blocking ambiguity materializes no handle, evidence, candidate, or option from
   planner traces. Add only the minimal truthful text branch: option-bearing clarification may ask
   the user to select; zero-option clarification asks for a distinguishing detail.
5. [x] Obtain one lean traversal replan review with `Critical=0/Important=0`; record reviewed hashes.
6. [x] RED-A: add only direct `requested_traversal` assertions to the four existing physical nodes
   and observe all four fail at `None`. Then implement only the Read whitelist and prove GREEN-A;
   zero/multiple/unknown/technology paths remain `None`.
7. [x] RED-B in the same S8R2 node: use one real Answer instance and call public `answer()` for a
   setup turn that displays evidence-bound `company-robotics` as `active_anchor`. Send the unchanged
   real S8R2 `EvidenceSet` on a second turn with `SessionDirective(referent="active_anchor")`.
   Observe a present receipt with `target_handle_ids=()`; never mutate `_sessions`, infer source from
   target/claim, or add a source handle to the traversal turn. The setup-only turn may use a fresh,
   fully Pydantic-validated same-release `EvidenceSet` containing exactly one evidence-aligned
   `company-robotics` item/handle, no traversal, and `claims=()`; it must not copy, complete, or
   mutate the real S8R2 output.
8. [x] Implement only the Answer exact physical matcher. Preserve the synthetic fallback; require
   exact trace class, source/target/path tuple, and item object/claim binding; never parse or strip
   strings. GREEN-B must assert receipt source `("company-robotics",)`, target `("patent-ada",)`,
   and path `company_to_patent`.
9. [x] Run focused GREEN, then Accepted S8/S9 owners, complete Canonical V2 no-external tests,
   Ruff/format/py_compile/Pyright, strict OpenSpec, `git diff --check`, locked-offline wheel/source
   parity, scope/secret/cache checks, and frozen original Postgres/Milvus/forensic checks.
10. [x] Perform one independent implementation/test-integrity review. Repair only open Critical or
   Important findings; record Minor/YAGNI without another theoretical loop.
11. [x] Write `s8x/verification-receipt.json`, mark S8X Candidate, and stop. Do not change Tasks 8/9,
   S11A, `tasks.md`, `acceptance.md`, or the `65/80` ledger.

## Candidate verification receipt — 2026-07-20T17:20:26Z

- RED-A failed only at the four absent `requested_traversal` values; GREEN-A passed all four real
  physical nodes. RED-B failed only because the real S8R2 traversal receipt had no target; GREEN-B
  produced the exact company-to-patent source, target, and path through public Read/Answer calls.
- Canonical-object and mixed-Web-object cross-wire regressions both failed before the final exact
  subject matcher and passed after it. A bounded sibling search found no second matcher requiring
  repair.
- Final dedicated owner: `6 passed in 0.41s`. Final complete Canonical V2 suite:
  `363 passed, 148 skipped, 3 warnings in 327.91s`; warnings are the existing hostile serializer
  probes.
- Complete Ruff/format/`py_compile` passed; complete Canonical V2 Pyright reported
  `0 errors, 0 warnings, 0 informations`. Strict OpenSpec, `git diff --check`, and
  `uv lock --check --offline` passed.
- Fresh offline wheel SHA-256:
  `72c07e7334acfa53ba8aa5a49923bf6ac5fb362f9257802603c60ae9fa13ec2e`; 278 entries, exact
  Read/Answer source-byte parity, and zero test or `.agents` entries. Owned wheel output was removed.
- Read-only source guards retained original Milvus, paused `pgtest`, network-none recovery lab, and
  the directly hashable forensic sentinels. The aggregate forensic identity is reported only as
  record-consistent, not independently recomputed.
- Final implementation and post-Pyright reviews are `Critical=0/Important=0/Minor=0/YAGNI=0`.
  At this checkpoint S8X stopped at Candidate without task, acceptance, ledger, portfolio, S11A, or
  remote Git changes. A separate Candidate-artifact review with the same zero-finding disposition
  permitted the mechanical Accepted transition at `2026-07-20T17:26:45Z`.

## Done means

- All three sibling handoffs run through actual public factories.
- Executable candidates are evidence/handle/coverage-bound and deterministic.
- Answer current-handle authorization uses only current-turn handles/items; result-set authorization
  never reuses prior-turn evidence or result sets.
- Blocking ambiguity always suppresses unsupported primary answers, exposes zero options, and does
  not imply nonexistent evidenced choices.
- The four Accepted public traversal directions are exact and every other cardinality/type defaults
  to no traversal.
- No Accepted behavior or protected source changes outside the specified Read-producer and
  Answer-authorization boundaries that enforce this one cross-seam invariant.

## Rollback

Remove the owner and S8X evidence, then restore only the S8X helper/calls in `knowledge_read.py` and
the current-turn/traversal authorization guards in `knowledge_answer.py`. No database, index, source, task, or
remote Git state requires rollback.

# Calibration Observation Bank V2 Dependency Audit

Date: 2026-07-24
Status: Passed for implementation readiness; no human labels or judge outputs recorded
Policy: `single-human-global-stratified-v2`

## Gate being audited

Before the replacement S2C3C2 slice entered implementation, the frozen repository inputs had to
contain at least 60 distinct, human-labelable, evidence-bounded judge requests with exact quotas of
20 claim/evidence, 10 identity/entity, 10 context/relationship, 10 safety/Web, and 10
insufficiency/assessment. Selection must not depend on a model result, YAML/reference prose, future
S8/S9 acceptance results, or dynamically synthesized evidence.

## Result

The dependency gate passes. A bounded read-only inventory found exactly 60 selected structured
Python-fixture observations with the required `20/10/10/10/10` distribution. Thirty-six are
mechanically marked critical probes. Critical status is a risk classification, not a gold label;
the bank and workload contain no expected/human/model decision. The runtime acceptance gate still
requires at least five critical probes to be labelled `unsupported` by the real human and zero
critical false accepts.

| Stratum | Sample IDs | Count | Critical probes | Requirement kind |
|---|---|---:|---:|---|
| claim/evidence | `cal-v2-ce-001` .. `cal-v2-ce-020` | 20 | 11 | `claim_entailment` |
| identity/entity | `cal-v2-ie-001` .. `cal-v2-ie-010` | 10 | 4 | `identity_consistency` |
| context/relationship | `cal-v2-ct-001` .. `cal-v2-ct-010` | 10 | 4 | `relationship_or_context` |
| safety/Web | `cal-v2-sw-001` .. `cal-v2-sw-010` | 10 | 10 | `safety_or_web_policy` |
| insufficiency/assessment | `cal-v2-is-001` .. `cal-v2-is-010` | 10 | 7 | `evidence_sufficiency` |
| **Total** |  | **60** | **36** |  |

## Frozen source identities

Only structured objects and literals in these checked-in Python tests are admitted. The Task 2
builder must recompute every whole-file hash before accepting any row.

| Source | SHA-256 | As-of used by its fixtures |
|---|---|---|
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_grounding_contract.py` | `fbd1866b6acffdf558742a632c38d3faa0d8f8df39eb9b15e715ca0a4f6c0cfb` | `2026-07-15T00:00:00Z` |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py` | `17a962e945850082512344f201b80713c22310d1ac4fae72ff7ee28c3df8eabf` | `2026-07-20T11:15:00Z` |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_retrieval_fusion_contract.py` | `974bd767e78e04041ee1eba09982848b2532734e3f3f6fe2d341fd44c0c027ba` | `2026-07-15T07:00:00Z` |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_atomic_green_contract.py` | `d8e753331a55938ff7f894ddb397fea6cedaa9a0d6f6d05d1649fd7fd1979699` | `2026-07-15T07:45:00Z` |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py` | `c217a5ebfd2469020c69068728d274f1f76f361090f4f3ee99f8f851fcc5cd7f` | `2026-07-15T00:00:00Z` |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_answer_successor_handoff.py` | `29191a15c875cf95f4d2c6c432a2c6136c3f4cd9571369ef00306a4767b79d01` | `2026-07-20T15:10:00Z` |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_sufficiency_retry_contract.py` | `aa8f0a67ebf1ee7b6cd92d5584e9b0f2f7ff8d0916df0a35c3c609d1c83b8b56` | `2026-07-15T03:00:00Z` |

## Source-locator inventory

Locators are semantic and line-number independent. The builder must parse source with `ast.parse`
without importing or executing a test module, prove the named `FunctionDef` is unique, and prove
each selector has one matching assignment/call use. Complex final JSON values are frozen in the
bank and remain bound by the whole-file hash.

| Samples | Structured fixture scope and semantic selector |
|---|---|
| CE01-CE09 | `test_material_claims_bind_exact_evidence_and_disclose_conflict_and_inference`; `_claim[claim_id=...]` plus the exact referenced `_item`/conflict values |
| CE10-CE12 | `test_product_capability_requires_direct_named_product_binding_and_status`; `_claim[claim_id=...]` and direct-product evidence |
| CE13-CE19 | `test_industry_brief_preserves_scope_routes_semantics_and_representative_coverage`; route claim IDs and exact local/Web evidence bindings |
| CE20 | `test_prose_failure_returns_the_same_deterministic_grounded_fallback`; fallback-name claim and evidence |
| IE01-IE04 | `test_identity_fusion_aggregates_before_constraints_and_validates_late_rerank`; use-site plus `_fusion_candidates` helper bindings |
| IE05 | `test_independent_seven_lane_recall_overlaps_and_retains_full_candidate_trace`; unresolved same-name Person candidate |
| IE06-IE08 | `test_web_handles_bind_snapshot_collision_expiry_and_read_only_resolution`; Web candidates, snapshots, and accepted resolution proposal |
| IE09 | `test_ambiguity_decision_handoff_blocks_or_preserves_selected_identity`; selected-decision use-site plus `_ambiguity_decision` helper |
| IE10 | `test_canonical_object_id_cannot_authorize_another_handle`; cross-wired item/candidate binding |
| CT01-CT03 | `test_canonical_anchor_displayed_set_and_typed_traversal_stay_exact`; traversal requests and partial-coverage continuation |
| CT04-CT06 | `test_unresolved_web_handle_corefers_but_never_traverses_as_canonical`; coreference and forbidden unresolved traversal values |
| CT07-CT09 | `test_continuation_candidates_require_server_owned_executable_contract`; valid/invalid operation and relation assignments |
| CT10 | `test_continuation_triggers_bind_options_and_topic_switch_replaces_active_state`; topic-switch request and new-topic evidence |
| SW01-SW05 | `test_safety_guidance_is_server_owned_bounded_and_official_snapshot_grounded`; static, official, wrong-predicate, unverified, and poisoned-contact assignments |
| SW06-SW10 | `test_initial_web_snapshot_policy_recomputes_bytes_and_rejects_missing_oversize_or_tamper`; valid, oversize, tampered, metadata-only, and direct-oversize snapshot assignments |
| IS01-IS08 | `test_sufficiency_is_per_material_part_and_product_capability_is_direct`; material parts, sufficiency decisions, direct/wrong/model-memory evidence |
| IS09-IS10 | `test_assessment_replays_evidence_relevance_and_degrades_visibly`; conflicting and wrong-binding assessment assignments |

## Deliberate evidence-boundary cases

- CE09, CE10, and IS07 are model-memory candidates with no supplied evidence; their snapshot arrays
  are intentionally empty.
- SW01 is server-owned static guidance and intentionally has no snapshot.
- SW09 freezes metadata stating that payload bytes were not supplied. The source's local
  `missing_payload_bytes` construction is not admitted as evidence delivered to the candidate.
- Helper-backed IE01-IE04 and IE09 bind both the use-site and helper selector so a matching helper
  name alone cannot authorize a row.

## Replay requirements for Task 2

The independent provenance anchor is
`calibration-observation-bank-v2-provenance.json`, raw SHA-256
`1a806bc6e99d1fcf219338f1007feb5963ef35e60de200fa3246a8e2baa0fa80`, content SHA-256
`3fea1e29ca388c0eab17d30844a034c1db3a7fd97d1faea0501acabb995f5f6b`. It freezes all 60 sample
IDs, audited source/test/selector bindings, and canonical hashes over each row's stratum, requirement
kind, critical flag, as-of, locator-free requirement, candidate observation, evidence snapshots, and
policy. The normal builder may validate this anchor but must never regenerate or update it; matching
changes to builder blueprints and generated bank bytes therefore still fail closed.

The generated bank/workload test must fail closed on source-hash drift, missing/non-unique AST
locator, changed order, wrong quota, duplicate request hash, semantic duplicate under a different
sample ID, missing critical-probe capacity, and any recursively present `human_label`,
`judge_decision`, `expected_label`, `gold_label`, `oracle_label`, or `ground_truth`. It must compute
`request_sha256` from canonical JSON excluding only that field and emit deterministic bytes sorted
by stratum order then sample ID.

This audit establishes input sufficiency only. It does not accept Task 2.8, authorize a judge,
provide a human decision, or prove calibration agreement.

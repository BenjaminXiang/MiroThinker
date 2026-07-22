# Slice Contract: S8V2 Professor Typed Vector-view Selection

## Status

Accepted at `2026-07-19T14:45:45Z`. Exact RED/GREEN, literal legacy identities, predecessor/owner/
complete Canonical V2 regressions, static/OpenSpec/package/frozen-target gates, and independent
review all pass. The review-found model-valid duplicate lookup-authority bypass was reproduced,
repaired by structural uniqueness before hash continuity, and re-reviewed to zero Critical/
Important/Minor/YAGNI. S2C3C2 gates reviewed calibration and claim-level acceptance-oracle
execution only; it did not block this deterministic Task 8.3 predecessor. Task 8.3 remains open and
the formal ledger stays `56/80`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec requirement:
  `specs/professor-retrieval-index-split/spec.md` — validated plans select Professor identity,
  research, or both projections
- OpenSpec task: `8.3` (Professor vector-view predecessor only; remains unchecked)
- Depends on: Accepted S7 Professor identity/research points and lookup projection, S8P2 finite
  recorded planning, S8E1 release-bound composition, and S8V1 audited vector execution/authority
  seam
- Implementation plan:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8v2/implementation-plan.md`

## Goal

Add one optional finite field, serialized only when present:

```python
professor_vector_view: Literal["identity", "research", "both"] | None
```

The field shall be recorded on `RecordedPlanningProposal`, copied unchanged to a non-blocking
planner-owned `RetrievalPlan`, and copied only into the vector `LaneRequest`. A recorded proposal
must carry it exactly for Professor+vector information retrieval and must omit it otherwise. A
planner-owned or release-bound plan has the same strict rule. Existing unbound synthetic/legacy
plans and their derived generic `LaneRequest` may continue omitting it so their Accepted fixture
identity and generic mock-adapter mechanics remain unchanged; such a request must still be rejected
by the real isolated Professor vector adapter, and a missing selector can never enter release-bound
execution. Any present selector remains forbidden outside Professor+vector execution.
`QueryViewProposal.kind` remains rewrite provenance and shall not be interpreted as an index
projection selector.

The release-scoped vector adapter shall admit Professor only with that typed selector. `identity`
scores only the accepted Professor identity point, `research` scores only the accepted Professor
research point, and `both` scores both before applying the existing deterministic raw-point
`max_candidates` bound. This Slice does not change budget semantics or implicitly expand a bound:
with `max_candidates=1`, `both` may return only the first deterministically ranked raw point. The
positive `both` case uses the current two-point Professor and a bound of two; existing fusion shall
return one canonical Professor with two distinct vector evidence items retaining `identity` and
`research` trace views.

Professor research embedded content intentionally has no display name. The adapter shall derive the
canonical Professor display name from the exact Professor public `LookupProjectionDocument` in the
same fully audited snapshot, revalidate it as `ProfessorProjection`, and require one unambiguous
public Professor exact-lookup match. Release ID and canonical object ID must match the point, and
`lookup_document.source_projection_content_sha256`, `point.source_projection_content_sha256`, and
the validated `ProfessorProjection.content_sha256` must be identical. The document must use
`projection_scope="public_domain"`, `domain="professor"`, `reference_type=None`,
`path="exact_lookup"`, `projection_view="identity"`, and the unique Professor public lookup
manifest's `projection_id`. It shall not modify S7 point content or fabricate a name from the
canonical ID.

The S8V1 release-authority post-validator shall additionally require every returned Professor vector
trace view to be permitted by the plan selector. It shall derive the same authoritative lookup name
and require the returned fused Professor candidate and canonical entity handle display names to
equal it. A model-valid internal adapter returning an identity point for a research-only plan, or
returning a selected point/trace with a forged display name, must fail `KnowledgeRead.execute`
without returning an `EvidenceSet`.

All absent-field `RecordedPlanningProposal`, `RetrievalPlan`, `LaneRequest`, local trace, paper/
company/patent vector, exact/structured/lexical, and Web serialization/content identities shall
remain byte/value identical.

## Non-goals

- No new intent taxonomy, intent classifier, heuristic keyword router, provider call, prompt,
  threshold, calibration, score policy, ANN/backend, rerank, or fusion algorithm.
- No per-view/per-identity budget, hidden oversampling, paired-view guarantee under a raw bound of
  one, or Task 8.5 ranking/fusion policy.
- No S7 point/index/lookup/schema/content change, no Professor public-domain shape change, and no
  fifth public domain.
- No relationship/internal-reference adapter, relationship publication correction, Universal-Web
  implementation, supplemental retrieval, answer/session behavior, reviewed S2C replay, Task 8.3
  completion, aggregate S8 acceptance, Commit, Push, PR, Archive, promotion, or Cutover.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` for the optional finite
  proposal/plan/request field, omission-preserving serializers, exact cross-field validation,
  planner propagation, and lane-specific request propagation.
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` for selector-aware
  Professor point filtering, audited lookup-derived display name, removal of the S8V1 Professor
  hard gate, and release-authority view validation.
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` for one
  exact-field physical vertical group and unchanged S8V1/predecessor assertions.
- `apps/miroflow-agent/tests/canonical_v2/test_knowledge_query_planning_contract.py` only to add the
  optional helper input and pass explicit `research` selectors in the existing valid D-taxonomy and
  Professor-vector institution matrices while retaining their assertions; do not broaden that
  owner.
- This contract/plan and S8V2-only evidence. Existing verification/change-log/agent-links/portfolio/
  mainline-plan artifacts may be synchronized only after Candidate review. Keep `tasks.md` and
  `acceptance.md` unchanged.

## Forbidden changes

- `QueryViewProposal.kind` reinterpretation, a second planner/read service, caller-owned lane map,
  arbitrary selector strings, selector inference from query text, or selector defaulting.
- Trusting bundle-only points without S8V1 physical audit, deriving research display name from an
  ID, admitting missing/duplicate/cross-release lookup display authority, returning a Professor
  point outside the selected view, or weakening release trace validation.
- Any index/projection/publication, relationship, internal-reference, answer/gap, provider,
  migration, admin/chat, original source/target, active pointer, or other test file.
- Xfail/skip weakening, credentials/network, broad formatting, or destructive worktree cleanup.

## Expected unchanged behavior

- S8V1 Paper/Company/Patent vector execution and its exact query/point/score/identity formulas remain
  unchanged when the selector is absent.
- Existing unbound proposal/plan/lane-request JSON and content hashes omit the new absent field.
  Literal pre-production JSON and SHA baselines for one representative absent-selector value of
  each type remain exact; existing synthetic S8RF Professor+vector plans may stay unbound and absent.
  Existing planner owners and all exact/structured/lexical/Web behavior remain GREEN.
- Existing `LocalProjectionTrace` and `LocalVectorTrace` schemas/identities do not change. Professor
  candidates reuse the existing per-point `projection_view` trace and canonical fusion behavior.
- Original PostgreSQL/Milvus/forensic sources, accepted physical target bytes, active pointers,
  Task 8.3, `acceptance.md`, and the formal `56/80` ledger remain unchanged.

## Required checks

- Before any production edit, one non-xfail baseline test freezes and passes literal full JSON plus
  SHA values for an absent-selector `RecordedPlanningProposal`, unbound `RetrievalPlan`, and
  `LaneRequest`. These are not computed from post-change expectations.
- RED normal: exactly one strict xfail. Forced `--runxfail`: exactly one direct
  `_MissingProfessorVectorViewSelection` failure before physical fixture acquisition.
- GREEN focused: exactly one pass. Three exact scenario-bound request/proposal/plan triples are
  `“陈艾达”是谁？` -> `identity`, `哪些教授研究机器人？` -> `research`, and mixed name/topic
  `“陈艾达”是否研究机器人？` -> `both`. The recorded proposal, not a heuristic, supplies each
  selector. The first two return only the selected Professor point view, while `both` with bound two
  fuses one canonical Professor with two distinct raw/evidence identities and both trace views.
- The same group proves the research display name comes from the exact audited Professor lookup
  projection and rejects missing, duplicate, cross-release, wrong-domain, mismatched-canonical, or
  wrong-view/projection-ID/source-projection-hash display authority before returning a candidate.
- Proposal matrices always reject missing selector for Professor+vector, selector on a non-Professor
  domain, selector without vector, and invalid same-class selector output. Planner-owned and
  release-bound plan matrices enforce the same strict rule and reject cross-wired propagation;
  blocking clarification drops execution and the selector. Legacy unbound plans/requests may omit
  it only for generic synthetic mechanics, while the isolated adapter and release service reject
  missing execution authority before physical, embedding, or Web effects.
- Direct request and release-authority negatives reject a returned point outside the selected view
  and reject a selected, correctly traced Professor result whose fused candidate or canonical handle
  display name differs from the authoritative lookup name. `both` with a raw bound of one follows
  existing deterministic truncation and does not claim paired evidence. Non-Professor public/
  internal filtering remains unchanged.
- Legacy absent-field proposal/plan/request payloads and hashes, S8V1 focused, S8P1/S8P2/S8E1/S8L3
  predecessors, complete physical/release owner, all KnowledgeRead/query-planning owners, and
  complete no-external Canonical V2 pass with actual counts recorded.
- Complete Ruff/format, changed-file compile, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/cache, and frozen-source/
  target checks pass.
- One independent review ends with zero open Critical/Important. Minor/YAGNI is recorded and does
  not block unless it proves a Spec/safety/model-valid bypass.

## Evidence to update

- This contract and
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8v2/verification-receipt.json`.
- Existing verification/change-log/agent-links/portfolio/mainline plan after acceptance. Do not
  change `tasks.md` or `acceptance.md`.

## Stop conditions

- Correct view selection requires changing S7 points/schema/content, inferring intent outside the
  recorded proposal, changing raw candidate budgets/fusion, or adding a provider/runtime policy.
- Research display identity cannot be derived from the exact audited lookup projection; a selected
  view can cross release/canonical identity; absent-field legacy hashes cannot remain stable; an
  existing owner regresses; or a Critical/Important finding remains.

## Done means

- One exact RED becomes a typed plan-to-lane-to-audited-Professor-view GREEN through the existing
  public `KnowledgeRead.execute` seam; required checks and independent review pass with zero open
  Critical/Important findings.
- S8V2 is Accepted only as a Task 8.3 predecessor. Task 8.3 and aggregate S8 remain open, the formal
  ledger stays `56/80`, and the next independent real-lane Slice is named.

## Rollback note

Remove the optional selector field/omission branches, planner/request propagation, Professor point/
lookup-name branches, release-authority view check, the single S8V2 group, and S8V2-only evidence;
restore S8V1's Professor hard refusal. S8V1, S7, external state, and the task ledger otherwise need
no rollback.

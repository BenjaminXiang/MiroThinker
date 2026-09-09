# Slice Contract: S8L3 Release-scoped Lexical Lookup Green

## Status

Accepted at `2026-07-19T08:35:45Z`. S8E1 and every S7/S8L1/S8L2/S8P predecessor are Accepted.
S2C3C2 gates reviewed calibration and later claim-level acceptance-oracle execution only; it does
not block this deterministic physical Task 8.3 predecessor. The formal ledger is `56/80` and remains
unchanged by this Slice.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `8.3` (release-scoped lexical-lane predecessor only; remains unchecked)
- Depends on: Accepted S7/S7I physical lookup projection, S8RG execution mechanics, S8L1/S8L2 local
  mapping/lineage, S8P1/S8P2 lane planning, and S8E1 release-bound composition
- Implementation plan:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8l3/implementation-plan.md`

## Goal

Add one package-internal factory:

```python
create_isolated_lexical_lookup_adapter(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
) -> Callable[[LaneRequest], RetrievalLaneResult]
```

The adapter shall accept only `lane="lexical"`, real-read and exact-snapshot-compare the bound
physical lookup documents, exact-validate each typed public projection, and return a bounded,
deterministically ordered recall set when the normalized lane query phrase occurs in the typed
projection's scalar content. It shall strip only the planner-owned trailing `[lane=lexical]` marker
and one exact matched surrounding quote pair from `“…”` or `"..."`, then reuse the existing NFKC,
casefold, and whitespace-collapse normalization. It shall not invent stopwords, stemming, synonym
expansion, or a ranking framework. An empty normalized phrase returns empty before physical read.

Reuse S8L1/S8L2 release, publication, typed-content, four-public-domain, eligibility, excluded-term,
candidate/evidence, and bundle-integrity rules. Extend `LocalProjectionTrace.execution_lane` to
`lexical` so exact, structured, and lexical evidence for one Canonical object remain collision-free
while all legacy exact/structured identities stay exact. Add the lexical adapter to the Accepted
S8E1 release-bound composition; callers still provide no local lane map.

## Non-goals

- No BM25/tokenizer/stemmer/synonym/stopword framework, lexical threshold calibration, semantic
  vector search, relationship traversal, internal Person/Technology execution, current-Web provider
  implementation, rerank/fusion policy change, or supplemental retrieval.
- No arbitrary field/filter DSL, geography/year/institution policy, task-level recall/precision/
  latency/cost claim, reviewed S2C replay, full Task 8.3/8.5, or aggregate S8 acceptance.
- No second public read service, caller adapter registry, persistence, migration, physical rebuild,
  database/index/source write, pointer change, Commit, Push, PR, Archive, promotion, or Cutover.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` for the lexical
  factory, narrowly shared matching helpers, and S8E1 composition inclusion.
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` only to extend the existing
  local trace execution-lane discriminator while preserving exact/structured identities.
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` for one
  lazy physical vertical group and changing S8E1's still-unsupported sentinel lane from lexical to
  vector.
- This contract/plan and S8L3-only evidence. After Candidate review, update existing verification/
  change-log/agent-links/portfolio/mainline-plan artifacts. Keep `tasks.md` and `acceptance.md`
  unchanged.

## Forbidden changes

- Any other production/shared-contract/S7 builder-reader/publication/planner/provider/answer/session/
  consumer file, accepted assertion, physical fixture source, original target, or active pointer.
- Matching internal auxiliary documents, ignoring request domains/excluded terms/candidate bounds,
  trusting raw lookup JSON without typed validation, dropping eligibility/source lineage, or reusing
  exact/structured candidate/evidence identities for lexical output.
- Treating substring recall as calibrated relevance/ranking; silently enabling vector/relationship/
  internal-reference lanes in S8E1; caller-owned local adapter maps; broad exception degradation.
- Test-local positive lexical adapter, monkeypatched positive reader, copied/rebuilt physical target,
  xfail/skip weakening, live network/credentials, or source mutation.

## Expected unchanged behavior

- S8E1 release-binding/Web/snapshot behavior, S8L1 exact behavior/identities, S8L2 structured
  behavior/identities, S8P1/S8P2 plan identities, and all existing KnowledgeRead owners remain GREEN.
- Initial RED is exactly one strict xfail and one forced direct missing-symbol sentinel before the
  physical fixture is acquired. GREEN is one pass through the S8E1 composition without a caller
  local adapter map.
- Original PostgreSQL/Milvus/forensic sources, physical target bytes, active pointers, Task 8.3, and
  the formal `56/80` ledger remain unchanged.

## Required checks

- RED normal: exactly `1 xfailed`; forced `--runxfail`: exactly one direct
  `_MissingIsolatedLexicalLookupAdapter` failure before physical fixture acquisition.
- GREEN focused: exactly `1 passed`, proving the no-protected-slot, proper non-equal substring
  `bound robotics` recalls the accepted `Evidence-bound robotics` Paper through direct lexical
  execution, while the full-title
  plan produces collision-free exact+lexical evidence for one identity through the S8E1
  `KnowledgeRead.execute` composition.
- The same group proves marker/finite-quote normalization, wrong lane, cross-release request,
  non-public request domain, and empty phrase all fail or return before read; it also proves public-
  domain/excluded-term/candidate bounds, internal exclusion, active/rolled-back serviceability,
  cross-release publication, unmarked/snapshot mismatch refusal, full release/projection/evidence
  trace, and S8E1 rejection of still-unsupported vector execution.
- Existing S8L1/S8L2/S8E1/S8P1/S8P2 focused groups, complete physical owner, all KnowledgeRead
  owners, and complete no-external Canonical V2 pass with actual counts recorded.
- Complete Ruff/format, `py_compile`, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/cache, and frozen-source/target
  checks pass.
- One independent review ends with zero open Critical/Important. Minor/YAGNI is recorded and
  nonblocking unless it proves a Spec/safety/model-valid bypass.

## Evidence to update

- This contract and
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8l3/verification-receipt.json`.
- Existing verification/change-log/agent-links/portfolio/mainline plan after acceptance. Do not
  change `tasks.md` or `acceptance.md`.

## Stop conditions

- Correct lexical behavior requires a new index/schema/public contract, calibrated ranking policy,
  external provider truth, or a product semantic absent from OpenSpec.
- Legacy exact/structured identities cannot remain stable, lexical output can cross public/internal
  or release boundaries, S8E1 must expose a caller lane map, or a Critical/Important finding remains.
- Any existing owner regresses or an original/production-like target changes.

## Done means

- One exact RED becomes one physical release-bound lexical GREEN through the existing public execute
  seam; all Required checks and independent review pass with zero open Critical/Important findings.
- S8L3 is Accepted only as a Task 8.3 predecessor. Task 8.3 and aggregate S8 remain open, the formal
  ledger stays `56/80`, and the next smallest real-lane Slice is named.

## Rollback note

Remove the lexical factory/matching helpers, S8E1 lexical inclusion, lexical trace discriminator,
the single S8L3 group, and S8L3-only evidence; restore S8E1's unsupported-lane case to lexical. S8E1,
S8L1/S8L2, external state, and the task ledger otherwise need no rollback.

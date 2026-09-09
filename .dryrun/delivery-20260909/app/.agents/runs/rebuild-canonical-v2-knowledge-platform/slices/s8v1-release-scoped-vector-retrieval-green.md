# Slice Contract: S8V1 Release-scoped Vector Retrieval Green

## Status

Accepted at `2026-07-19T10:16:54Z`. S7/S7I/S7J and S8L1/S8L2/S8E1/S8L3/S8P1/S8P2 are Accepted.
S2C3C2 gates reviewed calibration and claim-level acceptance-oracle execution only; it does not
block this deterministic physical Task 8.3 predecessor. The formal ledger is `56/80` and remains
unchanged by this Slice.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `8.3` (release-scoped vector-lane predecessor only; remains unchecked)
- Depends on: Accepted S7/S7J vector point/readback/release parity, S8RG execution mechanics, S8P
  planning, S8E1 composition, and S8L3's current release-bound lane set
- Implementation plan:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8v1/implementation-plan.md`

## Goal

Add one package-internal factory:

```python
create_isolated_vector_recall_adapter(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    embedding_adapter: EmbeddingAdapter,
) -> Callable[[LaneRequest], RetrievalLaneResult]
```

The adapter shall accept only `lane="vector"`, validate the explicit embedding model against the
release and require an exact positive non-Boolean adapter dimension before physical read, strip only
one exact trailing `[lane=vector]` planner marker, and return empty before embedding or physical read
for an empty topic or zero candidate bound. S7 binds model/schema but does not publish a dimension;
the dimension authority is the explicit adapter plus the marked physical collection. The full audit
must prove every stored point vector has exactly that dimension.

Before audit, validate request lane/release/public domains, reject any Professor domain until typed
view selection exists, and validate adapter model/basic dimension. Wrap the adapter so every
`embed_batch` call—including calls made by the S7 audit—converts adapter exceptions into
`IsolatedKnowledgeReadIntegrityError` and requires exact output cardinality, exact dimension,
numeric non-Boolean finite scalars, and non-zero finite norm. Audit then precedes the explicit query/
point embedding batch and every candidate construction. The wrapper freezes the initial model ID/
dimension and memoizes the first validated numeric vector for each exact input text. Any later model/
dimension drift or unequal vector for the same text is an integrity error before candidate
construction. Thus vectors re-used for scoring are exactly those validated against physical storage
during audit, even when the underlying adapter is stateful.

For a non-empty request, audit the complete marked isolated target through the Accepted S7 physical
reader and that validating adapter, exact-revalidate the returned `IsolatedIndexSnapshot`, and
require receipt index manifests, receipt lookup manifests, points, and lookup documents to match all
corresponding axes of the bound `IsolatedReleaseBundle`. Then recompute query and accepted point
embeddings locally. Score
each eligible public point by finite cosine similarity; filter request domains, displayed entity
IDs, and excluded terms; order deterministically by descending score plus stable typed tie-breakers;
and return at most `max_candidates`. The full audit proves the recomputed point vectors are equal to
the physically stored Milvus vectors. This Slice intentionally uses bounded O(release points)
deterministic scoring and makes no production latency/backend claim.

Add a content-bound `LocalVectorTrace` and use the existing `local_projection_trace` JSON key as a
`path`-discriminated lookup/vector trace union. Its exact fields are:

```text
target_id, target_marker_sha256, manifest_sha256, index_result_content_sha256,
point_id, canonical_object_id, release_id, domain,
projection_id, projection_scope="public_domain", path="semantic_recall",
execution_lane="vector", projection_view, projection_version, schema_version,
embedding_model, eligibility_policy_version, eligibility_decision_id,
eligibility_outcome, eligibility_limitations,
source_projection_content_sha256, embedded_content_sha256,
source_evidence_ids, publication_verification_evidence_ids,
lane_query_text_sha256, query_embedding_sha256, similarity_score,
raw_candidate_id, evidence_id, content_sha256
```

SHA fields use lowercase 64-hex. Lineage tuples are non-empty/sorted/unique where applicable;
`limited` requires limitations; score is finite in `[-1, 1]`. `lane_query_text_sha256` is SHA-256
of the exact UTF-8 `LaneRequest.query_text`, including its marker. `query_embedding_sha256` uses the
existing canonical JSON SHA-256 over the validated numeric tuple. Cosine is
`clamp(dot(query, point)/(norm(query)*norm(point)), -1, 1)`; zero norm is an integrity error.

With `lineage` equal to trace JSON excluding the final three identity/hash fields:

```text
raw_candidate_id = "local-vector-candidate:sha256:" + canonical_sha256(lineage)
evidence_id = "local-vector-evidence:sha256:" + canonical_sha256((lineage, raw_candidate_id))
content_sha256 = canonical_sha256(full trace JSON excluding content_sha256)
```

The EvidenceItem locator is `canonical-v2-isolated:{target_id}:{point_id}`; snippet hashes to
`embedded_content_sha256`; score equals `similarity_score`; and claim binding is
`(canonical_object_id, "semantic_recall", embedded_content_sha256, eligibility_outcome)`. Existing
exact/structured/lexical trace JSON, IDs, hashes, locator, and validation must remain byte-exact.

Extend the Accepted S8E1 signature exactly with
`embedding_adapter: EmbeddingAdapter | None = None`. `_ReleaseBoundKnowledgeRead` admits `vector`
iff that adapter is installed. When absent, vector plans fail before physical/Web effects; when
present and valid, the factory owns the vector adapter without exposing a caller lane map. Callers
still execute only `KnowledgeRead.execute`.

## Non-goals

- No external embedding provider, network, scalable/remote Milvus search API, approximate nearest-
  neighbor tuning, score threshold/calibration, oversampling/reranking policy, latency/cost claim,
  or acceptance-threshold result.
- No vector schema/point/rebuild change, path-policy replay, relationship/internal-reference
  execution, supplemental retrieval, fusion/rerank change, or Web behavior change.
- No Professor identity-versus-research intent selector. S8V1 rejects any Professor-domain vector
  request before embedding/physical read; an explicit S8V2 typed identity/research/both selector is
  required before Professor vector execution.
- No second public read service, caller adapter registry/map, persistence, migration, original/
  production-like target open, active pointer, Task 8.3/8.5/aggregate S8 acceptance, Commit, Push,
  PR, Archive, promotion, or Cutover.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` for `LocalVectorTrace`, the
  existing-key discriminated local trace union, and narrow path-aware local evidence validation/
  locator logic while preserving all legacy lookup identities.
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` for explicit
  embedding validation, full snapshot audit/compare, bounded cosine recall, vector candidate/
  evidence construction, and optional S8E1 composition inclusion.
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` for one
  exact-symbol physical vertical group and retaining S8E1's no-embedding vector rejection.
- This contract/plan and S8V1-only evidence. Existing verification/change-log/agent-links/portfolio/
  mainline-plan artifacts may be synchronized only after Candidate review. Keep `tasks.md` and
  `acceptance.md` unchanged.

## Forbidden changes

- Any S7 index/point/publication, shared contract, query planner, answer/gap, relationship, provider,
  migration, admin/chat, original source/target, active pointer, or unrelated test file.
- Trusting bundle-only points without physical audit, accepting a model/dimension mismatch, scoring
  internal auxiliary points in the public vector lane, replaying eligibility, fabricating/dropping
  S7J limitations, ignoring filters/bounds, or returning non-finite/unbound scores.
- Adding a new EvidenceItem JSON key that changes legacy serialization; reusing exact/structured/
  lexical candidate/evidence identities; allowing vector trace through a non-vector request; caller-
  owned local lane maps; xfail/skip weakening; live credentials/network.

## Expected unchanged behavior

- Exact/structured/lexical/Web behavior, S8E1 release binding, S8P plan identities, S7/S7J point/
  physical/release behavior, and every existing KnowledgeRead owner remain GREEN.
- Existing `LocalProjectionTrace` and every exact/structured/lexical EvidenceItem/Candidate retain
  identical serialized JSON, raw candidate ID, evidence ID, and content hash. The new union accepts
  only the two exact `path` discriminators.
- Original PostgreSQL/Milvus/forensic sources, accepted physical target bytes, active pointers,
  Task 8.3, `acceptance.md`, and the formal `56/80` ledger remain unchanged.

## Required checks

- RED normal: exactly one strict xfail; forced `--runxfail`: exactly one direct
  `_MissingIsolatedVectorRecallAdapter` failure before physical fixture acquisition.
- GREEN focused: exactly one pass. A direct query equal to the accepted Paper point content yields
  `paper-ada` first with cosine `1.0`; a release-bound exact+vector+Web plan fuses one Canonical Paper
  while preserving distinct exact/vector evidence and candidate identities.
- A pre-effect matrix proves wrong lane, cross-release, non-public domain, Professor domain, model
  mismatch, non-positive/Boolean dimension, empty topic, and zero bound before physical read; empty/
  zero also precede embedding. A validating-adapter matrix independently proves exception handling,
  output cardinality, exact dimension, numeric non-Boolean scalars, finiteness, and non-zero norm for
  query and point batches. A hostile adapter returning two different individually valid vectors for
  the same point text across audit and scoring must fail as non-deterministic before candidate
  construction. No failed path returns a candidate.
- The same group proves exact marker removal, request domain/displayed-ID/excluded-term filters,
  internal exclusion, deterministic score/tie ordering and candidate bound, active/rolled-back
  serviceability, and S7J limitations.
- Independent snapshot negatives cover receipt index manifests, receipt lookup manifests, bundle
  points, bundle lookup documents, extra/missing/cross-release points, audit-raised stored-vector
  mismatch, and marker/target mismatch. The adapter exact-revalidates the snapshot and compares every
  corresponding bundle axis; each failure produces no candidate. Positive execution still uses the
  real S7 audit, not a test-owned positive reader.
- The vector trace proves every named field and formula. Model-valid hostile combinations separately
  mutate path (a valid lookup trace on a vector request), execution lane, point/content/query hashes,
  score, raw/evidence IDs, and locator; the public trust seam rejects each. Legacy lookup payloads
  round-trip without a new JSON key or identity change.
- Existing S7J, S8L1/S8L2/S8E1/S8L3/S8P1/S8P2 focused groups, complete physical/release owner, all
  KnowledgeRead owners, and complete no-external Canonical V2 pass with actual counts recorded.
- Complete Ruff/format, changed-file compile, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/cache, and frozen-source/
  target checks pass.
- One independent review ends with zero open Critical/Important. Minor/YAGNI is recorded and does
  not block unless it proves a Spec/safety/model-valid bypass.

## Evidence to update

- This contract and `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8v1/verification-receipt.json`.
- Existing verification/change-log/agent-links/portfolio/mainline plan after acceptance. Do not
  change `tasks.md` or `acceptance.md`.

## Stop conditions

- Correct deterministic recall requires changing S7 points/schema, replaying policy, choosing a
  calibrated score/Professor-view threshold, exposing a caller lane map/client seam, or opening an
  original/production-like target.
- Legacy local trace serialization/IDs cannot remain stable; public vector output can cross release/
  internal/model boundaries; any existing owner regresses; or a Critical/Important finding remains.

## Done means

- One exact RED becomes one audited release-bound vector GREEN through the existing public execute
  seam; required physical/static/package/frozen checks and independent review pass with zero open
  Critical/Important findings.
- S8V1 is Accepted only as a Task 8.3 predecessor. Task 8.3 and aggregate S8 remain open, the formal
  ledger stays `56/80`, and the next smallest real-lane Slice is named.

## Rollback note

Remove `LocalVectorTrace`/union branches, vector factory/scoring helpers, optional composition port,
the single S8V1 group, and S8V1-only evidence. S7J, S8E1/S8L3, legacy local identities, external
state, and task ledger require no rollback.

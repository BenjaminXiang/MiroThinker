# paper-index-parity Specification

## ADDED Requirements

### Requirement: Canonical data and one versioned predicate own eligibility

The index planner SHALL derive **index eligibility** from current canonical paper/full-text/lifecycle
data and one versioned pure `index_eligibility` predicate on every reconciliation. The initial rule version MUST
preserve the Accepted `make-partial-papers-retrievable` semantics: ready papers are eligible subject
to lifecycle/identity exclusions; partial papers are eligible only when the single non-persisted
`paper_has_rich_retrieval_text` predicate is true; title-only partial and `needs_enrichment` papers
are ineligible. Rejected and merged records MUST
be excluded from desired index state and MUST NOT be counted as active enrichment backlog or index
coverage. A ledger observation or enrichment-lane predicate MUST NOT become a second readiness
authority or independently admit a paper to retrieval.

Separate versioned pure `enrichment_lane_membership` predicates MAY derive operational worklists
from canonical state (for example active `needs_enrichment`, active partial title-only, and
`needs_review`). They do not express retrieval readiness and cannot add an ID to desired index state.
Both predicate families are recomputed, versioned, saved with their SQL/rule hash, and exclude
terminal rejected/merged records from mutable work lanes.

#### Scenario: Raw backlog contains terminal records

- **WHEN** a raw status count includes active, rejected, and merged records
- **THEN** reporting SHALL split those lifecycle states
- **AND** only active records selected by a versioned enrichment-lane predicate SHALL enter that
  enrichment worklist, while only `index_eligibility=true` records SHALL enter desired index state

#### Scenario: Persisted observation disagrees with current canonical state

- **WHEN** a prior ledger observation says eligible but current canonical data/predicate says
  ineligible
- **THEN** current derived state SHALL control desired index state
- **AND** reconciliation SHALL record the new observation/rule version without using the stale row
  for retrieval admission

#### Scenario: Record becomes terminal

- **WHEN** an indexed paper becomes rejected or merged
- **THEN** it SHALL leave desired paper and chunk state
- **AND** reconciliation SHALL report and remove or quarantine stale chunks under the rollback-safe
  deletion policy

### Requirement: Data work is separated into auditable lanes

The lifecycle SHALL expose separate checkpointed lanes for active `needs_enrichment`, active partial
title-only records, and `needs_review` audit through versioned `enrichment_lane_membership` rules.
Active partial-rich and ready records SHALL instead be covered by index parity according to
`index_eligibility`; review records MUST NOT be silently promoted. Lane membership and index
eligibility may be mutually exclusive for one snapshot and MUST be reported separately.

#### Scenario: Snapshot worklists are created

- **WHEN** a lane run begins
- **THEN** it SHALL save snapshot identity, enrichment-lane-rule version, index-eligibility-rule
  version, input paper-ID set/count,
  excluded lifecycle counts, residual count, owner, and checkpoint for every lane

#### Scenario: Needs-review record is encountered

- **WHEN** a paper is in `needs_review`
- **THEN** automated enrichment SHALL leave its canonical decision unchanged
- **AND** the record SHALL appear in the review audit with its reason and owner

### Requirement: Every reconciliation-snapshot paper has an audit ledger row

The system SHALL persist a non-authoritative per-paper observation for every canonical paper in the
declared reconciliation snapshot. It MUST record paper ID, derived eligibility/reason,
index-eligibility-rule version, enrichment-lane memberships/rule versions, derivation time, source
snapshot, normalized source-content hash,
chunker/schema version, expected chunk count and manifest hash, embedding model/version, target
collection/index version, last confirmed success, last attempt, failure, and attempt count.

#### Scenario: Paper is ineligible without an embedding attempt

- **WHEN** a paper is terminal, title-only, needs review, or otherwise excluded by the predicate
- **THEN** its snapshot ledger row SHALL record the derived state/reason/rule version
- **AND** no embedding call SHALL be made

#### Scenario: Paper is eligible but only part of its chunks is confirmed

- **WHEN** fewer than all expected chunks for the current manifest/version tuple are confirmed in
  the target collection
- **THEN** the paper ledger SHALL remain failed or pending rather than successful

#### Scenario: Full snapshot bootstrap is incomplete

- **WHEN** any canonical paper in the declared reconciliation snapshot lacks its observation row
- **THEN** full-snapshot ledger coverage SHALL fail even if the tested subset passes

### Requirement: Chunk manifests define vector identity and version

Every eligible paper SHALL have an expected chunk manifest keyed by `chunk_id`. Each entry MUST
include paper ID, chunk type/index, normalized content hash, embedding model/version, chunker/schema
version, target index version, and write/run identity. The candidate Milvus row or a cryptographically
linked sidecar/write manifest MUST expose a verifiable tuple; a Postgres ledger assertion alone is
not proof of the stored vector version.

#### Scenario: One paper legitimately has multiple chunks

- **WHEN** a paper produces title, abstract, or intro chunks
- **THEN** each deterministic chunk ID SHALL appear once in its expected manifest
- **AND** repeated `paper_id` across different expected chunk IDs SHALL NOT be reported as a
  duplicate defect

#### Scenario: Candidate index lacks verifiable version metadata

- **WHEN** actual chunk rows cannot be joined or cryptographically linked to content/model/chunker/
  index/write identity
- **THEN** version parity SHALL fail rather than trust the ledger's self-report

#### Scenario: Duplicate chunk identity exists

- **WHEN** the active target contains duplicate/conflicting rows for one expected chunk identity or
  an unexpected chunk manifest
- **THEN** parity SHALL report a duplicate/conflict defect

### Requirement: Content and all generation versions trigger deterministic replay

A paper SHALL be stale when source-content hash, expected chunk manifest/hash/count,
chunker/schema version, embedding model/version, or target collection/index version differs from its
last fully confirmed tuple. Every stale eligible paper MUST enter replay.

#### Scenario: Paper content or chunking changes

- **WHEN** normalized source content or chunker/schema version changes
- **THEN** the expected chunk manifest SHALL be regenerated and reconciliation SHALL schedule all
  changed/missing chunks plus removal of obsolete chunks

#### Scenario: Embedding model or index version changes

- **WHEN** embedding model/version or target index version changes
- **THEN** prior success SHALL be reported stale and retained for audit/rollback

#### Scenario: No relevant state changes

- **WHEN** current derived eligibility and the full content/chunk/model/index tuple match confirmed
  success
- **THEN** replay SHALL skip the paper without calling the embedding provider or rewriting chunks

### Requirement: Lane execution is checkpointed, idempotent, and resumable

Enrichment, embedding, and reconciliation jobs MUST record deterministic checkpoints and MUST be
safe to restart without duplicating canonical records, chunk identities, successful writes, or
terminal actions.

#### Scenario: Job stops after a confirmed batch

- **WHEN** a lane job is interrupted after some chunk manifests are confirmed
- **THEN** restart SHALL resume from ledger/manifest/checkpoint state
- **AND** current confirmed chunks SHALL be skipped idempotently

#### Scenario: Failure occurs between embedding and index confirmation

- **WHEN** an embedding is produced but its target chunk write/version cannot be confirmed
- **THEN** that chunk and paper SHALL remain retryable and not successful
- **AND** replay SHALL converge on exactly one current row per expected chunk identity

### Requirement: Parity is two-level and version-aware

Parity verification SHALL compare both distinct desired paper coverage and the exact expected versus
actual chunk-ID/manifest/version sets. It MUST report missing/unexpected papers; missing/unexpected/
stale/conflicting chunks; failed papers/chunks; and unverifiable version tuples. Count equality or
distinct-paper equality alone is insufficient.

#### Scenario: Paper IDs match but one chunk is missing

- **WHEN** every desired paper ID appears in Milvus but one expected abstract/intro chunk is absent
- **THEN** paper coverage MAY pass while chunk parity SHALL fail

#### Scenario: Chunk counts match but identities differ

- **WHEN** desired and actual chunk counts match but one expected chunk is missing and one obsolete,
  terminal, or unknown chunk is present
- **THEN** parity SHALL fail and report both set differences

#### Scenario: IDs match but a vector tuple is stale

- **WHEN** expected chunk IDs exist but content, model, chunker, index, or linked write identity is
  stale or unverifiable
- **THEN** parity SHALL fail until replayed or explicitly excluded by an accepted rule

#### Scenario: Parity is promoted

- **WHEN** distinct paper coverage, exact chunk manifests, verifiable version tuples, ledger
  confirmations, and accepted exclusions agree with no unresolved failures
- **THEN** the run MAY record parity success for that exact snapshot and index version

### Requirement: Snapshot and index identities are preserved in evidence

Every baseline, lane, and parity artifact MUST identify code SHA, database snapshot/version,
eligibility-rule version, chunker/schema version, embedding model/version, Milvus collection/index
version or alias target, run/write IDs, timestamps, and raw machine-readable paper/chunk results.

#### Scenario: A later dataset is evaluated

- **WHEN** canonical data, eligibility/chunker rules, or the active index changes after a run
- **THEN** the later run SHALL receive a new snapshot/run identity
- **AND** it SHALL NOT overwrite the earlier baseline or claim a same-snapshot comparison

### Requirement: Backfill promotion is bounded, rollback-safe, and honestly scoped

Index mutations SHALL begin with a dry run, proceed in bounded non-production lane batches, and
verify every paper/chunk manifest before promotion. The prior collection/index alias target MUST be
preserved until acceptance. A non-production rehearsal proves mechanism only; production parity MAY
be claimed only from a read-only report of the actual active production snapshot/index after an
explicitly authorized rollout.

#### Scenario: Dry run reveals exclusions or unexpected deletes

- **WHEN** the dry run finds ambiguous lifecycle state, category/content ownership, or unexpected
  chunk deletion
- **THEN** the lane SHALL stop before mutation and emit an audit worklist

#### Scenario: Candidate index violates parity or retrieval gates

- **WHEN** a candidate fails paper/chunk parity, frozen retrieval quality, or latency acceptance
- **THEN** the active alias SHALL remain on or return to the recorded prior target
- **AND** ledger/manifest/run evidence SHALL preserve the failed candidate for diagnosis

#### Scenario: Production has not been reconciled

- **WHEN** only a bounded non-production candidate has passed
- **THEN** the Epic SHALL label ledger/reconciliation mechanism accepted but production parity,
  enrichment coverage, backfill, and promotion pending
- **AND** it SHALL report each residual active lane's count, owner, and follow-up change without
  claiming overall paper retrievability closure

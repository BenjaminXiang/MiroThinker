# S10O Durable Knowledge-Gap Operations Closure Dependency Audit — 2026-07-20

## Outcome

One bounded operations slice can close OpenSpec Tasks `10.3`, `10.4`, and `10.5` by persisting the
already-Accepted S10 remediation mechanics, exposing a minimal Canonical V2 admin read model, and
proving the online read/answer/gap path cannot mutate active canonical or Milvus state. S8C and S9I
are now Accepted, the exact eight-owner S10 baseline passes, and the corrected contract/plan review
reports zero open Critical/Important findings; S10O is Ready at `2026-07-20T12:12:15Z`.

S2C3C2/S2C3C3 still gate only the reviewed claim-level acceptance-oracle executions in Tasks `8.8`
and `9.8`. They do not block this deterministic operations slice, its explicit disposable Postgres
matrix, or its recorded no-external read-to-answer-to-gap owner.

## Accepted predecessors already available

- S2B: accepted complete backup/restore evidence and the write gate required before any Canonical V2
  persistence entry point writes.
- S3: shared `KnowledgeGap`, assertion, decision, review, release, manifest, and provenance contracts,
  plus the explicit-target database safety interface.
- S7: candidate/release/build-manifest and exact release/index verification mechanics.
- S10A/Task 10.1: all eight named gap-trigger RED families.
- S10B/Task 10.2: typed gap creation, bounded classification, confidence/review state, product demand,
  PRD family, owner, severity, and remediation proposal.
- S10C: exact offline-remediation, accepted-release-plus-effect, and hostile cross-wire RED contract.
- S10D: pure in-memory `KnowledgeGapFeedback.apply_remediation` GREEN mechanics.
- Canonical V2 migration chain through `C2_0010`; the `ops` schema exists but owns no gap table.

## Future hard dependencies

- S8C must be Accepted so the operations owner consumes the accepted real `KnowledgeRead.execute`
  result rather than a synthetic fixture or an in-progress query artifact.
- S9I must be Accepted so the same owner consumes an accepted grounded `KnowledgeAnswer.answer`
  result, complete trace IDs, admitted evidence IDs, and visible limitation state.
- Neither predecessor may be consumed while Specified, Ready, In Progress, or Candidate.

## Current production gaps

1. `knowledge_gap_feedback.py` is intentionally ephemeral. A process restart loses recorded gaps,
   remediation links, accepted effect evidence, and replay identity.
2. No Canonical V2 migration persists gaps or remediation transitions. The `ops` schema is empty,
   while assertions, decisions, releases, manifests, and provenance already live in their owning V2
   tables.
3. S10D validates internally consistent typed payloads, but does not cross-check the candidate
   release and manifest against durable V2 release/build records. Its own acceptance notes explicitly
   defer external receipt truth and cross-instance replay to the operational integration slice.
4. Admin `/api/review/issues` and `/api/pipeline-issues` still read and write the legacy
   `pipeline_issue` table through direct SQL. Evidence is arbitrary JSON, and a caller can set a bare
   `resolved` Boolean without accepted release or intended-effect evidence.
5. The legacy admin dependency falls back from `DATABASE_URL` to `DATABASE_URL_TEST` and imports
   legacy retrieval/provider/Milvus dependencies. A V2 operations path must instead use a dedicated
   V2-only dependency seam, require a dedicated URL, expected database identity, and `disposable` or
   `isolated-candidate` target kind, and never import or extend generic `backend/deps.py`.
6. Chat feedback and upload quality findings still emit legacy `pipeline_issue` rows. Replacing all
   those consumers belongs to S11; S10O must establish the typed durable destination and visible V2
   operator surface without rewriting every legacy caller.
7. No real-Postgres vertical owner currently proves that current-Web/LLM/read/answer/gap execution
   changes only `ops` gap history while canonical assertions/decisions, release pointers, and Milvus
   remain byte/count/hash unchanged.

## Chosen implementation boundary

### Durable append-only operations store

Add the next live Canonical V2 revision after `C2_0010` with only:

- `ops.knowledge_gap`: immutable initial typed gap payload plus filter columns and content hash;
- `ops.gap_remediation_transition`: immutable typed S10D request/result receipt, source/candidate
  release identity, state, transition time, and content hashes;
- `ops.current_knowledge_gap`: a deterministic read-only view selecting the initial gap or latest
  accepted transition for each gap.

Both tables use existing release/build identities, exact JSON payload hashes, foreign keys where the
owning record is durable, append-only mutation rejection, uniqueness/idempotency constraints, and a
safe reversible downgrade. Bounded state columns are `TEXT` plus `CHECK`, not database enums. The
downgrade takes an exclusive lock before its nonempty check so concurrent inserts cannot race a
destructive drop. Do not add a queue, scheduler, SLA, workflow graph, generic event store, or
universal remediation-kind matrix.

### One explicit-target Postgres adapter

Add `knowledge_gap_postgres.py` beside the pure module. It reuses
`KnowledgeGapFeedback.record/apply_remediation`; it does not reimplement classification or lifecycle
rules. The adapter:

- verifies the accepted backup gate, explicit target identity, and required migration before write;
- persists/reloads exact typed values and rejects same-ID/different-content replay;
- serializes per-gap transitions and rejects stale or branched current state atomically;
- verifies candidate release ID/state/manifest/build-run identity against `knowledge.release` and
  `publish.build_manifest` before storing a link or closure;
- closes only with S10D's exact accepted `ReleaseVerification` and later accepted
  `GapEffectVerification`;
- exposes a bounded list/detail admin read model from the same repository.

The admin detail contains the gap and immutable transition history, matching field/relationship
assertions and decisions for known evidence IDs, source-record/artifact provenance where present,
source/resolving release and build-manifest identities, and explicit unresolved evidence IDs. It does
not invent provenance for Web/trace IDs that have no durable local row.

### Minimal V2 operator surface

Add a thin read-only admin API and one small built-in browser view for V2 gaps. The list supports
bounded status/class/severity/domain/path/release filters and shows demand/PRD impact, owner, proposed
remediation, release, and update time. Detail shows the typed lifecycle plus assertion/decision/
release/provenance links.

The API imports its dependency only from `backend/canonical_v2_deps.py`. That V2-only seam lazily
composes the exact operations reader from dedicated Canonical V2 settings and imports neither
`backend/deps.py` nor any legacy retrieval/provider/Milvus dependency. The legacy app may register
the router during this slice; the router remains independently importable by the later candidate app.

There is deliberately no arbitrary `PATCH resolved=true`. Offline code applies the existing typed
remediation request through the Postgres adapter. The legacy review/pipeline issue endpoints remain
unchanged until S11B switches all remaining consumers and quarantines them; they are not accepted as
the V2 operations surface.

### Online write-boundary owner

One no-network real-disposable-Postgres owner executes the accepted S8C read result through the
accepted S9I answer seam, derives a typed gap signal from those public trace/evidence IDs, and records
it through the durable adapter. It snapshots before/after:

- `knowledge.source_assertion`, canonical/relationship decision tables, and `knowledge.release`;
- `publish.active_release` and build-manifest identity;
- the deterministic candidate-index adapter state and original Milvus file SHA-256.

Only the expected `ops.knowledge_gap`/transition rows may change. Recorded Web/LLM adapters may
propose evidence or classification but receive no canonical, publication, or index writer. A second
offline candidate/accepted transition scenario proves closure through exact durable release/effect
evidence without promotion.

## Alternatives considered

### Expand S10D's ephemeral cache into a global in-process registry

Rejected. It would not survive restart, enforce release/build truth, support admin operations, or
provide real database write-boundary evidence.

### Reuse or extend legacy `pipeline_issue`

Rejected. Its Professor/link/stage shape, arbitrary evidence JSON, mutable resolve fields, and generic
database target are pre-V2 implementation details. Preserving it would not migrate operations to
typed gaps, assertions, decisions, releases, and provenance.

### Build a full remediation workflow and operator console

Rejected for this convergence round. Scheduling, assignment, retries, SLAs, batch remediation,
reopen/dismiss policy, generic approvals, and a React redesign are not required to close Tasks
10.3–10.5 and would delay the runnable V2 checkpoint.

### Extend the generic admin dependency module

Rejected. `backend/deps.py` owns legacy SQL/retrieval/provider/Milvus construction and environment
fallbacks. Importing or extending it would make the S10O router fail the later candidate import
quarantine even if the new dependency function itself were careful.

## Readiness review disposition — 2026-07-20T11:02:45Z

- Critical: `0`.
- Important found and repaired: `2` — the planned admin router previously extended/imported generic
  `backend/deps.py`; the downgrade did not explicitly lock out concurrent inserts before its
  nonempty check. The repaired contract/plan require a V2-only dependency seam and an
  access-exclusive lock plus `TEXT`/`CHECK` reversible state storage.
- Open Critical/Important after repair: `0`.
- Minor, nonblocking: define `release_id` filtering as source-or-linked/resolving release; normalize
  database datetimes to stable ISO JSON; prefer dedicated configuration/persistence exceptions for
  sanitized HTTP mapping; label the built-in V2 tab as independent and explicitly unconfigured when
  its dedicated settings are absent.
- YAGNI, nonblocking: do not add cryptographic/notary infrastructure around the already typed,
  content-bound `GapEffectVerification` in this isolated-candidate slice.
- Ready was reached at `2026-07-20T12:12:15Z` after S8C receipt
  `9e912de80fad1d82c6b6e27d71f04b458a0c78799c104ff6ca0e659e0f43ebca`, S9I receipt
  `658c12f519a55d3e5ca02eea7b2a5deba36d47954fe04d9233934a434e0ac366`, the fresh `8 passed`
  S10A-D baseline, live `C2_0010` single head, clean planned ownership, strict OpenSpec, and diff
  checks. Reviewed Specified hashes are audit
  `0955f4077db5ce848ae556fc94743bde7d72aca01df79f11a5f11bdf7eac67ab`, plan
  `ba2d4330ac3d8fbf693c2878a462c0f9b3ae93dadbe8dae8cd20d9a20ba8334a`, and contract
  `2ee9787e4905957dc0d73c8d775ae0fe2ec76609ef45dc2894a6412f7a9593cf`.

## Exact task boundary

After implementation, required checks, and independent acceptance, S10O may check exactly Tasks
`10.3`, `10.4`, and `10.5`. It must not check Tasks `8.8`, `9.8`, any S11/S12 task, or claim that all
legacy chat/upload/admin consumers have cut over. Compute the ledger from the live `tasks.md`; the
slice delta is exactly three checked tasks.

## Durable sources

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md` — Tasks 10.3–10.5 and S11.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/knowledge-gap-feedback/spec.md`.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/canonical-v2-knowledge/spec.md`.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/design.md` — Decisions 0, 3, 6, 8,
  11, and 12.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/convergence-plan-remaining-24-2026-07-20.md`.
- Accepted S10A, S10B, S10C, and S10D Slice Contracts.
- Current `knowledge_gap_feedback.py`, S10 owner tests, Canonical V2 migration chain, and legacy
  admin review/data-quality issue surfaces as implementation evidence only.

No production code, test, migration, OpenSpec checkbox, existing slice, source, database, index,
provider, pointer, Commit, Push, PR, archive, or Cutover changed during this audit.

## Candidate implementation review disposition — 2026-07-20T13:20:32Z

- Initial implementation review: `Critical=0`, `Important=6` across restart replay, complete stored
  column validation, migration/hostile/admin owner integrity, online/offline no-write coverage,
  request-time configuration sanitization/import quarantine, and exact durable manifest truth.
- All six classes received direct counterexamples inside the existing eight owner groups. The
  counterexample run was agent `5 failed, 2 passed` plus admin `1 failed`; the repaired final run is
  agent `7 passed` with warnings denied plus admin `1 passed`.
- Frozen targeted re-review: `Critical=0`, `Important=0`. Minor/YAGNI remain nonblocking: read-only
  transactions are not additionally declared at the SQL session level, the array indexes remain
  simple inspectable indexes, and no generic workflow/SLA/notary infrastructure was added.
- Candidate code/test hashes and verification evidence are recorded in
  `s10o/verification-receipt.json`. No formal task checkbox, ledger, acceptance artifact, Commit,
  Push, PR, archive, or Cutover changed at Candidate.

# Slice Contract: S4D Bounded Evidence Landing Matrix

## Status

Accepted — `2026-07-11T22:07:12Z`

- Authority: user-authorized objective-verification self-approval through Task 4.5
- Acceptance evidence: `../s4-landing-review.md` and `../s4e/acceptance-record.json`

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Tasks: 4.4 only
- Depends on: Accepted tasks 4.1-4.3 and Accepted S2B/task 2.6

## Goal

Replay a deterministic, bounded six-family matrix from Accepted S2B backup/restore outputs into the
isolated candidate landing schema, preserving exact content identity, copy/derivation lineage,
record locators, partial fields, typed errors, and a reproducible checkpoint summary.

## Representative matrix

| Family | Accepted source | Restore input | Bound / expected behavior |
|---|---|---|---|
| WAL/FPI partial | `inventory:5e1ba9...c17c73` | `recovery/lab-01/miroflow-real-fpi-salvage.dump` | Exactly three named `salvage.paper` keys with their retained `field_errors`; all three remain partial |
| SQLite | `inventory:ffe87d...d34a0` | `workspace/logs/data_agents/released_objects.db` | First five primary-key ordered `released_objects` rows |
| JSONL | `inventory:f8fea0...2bae` | `workspace/docs/source_backfills/company_knowledge_fields.jsonl` | Entire accepted eight-record file |
| XLSX | `inventory:b9a897...b3c4a0` | `workspace/docs/source_backfills/patent_exact_identifier_supplement.xlsx` | Clean `Sheet1`; one data row |
| Milvus copy | `inventory:65c4a2...accd` | verified `milvus-probe/milvus.db` | Three fixed `company_profiles` primary keys, non-vector fields only, queried on an ephemeral byte-identical working copy |
| Recorded collection response | member of `inventory:3bf673...f1cd6` | one verified professor fetch-cache JSON | Preserve known URL/body; unknown retrieval time/status/content type remain typed missing provenance, never invented |

The committed matrix records complete IDs, paths, byte sizes, hashes, parser versions, selectors,
and expected summaries; abbreviated IDs above are only for readability.

## Non-goals

- Full source-family replay, canonical identity/assertion/domain construction, recollection, Web
  requests, LLM calls, release publication, Milvus rebuild, landing acceptance, or checkpoint dump.
- Inferring missing collection metadata, filling recovered TOAST values, or treating Milvus/cache
  payloads as canonical facts.
- Reading the original `pgtest` volume or repository Milvus path.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/evidence_landing.py`
- `apps/miroflow-agent/src/data_agents/canonical_v2/evidence_landing_postgres.py`
- `apps/miroflow-agent/src/data_agents/canonical_v2/evidence_adapters.py`
- Focused Canonical V2 landing tests.
- Task-scoped S4D matrix/replay/test/summary artifacts under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4d/`.
- This plan/contract, OpenSpec `tasks.md`/`change-log.md`, and run `verification.md`.
- One forward C2_0003 -> C2_0004 migration and immutable landing replay in the exact marked
  `miroflow_canonical_v2_candidate_s3b` database after all pre-write checks pass.

## Forbidden changes

- Original/recovery source writes; original Milvus client creation; any `pgtest` resume; any generic
  `DATABASE_URL`; any production-like target, canonical/publish/index table write, or candidate
  downgrade/truncate/delete/update.
- New live collection/provider request or invented response provenance.
- Business source data or derived record payloads committed to Git; only hashes/counts/error
  summaries and selectors may be committed.
- Unrelated application behavior, legacy migrations, accepted S2/S2B artifacts, thresholds, corpora,
  or protected root instructions.

## Expected unchanged behavior

- Accepted S1-S3/S2B and tasks 4.1-4.3 remain GREEN and byte-identical.
- Existing ephemeral and PostgreSQL landing ingestion remains compatible and immutable.
- Candidate knowledge/domain/publish/ops tables remain empty; active release remains absent.

## Required checks

1. RED tests fail only for absent artifact registration/matrix behavior, then pass without weakening.
2. Every matrix member is found in the exact Accepted backup member manifest; backup object and
   restore file match its byte size/SHA-256 and remain under the accepted distinct roots.
3. Large backup/restore artifacts are hashed by streaming registration; derived WAL/Milvus/cache
   artifacts link to the registered restore artifact; direct restore artifacts link to backup.
4. Bounded selectors are deterministic and fail closed on missing keys, unordered SQLite bounds,
   unexpected Milvus identities, malformed cache/WAL output, or any expected summary mismatch.
5. Candidate pre-write checks prove exact database name, marker, system identifier, network-none,
   no published port, C2_0003, and zero landing/business rows; exact S2B admission passes immediately
   before the forward migration and before every landing write.
6. First replay and restarted idempotent replay produce identical artifact/record/error summaries.
7. Focused/expanded Canonical V2, S1, S2/S2B, Ruff, Pyright, strict OpenSpec, diff, source hashes,
   `pgtest` paused volume, recovery-lab isolation, and candidate isolation checks pass.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4d/landing-matrix.json`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4d/landing-replay-summary.json`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- This contract status/evidence section.

## Stop conditions

- Accepted gate/member manifest/path/hash mismatch or a selected family is absent.
- Any path resolves outside accepted backup/restore roots, to an original path/inode, or changes
  during extraction.
- Candidate identity/revision/count/isolation mismatch; candidate contains unexpected rows.
- A materializer needs an original client, network access, unbounded vector output, invented field,
  or source/candidate mutation.
- Actual record/status/error/hash summary differs from the frozen matrix.
- Existing accepted behavior regresses or required objective evidence cannot decide correctness.

## Done means

- Exactly six representative parsed runs and their required backup/restore parent artifacts are
  immutable in the isolated candidate at C2_0004.
- Every direct/derived input, parser output, count, status, error, and record-set hash matches the
  committed deterministic checkpoint; restart replay is idempotent.
- Original sources and accepted evidence remain byte-identical, no canonical/published/index state
  changes, Task 4.4 evidence is complete, and the task has one reviewed commit.
- Status first became `Candidate`; Task 4.5 independently reviewed and Accepted it only after the
  database dump/manifest passed independent restore parity.

## Accepted evidence

- Frozen matrix SHA-256: `eaba2ecb93f1418b90ece45e91d7071d638095897bdd6a2c012efe6a9db9a923`.
- Durable replay-summary SHA-256: `a88b44fab38d4e56a7894fabb93e56b46c043278082c200773c038a7dc6e80b5`.
- Entry-summary SHA-256: `5b77b4a4f3ea9f0a0fd4667dfccff6afefa968b5fb43124de816e652d1c58293`.
- Candidate identity: `miroflow_canonical_v2_candidate_s3b`, exact isolated-candidate marker,
  PostgreSQL system identifier `7661313446684311592`, C2_0004, network-none, no ports.
- Durable counts: 15 artifacts, six ingest/parser runs, 21 records, six source errors; 17 parsed and
  four partial records; four accepted and two partial runs; six roots plus nine valid parent edges.
- Non-landing knowledge/publish tables remain exactly empty. Three repeated durable executions
  retained the same counts and byte-identical summary.
- Real disposable database baseline/integrity/landing verification is `35 passed`; default Canonical
  V2 is `73 passed, 33 explicit skips, 4 expected xfails`; S1 is `10 passed, 5 skips`; S2/S2B is
  `32 passed`.
- Task 4.4 commit `cef42a1e075d30c5a0e179f34ab543b4878edabd` is Accepted by Task 4.5.
  Checkpoint manifest `ab091aac...966b1` restored with exact logical parity under verification
  `caf789ae...f0acc`. No canonical construction, live recollection, release, index, or promotion is
  claimed.

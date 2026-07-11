# Verification Contract: rebuild-canonical-v2-knowledge-platform

## Status

S1 database-target safety is Accepted at commit `a58184c`. S2 read-only baseline tasks 2.1–2.5 and
their corpus/ground-truth/threshold policy are Accepted. S2B/task 2.6 is Accepted with backup
manifest `a14c1eab…e59c8`, restore verification `98826e8d…d231`, and acceptance record
`3155d890…fc5b`. Task 3.1's five deep-module RED interface contracts and Task 3.2's clean empty
database baseline are Accepted. Task 3.3's shared typed contracts are Accepted. Task 3.4 is next. No
landing evidence, canonical business row, published projection, or index write has begun.

## Behavior owner

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Acceptance: `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- Effect baseline: `.agents/runs/canonical-v2-logical-rebuild/outcome-requirements.md`

## Verification objective

Prove that a clean isolated Canonical V2 platform can be reconstructed from immutable evidence,
serve broad and precise four-domain/relationship retrieval with universal current-Web augmentation,
produce claim-grounded progressive answers, and publish canonical/index releases consistently and
reversibly without touching original forensic sources. Prove first that every required source family
has a content-addressed backup and independently verified recovery path, and that online query paths
cannot mutate offline canonical identity decisions.

## Environment and forbidden targets

- Original Postgres container: `pgtest`, last checked `paused=true`, exposed host port `15432`.
  It MUST remain paused and is never a connection, migration, repair, replay, or write target.
- Original Postgres volume:
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`. The paused
  source container still has its historical read-write mount, so no command may unpause or enter it;
  only the Accepted S2B copy run mounted it `rw=false`, and implementation tests may not mount it.
- Forensic checkpoint root:
  `/home/longxiang/.mirothinker_recovery/20260711T022932Z-pgtest-forensic-freeze/`;
  canonical source/copy manifest SHA-256:
  `bce14dce8fe2da4d053ac9cd930e1532f4abb436c5d03fff07aa69fd180e9e91`.
- Verified FPI salvage dump SHA-256:
  `cef8eb6ba18ebd23fde3e47023222ecb82bc8f27582040efe5a212a7f9fdfbb7`.
- Original repository Milvus file:
  `apps/miroflow-agent/milvus.db`, SHA-256
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
  No Milvus client may open it; hash-only checks are allowed.
- Recovery lab: `pgtest-recovery-lab-01`, network `none`, no exposed ports. Approved existing
  isolated databases are `miroflow_recovery_candidate` and
  `miroflow_recovery_candidate_verify`; S1 tests must use newly created disposable targets, not these
  evidence checkpoints.
- Candidate and disposable database DSNs: explicit full DSNs only; target database name/identity
  must be asserted before any destructive command.
- A generic `DATABASE_URL` is never accepted as fallback for migration/test/rebuild targets.
- Real provider calls are allowed only in named acceptance runs with secrets from the approved
  environment and no credential values in logs/evidence.
- Backup/restore gate: Accepted S2B evidence is in
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/`. Every future rebuild-write entry point
  must verify the exact acceptance record before its first write; changed/missing evidence fails
  closed.
- S2B backup coverage MUST include original PostgreSQL, original Milvus, WAL/FPI, salvage, and all
  inventoried historical SQLite/JSONL/XLSX/PDF/cache/raw-source families. Restore targets must be
  distinct from original and backup locations; original volumes/files remain read-only.

Last identity/hash check recorded in `verification.md`: `2026-07-11T16:19:12Z`.

## Hard invariants

1. Original Postgres/Milvus write attempts: zero.
2. Destructive target-identity ambiguity: fail before writes.
3. Wrong-identity canonical merge or cross-domain join in reviewed gold: zero.
4. Invented placeholder entity/fact/evidence from partial recovery: zero.
5. Unsupported material answer claims in accepted samples: zero.
6. Unsourced material current-Web claims: zero.
7. Broken canonical relationship references: zero.
8. Mixed canonical/published/Milvus release IDs: zero.
9. Unexplained missing/extra/stale/cross-release index points: zero.
10. Direct online Web/LLM write to active canonical/index: zero.
11. Canonical V2/landing write before accepted complete backup and restore verification: zero.
12. Query/answer-path canonical identity or source-identity mapping mutation: zero.

## RED artifacts by slice

### S1 — Database target safety

- Integration tests invoke Alembic/test helpers with conflicting generic and explicit DSNs.
- RED proves current code can select/fall back to the wrong target or lacks identity assertion.
- GREEN proves only the explicit disposable target changes and ambiguous/missing targets fail closed.

### S2 — Baseline and thresholds

- Read-only inventory manifests and reviewed corpus manifests.
- Baseline reports for data/relationship coverage, path reach, recall, precision, ranking, answer
  support, Web behavior, latency, and cost.
- `acceptance-thresholds.json` approved before later slices become Ready.

### S2B — Complete source backup and independent restore gate

- A reviewed source-to-backup manifest proves family completeness, source/backup identities, byte
  sizes, SHA-256, copy run/time, storage location, and no hard-link dependence.
- A second isolated restore/materialization target proves PostgreSQL database/revision/schema/count,
  Milvus copy schema/collection/count, and file/recovery-family hash plus bounded readability/replay.
- RED gate tests prove missing families, hash mismatch, source-path use, absent restore evidence, or
  failed probes reject task 3.2 and all Canonical V2/landing writes before their first write.
- Original Postgres remains quiesced; any dedicated backup mount is read-only. Original Milvus is
  copied without opening a client; only the verified copy may be inspected.
- Accepted evidence covers 50/50 source records and passed PostgreSQL, Milvus, forensic/WAL/FPI,
  mount-policy, independent-materialization, and source-invariant probes.

### S3–S7 — Data platform and release

- Real isolated Postgres migration/constraint/transaction tests.
- Chain-of-custody replay and hash fixtures for every source-adapter family.
- Identity/fusion/relationship/eligibility scenario matrices through module interfaces.
- Candidate manifest, full-index build, exact parity, promotion rehearsal, and rollback rehearsal.

### S8–S10 — Query, answer, and feedback

- Scenario eval and trace replay are mandatory RED/GREEN evidence; unit-only evidence is insufficient.
- Recorded external-provider adapters cover success, timeout, invalid schema, conflict, duplicate,
  missing evidence, and budget exhaustion.
- Named real-provider acceptance run covers Universal Web, LLM plan/rerank/sufficiency/synthesis,
  claim citation, progressive multi-turn behavior, latency, and cost.

### S11–S12 — Consumer migration and final candidate

- API/admin/state integration, reviewed regression/challenge eval, and complete isolated rebuild.
- Broad checks run only after S1 Accepted and with explicit disposable/candidate targets.

## Required evidence shape

Every verification run SHALL record:

- run ID, timestamp, git commit/worktree state, OpenSpec hash, corpus/threshold versions;
- explicit sanitized database/index target identities and release IDs;
- command and exit code;
- source/parser/policy/model/prompt/schema/embedding/reranker versions as applicable;
- counts, hashes, per-domain/path metrics, failures, and hard-invariant results;
- provider availability, calls, latency, cost, and degradation path;
- artifact paths and SHA-256 hashes;
- for S2B, source/backup/restore identities, family completeness, copy independence, format-specific
  recovery probes, and the accepted backup-manifest hash;
- reviewer/acceptance status without claiming later-slice closure.

## Verification order

1. Static/OpenSpec validation.
2. Nearest pure/interface tests.
3. Complete backup manifest and independent recovery verification; accept S2B before any rebuild
   write.
4. Real isolated Postgres migration/integration tests.
5. Recorded adapter/trace replay scenarios.
6. Bounded isolated source/candidate replay.
7. Full versioned Milvus candidate and parity.
8. API/session/admin integration.
9. Frozen regression then challenge evaluation.
10. Named real-provider acceptance.
11. Rollback rehearsal and final evidence review.

## Stop conditions

- Original source pause/hash/identity changes unexpectedly.
- Any command resolves to a forbidden or ambiguous target.
- A hard invariant fails.
- A slice requires behavior absent from the OpenSpec capability.
- A later slice depends on a predecessor not marked Accepted.
- Threshold, corpus, schema, policy, or model version changes without a new versioned baseline.
- Verification evidence cannot distinguish local, current-Web, LLM inference, or release identity.
- A task 3.2+ or other rebuild-write command is proposed before complete S2B backup/restore evidence
  is reviewed and Accepted.
- Query/answer code attempts to create, merge, split, relink, or update canonical identities or
  source-identity mappings instead of emitting an offline review gap.

## Completion rule

The Epic reaches Candidate only when all slices are independently Accepted, every acceptance item is
evidenced, strict OpenSpec validation passes, and the complete isolated candidate passes the frozen
gates. Candidate does not authorize production-like cutover.

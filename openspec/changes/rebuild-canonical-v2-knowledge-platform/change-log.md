# Change Log

## 2026-07-11

- Created the breaking pre-launch Canonical V2 Epic from the user-confirmed PRD/effect grill.
- Selected a clean typed platform over V042 sidecars and a fully generic knowledge graph.
- Added six new capability specs and modified Paper identity and Professor split-index behavior.
- Added staged tasks, acceptance gates, source/agent links, and the verification contract.
- Implemented and accepted S1 database-target safety: dedicated destructive target inputs,
  server-side database identity marker, fail-closed Alembic enforcement, direct seed-loader sibling
  protection, RED/GREEN coverage, and a real isolated upgrade/downgrade cycle.
- Original Postgres and Milvus remained frozen; no recovery replay, Canonical V2 schema, broad
  migration suite, or cutover was performed.
- Completed S2 task 2.1 at the S1 checkpoint: deterministic read-only inventory covers authoritative
  PRDs, workbook/backfills, ignored historical SQLite/JSONL/XLSX/cache/release/PDF families,
  forensic recovery artifacts, and recovery-database counts. Original Milvus remains hash-only
  because no verified copy exists.
- Completed S2 task 2.2: the reviewed source-to-PRD matrix maps four domains, typed sub-objects,
  relationship families, retrieval/answer paths, and all six north-star effects to inventoried
  evidence, explicit ceilings, and future owning slices.
- Completed S2 task 2.3: froze deterministic 40-case regression and 12-case challenge corpora with
  source/protected-slot/A-G metadata. User-confirmed workbook answers/key points are case-specific
  reference ground truth, including an explicitly marked known-bad historical response; generated
  PRD/challenge expectations remain pending review and are not treated as factual gold.
- Added the user-confirmed pre-rebuild safety gate: task 2.6/S2B must back up and independently
  restore-verify original PostgreSQL, Milvus, WAL/FPI, salvage, and every inventoried historical
  source family before task 3.2 or any Canonical V2/landing write. Also made offline data builds the
  sole canonical-identity mutation authority; query/answer paths are identity-read-only.
- Completed S2 task 2.4: the deterministic nine-dimension report separates current measurements,
  legacy evidence, and unavailable metrics. Current offline intent fallback is 100/100; current
  retrieval/answer/Web/provider metrics remain unavailable, and legacy precision is explicitly
  unscored rather than treated as zero-false-positive acceptance.
- Completed and accepted S2 task 2.5: froze 24 PRD minima, 25 hard invariants, and 34 calibrated
  product-effect gates. The Accepted registry is cryptographically bound to the exact reviewed
  Candidate; the user also accepted the corpus ground-truth policy and S2 tasks 2.1–2.5. Task 2.6
  remains the mandatory backup/independent-restore gate before any rebuild write.
- Completed and accepted task 2.6/S2B under the user's objective-verification self-approval
  authorization. Content-addressed backup and independent restore cover 48 frozen inventory records
  plus original PostgreSQL and the forensic/WAL/FPI tree; PostgreSQL, Milvus, and forensic probes
  passed. A shared mount-policy repair also removed seven attributable empty anonymous volumes and
  prevents Postgres-image implicit volumes in S2B tool containers.
- Completed and accepted task 3.1 as a test-only RED slice: five strict-xfail contracts freeze the
  typed public seams and observable outcomes for EvidenceLanding, KnowledgeBuild, KnowledgeRead,
  KnowledgeAnswer, and ReleasePublication. Normal pytest stays green while `--runxfail` proves five
  genuine missing-module RED failures; no production module or database write was added.
- Completed and accepted task 3.2: an independent `C2_0001` Alembic history verifies the exact S2B
  admission before engine creation and target identity before DDL, then creates eight empty
  Canonical V2 namespaces without replaying V001–V042. A new network-none/no-port, marked candidate
  passed upgrade/downgrade/re-upgrade and remains at the clean baseline with no business rows.

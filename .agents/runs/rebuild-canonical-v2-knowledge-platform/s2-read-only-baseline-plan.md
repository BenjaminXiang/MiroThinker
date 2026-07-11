# S2 Read-only Baseline and Threshold Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce an immutable, auditable S2 evidence package that freezes available source coverage,
scenario corpora, current/legacy baseline measurements, and PRD-grounded acceptance thresholds.

**Architecture:** Treat every source and metric as an evidence record with identity, time, substrate,
hash, authority, and limitation. Database evidence is queried only in forced read-only sessions;
filesystem evidence is hashed without mutation; corpus and threshold artifacts are deterministic
review inputs, not production behavior.

**Tech Stack:** Git, OpenSpec, PostgreSQL 16 `psql`, SHA-256, JSON/JSONL, Markdown, Python 3.12
read-only validation, `openpyxl` for workbook inspection.

---

### Task 1: Freeze safety and source inventory

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/build_source_inventory.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/test_build_source_inventory.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/recovery-db-readonly-snapshot.json`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/source-inventory.json`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`

- [x] Record commit/worktree, `pgtest` pause/volume, recovery-lab network/ports, Milvus hash,
  forensic manifest hash, and salvage dump hash.
- [x] Add RED tests proving the inventory builder uses immutable SQLite mode, hashes Milvus-like
  files without opening them, and produces deterministic aggregate manifests; implement only after
  the RED failures are observed.
- [x] Inventory authoritative PRDs, workbook, committed JSONL/XLSX/SQLite/Milvus artifacts, recovery
  checkpoint documents, and recollection-capable source families with size and SHA-256.
- [x] Query `miroflow_recovery_candidate` and `miroflow_recovery_candidate_verify` only with
  `PGOPTIONS='-c default_transaction_read_only=on'`; record database identity, read-only flag,
  schema/table names, row counts, and Alembic revision if present.
- [x] Validate `source-inventory.json` with `python -m json.tool` and recompute listed hashes.

### Task 2: Map sources to PRD outcomes

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/source-coverage-matrix.md`

- [x] Extract domain inclusion, typed object/sub-object, evidence, identity, temporal, quality, and
  relation requirements from the authoritative shared/domain PRDs.
- [x] Map each requirement family to available recovery/historical/recollection sources and label it
  `covered`, `partial`, `missing`, or `recollectable` with an evidence reference.
- [x] Separate object coverage from exact/semantic/filter/relation retrieval reach and from answer
  synthesis; record the known ceiling and owning future slice for every gap.
- [x] Review the matrix against the six confirmed outcome requirements and relationship-family
  catalog in the parent OpenSpec.

### Task 3: Freeze regression and challenge corpora

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/corpora/regression-v1.jsonl`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/corpora/challenge-v1.jsonl`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/corpus-manifest.json`

- [x] Read `docs/测试集答案.xlsx` without modification and convert its information-retrieval rows
  into seed cases retaining workbook row identity and user-confirmed, case-specific reference
  answers/key points with provenance; do not generalize them into an answer template.
- [x] Add PRD-derived exact, semantic, structured-filter, relationship, A-G, multi-turn, Universal
  Web, provenance, conflict, partial-answer, and evidence-based-assessment families.
- [x] Add separately versioned alias, spelling, time/geography/negation, relation-direction,
  referent, displayed-set, topic-switch, provider-failure, and insufficient-evidence challenges.
- [x] Give every case an observable expected behavior, protected slots, source, and review status;
  do not invent factual gold beyond workbook/PRD/verified evidence.
- [x] Parse every JSONL line, calculate corpus SHA-256/counts, and write `corpus-manifest.json`.

### Task 4: Record current and legacy baseline

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/baseline-report.json`

- [x] Recount committed benchmark fixtures and stored reports without modifying their oracle,
  scorer, corpus, or outputs.
- [x] Record read-only evidence coverage and relationship counts from Task 1.
- [x] Run deterministic/offline benchmark checks that do not require production data, Milvus, Web,
  LLM, or secrets; record exact command, commit, corpus hash, and result.
- [x] Label each metric `measured_current`, `legacy`, or `unavailable`; explain destroyed/stale/missing
  substrate and prohibit comparisons across changed populations/oracles.
- [x] Include coverage/reach, Recall@K, Precision@K/rank, intent, answer support/citation, Universal
  Web, multi-turn, latency, provider calls, and cost even when the honest value is unavailable.

### Task 5: Freeze thresholds and obtain acceptance

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/acceptance-thresholds.json`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/review.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`

- [ ] Encode PRD minima unchanged: intent accuracy `>=0.90`, applicable Top-5 relevance `>=0.85`,
  applicable human summary quality `>=4.0/5.0`, company semantic retrieval `<=5s`, context resolve
  `<500ms`, session TTL `1800s`, and route TTFT `5–25s` where applicable.
- [ ] Add hard invariants and calibrated per-domain/path recall, precision, relation, provenance,
  support, Web invocation, multi-turn, latency, and cost gates with rationale and corpus version.
- [ ] Mark unapproved calibrated values pending rather than choosing implementation-convenient gates.
- [ ] Validate all JSON/JSONL, hashes/counts, OpenSpec strict validity, source invariants, and clean
  scope diff; write review evidence.
- [ ] Present corpus/threshold decisions for user acceptance. Mark tasks 2.1–2.5 and S2 Accepted only
  after review; do not start S3 in the same acceptance step.

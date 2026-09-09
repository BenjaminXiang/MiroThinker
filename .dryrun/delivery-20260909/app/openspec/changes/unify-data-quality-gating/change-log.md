# Change Log — unify-data-quality-gating

- **2026-06-26** — Cross-domain data-collection/cleaning audit (four parallel
  Explore agents + `docs/index.md` + 6/22 portfolio) surfaced quality-gate
  fragmentation as a systemic gap: two parallel systems
  (`quality/promotion_rules.py` batch vs per-domain `quality_promotion.py`)
  that do not reference each other; paper's `evaluate_paper_promotion` bypassed
  by an inline SQL `CASE` in the canonical writer; company has no write-time
  gate; patent absent from the batch system. Root consequence: rows can be
  collected + cleaned but not promoted to `ready` at write time → not indexed
  in Milvus → not retrievable via `/api/chat`.
- **2026-06-26** — User decision: split the cross-domain structural fix into
  two sibling changes — `unify-data-quality-gating` (this change) +
  `harden-entity-normalization`. Independent code paths, independent
  verification. User flagged retrieval-readiness as the core concern; made it
  the explicit invariant of this change.
- **2026-06-26** — Created OpenSpec change `unify-data-quality-gating` (Epic,
  behavior-affecting, new capability `data-quality-gating`): `proposal.md`,
  `specs/data-quality-gating/spec.md`, `design.md`, `tasks.md`,
  `acceptance.md`, `source-links.md`, `agent-links.md`, this log.
- **Pending** — verification-contract (task 1.1), implementation (Codex,
  `tasks.md`), real dry-run / bounded apply / Milvus re-backfill evidence,
  `change-ledger.md` registration, `openspec validate --strict`.
- **2026-06-26 (re-scope, DB-grounded)** — read-only `miroflow_real` scan
  measured the real gating delta: **paper 66** ready-worthy-but-not-`ready`
  rows (write-path `CASE` bypass; all have `summary_zh` ≥ 150 so the backfill
  ran), **company 0** (6,514/6,514 already `ready`), **patent 0 ready but
  11,408/11,408 `partial`** because `patent_type` is NULL on every row
  (source-data defect, NOT gate logic — `evaluate_patent_promotion` is already
  wired at `release.py:251` and returns `partial` correctly). **Downgraded
  Epic → Standard.** Cut the company write-time state machine (0 delta). Patent
  moved to out-of-scope (separate patent-sourcing change owns the 0-ready gap).
  Added Milvus rebackfill coupling (Defect M) so the 66 promoted rows + future
  Phase-3 output become retrievable. Rewrote proposal/specs/design/tasks/
  acceptance to the measured scope. Sibling `harden-entity-normalization`
  WITHDRAWN same day — its premise (strengthen person-name matching for
  inventor links) is invalidated: `inventors_parsed` is empty `[]` for all
  11,408 patents (no xlsx inventor column alias; R20). The strict-normalizer
  concept is deferred to a future patent-inventor-sourcing change if inventor
  data is acquired.

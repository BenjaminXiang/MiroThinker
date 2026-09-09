# Change Log — infer-patent-type-from-patent-number

- **2026-06-26** — Cross-domain DB-grounded audit found patent **0/11,408
  ready (all `partial`)** → 0 retrievable. Root cause: `patent_type` NULL on
  every row → `evaluate_patent_promotion` requires `has_patent_type` →
  `partial`. The patent gate is correct; the field is missing.
- **2026-06-26** — Feasibility investigation (source-xlsx header inspection +
  `patent_number` kind-code scan) scoped the fix:
  - The source xlsx (`11月专利完整版.xlsx`, 11,408 rows) has columns
    标题/摘要/申请人/公开（公告）号/公开（公告）日/技术功效句 — **no 专利类型**.
  - No patent API exists; external enrichment is design-forbidden
    (`patent/quality_promotion.py:5`).
  - But `patent_number` (e.g. `CN115709471A`) deterministically encodes type:
    kind-code `A`/`B`→发明, `U`/`Y`→实用新型, `S`/`D`→外观设计 (leading-digit
    fallback 1/2/3). Scan: `CN…A` 7,485 + `CN…U` 3,923 = 11,408 (100% covered).
  - So `patent_type` is inferable from already-collected `patent_number` with
    **no new data source, no API, no design-constraint relaxation**.
- **2026-06-26** — User chose the patent-sourcing direction (option A) with a
  feasibility-first mandate. Feasibility revealed the biggest piece (patent_type
  → 11,408 retrievable) needs no new data; inventors remain data-blocked (no
  发明人 source column; enrichment forbidden) → deferred to a separate change.
- **2026-06-26** — Created OpenSpec change `infer-patent-type-from-patent-number`
  (Standard, behavior-affecting, new capability `patent-type-inference`):
  `proposal.md`, `specs/patent-type-inference/spec.md`, `design.md`,
  `tasks.md`, `acceptance.md`, `source-links.md`, `agent-links.md`, this log.
- **Pending** — verification-contract (task 1.1), implementation (Codex,
  `tasks.md`), real dry-run + bounded backfill + Milvus rebackfill evidence,
  `change-ledger.md` registration, `openspec validate --strict`.
- **2026-06-26 (implementation + scope expansion)** — Codex implemented slices
  1.2/1.3/2.1/2.2 (type_inference.py + release.py wiring + tests; 34 tests
  GREEN, ruff clean; §10 review accepted — the 1 `test_release` failure is
  pre-existing, confirmed by stash, unrelated company-linking). Codex then wrote
  the backfill script (`run_patent_type_inference_backfill.py`). Claude's real
  `--dry-run` on `miroflow_real` reported **`promoted_to_ready=0`** (not 11,408):
  the gate requires `has_filing_or_grant_date`, but all 11,408 patents have only
  `publication_date` (source xlsx has `公开（公告）日`, no `申请日`). Confirmed the
  fix: relaxing the gate's date signal to accept `publication_date` yields
  11,408→ready (was 0). **Scope expanded** to include this one gate relaxation
  (task 2.3, RED #7). Updated spec/proposal/tasks/verification-contract: the
  date-signal relaxation is the ONLY permitted gate change; all other ready
  criteria, the enum, forward-monotonicity, and the no-enrichment constraint
  remain unchanged. Apply NOT run — pending the 2.3 implementation + a dry-run
  showing `promoted_to_ready=11,408`.

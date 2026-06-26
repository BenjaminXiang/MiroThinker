# Proposal: infer-patent-type-from-patent-number

## Why

The patent domain is the single biggest "collected but not retrievable" gap: a
2026-06-26 read-only scan of `miroflow_real` found **11,408 patents, 0 `ready`
(all `partial`)**, so **zero** are indexable by Milvus → none retrievable via
`/api/chat`. Root cause: `patent_type` is **NULL on every row**, and the patent
quality gate (`evaluate_patent_promotion`) requires `has_patent_type` for
`ready` — without it the gate correctly returns `partial`
(`patent/quality_promotion.py`). The gate logic is fine; the field is missing.

The field is missing because the source xlsx that populated the 11,408 rows
(`data/admin_uploads/patent/.../11月专利完整版.xlsx`) has columns
`标题/摘要/申请人/公开（公告）号/公开（公告）日/技术功效句` but **no `专利类型`
column**. There is no patent API in the codebase, and external patent
enrichment is design-forbidden (`patent/quality_promotion.py:5`: "Patent has no
external enrichment; only xlsx-merge can enrich").

But `patent_type` does **not** need a new data source: the Chinese patent
number already collected on every row (`patent_number`, e.g. `CN115709471A`)
**deterministically encodes the type** via its kind-code suffix and leading
digit:

- suffix `A`/`B` (or leading `1`) → 发明 (invention)
- suffix `U`/`Y` (or leading `2`) → 实用新型 (utility model)
- suffix `S`/`D` (or leading `3`) → 外观设计 (design)

A scan confirms the corpus is exactly `CN…A` (7,485) + `CN…U` (3,923) = 11,408.

So `patent_type` can be **inferred from `patent_number` with no new data, no
API, and no relaxation of the no-external-enrichment constraint**. Once
populated, the existing gate promotes all 11,408 to `ready`; a Milvus rebackfill
makes them retrievable. This is the highest-leverage, fully-feasible retrieval
move in the patent domain.

This change is **behavior-affecting** (populates `patent_type`; flips
`quality_status` partial→ready for 11,408 rows; changes Milvus indexability)
and **Standard** weight (deterministic inference, but mass status mutation).

## What Changes

1. **ADD** a new capability `patent-type-inference` (baseline + contract in
   `specs/`): `patent_type` SHALL be derived from `patent_number` when absent,
   via the CN kind-code mapping (A/B→发明, U/Y→实用新型, S/D→外观设计) with a
   leading-digit fallback (1/2/3, plus 8/9 PCT). The inference SHALL be
   deterministic and SHALL NOT overwrite a non-null `patent_type`.

2. **ADD** `infer_patent_type(patent_number, *, current_type=None)` in
   `patent/` (pure function): returns the inferred type or `None` if the number
   has no recognizable type signal.

3. **MODIFY** the patent import/canonical path: when `patent_type` is absent
   after xlsx mapping, compute it via `infer_patent_type(patent_number)` before
   the quality gate runs, so newly imported patents are `ready`-eligible at
   write time.

4. **ADD** a one-time backfill that populates `patent_type` for the existing
   11,408 rows (each carrying `run_id`), after which the existing
   `evaluate_patent_promotion` promotes them to `ready`.

5. **RELAX** the gate's date signal to accept `publication_date`
   (`filing_date OR grant_date OR publication_date`). The source xlsx provides
   only `公开（公告）日` (`publication_date`); without this relaxation the 11,408
   stay `partial` even with `patent_type` inferred (a 2026-06-26 dry-run
   confirmed `promoted_to_ready=0` before the relaxation, `11,408` after). This
   is the only gate change; all other ready criteria, the enum,
   forward-monotonicity, and the no-enrichment constraint are unchanged.

6. **ADD** a Milvus rebackfill of `patent_profiles` so the 11,408 newly-`ready`
   patents become retrievable.

Non-goals (deferred):

- **Patent inventors / `professor_patent_link`** — the source xlsx has no
  `发明人` column and external enrichment is design-forbidden, so inventor
  data is unavailable. `professor_patent_link` stays 0. A separate
  patent-inventor-sourcing change (blocked on a data-source decision: re-exported
  xlsx with `发明人` OR a design change to allow a patent API) owns this. Note:
  patent↔professor is *partially* reachable today via the company hop
  (`patent → company_patent_link → company → professor_company_role`), which is
  unaffected by this change.
- **No change to the quality gate EXCEPT the `publication_date` date-signal
  relaxation** (point 5). The `quality_status` enum, the no-external-enrichment
  constraint, and all other ready criteria are unchanged.
- **No patent API / external provider.** Inference is purely from already-
  collected `patent_number`.
- **No change to classification A–G, `_VALID_DOMAINS`, evidence shape, or any
  serialized public format.**

## Capabilities

### New Capabilities
- `patent-type-inference` — derive `patent_type` from `patent_number` when
  absent (baseline + contract in `specs/`).

### Modified Capabilities
<!-- none -->

## Impact

- **Affected code** (all under `apps/miroflow-agent/`):
  - NEW `src/data_agents/patent/type_inference.py` — `infer_patent_type` (pure,
    unit-tested, no DB).
  - UPGRADE the patent import/canonical path to call `infer_patent_type` when
    `patent_type` is absent (e.g. `patent/import_xlsx.py` /
    `patent/release.py::_calculate_quality_status` input /
    `patent/canonical_writer.py`).
  - NEW one-time backfill script (e.g.
    `scripts/run_patent_type_inference_backfill.py`) — populate `patent_type`
    for the 11,408 rows + re-evaluate `quality_status` via the existing gate.
- **Storage**: no migration. `patent_type` column already exists; only its
  values are populated.
- **Retrieval impact (the core concern)**: 11,408 patents partial → `ready`;
  after the Milvus rebackfill, the entire current patent corpus becomes
  retrievable (was 0). A dry-run reports the partial→ready count before apply.
- **Rollback**: revert code + clear the inferred `patent_type` (the backfill
  records which rows it touched, by `run_id`); `quality_status` reverts to
  `partial` on re-evaluation. No irreversible migration.

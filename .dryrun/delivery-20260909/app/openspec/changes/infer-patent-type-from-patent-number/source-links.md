# Source Links — infer-patent-type-from-patent-number

> Per CLAUDE.md §14.3 (touch-to-promote). Legacy docs / code consulted and what
> was extracted into the new `patent-type-inference` capability spec.

## Consulted legacy sources

- **`docs/Data-Agent-Shared-Spec.md`** — extracted the patent-canonical field
  expectations and the retrieval-readiness stance (`quality_status` gates
  indexability).
- **`docs/Patent-Data-Agent-PRD.md`** — extracted the patent canonical field
  set (patent_number, title, patent_type, applicants, dates) and the
  "no external enrichment" design posture.
- **`docs/audits/patent-requirement-code-reconciliation-2026-05-10.md`** —
  extracted R12 (patent_number identity anchor ✅) and the patent quality-gate
  findings.
- **`docs/index.md` (2026-06-26 correction block)** — extracted the grounded
  patent baseline: 11,408 total, 0 ready (all partial), `patent_type` NULL on
  every row.

## Code anchors extracted into the design

- `data_agents/patent/quality_promotion.py:5` — the no-external-enrichment
  design constraint ("only xlsx-merge can enrich"); confirms inference (derivation
  from collected `patent_number`) is the design-compliant path, NOT an external
  API.
- `data_agents/patent/quality_promotion.py::evaluate_patent_promotion` +
  `PatentEnrichmentSignals.has_patent_type` — the gate requiring `patent_type`
  for `ready`; reused unchanged.
- `data_agents/patent/release.py::_calculate_quality_status:241` — where
  `PatentEnrichmentSignals` is built (`has_patent_type=bool(
  _normalize_patent_type_for_canonical(patent_type))`); inference feeds this.
- `data_agents/patent/import_xlsx.py::_COLUMN_HEADER_ALIASES` — already maps
  `专利类型` → `patent_type`; the source xlsx simply lacks the column.
  Confirmed by inspecting `11月专利完整版.xlsx` headers (6 cols, no 专利类型).
- `data_agents/patent/import_xlsx.py::_normalize_patent_type_for_canonical`
  (line ~247: `if "发明" in text: return "发明"`) — the normalizer the inference
  must satisfy (emit 发明/实用新型/外观设计).
- `storage/milvus_*::_is_indexable_patent` — the retrieval-readiness consumer
  (keys on `quality_status=='ready'`); unchanged.

## What was NOT migrated

- Patent inventors / `professor_patent_link` (R17/R20) — data-blocked (no
  发明人 source column; no API; enrichment forbidden). Separate change.
- Patent API / external enrichment — design-forbidden; explicitly out of scope.
- The quality gate, the enum, the no-enrichment constraint — unchanged.

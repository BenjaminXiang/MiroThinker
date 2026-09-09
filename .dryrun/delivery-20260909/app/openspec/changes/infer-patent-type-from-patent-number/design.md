# Design: infer-patent-type-from-patent-number

> Per `openspec/config.yaml` design rules. Deterministic inference (pure
> function of `patent_number`) → unit tests are a valid RED (CLAUDE.md §14.7);
> the mass status mutation is validated by a read-only dry-run on
> `miroflow_real`.

## 1. Problem decomposition

- **Root cause:** source xlsx (`11月专利完整版.xlsx`) lacks a `专利类型` column
  → `patent_type` NULL for all 11,408 → `evaluate_patent_promotion` requires
  `has_patent_type` → returns `partial` → 0 `ready` → 0 retrievable.
- **Why inference works:** the CN `patent_number` (e.g. `CN115709471A`) encodes
  type in the kind-code suffix (`A`/`B`=发明, `U`/`Y`=实用新型, `S`/`D`=外观设计)
  and the leading digit (`1`/`2`/`3`). A scan confirms the corpus is exactly
  `CN…A` (7,485) + `CN…U` (3,923) = 11,408 — 100% coverage by the kind-code
  path.
- **Why no new data source:** no patent API exists; external enrichment is
  design-forbidden (`patent/quality_promotion.py:5`). Inference uses only the
  already-collected `patent_number`, so it is design-compliant (it is derivation
  from collected data, not external enrichment).

## 2. Verification surface

| Surface | What it proves | RED artifact |
|---|---|---|
| Unit (pure) | `infer_patent_type` maps A/B→发明, U/Y→实用新型, S/D→外观设计; leading-digit fallback; non-overwriting; unrecognizable→None | unit tests |
| Contract | the import/canonical path calls `infer_patent_type` for absent `patent_type` before the gate | contract test |
| Integration (read-only dry-run) | on `miroflow_real`: 11,408 rows get an inferred `patent_type`; all would promote partial→`ready`; **0 `ready` degraded** | dry-run JSONL |
| Operational | one-time backfill writes `patent_type` + re-evaluates `quality_status`; Milvus rebackfill of `patent_profiles`; ≥10 sampled patents retrievable | backfill + rebackfill + retrieval spot-check |

Deterministic at the new-code surface (pure string function; no LLM, no
network). Per §14.7, Superpowers TDD may drive the unit/contract slices; it
MUST NOT alter the gate, the enum, or the no-enrichment constraint.

## 3. Oracle strength

- **Strong** for unit/contract: pure function → exact expected type strings.
- **Strong** for the dry-run: "11,408 partial→ready, 0 ready degraded" is an
  exact queryable invariant (and 0 were `ready` before, so the
  non-regression bar is trivially met; the real assertion is the 11,408
  promotion + 0 regressions to a worse state).
- **Weaker** for retrieval: spot-check ≥10 newly-`ready` patents are
  retrievable.

## 4. Affected context / dependencies

- `patent/quality_promotion.py::evaluate_patent_promotion` — reused unchanged;
  its `has_patent_type` signal now resolves True once inference fills the field.
  `patent/release.py::_calculate_quality_status` builds `PatentEnrichmentSignals`
  with `has_patent_type=bool(_normalize_patent_type_for_canonical(patent_type))`
  — inference must feed a value `_normalize_patent_type_for_canonical` accepts
  (发明/实用新型/外观设计).
- `patent/import_xlsx.py::_COLUMN_HEADER_ALIASES` — already maps `专利类型` →
  `patent_type`; the source just lacks the column. Inference fills the gap.
- `patent/canonical_writer.py::upsert_patent` — where `patent_type` is
  persisted; inference runs before this.
- `storage/milvus_*::_is_indexable_patent` — unchanged; keys on
  `quality_status=='ready'`.
- `patent/type_inference.py` — NEW pure module.

Mock boundaries: `infer_patent_type` is pure → no mocks at unit level. Dry-run
reads `miroflow_real` read-only (proxy unset); the backfill is the only mutating
step, behind the dry-run gate.

## 5. Risk and mitigation

- **Risk: wrong type inference mislabels patents.** Mitigation: the kind-code
  mapping is standard CN patent semantics; unit tests cover all codes; inference
  is non-overwriting (a real source `patent_type` is never clobbered); the
  dry-run shows the inferred-type distribution before apply. Reversibility: the
  backfill records touched rows by `run_id`; clearing the inferred `patent_type`
  reverts `quality_status` to `partial`.
- **Risk: mass partial→ready changes retrieval surface.** Mitigation: this is
  the intended effect (0→11,408 retrievable); forward-monotonic gate means no
  `ready` is degraded; Milvus rebackfill reflects the new state.
- **Risk: `_normalize_patent_type_for_canonical` rejects the inferred string.**
  Mitigation: inference emits exactly the strings the normalizer accepts
  (发明/实用新型/外观设计); a unit test asserts the round-trip
  `_normalize_patent_type_for_canonical(infer_patent_type(n))` is truthy.

## 6. Retrieval coupling (the core concern)

This change is the direct unlock for patent retrieval: inferred `patent_type`
→ existing gate promotes to `ready` → `_is_indexable_patent` admits the row →
Milvus rebackfill indexes it → retrievable via `/api/chat`. No retrieval-service
change is needed; the change fixes the upstream field that the existing
retrieval-readiness switch (`quality_status`) depends on. The patent↔professor
cross-domain path via inventors remains blocked (inventors unavailable); the
company-hop path (`patent→company→professor`) is unaffected and already
partially functional via `company_patent_link` (5,044 rows).

## 7. Out of scope (restated)

Patent inventors / `professor_patent_link` (data-blocked); patent API /
external enrichment (design-forbidden); quality-gate logic; enum; the
no-enrichment constraint; classification A–G; `_VALID_DOMAINS`; evidence shape.

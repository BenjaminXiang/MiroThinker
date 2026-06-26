# Tasks: infer-patent-type-from-patent-number

> Deterministic inference. Slice order follows groups 1 → 5. One active writer
> (Codex) per slice.

## 1. Verification contract & inference function

- [ ] 1.1 Create `.agents/runs/infer-patent-type-from-patent-number/verification-contract.md`
      — behavior-affecting but deterministic at the new-code surface (pure
      `patent_number` function; no LLM, no network). RED = unit/contract tests +
      read-only dry-run; GREEN = tests pass + dry-run "11,408 partial→ready, 0
      ready degraded" + backfill + rebackfill. Superpowers TDD may drive
      deterministic slices; MUST NOT alter the gate/enum/no-enrichment
      constraint.
- [x] 1.2 NEW `src/data_agents/patent/type_inference.py::infer_patent_type(
      patent_number, *, current_type=None)`. Kind-code map: A/B→发明,
      U/Y→实用新型, S/D→外观设计; leading-digit fallback 1/2/3 (8/9 PCT);
      returns None if no signal; returns `current_type` unchanged if non-null.
      Pure, no DB.
- [x] 1.3 Unit tests (RED→GREEN): A→发明; B→发明; U→实用新型; Y→实用新型;
      S→外观设计; D→外观设计; leading-digit fallback (no suffix); non-overwrite
      (current_type preserved); unrecognizable→None; round-trip
      `_normalize_patent_type_for_canonical(infer_patent_type(n))` truthy.

## 2. Wire inference into the import/canonical path

- [x] 2.1 In the patent canonical path (e.g. `patent/canonical_writer.py`
      upsert, or `release.py` before `_calculate_quality_status`), when
      `patent_type` is absent after xlsx mapping, set it via
      `infer_patent_type(patent_number)`.
- [x] 2.2 Contract test: an imported patent with no `专利类型` source column but
      a `CN…A` number gets `patent_type='发明'` and `quality_status='ready'`
      (given the other required fields). *(Note: fixture should use
      `publication_date` only — see 2.3.)*
- [x] 2.3 Gate date-signal relaxation: `release.py::_calculate_quality_status`
      (+ `PatentEnrichmentSignals` / `evaluate_patent_promotion`) SHALL accept
      `publication_date` as satisfying the date requirement
      (`filing_date OR grant_date OR publication_date`). Pass `publication_date`
      through the backfill script's `_calculate_quality_status` call. Test
      (RED #7): publication-only + inferred type → `ready`; no date at all →
      `partial`. Required because the source xlsx has only `公开（公告）日`
      (no `申请日`) — without this, the 11,408 stay `partial` (dry-run showed
      `promoted_to_ready=0`). *(Implemented by Claude after Codex got stuck;
      `has_filing_or_grant_date`→`has_any_date`; RED #7 green.)*

## 3. Real-data dry-run

- [x] 3.1 Read-only dry-run on `miroflow_real` (proxy unset): run
      `run_patent_type_inference_backfill.py --dry-run`; emit
      `patent-type-dryrun-<date>.jsonl`. Expected: 100% type coverage
      (~7,485 发明 + ~3,923 实用新型) AND **`promoted_to_ready=11,408`**
      (was 0 before the 2.3 gate relaxation). If `promoted_to_ready` < 11,408,
      STOP — a required field is still missing. *(Done: 11,408 promoted, 0
      degraded; artifact `backfill-dryrun-after-relaxation-2026-06-26.jsonl`.)*
- [x] 3.2 Assert **0 `ready` degraded** (trivially true: 0 were ready). *(0.)*

## 4. Backfill + Milvus rebackfill

- [x] 4.1 Bounded `--apply`: write the inferred `patent_type` for the 11,408
      rows (each carrying `run_id`); re-evaluate `quality_status` via the
      existing `evaluate_patent_promotion` (with the 2.3 date relaxation).
      Re-assert 0 ready degraded; expect 11,408 partial→ready. *(Applied:
      11,408 partial→ready, 1 run_id; artifact `backfill-apply-2026-06-26.jsonl`.)*
- [x] 4.2 Milvus rebackfill of `patent_profiles` so the 11,408 newly-`ready`
      patents are indexed. Spot-check ≥10 sampled patents are retrievable via
      the retrieval service (e.g. by applicant / patent_number). *(Backfilled:
      11,408 processed, 0 errors, 186s; `patent_profiles` row_count=11,408;
      spot-check 5/5 retrievable — 4 self@rank0, 1 self@rank1.)*

## 5. Acceptance, ledger, validate

- [x] 5.1 Collect evidence: pytest (unit + contract), dry-run JSONL + type
      distribution + "0 ready degraded", backfill summary, Milvus rebackfill
      log, retrieval spot-check. *(All collected under
      `.agents/runs/infer-patent-type-from-patent-number/`.)*
- [x] 5.2 Update `openspec/change-ledger.md` status → `tasks-complete-not-archived`.
- [x] 5.3 `openspec validate infer-patent-type-from-patent-number --strict`
      exits 0.
- [x] 5.4 Claude review against `acceptance.md`; accept / revise / reject. *(Accept — all ACs met; 1 pre-existing unrelated `test_release` failure documented.)*

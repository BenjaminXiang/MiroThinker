# Tasks: d1a-tech-vocabulary

## 1. Inputs and evidence

- [x] T1 Read-only inventory of the run15 pack (`/tmp/d1a-scratch/`):
      4,945 distinct `tech_tags` values, 41 distinct `industry` values,
      `industry_tags` redundancy, tags-per-company histogram, category-probe baseline
      (`.agents/runs/d1a-tech-vocabulary/scripts/extract_vocabulary_inputs.py`,
      `out/vocabulary-inputs.json`).
- [x] T2 Verification contract written before production edits
      (`.agents/runs/d1a-tech-vocabulary/verification-contract.md`).

## 2. Induction and recording

- [x] T3 Batched induction (`scripts/induce_vocabulary.py`): 1 concept-induction call
      over a deterministic stratified sample, then `value_mapping` calls over every
      distinct value of both fields; transcripts recorded.
- [x] T4 Decision bundle written with provider/model/prompt version, per-call batch
      composition, raw outputs and hashes (`out/recorded-vocabulary-decision-bundle.json`).

## 3. Module

- [x] T5 `canonical_v2/tech_vocabulary.py`: vocabulary/bundle contracts, fail-closed
      replay, mapping helpers, projection application, quality section, gate.
- [x] T6 Packaged artifact `catalogs/technical-vocabulary-v1.json` = replay output,
      content-hash pinned in the module.
- [x] T7 Projection seam in `domain_projection._ProjectionContext.project_identity`.
- [x] T8 Tests: replay determinism (two loads byte-identical), bundle tamper
      detection, unmapped retention, mapping determinism, projection application,
      report section + gate, prompt drift.

## 4. Verification

- [x] T9 Replay counters on the run15 copy: distinct values -> concepts, coverage,
      unmapped, tags per company, category-probe support before/after
      (`scripts/count_vocabulary_replay.py`, `out/vocabulary-replay-counts.json`).
- [x] T10 Focused + regression test runs recorded in `.agents/runs/d1a-tech-vocabulary/verification.md`.

## 5. Documentation

- [x] T11 OpenSpec change (this directory) + `openspec/change-ledger.md` row.
- [x] T12 Human log `docs/plans/2026-09-15-d1a-tech-vocabulary-log.md` +
      `docs/plans/index.md` row.

# Acceptance: infer-patent-type-from-patent-number

A change is accepted only when ALL of the following hold.

## Spec contract (inference)

- [ ] `infer_patent_type` maps A/B→发明, U/Y→实用新型, S/D→外观设计; leading-
      digit fallback (1/2/3; 8/9 PCT); unrecognizable→None.
- [ ] Inference is non-overwriting: a non-null `current_type` is returned
      unchanged.
- [ ] Round-trip: `_normalize_patent_type_for_canonical(infer_patent_type(n))`
      is truthy for every recognizable `n`.

## Writer contract

- [ ] The patent canonical path fills an absent `patent_type` via
      `infer_patent_type` before the quality gate runs.
- [ ] A newly imported patent with a `CN…A` number, title, date, and
      applicants (but no source `专利类型` column) is `ready` at write time.

## Dry-run (the measured delta)

- [ ] `patent-type-dryrun-<date>.jsonl` records an inferred type for every
      NULL-`patent_type` patent.
- [ ] Inferred-type distribution matches the kind-code scan (~7,485 发明 +
      ~3,923 实用新型); any unrecognizable numbers are documented.
- [ ] Resulting `quality_status` would be `ready` for all 11,408; **0 `ready`
      degraded.**

## Backfill + retrieval (the core concern)

- [ ] Bounded apply writes `patent_type` (with `run_id`) for the 11,408 rows;
      `quality_status` re-evaluated to `ready`; 0 ready degraded.
- [ ] Milvus rebackfill of `patent_profiles` indexes the 11,408.
- [ ] ≥10 sampled patents are retrievable via the retrieval service (was 0
      retrievable from the current corpus).

## Code quality / invariants

- [ ] No schema migration; `patent_type` column unchanged (values only).
- [ ] `evaluate_patent_promotion` unchanged; enum unchanged; no-external-
      enrichment constraint unchanged; no patent API added.
- [ ] No secrets logged; no public API / serialized-format change; A–G and
      `_VALID_DOMAINS` untouched; evidence shape unchanged.
- [ ] `uv run pytest` green; `just lint` clean.

## Evidence to report

- Pytest output (unit + contract).
- `patent-type-dryrun-<date>.jsonl` + type distribution + "0 ready degraded".
- Backfill summary (`apply-summary.json`) + Milvus rebackfill log.
- Retrieval spot-check (sampled patents returned; was 0).

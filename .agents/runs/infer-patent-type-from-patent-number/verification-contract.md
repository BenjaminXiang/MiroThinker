# Verification Contract — infer-patent-type-from-patent-number

> Per CLAUDE.md §14.7. Claude-owned. Defines the RED/GREEN boundary before any
> production-code edit. Codex/Superpowers must not independently change the RED
> artifact, the kind-code mapping, or the gate.
> Grounded 2026-06-26 against a fresh read-only `miroflow_real` scan.

## Change
- **OpenSpec change:** `infer-patent-type-from-patent-number` (Standard, behavior-affecting).
- **Capability:** `patent-type-inference` (new).
- **Specs:** `openspec/changes/infer-patent-type-from-patent-number/specs/patent-type-inference/spec.md`.
- **Tasks:** `openspec/changes/infer-patent-type-from-patent-number/tasks.md`.
- **Grounding:** 11,408 patents, 0 `ready` (all `partial`); `patent_type` NULL on every row; source `11月专利完整版.xlsx` has no `专利类型` column; `patent_number` kind-code scan = `CN…A` 7,485 + `CN…U` 3,923 = 11,408 (100% covered).

## Change Type
- `deterministic_module`

Behavior-affecting **at the retrieval boundary** (flips 11,408 rows partial→ready → Milvus indexability), but the **new code surface is deterministic**: a pure function `infer_patent_type(patent_number)` + a canonical-path wiring call + a backfill script. No LLM, no network. The quality gate (`evaluate_patent_promotion`), the enum, and the no-external-enrichment constraint are **reused unchanged**.

## Superpowers Mode
- `full_tdd_allowed`

Per §14.7: deterministic module → full Superpowers TDD, RED = unit/contract tests. NOT agentic-RAG/badcase work. TDD must NOT alter the gate, the enum, the no-enrichment constraint, or add a patent API.

## RED artifact (must fail before implementation)
Unit/contract tests, written first, all failing:

1. `tests/data_agents/patent/test_type_inference.py::test_kindcode_matrix` — `infer_patent_type` maps suffix `A`/`B`→发明, `U`/`Y`→实用新型, `S`/`D`→外观设计. Covers every code, not one.
2. `test_leading_digit_fallback` — no suffix → leading digit `1`→发明, `2`→实用新型, `3`→外观设计 (and `8`/`9` PCT).
3. `test_non_overwriting` — `infer_patent_type(n, current_type='发明')` returns `'发明'` unchanged; a non-null current_type is never clobbered.
4. `test_unrecognizable_returns_none` — empty / no-signal number → `None` (no fabricated type).
5. `test_roundtrip_with_normalizer` — `_normalize_patent_type_for_canonical(infer_patent_type(n))` is truthy for every recognizable `n` (the inferred string is one the gate's normalizer accepts).
6. `tests/data_agents/patent/test_canonical_writer.py` (extend) — contract: an upserted patent with absent `patent_type` and a `CN…A` number gets `patent_type='发明'` and `quality_status='ready'` (given title + date + applicants); a `CN…U` number → `实用新型` + `ready`. No inline type when source provides one. **The fixture MUST use `publication_date` only (no `filing_date`/`grant_date`) to reflect the real source xlsx** — otherwise the test masks the gate date-signal gap (see #7).
7. `tests/data_agents/patent/test_quality_promotion.py` (extend) — the gate's date signal SHALL accept `publication_date`: a patent with `publication_date` set, `filing_date`/`grant_date` NULL, and an inferred `patent_type` → `ready`; a patent with all three dates NULL → `partial`. This is the gate-relaxation RED (added 2026-06-26 after the dry-run caught `promoted_to_ready=0`).

#1–#5 are the live RED (new `type_inference.py`). #6 is the contract RED (wiring). #7 is the gate-relaxation RED.

## Oracle Strength
- Observable: exact type strings per kind-code/leading-digit; non-overwrite; None on no-signal; round-trip truthiness; the contract end-state (`patent_type` set + `quality_status='ready'`).
- Stronger than a snapshot: the full kind-code matrix covers the condition space; the round-trip guards the load-bearing invariant (inferred value must pass `_normalize_patent_type_for_canonical`).
- Complementary real check: the `miroflow_real` dry-run (100% type coverage; 11,408 partial→ready; 0 ready degraded) + Milvus rebackfill retrieval spot-check.

## GREEN
Minimal implementation that turns RED green, no weakening:
- NEW `src/data_agents/patent/type_inference.py::infer_patent_type(patent_number, *, current_type=None)` — kind-code suffix map + leading-digit fallback + non-overwrite + None-on-no-signal.
- Wire the canonical path (e.g. `patent/canonical_writer.py` upsert, or `release.py` before `_calculate_quality_status`) to call `infer_patent_type` when `patent_type` is absent.
- NEW `scripts/run_patent_type_inference_backfill.py` — populate `patent_type` + re-evaluate `quality_status` for the 11,408 rows.
- RELAX the gate's date signal to accept `publication_date`: `release.py::_calculate_quality_status` (and `PatentEnrichmentSignals` / `evaluate_patent_promotion`) SHALL treat `filing_date OR grant_date OR publication_date` as satisfying the date requirement. Pass `publication_date` through the backfill script's `_calculate_quality_status` call too. This is the ONLY gate change; all other ready criteria, the enum, forward-monotonicity, and the no-enrichment constraint are unchanged.
- No migration (`patent_type` column reused); no change to `_is_indexable_patent`, the enum, or the no-enrichment constraint; no patent API.

## Real-interaction / acceptance evidence (not RED; required for acceptance.md)
- **Dry-run (task 3.1)**: unset the 6 proxy env vars (localhost must not be hijacked), run the backfill script in `--dry-run` on `miroflow_real`; save `patent-type-dryrun-<date>.jsonl` + the inferred-type distribution. Expected: ~7,485 发明 + ~3,923 实用新型; **100% of 11,408 get a type** (document any unrecognizable).
- **Promotion audit (task 3.2)**: assert every row would flip partial→`ready` (all other required fields — patent_number, title, date, applicants — already present on all 11,408); assert **0 `ready` degraded** (trivially true: 0 were ready).
- **Bounded apply (task 4.1)**: `--apply` writes `patent_type` (with `run_id`) + re-evaluates; re-assert 0 ready degraded; expect 11,408 partial→ready.
- **Milvus rebackfill (task 4.2)**: `run_milvus_backfill.py` for `patent_profiles`; spot-check ≥10 sampled patents retrievable via the retrieval service (by applicant / patent_number). Was 0 retrievable.

## Acceptance contract — maps to `acceptance.md`
- Inference contract: kind-code matrix + fallback + non-overwrite + None + round-trip (RED #1–#5).
- Writer contract: absent-type patent gets inferred type + `ready` (RED #6).
- Dry-run: 100% type coverage + 11,408 partial→ready + 0 ready degraded.
- Backfill + retrieval: 11,408 indexed; ≥10 retrievable (was 0).
- Code quality: no migration; gate/enum/constraint unchanged; no API; pytest green; lint clean.
- `openspec validate infer-patent-type-from-patent-number --strict` exits 0.

## Verification commands
- RED: `cd apps/miroflow-agent && uv run pytest tests/data_agents/patent/test_type_inference.py -n0` (fail until 1.2).
- GREEN: `cd apps/miroflow-agent && uv run pytest tests/data_agents/patent/test_type_inference.py tests/data_agents/patent/test_canonical_writer.py -n0`.
- Regression: `cd apps/miroflow-agent && uv run pytest tests/data_agents/patent/ -n0`.
- Dry-run (real): `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy no_proxy NO_PROXY && cd apps/miroflow-agent && uv run python scripts/run_patent_type_inference_backfill.py --dsn "$DATABASE_URL" --dry-run --json-output .agents/runs/infer-patent-type-from-patent-number/patent-type-dryrun-<date>.jsonl`.
- Apply (bounded, post-dry-run): `... --apply` then the ready-degradation audit `SELECT count(*) FROM patent WHERE quality_status='ready' AND updated_at > now()-interval '1 day'` (expect 11,408) and `SELECT count(*) FROM patent WHERE quality_status<>'ready'` (expect 0).
- Milvus: `cd apps/miroflow-agent && uv run python scripts/run_milvus_backfill.py` (patent_profiles).
- Validate: `openspec validate infer-patent-type-from-patent-number --strict`.

## Do-not rules (Codex)
- The ONLY permitted gate change is the date-signal relaxation to accept `publication_date` (RED #7). Do NOT change any other ready criterion (`patent_number`, `title`, `patent_type`, applicants/inventors), the forward-monotonic logic, `_is_indexable_patent`, any alembic migration, the `quality_status` enum, or the no-external-enrichment constraint.
- Do not overwrite a non-null source `patent_type` (inference only fills absent values).
- Do not add a patent API / external provider (no-external-enrichment constraint is load-bearing).
- Do not `--apply` without a prior dry-run artifact whose type distribution + coverage **and `promoted_to_ready` count** are recorded and reviewed. The dry-run MUST show `promoted_to_ready=11408` (was 0 before the gate relaxation) before any apply.
- Report back per slice with: files changed, test command + pass count, and artifact paths produced.

## Rollback
Fully reversible — the backfill records touched rows by `run_id`; clearing the inferred `patent_type` (`UPDATE patent SET patent_type=NULL WHERE run_id=<id>`) + re-evaluating `quality_status` reverts rows to `partial`; a Milvus rebackfill drops them from the index. No irreversible column overwrite (inference only adds, never removes).

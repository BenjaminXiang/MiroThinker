# Verification Contract

## Change

- Change ID: `d1a-tech-vocabulary` (D1-a, R21 §8.5; launch gate #5 of §11)
- OpenSpec path: `openspec/changes/d1a-tech-vocabulary/`
- Run workspace: `.agents/runs/d1a-tech-vocabulary/`

## Change Type

- `data_contract_or_storage` (a controlled vocabulary becomes a build input and
  decides what the tag fields publish) with a `deterministic_module` replay core.

## Superpowers Mode

- `contract_first`

## RED Artifact

- Type: unit/contract tests + a read-only replay counter with before/after counts.
- Path: `apps/miroflow-agent/tests/canonical_v2/test_tech_vocabulary.py` and
  `.agents/runs/d1a-tech-vocabulary/scripts/count_vocabulary_replay.py`.
- Expected failing reason before the change: `data_agents.canonical_v2.tech_vocabulary`
  does not exist, and the run15 copy publishes 4,945 uncontrolled tag values with
  `送餐` = 0 / `配送机器人` = 1 tag-field hits.
- Behavior class covered: controlled-vocabulary induction + recorded replay +
  projection-time application + quality gate. Not a single example: the counters run
  over all 7,086 run15 company documents, and the tests exercise the replay
  invariants (tamper, drift, missing call, unknown concept, malformed line) rather
  than one golden transcript.

## Oracle Strength

- Observable behavior checked:
  1. `replay_vocabulary_from_bundle(bundle) == packaged artifact` (byte-identical),
     and two independent replays are byte-identical;
  2. the run15 counter's before/after numbers (distinct values, coverage, unmapped,
     tags per company, category-probe support);
  3. the projection seam's output values for mapped and unmapped inputs;
  4. the gate's failure modes and the report section shape.
- Why this is stronger than a snapshot: the mapping is derived from recorded provider
  bytes by a total, fail-closed parser, and the counter is computed on the real
  production pack copy, so the claim "category queries now recall" is a count over
  7,086 documents, not a hand-picked example.
- For LLM/agentic changes, scenario contract: the recorded bundle is the trace
  contract; every published concept must be resolvable to the recorded transcript
  that produced it, and any bundle/transcript/vocabulary mismatch fails the build.

## Diagnosis / Anti-Overfit Check

- Root-cause hypothesis: category recall fails because the published tag values are
  agent-written marketing phrases with one occurrence each, not because of a
  formatting rule. Confirmed against the assessment (`docs/plans/2026-09-15-data-quality-assessment.md`
  finding 4: normalization merges 0 labels) and re-measured here.
- Sibling patterns searched: `industry` (41 overlapping labels, same defect),
  `industry_tags` (100% redundant axis), `venue` labels (D0-b: rule-derivable, so
  *not* part of this change), `research_directions` (D0-a junk, different defect).
- Why this RED covers a behavior class: the assertions are invariants of any
  controlled vocabulary (coverage, no-guess, replay fidelity, gate) and are checked
  against the whole value space.
- Why the implementation cannot pass by hardcoding: the artifact must equal the
  bundle replay, and the counter is recomputed from the pack copy; hardcoding a
  mapping without a matching bundle breaks the equality test, and a bundle whose
  calls do not match the recomputed batch composition fails to load.

## Context / Dependency Surface

- Source OpenSpec requirement(s): R21 (§8.5 LLM-in-the-loop guards), §11 gate #5.
- Legacy/source-of-truth docs consulted: `docs/plans/2026-09-15-data-quality-assessment.md`,
  `docs/plans/2026-09-15-requirements-gap-plan.md` §8/§10/§11, D0-a/D0-b designs
  (`openspec/changes/data-cleaning-batch{1,2}/`).
- Affected modules: `canonical_v2/tech_vocabulary.py` (new),
  `canonical_v2/domain_projection.py` (one seam), `canonical_v2/catalogs/` (new artifact).
- Existing tests/evals likely affected: `tests/canonical_v2/test_domain_projection*.py`
  (projection output values change only for company tag fields), plus anything that
  asserts tag values verbatim.
- Regression surface: company projection content hash; the company projection tests
  that build fixtures with tag values.
- External/provider/browser/storage dependencies: DeepSeek chat completions (offline
  recording only), used through the repository's credential chain.

## Mock Policy

- Mocks used: tests build their own small bundle + vocabulary to exercise replay
  failure modes; the provider is never called in tests.
- Behavior not mocked away: the packaged artifact and the recorded run15 bundle are
  the real ones in the artifact-equality test and the counter.
- Complementary real interaction: the induction run calls the real provider and
  records real bytes; `llm_calls` in the quality section is that run's count.

## GREEN Criteria

- The declared RED artifacts pass.
- Relevant prior regression tests/evals still pass.
- No test, eval, schema, or guardrail is weakened without an OpenSpec update.
- Implementation generalizes beyond the visible example (whole value space).
- Source traceability, evidence shape, public APIs and data contracts remain intact.
- For mock-heavy tests, the complementary real-interaction check (recorded bundle
  from the real provider) passes.

## Forbidden Shortcuts

- No hardcoded mapping without the matching recorded bundle.
- No test-only production branches; no silent LLM fallback at build time.
- No dropping of undecidable values to raise coverage.
- No weakening of the coverage floor or the gate to make the run pass.

## Verification Plan

- RED command: `uv run pytest tests/canonical_v2/test_tech_vocabulary.py`
  (before the module exists) + the counter script showing the run15 baseline.
- Focused GREEN command: `uv run pytest tests/canonical_v2/test_tech_vocabulary.py -q`
- Regression command: `uv run pytest tests/canonical_v2 -q`
- Replay/counter command: `python3 .agents/runs/d1a-tech-vocabulary/scripts/count_vocabulary_replay.py`
- Real interaction command: `python3 .agents/runs/d1a-tech-vocabulary/scripts/induce_vocabulary.py --phase all`
- OpenSpec validation command: `openspec validate d1a-tech-vocabulary` (or the
  repository's equivalent listing check).

## Notes

- Assumptions: run15 pack copy at `/tmp/d1a-scratch/lookup-run15.sqlite3` is the
  read-only replica; DeepSeek `deepseek-v4-pro` is reachable through the repo key chain.
- Out of scope: re-tagging candidates from local free text, mining new tags, retiring
  the `industry_tags` declaration, the rebuild itself.
- Rollback note: revert the branch; the projection falls back to publishing raw tag
  values (the run15 behaviour). No data is mutated by this slice.

# Verification Contract

## Change

- Change ID: `professor-dataset-candidate-generation`
- OpenSpec path: `openspec/changes/professor-dataset-candidate-generation/`
- Run workspace: `.agents/runs/professor-dataset-candidate-generation/`

## Change Type

- `data_contract_or_storage`

## Superpowers Mode

- `contract_first`

## RED Artifact

- Type: unit test and contract test
- Path: `apps/miroflow-agent/tests/data_agents/professor/test_dataset_candidate_generation.py`
- Expected failing reason: the typed candidate models, lane report builder, validation failure accounting, provider failure accounting, and write-mode evidence projection do not exist yet.
- Behavior class covered: source-grounded candidate dry-run evidence for the four Professor dataset-quality closure lanes.

## Oracle Strength

- Observable behavior checked: candidate objects validate lane-specific contracts, invalid candidates are counted as validation failures, provider failures are preserved, affected Professor/Paper ids are derived only from valid candidates, and candidate evidence can be projected into keys already accepted by the existing write-mode closure path.
- Why this is stronger than a single string, DOM node, snapshot, or visible example: the tests exercise all four remediation lanes and validate counts, ids, evidence keys, rejection reasons, and provider failure metadata rather than matching one rendered output.
- For web/UI changes, browser/API/state workflow to verify: not applicable for this slice; frontend behavior is outside this change.
- For LLM/agentic changes, scenario/eval/trace contract to verify: LLM calls are behind injectable providers; later dry-runs must record provider metadata, provider failures, source hashes, and bounded samples.

## Diagnosis / Anti-Overfit Check

- Root-cause hypothesis: the existing quality-closure writer only persists candidates already present in bucket evidence, but the candidate-generation layer and validation/report schema are missing.
- Sibling patterns searched: profile summary contract, research overview section builder, output summary input selector, dataset quality closure dry-run/write reports, and duplicate paper merge writer.
- Why this RED covers a behavior class rather than one visible example: the tests cover profile summary, research overview, Professor paper summary, duplicate merge, invalid candidate, provider failure, and skipped/rejected row paths.
- Why the implementation cannot pass by hardcoding or bypassing the case: the report builder must group arbitrary candidate objects by lane, derive ids from candidate payloads, validate lane-specific required fields, and serialize write-mode evidence from the candidate instances.

## Context / Dependency Surface

- Source OpenSpec requirement(s): all requirements in `openspec/changes/professor-dataset-candidate-generation/specs/professor-dataset-candidate-generation/spec.md`.
- Legacy/source-of-truth docs consulted: `docs/Data-Agent-Shared-Spec.md`, `docs/Professor-Data-Agent-PRD.md`, and existing Professor quality-closure code.
- Affected modules: `apps/miroflow-agent/src/data_agents/professor/dataset_candidate_generation.py`, `apps/miroflow-agent/src/data_agents/professor/dataset_quality_closure.py`, `apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py`.
- Existing tests/evals likely affected: Professor dataset quality closure tests, Professor profile section tests, Professor output summary tests, and the closure CLI tests.
- Regression surface: dry-run evidence schema, write-mode evidence gate, profile summary length contract, research overview source traceability, Professor-Paper link provenance, and paper merge identity safety.
- External/provider/browser/storage dependencies: unit tests use injectable fake providers only; real dry-run tasks require the `miroflow_real` database and configured LLM provider.

## Mock Policy

- Mocks used: injectable fake providers may be used for LLM synthesis and translation failure/success paths.
- Behavior not mocked away: candidate validation, source-hash preservation, candidate-to-write-evidence projection, lane count aggregation, and unsafe merge rejection.
- Complementary real interaction / contract / trace / browser check: bounded read-only dry-runs against `miroflow_real` must be recorded before write-mode handoff.

## GREEN Criteria

- The declared RED artifact passes.
- Relevant prior regression tests/evals still pass.
- No test, eval, schema, or guardrail is weakened without an OpenSpec update.
- Implementation generalizes beyond the visible example.
- Source traceability, evidence shape, public APIs, and data contracts remain intact unless the OpenSpec change explicitly modifies them.
- For mock-heavy tests, the complementary real-interaction check passes or a blocker is recorded.

## Relaxed Gate Amendment

- Reason: the user changed the candidate-generation policy from strong
  pre-write blocking to a development-mode LLM-first flow with few hard
  constraints, LLM self-check, and evidence recording.
- RED command: `cd apps/miroflow-agent && uv run pytest -n0 tests/data_agents/professor/test_dataset_candidate_generation.py -k "relaxed or candidate_generation_report_counts"`
- Expected failing reason before implementation: weak but usable candidates are
  still rejected or counted as validation failures, and candidate evidence lacks
  `candidate_status`, `quality_flags`, `source_confidence`,
  `write_recommendation`, or `llm_self_check`.
- GREEN behavior: short Chinese profile summaries, Chinese research overview
  candidates with weak source hashes, unresolved-duplicate paper summaries, and
  title/year-only duplicate merge plans are emitted as `needs_review`
  candidates. Provider failures remain first-class report evidence and do not
  become candidates.

## Real Provider Amendment

- Reason: the remaining gap is that `candidate-dry-run` only used injectable
  fake providers or deterministic fallback. Development mode must connect the
  real OpenAI-compatible provider by default.
- RED command: `cd apps/miroflow-agent && uv run pytest -n0 tests/data_agents/professor/test_candidate_llm_provider.py tests/scripts/test_run_professor_dataset_quality_closure.py -k "candidate_llm_provider or real_llm_provider or deterministic_mode or provider_mode"`
- Expected failing reason before implementation: the provider adapter module
  does not exist, CLI does not build real providers by default, and provider
  metadata/self-check evidence cannot reach candidate output.
- GREEN behavior: the adapter parses strict JSON, retries malformed output
  once, records provider metadata and self-check payloads, turns missing
  credentials into typed provider failures, and the CLI defaults to real
  provider mode while requiring explicit deterministic mode.
- Real interaction: run a bounded `miroflow_real` candidate dry-run. If
  credentials are missing, the artifact must show `MissingLLMCredentials`
  provider failure with profile/model metadata instead of deterministic
  fallback.

## Cache-Only Paper Source-Gap Amendment

- Reason: the current Paper table still has tens of thousands of active rows
  missing `summary_zh` or `abstract_clean`. The safe next source-expansion lane
  is existing title-resolution cache evidence for `prof_page_only` rows before
  another LLM summary pass.
- RED command: `cd apps/miroflow-agent && uv run pytest -n0 tests/scripts/test_run_paper_title_enrichment_backfill.py -k "paper_id_file or cache_only" -q`
- Expected failing reason before implementation: the title enrichment CLI lacks
  `--paper-id-file` and `--cache-only`, dry-run disables cache reads entirely,
  and resolver calls cannot be forced to cache-only mode.
- GREEN behavior: Paper ids can be scoped from files, cache-only mode forwards
  `cache_only=True` to the resolver, dry-run may read existing cache without
  writing, cache misses remain unresolved, and report/run-scope evidence records
  the mode.
- Real interaction: generate a current Paper id file from missing-summary rows
  with existing title-resolution cache hits, run cache-only title enrichment
  dry-run and write-mode backfill, then run bounded parallel Paper summary
  backfill and re-audit aggregate gaps.

## Live Resolver Provider Preflight Amendment

- Reason: the next unresolved source-acquisition lane should use OpenAlex as
  the primary title resolver, Crossref with configured contact metadata, and
  Semantic Scholar only when credentials and rate limits are ready. The user
  chose to proceed without waiting for Semantic Scholar approval.
- RED command: `uv run pytest -n0 apps/miroflow-agent/tests/data_agents/paper/test_title_resolver.py::test_crossref_title_search_uses_configured_contact apps/miroflow-agent/tests/data_agents/paper/test_title_resolver.py::test_resolve_can_defer_semantic_scholar_title_search_until_api_key_available apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_process_rows_forwards_semantic_scholar_disable_flag_to_title_resolver apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_empty_report_records_semantic_scholar_title_search_switch apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_cli_help_lists_safe_scoping_flags apps/miroflow-agent/tests/data_agents/paper/test_crossref.py::test_request_json_uses_configured_crossref_contact apps/miroflow-agent/tests/data_agents/paper/test_semantic_scholar.py::test_request_json_uses_configured_semantic_scholar_api_key`
- Expected failing reason before implementation: Crossref still uses the
  placeholder mailto, `resolve_paper_by_title` lacks a Semantic Scholar title
  search switch, the title-enrichment CLI lacks matching report/run-scope
  evidence, and Semantic Scholar metadata requests do not send API key headers.
- GREEN behavior: Crossref reads contact metadata from environment variables,
  Semantic Scholar title search can be disabled without blocking later enabled
  providers, Semantic Scholar requests send the configured API key header, and
  title-enrichment reports/run scopes record provider enablement.
- Real interaction: no live resolver shard is required for this preflight; the
  next real interaction belongs to tasks 15.1-15.5.

## DOI Pollution Admission Gate Amendment

- Reason: current residual Paper gaps include polluted DOI values. Sending
  combined, truncated, or URL-tailed DOI strings to external providers wastes
  resolver quota and records source pollution as generic provider failure.
- RED command: `uv run pytest -n0 apps/miroflow-agent/tests/data_agents/paper/test_enrichment.py::test_polluted_doi_does_not_call_doi_lookup_providers apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py::test_cli_skips_doi_enrichment_for_polluted_doi_only_row`
- Expected failing reason before implementation: the hybrid enrichment
  aggregator sends polluted DOI strings to DOI lookup providers, and summary
  backfill has no `metadata_enrichment_skipped_bad_doi` report bucket.
- GREEN behavior: bad DOI-only rows do not call DOI lookup providers,
  `metadata_enrichment_skipped_bad_doi` and bounded `bad_doi_samples` are
  recorded, and rows with arXiv/OpenAlex ids may still use those non-DOI
  identifier paths.
- Real interaction: no live database mutation is required for this admission
  gate; it should affect the next summary/resolver backfill reports.

## Title Enrichment DOI Shortcut Amendment

- Reason: Paper title enrichment had an existing-identifier shortcut that could
  promote a polluted DOI as a high-confidence `doi_lookup` result before live
  title resolution ran. That bypass turns source pollution into canonical
  Paper identity.
- RED command: `uv run pytest -n0 apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_process_rows_does_not_trust_polluted_existing_doi_identifier`
- Expected failing reason before implementation: `_process_rows` trusts the
  row DOI through `_resolved_from_existing_identifier`, never calls
  `resolve_title`, and records no `bad_doi_identifiers` report evidence.
- GREEN behavior: title enrichment classifies bad existing DOI values, reports
  bounded bad DOI samples, skips the polluted DOI shortcut, and may continue
  resolution through the cleaned title and enabled resolver providers.
- Real interaction: no live database mutation is required for this shortcut
  gate; it should affect the next live title resolver backfill reports.

## Forbidden Shortcuts

- No hardcoded visible input/output cases.
- No test-only production branches.
- No brittle one-case parsing unless the behavior is explicitly specified.
- No mock that removes the behavior under validation.
- No exact-output assertion for open-ended LLM behavior unless the output is a structured schema.
- No name-only external literature provider discovery for Professor core paper summaries.
- No hidden company/startup role dependency in Professor core candidate generation.

## Verification Plan

- RED command: `cd apps/miroflow-agent && uv run pytest tests/data_agents/professor/test_dataset_candidate_generation.py`
- Focused GREEN command: `cd apps/miroflow-agent && uv run pytest tests/data_agents/professor/test_dataset_candidate_generation.py`
- Regression command: `cd apps/miroflow-agent && uv run pytest tests/data_agents/professor/test_dataset_candidate_generation.py tests/data_agents/professor/test_dataset_quality_closure.py tests/scripts/test_run_professor_dataset_quality_closure.py`
- Browser/API/state workflow command: not applicable for this slice.
- Real interaction / contract / trace command: `cd apps/miroflow-agent && uv run python scripts/run_professor_dataset_quality_closure.py --mode candidate-dry-run --lane all --bucket-limit 5 --candidate-output <path>`
- OpenSpec validation command: `openspec validate "professor-dataset-candidate-generation" --strict`

## Notes

- Assumptions: this slice starts with typed models and pure validation before adding provider-backed candidate assembly.
- Out of scope: broad write-mode remediation, Agentic RAG behavior changes, company/news role inference, and vector index refresh.
- Rollback note: remove the candidate-generation module, tests, and run artifacts; existing quality-closure write paths remain unchanged until CLI integration is implemented.

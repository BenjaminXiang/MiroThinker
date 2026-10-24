# Proposal: professor-web-enrich-deepseek-fallback

Human doc: `docs/plans/2026-10-24-professor-web-enrich-deepseek-log.md`.

## Why

The professor web-enrichment paths still built Serper directly:

- `src/data_agents/professor/pipeline_v3.py` constructed
  `WebSearchProvider(api_key=config.serper_api_key)` and passed it to every
  professor task.
- `scripts/run_professor_web_enrich.py` constructed `WebSearchProvider()` from
  `SERPER_API_KEY` alone.

At the customer site Serper credits are exhausted and overseas top-up is not an
option. Two other lanes already moved to the DeepSeek search API and are
carrying production traffic:

- the canonical-v2 chat web lane (`deepseek-v1`: 72 provider calls and 196
  cached results on 2026-10-24; `serper-v1`: 0 calls),
- company news ingestion (`company_news_item.source_adapter = deepseek-search`
  for all 109 rows).

Professor enrichment was the remaining consumer that could still call a dead
paid provider, and it failed closed to "no web results" when Serper returned an
error.

## What Changes

1. Add `src/data_agents/providers/fallback_web_search.py`:
   - `FallbackWebSearchProvider(providers=(...))` tries providers in order and
     falls through on an exception or an empty `organic` list.
   - `resolve_deepseek_search_key()` reads `DEEPSEEK_API_KEY`, then the managed
     secrets file (`llm.api_key`), so job subprocesses do not depend on an
     exported environment variable.
2. `pipeline_v3` builds its search provider through
   `_build_professor_search_provider(config)`: DeepSeek → Bocha → Serper (only
   when `config.serper_api_key` is set). `skip_web_search` semantics are
   unchanged.
3. `scripts/run_professor_web_enrich.py` uses the same ordered chain and gains
   the repository-standard `PROJECT_ROOT` sys.path bootstrap, so
   `python scripts/run_professor_web_enrich.py` works from any working
   directory (the job runner does not export `PYTHONPATH` for every task).

## Impact

- Affected callers: `run_professor_pipeline_v3` (admin `/upload` professor
  import and `run_batch_reprocess_v3.py`) and the manual ops script
  `run_professor_web_enrich.py`.
- Customer site: `SERPER_API_KEY` is absent from the bundle `.env`, so the
  effective chain is DeepSeek → Bocha; Serper is unreachable there.
- No schema, API, or answer-contract change. The search payload shape
  (`{"organic": [...]}`) is unchanged.

## Non-goals

- The daily professor Seed refresh (`run_admin_seed_refresh.py` →
  `seed_runner` → `pipeline.py`) performs no web search; it is not modified and
  must not be described as switched.
- The chat web lane and company news keep their existing DeepSeek composition.
- Serper is not deleted from the codebase; it stays as an optional last resort
  for environments that still hold credits.

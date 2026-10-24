# Tasks: professor-web-enrich-deepseek-fallback

- [x] 1.1 Add `FallbackWebSearchProvider` with ordered fallthrough on error or
      empty `organic`, plus `resolve_deepseek_search_key()` reading
      `DEEPSEEK_API_KEY` then the managed secrets file.
- [x] 1.2 Add unit tests for first-provider-wins, error/empty fallthrough, and
      the all-providers-fail empty result.
- [x] 1.3 Route `pipeline_v3` provider construction through
      `_build_professor_search_provider` (DeepSeek → Bocha → Serper).
- [x] 1.4 Route `run_professor_web_enrich.py` through the same chain and add the
      `PROJECT_ROOT` sys.path bootstrap.
- [x] 1.5 Run the professor pipeline regression suite and the script contract
      tests.
- [x] 1.6 Deploy the three files to the customer bundle and verify md5 equality.
- [x] 1.7 Verify the deployed provider chain and a live DeepSeek query on the
      customer machine.
- [x] 1.8 Verify the ops script imports and prints usage from `/tmp` on the
      customer machine.
- [x] 1.9 Record acceptance evidence in
      `.agents/runs/professor-web-enrich-deepseek-fallback/verification.md`.
- [x] 1.10 Add chain-order regression tests
      (`TestProfessorSearchProviderChain`): DeepSeek → Bocha → Serper order,
      Bocha-first without a DeepSeek key, and `skip_web_search` returning `None`.
- [x] 1.11 Run the full write path (search → identity filter → fetch → synthesis
      → `profile_summary` + `professor_fact`) in an isolated schema clone, for
      both a success case and a total-failure case.
- [x] 1.12 Pass `build_non_thinking_extra_body(model)` on both script LLM calls;
      without it `deepseek-v4-flash` returns empty content after spending the
      token budget on reasoning.
- [x] 1.13 Record `pipeline_run.status='failed'` and exit 1 when a run had
      candidates and enriched none (previously always `succeeded`).
- [x] 1.14 State the Seed boundary precisely: no cron, admin-triggered, no
      search API (page fetches only), `quota="web_search"` is a bucket label.

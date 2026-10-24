# Acceptance: professor-web-enrich-deepseek-fallback

| # | Criterion | Evidence |
|---|---|---|
| A1 | Fallback returns the first provider's results and does not call later providers | `test_fallback_uses_first_provider_with_results` |
| A2 | An error or empty result falls through to the next provider | `test_fallback_tries_next_on_error_or_empty` |
| A3 | All providers failing yields an empty organic list, not an exception | `test_fallback_returns_empty_when_all_fail` |
| A4 | Professor pipeline regression suite stays green | `tests/data_agents/professor/test_pipeline_v3.py` 20 passed |
| A5 | Script contract tests stay green after the sys.path bootstrap | `tests/scripts/test_professor_profile_summary_source_contract.py` 5 passed |
| A6 | Four-file suite total | 35 passed in 22.69s (worktree `embedding-switch-line`) |
| A6a | Chain order is DeepSeek → Bocha → Serper when both keys exist | `test_chain_prefers_deepseek_and_keeps_serper_last` |
| A6b | Without a DeepSeek key the chain starts at Bocha | `test_chain_without_deepseek_key_starts_with_bocha` |
| A6c | `skip_web_search` still suppresses the provider | `test_skip_web_search_returns_no_provider` |
| A7 | Deployed provider chain is DeepSeek then Bocha | customer machine: `chain: ['DeepSeekSearchProvider', 'BochaSearchProvider']` |
| A8 | Live DeepSeek search returns results | `丁文伯 清华大学 专利` → 10 organic, first `丁文伯：执着，让梦想开花-清华大学` |
| A9 | LLM query rewrite and search work in one process | `qwen3.6-35b-a3b` produced 2 queries; each returned 10 organic results |
| A10 | Ops script runs from a neutral cwd | `cd /tmp && python .../scripts/run_professor_web_enrich.py --help` → usage, exit 0 |
| A11 | Deployed files equal the source files | md5 match for `pipeline_v3.py`, `run_professor_web_enrich.py`, `fallback_web_search.py` |
| A12 | Serper is unreachable at the customer site | `SERPER_API_KEY` absent from the bundle `.env`; chain stops at Bocha |
| A13 | Full write path produces a summary and a fact | isolated schema: `1/1 enriched (261c, 23 verified, 5 pages)`; `profile_summary` 261 chars; `professor_fact` homepage/active/`web_enrich: 23 verified` |
| A14 | Total failure is recorded as failure | 502 run: `0/1 enriched, 1 failed, status=failed`, exit 1; `pipeline_run=failed/0` |
| A15 | DeepSeek synthesis is non-empty | `build_non_thinking_extra_body` added on both LLM calls; 0 chars without it, 171+ chars with it |
| A16 | Deployed script matches the source | md5 `8e299141b14f378781ed2b824df9e7fe` |
| A17 | Seed boundary is stated precisely | `admin-seed-refresh`/`-sample` have no cron, run `pipeline.py` v2, import no search provider, and fetch known URLs only; `quota="web_search"` is a bucket label |

## Not verified

- The production database itself was not written. The isolated schema clone
  (same DDL checks/indexes; 15 real FKs satisfied by construction) proves the
  code path and value shape, not production row-level effects beyond that.
- The admin `/upload` professor import (`pipeline_v3`) was not run live with
  DeepSeek; it shares the provider builder and 20 unit tests.
- A written `profile_summary` is not visible in chat until the serving pack is
  rebuilt/backfilled.

Evidence: `.agents/runs/professor-web-enrich-deepseek-fallback/verification.md`.

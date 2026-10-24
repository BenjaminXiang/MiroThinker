# Verification: professor-web-enrich-deepseek-fallback

Date: 2026-10-24
Line: serving worktree `switch/embedding-model-to-qwen37-flash`
(`/home/longxiang/MiroThinker/.worktrees/embedding-switch-line`)

## 1. Code under test

Changed files:

- `apps/miroflow-agent/src/data_agents/providers/fallback_web_search.py` (new)
- `apps/miroflow-agent/tests/data_agents/providers/test_fallback_web_search.py` (new)
- `apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py`
- `apps/miroflow-agent/scripts/run_professor_web_enrich.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_pipeline_v3.py`

## 2. New tests

6 tests.

3 in `test_fallback_web_search.py`:

- `test_fallback_uses_first_provider_with_results` — first provider with organic
  results wins; later providers are not called.
- `test_fallback_tries_next_on_error_or_empty` — an exception and an empty
  result both advance the chain.
- `test_fallback_returns_empty_when_all_fail` — all failing returns
  `{"organic": []}`.

3 in `test_pipeline_v3.py::TestProfessorSearchProviderChain`:

- `test_chain_prefers_deepseek_and_keeps_serper_last` — with a DeepSeek key and
  a Serper key, the chain is DeepSeek → Bocha → Serper in that order.
- `test_chain_without_deepseek_key_starts_with_bocha` — no DeepSeek key means
  Bocha leads.
- `test_skip_web_search_returns_no_provider` — `skip_web_search` without the
  low-signal override still returns `None`.

Fixture source: constructed providers (no network, no live credential).

## 3. Pre-existing suites

Command (worktree):

```bash
cd apps/miroflow-agent && uv run pytest \
  tests/data_agents/providers/test_fallback_web_search.py \
  tests/data_agents/providers/test_deepseek_search.py \
  tests/data_agents/professor/test_pipeline_v3.py \
  tests/scripts/test_professor_profile_summary_source_contract.py -q
```

Result: **35 passed in 22.69s** (6 new, 29 pre-existing).

## 4. Deployment

Three files copied to
`/root/deploy/fullstack-v2/code/apps/miroflow-agent/...`; md5 verified equal:

| file | md5 |
|---|---|
| `src/data_agents/professor/pipeline_v3.py` | `b3f54a36cec39fd8f90e7f82257f7474` |
| `scripts/run_professor_web_enrich.py` | `8e299141b14f378781ed2b824df9e7fe` |
| `src/data_agents/providers/fallback_web_search.py` | `789cf13c2f70cfaafd5137857362d108` |

No service restart was needed: both call sites are job subprocesses that import
at start.

## 5. Live evidence (customer machine)

### 5.1 Provider chain through the production builder

```python
cfg = SimpleNamespace(skip_web_search=False,
                      force_web_search_for_low_signal=True,
                      serper_api_key="")
p = _build_professor_search_provider(cfg)
```

Output:

```text
wrapper: FallbackWebSearchProvider
chain: ['DeepSeekSearchProvider', 'BochaSearchProvider']
organic: 10
- 基于压缩感知信道估计的时域训练序列的填充方法及系统农业专利-农业学术服务平台 | ...
- 丁文伯：执着，让梦想开花-清华大学 | https://www.tsinghua.edu.cn/info/1181/46645.htm#1
- 丁文伯:执着,让梦想开花 | https://www.tsinghua.edu.cn/info/1179/17242.htm#1
```

`SERPER_API_KEY` is absent from the bundle `.env`, so Serper is not appended.

### 5.2 LLM query rewrite + search in one process

`resolve_professor_llm_settings("gemma4")` resolved to `qwen3.6-35b-a3b`.

```text
queries: ['丁文伯 清华大学深圳国际研究生院 教授 简介',
          '丁文伯 清华大学深圳国际研究生院 研究方向 科研项目']
search '丁文伯 清华大学深圳国际研究生院 教授 简介': 10 results
   first: 机器人行业奋斗中的清华人｜下周预告 | https://www.ee.tsinghua.edu.cn/info/1076/4765.htm
search '丁文伯 清华大学深圳国际研究生院 研究方向 科研项目': 10 results
   first: 深圳国际研究生院丁文伯团队在透明物体抓取领域取得新进展-清华大学 | https://www.tsinghua.edu.cn/info/1175/105464.htm
```

### 5.3 Ops script from a neutral cwd

```bash
cd /tmp && /root/deploy/fullstack-v2/.venv/bin/python \
  /root/deploy/fullstack-v2/code/apps/miroflow-agent/scripts/run_professor_web_enrich.py --help
```

Prints the argparse usage and exits zero. Before the change the same command
raised `ModuleNotFoundError: No module named 'src.data_agents.providers.deepseek_search'`
because `sys.path[0]` was `scripts/`.

## 6. Full write-path verification (isolated schema)

No production row was touched. A scratch schema was created in the customer
database:

```sql
CREATE SCHEMA enrich_scratch;
CREATE TABLE enrich_scratch.<t> (LIKE public.<t> INCLUDING ALL);  -- 5 tables
-- one professor (丁文伯, short summary) + affiliation + source_page
```

The deployed script ran with
`--dsn ".../miroflow_collection_v1?options=-csearch_path%3Denrich_scratch"` and
`--professor-id scratch-prof-001`.

Success case (DeepSeek chat profile, which requires the non-thinking flag below):

```text
1/1 enriched (261c, 23 verified, 5 pages fetched) ✓ written
DONE: 1/1 enriched, 0 failed, status=succeeded
```

Database after the run:

- `professor.profile_summary` length 261
- `professor_fact`: `homepage` / `active` / `web_enrich: 23 verified` / 0.85
- `pipeline_run`: `succeeded`, `items_processed=1`

Failure case (`--llm-profile gemma4`, whose gateway returned 502):

```text
0/1 enriched, 1 failed, status=failed   (exit 1)
pipeline_run: failed, items_processed=0
```

The scratch schema was dropped afterwards. The real tables carry 15 foreign
keys (the `LIKE` clone does not copy them); every written value satisfies them
(professor, source_page, pipeline_run all exist). No user triggers exist on the
five tables, so the clone does not omit trigger behaviour.

## 7. Two defects found and fixed while verifying

### 7.1 DeepSeek synthesis returned empty content

Without `extra_body={"thinking": {"type": "disabled"}}`, `deepseek-v4-flash`
spent the whole 800-token budget on reasoning and returned `content=""` with
`finish_reason=length`. `_generate_queries` silently fell back to two fixed
queries, then the synthesis gate skipped every professor ("synthesis too
short (0c)"). Fixed by passing `build_non_thinking_extra_body(model)` on both
LLM calls in the script. Measured: without the flag 0 chars, with it 171 chars
for the same prompt; the full run then wrote 261–278 chars.

### 7.2 Total failure was recorded as success

The final `UPDATE pipeline_run` always wrote `status='succeeded'`. Both the
502 run and the empty-synthesis run left `succeeded, items_processed=0` and
exit 0. Fixed: track `failed_count`; status is `failed` when the run had
candidates and enriched none; exit 1. Verified in the scratch schema:
`failed, 0` / exit 1 on the 502 run, `succeeded, 1` / exit 0 on the DeepSeek
run.

## 8. Not verified / boundaries

- The production database itself was not written. The isolated clone proves the
  code path and value shape, not production row-level constraints beyond the
  copied checks/indexes (the 15 FKs are satisfied by construction).
- The admin `/upload` professor import (`pipeline_v3`) shares the provider
  builder and its 20 unit tests, but no live DeepSeek import was run.
- `professor.profile_summary` lives in the collection DB; chat answers read the
  serving pack. A write is not visible in chat until a rebuild/backfill.
- On the customer bundle the default `gemma4` profile still points at
  `https://star.sustech.edu.cn/...`, which returned 502 during this session. A
  default run fails until that gateway recovers or the operator passes
  `--llm-profile deepseekv4flash`.
- Seed refresh (`admin-seed-refresh` / `-sample`) has **no cron** and is
  admin-triggered per seed. It runs `seed_runner` → `pipeline.py` (v2), imports
  no search provider, and only fetches known roster/homepage URLs via httpx.
  "No web search" should be read as "no search API"; the registry's
  `quota="web_search"` is a quota bucket, not a search call.

## 9. Rollback

Restore the three deployed files from their customer-site backups
(`.bak-deepseekfallback-20261024-0900` for the two pre-existing files; delete
`fallback_web_search.py`). The script's `extra_body`/status changes are part of
the current file. No data migration to reverse.

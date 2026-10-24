# Verification: fix-enumeration-search-view-company-truncation

Date: 2026-10-24
Line: serving worktree `switch/embedding-model-to-qwen37-flash`

## 1. Root cause

`_search_view` in `src/data_agents/canonical_v2/followup_referents.py` returns
the first `COMPANY_NAME_PATTERN` match as the retrieval text. The pattern accepts
any CJK run ending in 公司, so `深圳哪些公司做激光雷达` matched `深圳哪些公司`
and dropped `激光雷达`. `_has_explicit_company_name` in the same module already
rejects question words; `_search_view` did not use that list.

Reproduction before the fix (customer machine and local worktree):

```text
'深圳哪些公司做激光雷达' -> '深圳哪些公司'
'深圳有哪些公司做激光雷达' -> '深圳有哪些公司'
'深圳什么公司做激光雷达' -> '深圳什么公司'
```

Trace evidence (2026-10-23 01:51, session
`C4XrUsD91G4LegDYgkoomeezYIllcZ9d`):

- `lanes`: lexical 0, exact 0, structured 0, vector 128, web 12
- The only web views attempted were `深圳哪些公司` (bocha cache hit) and the
  same view on Serper (error)
- `answer_subject`: `深圳有哪些大型公司(2014年数据)_深圳发展数据库有关的公司名称-CSDN博客`
- Answer: "没有直接列出深圳从事激光雷达业务的公司名单" + 华为/中兴/比亚迪/
  腾讯/平安/招行/万科 + a 114-company disclosure dump

The pack contains 61 Shenzhen companies whose structured fields mention
激光雷达 (镭神智能, 览沃科技, 海伯森, 砝石激光雷达, …), so this was never a data
gap.

## 2. Change

```python
company = COMPANY_NAME_PATTERN.search(search_value)
if company is not None and not any(
    marker in company.group(1) for marker in _EXPLICIT_COMPANY_REJECT_MARKERS
):
    return company.group(1)
```

A match containing a question/anaphora word (哪些/什么/几/多少/这/那/该/此/…)
falls through to the full query text.

## 3. New tests

`tests/canonical_v2/test_followup_referents.py`:

- `test_search_view_keeps_content_term_after_question_word_company` — three
  phrasings (`哪些公司`, `有哪些公司`, `什么公司`) keep the full query.
- `test_search_view_still_compacts_real_company_names` — the named-company
  control (`深圳市优必选科技股份有限公司`), the anaphora form (`优必选这家公司`),
  and `深圳激光雷达公司有哪些` keep their current compaction.

Fixture source: constructed query strings; no network.

## 4. Regression suites

| Suite | Result |
|---|---|
| `tests/canonical_v2/test_followup_referents.py` | **152 passed** |
| `tests/canonical_v2/test_knowledge_query_planning_contract.py` + `test_enumeration_deep_fetch.py` | **11 passed** |
| `tests/canonical_v2/test_knowledge_serving_isolated.py` | **312 passed** |

Static checks: `ruff check` reports only the pre-existing F811 duplicate
`has_personal_pronoun` (present at HEAD); the added hunk is format-clean.

## 5. Deployment

`src/data_agents/canonical_v2/followup_referents.py` copied to
`/root/deploy/fullstack-v2/code/apps/miroflow-agent/...`, md5
`c82ac86ff3c28f19e4cf48a583ba0bfe`. Customer-machine import check:

```text
'深圳哪些公司做激光雷达' -> '深圳哪些公司做激光雷达'
'深圳有哪些公司做激光雷达' -> '深圳有哪些公司做激光雷达'
'深圳市优必选科技股份有限公司有哪些专利' -> '深圳市优必选科技股份有限公司'
```

Service restarted; `/api/health` returned 200 after the cold mount (the boot
took longer than usual because the process was swapping: RSS 19.5GB + 2.1GB
swap, memory pressure avg10 ≈ 26%).

## 6. Live verification (after restart)

Query `深圳哪些公司做激光雷达` (fresh session):

- Trace `ts 2026-10-24T14:29:33Z`:
  - lanes: web 72, lexical 128, vector 128, exact 0, structured 0
  - `answer_subject`: 深圳市砝石激光雷达有限公司 (a local entity, not a web page)
  - citations: 12
  - web views: `深圳哪些公司做激光雷达`, `深圳 激光雷达 公司 厂商`,
    `深圳 激光雷达 企业 车载 机器人`, `Shenzhen LiDAR companies manufacturers 深圳`
    — no `深圳哪些公司`-only view
- Answer: a structured list of 12 vendors (速腾聚创, 镭神智能, 览沃科技, 力策科技,
  砝石激光雷达, 煜炜光学, 玩智商/YDLIDAR, 机智人, 锐驰激光, 大族锐波, 海伯森,
  迈测科技), each with a one-line product description.
- Citations: 11 local `company` + 1 `web`; the first is
  `深圳市砝石激光雷达有限公司`.

Control query `深圳市优必选科技股份有限公司有哪些专利`: 12 `patent` citations,
structured by technical direction; no truncation regression.

## 7. Residual (not fixed in this slice)

- The answer still appends the member-coverage disclosure
  (`此外，本次检索还召回以下相关本地企业：…`) with up to 64 names. The names are
  now actually lidar-related, but the tail is still a long unstructured list.
  The sentence is appended **before commit** so its names widen the session
  universe for narrowing follow-ups; shortening it is a product/UX decision,
  not a retrieval bug.
- The indexed lexical lane (`CANONICAL_V2_LEXICAL_INDEX`) stays off; the
  substring lexical lane now returns 128 candidates because the content term
  survives. `jieba` is absent from the bundle venv, so the FTS artifact cannot
  be built there without a dependency install.

## 8. Rollback

Restore the pre-change file from the worktree HEAD (`git checkout --` the one
file) and restart. No data or schema change.

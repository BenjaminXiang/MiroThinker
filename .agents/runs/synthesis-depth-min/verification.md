# Verification — synthesis-depth-min (slice ①min)

Layered evidence. RED and diagnosis: `red-case.md` (live transcript, provider
probe, merge-order read, the `local_scope_foothold` gate). Contract:
`verification-contract.md`.

## ① New tests written this slice (7, all green)

`apps/miroflow-agent/tests/canonical_v2/test_web_wide_window.py` — fixture source:
the round-42 reported ask (verbatim), a same-family case with a different subject,
and the sibling suite's synthetic bundle (max_candidates=12, max_web_results=5) so
the three window widths stay readable.

| cluster | locks |
|---|---|
| window gate matrix | Web-only list → bundle sum (17); same family, different subject → bundle sum; 「…是谁」 → bundle width (5); local list → enumeration width (128); candidates never widened by this slice |
| kill switch | `CANONICAL_V2_WEB_WIDE_WINDOW=0/false/OFF/no` → bundle window, read per call |
| rewrite prompt | the English/full-name clause and its worked example are present; the length rule is scoped to Chinese queries |
| merge cap | `per_view_head` lets view 2 into a 16-wide window; the pre-slice merge buries it behind view 1's ten junk slots |

Plus the deliberate flip of a pre-existing assertion:
`test_knowledge_serving_isolated.py::test_no_foothold_query_executes_only_the_public_web_lane`
now parametrises the list-shaped boundary (the JEPA ask moved from "bundle width"
to "lane width"); its docstring records why.

## ② Pre-existing regression suites

| suite | result |
|---|---|
| `test_knowledge_serving_isolated.py` (-k window/foothold) | 31 passed |
| `test_knowledge_serving_isolated.py` (-k rewrite/merge/window/web) | 99 passed |
| `test_serving_pack_loader.py` + `test_manual_recall_points.py` + `test_fast_boot.py` + `test_alias_foothold.py` | 60 passed; `test_release_bound_vector_validator_exempts_manual_traces` fails — the known pre-existing Milvus-environment red recorded in slice ② |
| `test_llm_query_rewrite.py` | 33 passed; one **pre-existing race-flake** documented below |

### The pre-existing flake (evidence)

`test_rewriter_*_falls_back_to_deterministic_view` intermittently fails under the
full-file run and passes in isolation (5 runs today: 2 failures, 3 passes). The
failure detail is the arrival order of the two concurrent round-2 refinement
views:

```
assert providers.bocha_queries == [... 榜单, ... 名单]
E  At index 1 diff: '… 名单' != '… 榜单'
```

`_merged_results_for_views((f"{query_text} 榜单", f"{query_text} 名单"))` submits
both views' provider calls as concurrent futures and the fake provider records the
call when the worker thread starts, so the recorded order is scheduling-dependent.
This slice does not touch that path (the test's query holds a local foothold and
the slice leaves local windows and the discovery merge untouched).

## ③ Replay / fault-injection

| surface | result |
|---|---|
| scratch (v3 pack, port 18311) — 片② matrix | family 5 web citations; 优必选 12 patent; 深圳具身 20 company; 国先中心 1; negative control web-only |
| scratch replay gate | **ALL PASS 7/7** |
| scratch recall gate (37 cases: testset + semantic probes) | **REVIEW — 0 fail-level, 1 review-level** on both diffs (q13t1 「合成数据」, concept wording, present in both); vector median 61 → 69 (testset) / 72 → 72 (probes); candidate-layer hits 22 → 30 |
| dev line 18188 after cutover | JEPA audit 7 citations / 5 groups; matrix 5/5; replay **ALL PASS 7/7** |

**Measurement warning (recorded because it cost a round):** the first recall run
passed only `testset-cases.json` and reported a fail-level vector-median drop
(61 → 29.5). The baseline was captured with **two** case files
(`testset-cases.json` + `semantic-probes.json`, 37 rows, suites testset/probes);
the missing 12 probe rows moved the median and produced "coverage sNN present in A
only" rows. Re-run with both files → 0 fail-level. Always mirror
`baseline.json["cases_source"]`.

## ④ The reported case, before → after (AC1/AC2)

| | before (v2 pack, 2026-10-16 morning) | after (v3 pack) |
|---|---|---|
| answer | 719 chars, **0 citations**, 6 flat variants | 766 chars, **7 citations**, **5 categorised groups** with per-item key points (I-JEPA / DSeq-JEPA / LeWorldModel / 多模态 JEPA / 图结构 JEPA) |
| kept Web material | 10 items, **0 relevant** (all view-1 「EJA 压力变送器」) | 10 items incl. 什么是JEPA / LeCun 介绍 / 投资界复刻报道 / arXiv `[2505.12477] Joint Embedding vs Reconstruction` / `[2509.15470]` — **DSeq-JEPA in the answer came from an arXiv item** |
| mechanism | window 8 + view-order merge → the rewrite views' material (ranks 11+) truncated | window 16 + `per_view_head=4` → all four views land inside the window |

## ⑤ TTFT (AC7)

| ask | dev line, before | dev line, after |
|---|---|---|
| JEPA warm | 15.4 / 16.5 s (scratch, DP1+DP2 only) | ~15 s; live audit run 73 s wall incl. cold lazy linker |
| family (联邦学习) | — | 12.5 s |
| 优必选专利 / 深圳具身 / 国先中心 / 负控 | 29.8 / — / 9.5 s … | 26.9 / 13.2 / 5.0 / 6.4 s |

All inside the round-43 envelope; the only new cost is keeping up to 16 Web
results instead of 8 on list-shaped turns.

## ⑥ Reseal + cutover

- Dev line: manifest-only reseal (v2 → v3, `reader_contract_sha256=4ffbf9cd…`,
  three rebound fields, four hardlinks, zero bytes copied); cutover via the s12g
  command file + `systemctl --user restart`; boot took the **receipt fast path
  (mount 120.9 s)**; `/chat` and `/api/health` 200; rollback = the pre-synthdepth
  command file + the byte-identical v2 pack.
- Site (100.64.0.96): staged tree with exactly two files differing; resealed with
  the **site** interpreter (`3b5623a3…`, pydantic 2.13.4); switch with the
  fail-closed install (`cmp` per file + the site's live contract must equal the
  sealed value); first boot does the full verification; rollback script + the v2
  pack kept.

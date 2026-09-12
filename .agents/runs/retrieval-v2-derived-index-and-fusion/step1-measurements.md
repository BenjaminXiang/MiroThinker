# Step 1 measurements (2026-09-12)

## Artifact (sealed run14 pack)

- dictionary words: 76,206 (entity name forms; AQ-S7 derivation)
- documents indexed: 47,071 (all domains)
- artifact: 94.2 MB, build 69.4s (incl. 635MB pack sha256)
- pack sha (manifest): c392d559f403…

## Query latency (real artifact)

| phrase | latency | hits |
|---|---|---|
| 激光雷达 | 2.6ms | 128 |
| 储能电池 | 4.8ms | 128 |
| 酒店送餐机器人 | 22.4ms | 128 |
| PCB打板 | 1.0ms | 103 |
| 具身智能 | 7.3ms | 128 |
| 无人机整机 | 2.7ms | 128 |
| 医疗器械 | 3.3ms | 128 |

Baseline (substring lane, live turn-debug): 0.92-3.54s per turn.

## Recall where the substring lane finds nothing

| phrase | old matched | index hits |
|---|---|---|
| 酒店送餐机器人 | 0 | 128 |
| PCB打板 | 0 | 103 |
| 无人机整机 | 2 | 128 |

## Phrase vs OR (the adjacency correction)

| phrase | phrase hits | OR hits |
|---|---|---|
| 激光雷达 | 66 | 128 |
| 储能电池 | 114 (raw-quoted phrase: **0**) | 128 |
| 具身智能 | 86 | 128 |
| 医疗器械 | 128 | 128 |
| 酒店送餐机器人 | 9 | 128 |

## Window composition (index top-64 vs old document-order top-64)

typed = phrase/tokens in name or tags; body_only = only body text; neither =
other flattened field. NOTE: the pack's typed fields are sparse (review §9),
so `typed` under-credits true positives — this view is kept as a leak
indicator, not as the acceptance metric (the acceptance metric is the live
generalization-probe P2 count).

| phrase | index typed/body_only | old typed/body_only |
|---|---|---|
| 激光雷达 | 0.11 / 0.83 | 0.09 / 0.91 |
| 储能电池 | 0.05 / 0.86 | 0.05 / 0.93 |
| 具身智能 | 0.23 / 0.75 | 0.19 / 0.81 |
| 医疗器械 | 0.27 / 0.73 | 0.19 / 0.77 |

## Correction (2026-09-12 23:45–00:10): the raw-question OR fill was a precision regression

The tables above measured `index.search` directly (phrase and OR passes). Wiring
the lane into serving exposed what the OR pass does to the *window*: it OR'd the
raw question's tokens, 公司/的/有/深圳 included, so unrankable matches crowded out
the real category members.

Harness A/B, same turns, same pack (`harness-lexical-v2` = substring lane,
`harness-lexical-v2e` = indexed lane with the raw-question fill):

| turn | window | id overlap | g2 GT in window |
|---|---|---|---|
| lidar-t1 | 128 vs 128 | 0.66 | n/a |
| g2-t1 | 128 vs 128 | 0.35 | v2: 云迹/普渡/开普勒/擎朗 present; v2e: **absent** |
| pcb-t1 | 128 vs 128 | 0.45 | n/a |

Live generalization probe with the index on: `gen-lidar#1` reported 15
off-category companies out of 64 — 心鉴智控 / 超联讯 / 骏之源 / 兰星 / 门庭 /
德龙艺彩 / 大德激光 — which are exactly the ids the index lane had added to the
window (id-level diff of the two harness rounds). The junk the fill introduces
reaches the answer, not just the candidate pool.

### Fix (876662cd)

1. Index query = content residue (the category path's stop-phrase stripping:
   深圳/中国/有哪些/公司/的/做 …), never the raw question.
2. Wide fill only for category questions (the enumeration markers); entity and
   keyword lookups keep the narrow adjacency pass and fall through to the
   substring lane when it is thin.

Offline A/B against the deployed artifact (`step1_lane_query_ab.py`; window 128,
company domain):

| query | raw question | content residue |
|---|---|---|
| 深圳有哪些做激光雷达的公司 | 128 selected, top 5 mixed | 128 selected, top 5 all real lidar companies |
| 中国有哪些成熟的酒店送餐机器人供应商 | 128, GT: 成都普渡 only | 128, GT: 云迹/上海擎朗/深圳普渡/上海开普勒 re-recalled |
| 我想找PCB打板, 有哪些推荐 | 128 | 117 (same top 5) |

### One-time open cost (new finding)

`LexicalIndex.open` costs 5.7s on the run14 pack (jieba domain dictionary +
FTS5 connect) and the first lane call used to pay it inside the first user turn
(live lidar turn: lexical lane 9.4s wall). The serving composition now warms the
index in a daemon thread at boot; the open is process-cached and only successful
opens are cached, so a rebuilt artifact is picked up without a restart.

## Harness round v2f (00:05, after the fix): lane cost and window composition

`harness-lexical-v2f/` — same four turns, index on, debug on. Zero fallbacks;
the index lane served all four turns (`[lexical-index]` lines):

| turn | index query | selected | select | build | total | lane stage wall |
|---|---|---|---|---|---|---|
| lidar-t1 | 激光雷达 | 128 | 0.003s | 0.053s | **0.056s** | 9.14s (first lane call in the process: the shared bound-document read) |
| g2-t1 | 酒店送餐机器人 | 128 | 0.555s | 0.051s | **0.607s** | 0.61s |
| pcb-t1 | 我想找PCB打板, | 117 | 0.578s | 0.132s | **0.710s** | 0.71s |
| pcb-t2 | quoted display-name list | — | — | — | — | 0.33s |

Baselines: substring lane 0.92-3.54s (live turn-debug, frozen above); the same
four turns on the substring lane measured 1.13 / 2.46 / 3.71 / 0.37s in
`harness-lexical-v2`.

Window composition vs the substring lane (`v2`), by canonical id:

| turn | window | id overlap | notes |
|---|---|---|---|
| lidar-t1 | 128 vs 128 | 0.72 | v2f top 6 are laser/lidar companies; the v2e junk (心鉴智控/门庭/德龙艺彩) is gone |
| g2-t1 | 128 vs 128 | 0.61 | GT back: 云迹/上海擎朗/深圳普渡; 上海开普勒 and 九号 dropped (window is 128 and the fill is BM25-ranked) |
| pcb-t1 | 128 vs 128 | 0.44 | v2f adds 找铅网/数位汇聚 (matched 找/PCB tokens — 我想找 is not in the stop list) |
| pcb-t2 | 32 vs 32 | 0.19 | carryover turn; window is the displayed set, mostly from other lanes |

Note: the harness lane-stage wall for the first lane call still shows ~9s — it
is the process's first `_read_bound_documents` (all 47k documents), shared by
every lane, not the index call. The live service pays the same cost on its
first turn; the boot warm covers the index open only.

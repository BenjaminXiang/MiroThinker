# RED — synthesis-depth-min (slice ①min)

Verbatim evidence, dev line 18188 (fembed-v2 pack), 2026-10-16 morning. Fixture
source: the customer's reported question (round 42) and the line's own live turns.

## 1. The reported case, verbatim

Ask: `目前有哪几种主流的JEPA变体？` (fresh session, `/api/chat/stream`)

```
query_type:   canonical_v2:A:answer
answer_style: llm_synthesized
answer chars: 719
citations:    0
evidence:     0
lanes:        [{"lane":"web","status":"succeeded","candidates":16}]
```

Answer head (verbatim): 「JEPA（Joint Embedding Predictive Architecture，联合嵌入预测架构）
是Meta首席AI科学家Yann LeCun提出的一类自监督学习架构…目前公开讨论中较为主流的变体方向大致有以下几类：
**I-JEPA**…**V-JEPA**…**A-JEPA**…**Point-JEPA**…**MC-JEPA**…**S-JEPA**…此外还有一些面向
特定模态或任务的衍生工作…需要说明的是，JEPA本身仍是一个快速演进的研究方向…」

Six flat variants, no citations, no sources — versus the customer's reference
(7 categories, 20+ variants, per-item details).

## 2. What the turn actually kept as material

Turn-debug dump for the ask (chat layer's own record):

```
recalled_handles: 8      committed_names: 4
evidence_items: {total: 8, by_domain: {professor: 8}, by_lane: {web: 8},
                 by_source_nature: {current_web: 8}}
lane_timings: 1 (web only)      render_mode: prose_renderer
```

The 8 kept Web items, all of them:

```
1. EJA选型 - 豆丁网                              2. EJA选型 - 豆丁网 (m)
3. EJA选型.doc - 原创力文档                       4. 产品中心-紫龙雄宇科技
5. eja压力变送器型号有几种 - 住范儿                6. eja压力变送器型号及参数大全
7. EJA-CXT型号对比表 - 豆丁网                     8. 横河EJA和EJX液位变送器型号 - 搜狐
```

**0 of 8 relevant**: the search matched 「EJA」 (Yokogawa pressure transmitters)
against 「JEPA」.

## 3. Control: the short form reaches real material

Ask: `JEPA 有哪些变体？` — same line, same minute:

```
citations: 3 {'web': 3}      elapsed 6.8s
1. 160行代码读懂LeCun的JEPA世界模型|投资界
2. JEPA:Yann LeCun 提出的联合嵌入预测架构 - 掘金
answer head: 「JEPA（Joint-Embedding Predictive Architecture…）…**I-JEPA 系列（图像方向）**
公开信息显示，有开发者用 PyTorch 以极简单文件形式复刻了 JEPA 核心系列…**AdaJEPA（自适应潜在世界模型）**
据智源社区论文介绍…**LeWorldModel**…」
```

Same pipeline, better material, grounded answer. The difference is **which
strings reached the search engine and what survived the window**.

## 4. Provider probe — which search string yields real material

Direct Bocha probe (production provider, `count=12`, titles only):

| query string | organic | relevant |
|---|---|---|
| `目前有哪几种主流的JEPA变体` (the deterministic view today) | 10 | **0** |
| `JEPA 有哪些变体` | 12 | ~3 |
| `JEPA 架构 变体 汇总 I-JEPA V-JEPA` | 12 | 0 (变压器/变配电 noise) |
| `JEPA joint embedding predictive architecture variants` | 11 | **11 (arXiv MTS-JEPA / VJEPA / DSeq-JEPA / MJEPA …)** |

## 5. Mechanical root cause

- The Web lane searches up to 4 views: the deterministic view (= the raw question,
  `_search_view(original_query)`) plus up to 3 LLM rewrite views. On the live line
  the rewriter works and returns, verbatim:
  `('JEPA 变体', 'JEPA 主要变体 类型', '联合嵌入预测架构 变体')`
  (verified in-process with the managed runtime applied — `CHAT_LLM_PROFILE` is
  projected at boot, so a bare-process test resolves the stale `gemma4` profile and
  wrongly reports an empty rewrite).
- `_merge_web_results_across_views` concatenates **in view order**; the
  deterministic view leads. Its 10 junk items therefore occupy ranks 1–10.
- The read side keeps `max_web_results = bundle.max_web_results = 8` for this turn
  because `enumeration_window_widened` requires a local-scope foothold
  (`knowledge_serving_isolated.py` ~line 865). Ranks 11+ — where the rewrite views'
  real material lives — are truncated before fusion.
- Measured consequence with the real provider, merging the 4 views in pipeline
  order: **window 8 → 0 relevant kept; window 16 → 3; window 24 → 4.**

## 6. What the answer can be, given material

The renderer prompt (`knowledge_serving_isolated.py` ~line 5866) already requires
categorised concept answers ("对'方法/路线/方式/差异/原理'类概念问题：按行业常见分类分条组织
答案…只组织输入中有依据的内容，不得为凑分类而编造"). The RED therefore is a **material**
failure surfacing as a **synthesis** symptom; the fix must move material, not
soften the grounding rule.

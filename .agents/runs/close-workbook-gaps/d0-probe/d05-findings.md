# D0.5 深挖证据 — 选择环准入 / 门逐条分析 / 结构化车道空转（2026-09-11）

> 承接 D0（`d0-findings.md`）：D0 把每个 GT 实体定位到丢失阶段（①未召回/②召回未承载/⓪数据缺口），
> 本切片把三个阶段内部的**判定规则**拆开：② 的选择环准入规则（Q1）、t2 subject-consistency
> 门的逐条裁决（Q2）、① 的确定性车道为何对类目查询空转（Q3）。
> 全程离线：生产痕迹 + web_lane 缓存 + run14 封印包（只读），无任何网络访问，不改任何 src。
> 采集脚本 `collect_d05_gate_replay.py`（可重跑），结构化产出 `d05-gate-replay.json`。

## 0. 方法与验证锚点

Q2 的门重放不是近似模拟：从 `var/turn-trace/web_lane.sqlite3` 按 `sha256(view)` 取出
**生产当天真实 bocha/serper 返回体**（视图原文取自 trace `web_outcomes`），导入
`knowledge_serving_isolated` 的**真实函数**（`_merge_web_results_across_views` /
`_discovery_front_merge` / `_web_result_relevance_tier` / `_anchor_location_qualifier` /
`_web_identity_*`）重建门输入并逐条裁决。正确性锚点全部命中：

| 锚点 | 生产 trace | 离线重放 | 吻合 |
|---|---|---|---|
| g2-t2 门输入条目数 | in=74 | 74 | ✓ |
| g2-t2 门输出 | retained=7 | 7 | ✓ |
| g2-t2 门丢弃数 | gate_drops=67 | 67 | ✓ |
| g5-t2 门输入 | in=84 | 84 | ✓ |
| g5-t2 门输出 | retained=3 | 3 | ✓ |
| g5-t2 门丢弃数 | 81 | 81 | ✓ |

**关键副发现（视图数对账）**：两轮 t2 的 trace 各记录 6 个 web 视图（12 条 outcome），
但门输入只相当于**前 4 个视图**的合并结果。原因：`web_search` 适配器实例被两处复用——
主车道一次调用（`_request_view_queries` 被 `_SERVING_WEB_MAX_QUERY_VIEWS=4` 截断，
`knowledge_serving_isolated.py:1331,1641`）+ **supplemental 探针**（`_create_serving_person
_criteria_sufficiency_supplemental` 内部另建 `probe_adapter`，走 `_merged_results` 单查询路径，
`:4097-4114`）——探针路径**不过 subject-consistency 门**（门只在主车道 `__call__` 的
`:1462` 触发）、**不落 lane 计数**（`_merged_results` 无 `record_lane_counts`），
所以 trace 里 `lanes.web.in=74/84` 只反映主车道，两轮多出来的 2 个视图（g2：
"深圳 机器人 企业 总部"/"深圳 服务机器人 公司 列表"；g5："上述企业名单"/"企业注册地 深圳"）
是探针视图。g2-t2 探针视图里正好有**普渡深圳总部的强证据**（见 Q2）。

## 1. Q1 选择环准入规则（g2-t1 普渡/九号、g5-t1 深南电路）

### 1.1 准入链逐环（run14 生产参数：bundle `max_candidates=8 / max_web_results=8`，
见 `s12g/serving-bundle-run14.json`；类目查询含"哪些/推荐"→ 枚举分支全线放宽到 48）

| 环 | 规则 | 代码位置 |
|---|---|---|
| 规划窗口 | 枚举查询：max_candidates=max(8+8,48)=**48**，max_web_results=max(8,48)=**48** | `knowledge_serving_isolated.py:736-774`（`_ENUMERATION_CANDIDATE_WINDOW=48`，`:2762`） |
| 车道产出（g2-t1 trace） | exact 0 / structured 0 / lexical 0 / vector 48 / supplemental 10 / web 66→66（t1 无绑定实体→门不触发，`:862-863`） | trace `JgjH8u4M…` t1 |
| 融合窗口 | 融合证据集按 object_id 截到 plan.max_candidates=**48** 个对象 | `knowledge_read.py:7795` |
| selector 准入 | 枚举查询：`eligible`=全量（`:5826-5833`，enumeration=True 放行一切）；local/web 交错平衡（`:5840-5845`）；claim 上限 local=**max(8,16)=16**、web=**48**（`:5846-5862`）；每条须 `claim_binding` 非空、按 (object_id, 来源组) 去重、过 raw-dump 与概念离题过滤（`:5877-5900`） | `knowledge_serving_isolated.py:5742-5939` |
| 展示集 | `displayed_handle_ids` 只由**进入 claims 的条目**的 handle 构成（`:5901-5908`） | 同上 |
| prose 选中 | `selected_handle_ids ⊆ 当轮 displayed ∪ anchor`，越界即 ValueError | `knowledge_answer.py:2411-2431`（`_apply_prose_synthesis`） |
| 会话提交 | 选中非空 → **用 selected_handle_ids 整体重写** session displayed set；空选中才保留全集 | `knowledge_answer.py:2488-2559`（`_commit_prose_scope`，重写点 `:2505-2520`，空选保护 `:2498-2502`） |
| 下轮绑定 | 只有 `handle.kind=="canonical"` 的 id 进入下一轮 displayed_entity_ids / referent history | `canonical_v2_chat.py:2035-2048`（`_displayed_ids`）、`:711-716`（`_next_referent_history`） |
| web→canonical 绑定 | 仅当 LaneRequest 带 `bound_entity_names` 时 `_matched_bound_entity` 才可能命中；**首论类目查询绑定集为空 → 恒 None** | `knowledge_serving_isolated.py:2497-2498`；bound 集来自规划确定性视图 `knowledge_read.py:5108-5117` |

### 1.2 普渡/九号为何未进展示/承载集（g2-t1，会话 `JgjH8u4M…`）

两道结构性闸门，各由代码钉死：

1. **canonical handle 根本没产生**。普渡在包内有 3 个 identity 文档、75 处顺带提及
   （`d0-evidence.json`），但首论类目查询下：exact/structured/lexical 三条确定性车道
   **结构上空转**（Q3），web 车道的 66 条结果因绑定集为空**永远绑不到 canonical id**
   （`_matched_bound_entity` 恒 None，`:2497-2498`）——web 条目只能挂 `web-object:sha256:*`
   对象。唯一可能产出普渡 canonical handle 的是 vector 车道（48 候选，远程 embedding，
   **离线不可重放**，D0 §3 盲格）与 supplemental（10 候选，内容未落盘）。
2. **即便 web 证据进了 claims 和 prose 选中，也进不了承载集**。t2 的绑定集由
   `_displayed_ids` 的 canonical-only 过滤产生（`canonical_v2_chat.py:2044-2048`）——
   web-only 实体**按构造**不可能出现在 t2 的 displayed_entity_ids 里。D0 已证 t2 的
   structured/vector 12/12 重查正是这 12 个 canonical id。

生产未落盘、因而**不可判定**的子环节（诚实边界）：普渡的 web 对象是否挺过 48 对象融合窗
与 16/48 claim 上限进入 prose prompt（若进了，是 LLM 没选用；若没进，是窗口截断）——
claim 清单只有结果（答案未含普渡）可考，过程不可考。

### 1.3 深南电路"答而未承载"（g5-t1，会话 `-YZXc4pO5…`）

机制链逐字钉死：

- prose 模型在答案尾部写了"此外…深南电路…"（D0 已证命中归档答案），但
  `selected_handle_ids` 只含 4 家（顺易捷/驭鹰者/嘉立创/深华科，t2 structured/vector
  4/4 重查证实）。
- `_commit_prose_scope`（`knowledge_answer.py:2488-2559`）：**提交只认
  selected_handle_ids，不认答案正文提及**。选中非空即把会话展示集重写为这 4 家
  （`:2505-2520`）；正文里讨论但未选中的 ~10 家（含深南电路）随重写被逐出会话宇宙。
- 选中合法性（`knowledge_answer.py:2411-2431`）要求选中 ⊆ 当轮展示集 ∪ anchor——
  即"提及"只需要 claim 在 prompt 里，"承载"还需要模型把它的 handle 填进选中清单。
  **提及 ≠ 提交**，差的就是这一步。
- 后果（D0 已证）：g5-t2 绑定集=4 家 → 深南电路在 t2 的 web 证据被门当"跑题"丢
  （见 Q2 C 类），追问结构性不可达。

## 2. Q2 门逐条分析（g2-t2 web 74→7 / g5-t2 84→3）

### 2.1 判定规则（`_apply_web_subject_consistency`，`knowledge_serving_isolated.py:847-919`；
tier 判定 `_web_result_relevance_tier`，`:2420-2458`）

只在有绑定实体（=上轮承载集，可加 soft_context_subject）时触发（`:854-863`）。
每条结果按 title+snippet（**不含 summary/正文**）分六档：

| tier | 条件 | 去向 |
|---|---|---|
| T0 | 双通道佐证（bocha+serper 同 URL）≥2 | 必留（kept） |
| T1 | 全名命中绑定实体 + anchor 城市限定词共现（如"深圳"） | 留（kept） |
| T2 | 全名命中绑定实体（无限定词共现） | kept≥3 时留；否则进回填池 |
| T3 | 全名命中但带**其他分支**城市限定词（如"（北京）"） | 同 T2，排在后 |
| T4 | 仅短别名命中（如"锐曼"+"机器人"语境） | kept≥3 时**丢**；否则进回填池 |
| T5 | 无任何名字命中 | kept≥3 时**丢**；否则进回填池 |

分支规则（`:896-910`）：kept(T0+T1) ≥ **floor=3** → 留 kept+related(T2+T3)，T4/T5 全丢；
kept < 3 → kept + 从 T2→T3→T4→T5 顺序回填**到恰好 3 条**，其余全丢。

anchor_qualifier 的产法（`:2306-2328`）：绑定名里第一个带括号地名（词典
`:2282-2289`）的限定词，或词干出现在查询里时查询残余中的地名。

### 2.2 g2-t2（绑定=12 家，anchor_qualifier=深圳，来自"中铧机器人（深圳）有限公司"）

重放：kept=4（全 T1）≥3 → 留 T1×4+T2×3=**7**（与 trace 吻合），丢 T4×8+T5×59=**67**（吻合）。
逐条分类（`d05-gate-replay.json` 全量）：

| 类 | 数 | 判定 | 实例 |
|---|---|---|---|
| A（仅别名命中展示集成员） | 8 | **别名碰撞为主**：~5 条"深圳市锐曼智能**装备**有限公司"（≠成员"锐曼智能**技术**"）、1 条"深圳中智锐曼"（第三方公司）；仅 1 条真在题（Reeman Robotics 官网"关于我们"页=锐曼智能技术官方品牌页） | 门把 T4 当"suspect"被数据证实大体正确 |
| C（展示集外 GT 实体） | 1 | "2024年十大关键词数说深圳576家上市公司"（顺带提及普渡的泛列表，弱证据） | 应丢，但记下普渡信号 |
| D（跑题噪声） | 58 | 深圳上市公司名录/排行榜等 | 应丢 |

**结论：g2-t2 的门本身裁决质量尚可**（67 丢里约 59-66 确为噪声/碰撞，1 条弱 GT 信号误伤）；
真正的损失在别处——**普渡深圳总部的强证据（"普渡机器人全球新总部在南山启用"、
"深圳再添一家机器人总部企业"）出现在第 5-6 视图的返回体里，走的是不过门的
supplemental 探针路径**（§0），根本没进被门的 74 条。它在探针→supplemental 候选段
的死因未落盘（D0 §3 盲格延续）。

排列稳健性：72 个合法视图排列下 A/C/D 计数区间为 A[0,8] / C[1,4] / D[57,67]
（敏感点是同 URL 双通道 snippet 谁占槽）；表中数字取生产最可能的排列
（query_text 优先 + outcome 记录顺序 = 视图 0-3），门输出的 7 条在该排列下与 trace 逐数吻合。

### 2.3 g5-t2（绑定=4 家，anchor_qualifier=**None**）

4 家绑定名均无括号地名、词干也不在查询"上述企业有哪些是深圳的企业"里 →
T1 **不可达**；且中文 B2B 页面 bocha/serper 结果几乎不重叠 → T0=0 → kept=0 < 3 →
**回填分支截断到恰好 3 条**。重放：留 3（驭鹰者×2+嘉立创×1），丢 81（吻合 trace）。
逐条分类（24 个排列下计数完全稳定）：

| 类 | 数 | 判定 | 实例 |
|---|---|---|---|
| **B+（全名命中展示集成员，被 floor=3 截断）** | **9** | **误伤**：顺易捷×6（启信宝/天眼查/官网/百度百科，全名+注册信息页）、驭鹰者×1、嘉立创百度百科×1——正是"是不是深圳企业"问题的注册地证据 | **门的设计缺陷点** |
| A（仅别名命中） | 4 | 顺易捷 PCB 官网页×2、嘉立创报道×1、启信宝"顺易捷实业"×1（碰撞存疑） | 部分真在题 |
| C（展示集外 GT） | 1 | "深圳500强企业.xls"（含深南电路） | 应丢（对当轮问题而言），但即 D0 的"召回被门丢"实例 |
| D（跑题噪声） | 67 | 深圳上市公司名单/名录类 | 应丢 |

**结论：g5-t2 的门是主动误伤源**——floor=3 回填截断把 9 条全名命中的成员证据连同
4 条别名命中一起丢了；失能根源是 anchor_qualifier=None 时 T1 不可达 + T0 双通道
佐证在中文企业页面上近乎不发生（两轮 T0 均为 0）。

### 2.4 "保精度放行在题证据"的最小改进形态（分析，不实现）

按改动面从小到大：

1. **回填分支不截断 T2/T3**（一行级改动）：kept<floor 时保留**全部**全名命中
   （全名命中正是 kept≥3 分支信任的同一信号，精度不降），只把 T4/T5 的回填截到
   floor。g5-t2 即由 3→12 条在题证据全保。
2. T4 别名命中降级保留（小上限、排在 T2/T3 后）：g2-t2 数据显示 T4 里确有真在题
   （Reeman 官网）但别名碰撞多（锐曼装备），需配合别名歧义防护，不可无条件放行。
3. anchor_qualifier=None 时把全名命中视作 kept 计数的合格来源（消除 T1 不可达的
   不对称）——改动语义更大，留主上下文取舍。

注意：即使门全放行，g5-t2 的 GT 缺口大头仍是⓪数据缺口（华秋/中信华不在包）与
B3 继承（深南电路未承载）——门修复是必要非充分。

## 3. Q3 结构化车道空转事实核查（类目查询 exact/structured/lexical=0）

### 3.1 三条确定性车道的匹配规则（代码钉死）

| 车道 | 匹配规则 | 代码位置 |
|---|---|---|
| exact | 规范化后的**整条查询**等于某文档的 display/identifier 词（公司=名+别名/统一信用代码），或保护槽指名 | `knowledge_read_isolated.py:8188-8230`（`_matches_exact_request`）、词表构建 `:8116-8149`（`_projection_terms`） |
| structured | **仅按 id 重查**上轮展示集：`canonical_object_id ∈ displayed_entity_ids`；适配器在展示集为空时直接返回空 | `knowledge_read_isolated.py:8232-8246`（`_matches_structured_request`）、`serving_pack_loader.py:959-963`（空集短路） |
| lexical | **整条查询短语**是某文档某个 content 词的**子串**（或公司名换位匹配） | `knowledge_read_isolated.py:8248-8273`（`_matches_lexical_request`）、短语提取 `:8165`（`_lexical_query_phrase`） |

"中国有哪些成熟的酒店送餐机器人供应商"这类类目查询：无实体名 → exact 无可等；
t1 无展示集 → structured 短路为空；整句 17 字不会是任何单字段值的子串 → lexical 空。
**三条车道按构造都不做类目召回**，trace 计数（g2-t1/g5-t1 三条全 0）与构造一致。

### 3.2 本地 catalog 有没有现成字段可供确定性类目召回？——**有**

关键事实：`content_terms` = `_normalized_scalar_values(projection.model_dump(mode="json"))`
（`knowledge_read_isolated.py:8147` + `:8166-8184`）——**投影全部标量字符串字段递归入词表**，
即字段内容已经在车道可读的数据结构里，缺的只是"类目词→字段"的匹配规则。

CompanyProjection 的类目相关字段（`domain_projection_models.py:380-408`）：
`industry`（`:390`）、`industry_tags`（`:391`）、`tech_tags`（`:403`）、
`business_scenarios`（`:405`）、`capabilities`（`:406`）、`product_description`（`:398`）、
`profile_summary`/`technology_route_summary`（100% 必填）。

run14 封印包实测（7,089 个 public_domain 公司文档，`lookup.sqlite3` 全扫）：

| 字段 | 填充数 | 填充率 |
|---|---|---|
| industry | 6,517 | **91.9%**（41 个 distinct 行业名，含 机器人/电子制造/先进制造/物流运输/餐饮业） |
| industry_tags | 5,480 | 77.3% |
| tech_tags | 5,485 | 77.4% |
| product_description | 5,368 | 75.7% |
| profile_summary / technology_route_summary | 7,089 | 100% |
| registered_address | 6,506 | 91.8% |
| geography | 5,491 | 77.5% |
| **business_scenarios / capabilities** | **0** | **0.0%**（包内全空，不可用） |

GT 实体抽查（包内实际值）：

| 实体 | industry | tech_tags / product_description | 类目可召回性 |
|---|---|---|---|
| 普渡（深圳市普渡科技） | 机器人 | 空 | industry=机器人 可中 |
| 普渡科技股份（另一 identity） | 物流运输 | "室内外配送机器人研发商" | tech_tags 文本可中，industry 漏 |
| 九号机器人 | 机器人 | 空 | industry 可中 |
| 开普勒/云迹/擎朗 | 机器人 | 空/空 | industry 可中 |
| 艾唯尔 | **餐饮业** | "餐饮行业的智能交互服务机器人研发商" | industry 漏，tech_tags 可中 |
| 安赛步 | 人工智能 | prod="AS09" | 弱 |
| 深南电路 | 电子制造 | 全空 | **只能靠 profile/tech_route 全文** |
| 一博 | 电子制造 | prod="未找到" | 同上 |
| 兴森/则成/上达/精诚达 | 生产制造 | "印制线路样板…"/"FPC…" | tech_tags 可中 |

结论：**字段存在且已入 content_terms**（industry 91.9% + tech_tags 77.4% + 两个 100%
全文摘要），确定性类目召回有数据基础；但单一 industry 字段不足以覆盖细粒度类目
（"酒店送餐机器人"横跨 机器人/餐饮业/人工智能/物流运输四个行业值；"PCB打板"=
电子制造/生产制造 + tech_tags/profile 文本），需要"类目词→多字段"的映射设计——
属于方案取舍，移交主上下文。business_scenarios/capabilities 在 run14 包内 0 填充，
不可作为依据。

## 4. 盲格与边界（诚实清单）

- **vector 车道 48 候选的逐实体成员**离线不可判定（远程 embedding 服务）——普渡/九号
  的 canonical 文档是否进过候选，不可考。
- **融合窗（48 对象）与 claim 窗（16/48）的逐对象去向**生产未落盘——普渡 web 对象
  是否进过 prose prompt 不可考（进了=LLM 没选用，没进=窗口截断）。
- **supplemental 探针→候选的死因**未落盘：g2-t2 探针视图里的普渡深圳总部强证据
  具体死在哪一步不可考（只知 supplemental in=2，未进答案）。
- **prose 模型的 selected_handle_ids 选择理由**不可考（只有结果）。
- g2-t2 重放的 A/C/D 计数对"同 URL 双通道 snippet 谁占槽"敏感（区间已给）；
  g5-t2 计数在全部 24 个排列下稳定。
- g2-t1 trace 显示 `degradation=interpretation-rejected`：解释层当日对这些轮次未生效，
  本分析不覆盖解释层修复后的形态。

## 5. 产物清单

- `collect_d05_gate_replay.py`：门重放脚本（真实函数导入 + 视图集 brute-force 验证 +
  排列稳健性扫描），可重跑。
- `d05-gate-replay.json`：两轮 t2 的逐条目 tier/分类/标题/URL/通道全量。
- 本文件。证据指针全部使用 worktree 相对路径 + 行号（行号以 commit `04e15966` 为准）。

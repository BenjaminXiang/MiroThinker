# 答案质量切片 · 实现级设计（归档，2026-09-11）

> 来源：plan agent-13 只读设计（主上下文已裁定，见 §6）。配套证据：
> `answer-quality-evidence-addendum.md`、`change-log.md` 的 r3/r4 归因条目、
> `d0-probe/f1b-downstream-trace.md`。行号均指 s11 worktree。

## 0. 地基事实（设计前提）

- 两把刀决定展示集：read 层 `ordered[:plan.max_candidates]`
  （`knowledge_read.py:8059-8060`，枚举类 =48）+ selector 层
  `local_claim_limit = max(bundle.max_candidates,16)=16`
  （`serving:5857-5864`）。reranker 固定 local/web 1:1 交错 →
  **ordered 48 = 24 local + 24 web**；"16 窗"之外还有"24 local"这层隐形约束。
- 枚举判定：`request.enumeration_context.requested` 或查询含
  `_ENUMERATION_QUERY_MARKERS`（哪些/谁/多少/几个/几种/列出/所有/分别/
  推荐/厂商/供应商；`serving:2777-2789`、`:736-775`）。g2-t1/t2/t3、
  g5-t1/t2 全部命中"哪些"，走同一套枚举参数。
- 本地候选 raw_score 恒 1.0（`read_isolated:8756`）；vector/manual 车道
  得分 <1.0，永远排在 1.0 之后（F4 后并列组内保输入序）。
- 公司 claim 文本只渲染 简介/技术路线（`serving:4207-4220`），而
  `lookup_content` 里带着 `registered_address`（91.8%）与 `geography`
  （77.5%）——证据在，没渲染。
- 收窄轮的确定性地理判定存在（`knowledge_read.py:6511-6562`，名字启发式
  `:6540-6551`），但结论不落 claim；prose 提示 `serving:5153-5154` 明令
  不得由名称/分支机构/服务地点推断总部。
- run14 包 hash 封死，不能就地打补丁；唯一 sanctioned 写路径 = 运营侧车
  manual recall（`manual_recall_points.py`，`CANONICAL_V2_MANUAL_RECALL_DIR`）
  ，但它只挂 vector 车道 → 位置天然靠后。
- C1 批 0 已在 s11 worktree 落文件：`catalogs/anchoring-declaration-v1.json`
  （`terms[]`：tier/anchor_field/match_mode/multiplier/whitelisted）+
  `anchoring_declaration.py`；`read_isolated:8443` 目前只消费
  `f1_category_scoring`，`terms[]` 尚无消费者（= A-2 的落点，须排队）。

## 1. 逐类最小修法

### A. 枚举覆盖-窗口外

**A-1（g2：安赛步/锐曼在 local-16 之外）**

根因：`serving:5857-5864`（16 窗）+ `knowledge_read.py:8059-8060`
（48 截断）+ 1:1 交错（`serving:2578-2588`）。after-F4 重放 local 序：
云迹1 普渡2 开普勒3 擎朗4 九号8 中科世界9 艾唯尔12 小村13 …锐曼=26
（超 16 且超 24 半区）；**安赛步未召回**（F1 pool 436，industry=人工智能、
tags 空、product="AS09"）→ 数据天花板，本轮不修。

修法（按查询类型分层）：

| 查询类 | local claim 窗 | web claim 窗 | plan/read 截断 |
|---|---|---|---|
| 非枚举（不动） | 3 | bundle.max_web（8） | bundle.max_candidates（8） |
| 枚举（本切片改） | **32**（`_ENUMERATION_LOCAL_CLAIM_WINDOW`） | **32**（`_ENUMERATION_WEB_CLAIM_WINDOW`） | **64**（`_ENUMERATION_CANDIDATE_WINDOW` 48→64） |

联动（必须一起改）：`_ENUMERATION_CANDIDATE_WINDOW`（`serving:2773`）同时
供 plan 窗口（`:736-752`）、read 侧 web 上限（`:762-775`）、web_claim_limit
（`:5870`）→ 改 64 会连带把 read/F1 截断带到 64（顺带把 g5 的嘉立创 pool 54、
则成 62 拉进 F1 窗，免费收益）；**web_claim_limit 必须从该常量解耦**。
不变式：`local_window = cut/2`（1:1 交错）。
成本：local +16 claim（≈+5–6K 字符）、web −16（≈−4–5K），净变化接近持平；
TTFT 必须实测（基数 p50 +6.7s / p95 +32.4s）。
测试 RED：①selector 级——40 local+40 web 枚举 fixture 断言 local #17–32
进 claims（现状 RED）、非枚举仍 3；②plan 级——枚举 max_candidates==64；
③离线包探针断言嘉立创/则成进窗。
验证：四文件 328 + hermetic + B1 focused + replay 7 会话 + 线上双跑。
风险：p95 延迟；web 尾部 48→32 丢 web-only 供应商（differential 观察）；
回滚 = 常量回 48/16。

**A-2（g5：一博/兴森/则成/上达/精诚达在 F1 召回窗外）**

根因（`f1-verify.md`）：嘉立创 54 / 则成 62 / 兴森 70 / 一博 98 = 只有长摘要
命中 score 2 与上百家并列后按 canonical id 截断；上达/精诚达只讲 FPC/柔性
线路板，与 {pcb, 打板} 零词面重合。
修法：扩 C1 声明 `terms[]`（PCB ↔ 印制线路板/线路板/电路板/打样/FPC/柔性板，
展开词降权，仅触发词命中时生效），F1 matcher（`read_isolated:8453-8476`）
加消费者。先量测（离线表证明 8 家包内 GT 进窗，含 A-1 的 64 窗），否则一博
（98）走 B/D 补采或承认缺口。**触及 C1 批 0 文件所有权 → 排 C1 之后**。
测试：扩 F1 单测矩阵 + 反例（"机器视觉 vs 机器人"防误召）；RED=当前 2/8。

### B. 枚举覆盖-资料薄（开普勒/九号在 payload 里但被 LLM 跳过）

根因：payload 里开普勒 local#3、九号 local#8，但 claim 文本不含类目证据
（开普勒只有技术路线一句"酒店餐厅商场服务"；九号只有"服务机器人+创新短
交通"）；九号 web 有一条京东"九号飞碟D2酒店送物机器人"但埋在 48 条里。
**首轮类目查询下 `bound_entity_names` 为空，web 证据结构上绑不到 canonical
实体**（`serving:2495-2521` `_matched_bound_entity` 恒 None）。
修法（B-probe = 成员类目探针 + 绑定可见性）：
1. 触发位置：chat 层 read→answer 之间（`canonical_v2_chat.py:1746`…`:1818`；
   `:1813 _merge_prior_web_evidence` 是"改 evidence_set 再答"先例）。
2. 选人：枚举轮 displayed 本地成员中"claim 不覆盖问句类目"的（按 lane 序，
   cap 沿用 `_SUPPLEMENTAL_PROBE_MAX_COMPANIES=6`，`serving:2793`），
   探针词 = 类目词（复用 `_relation_probe_term` 形状 `serving:2981-2989`）。
3. 绑定：命中后生成 `claim_binding.subject_id=成员 canonical id`、
   `predicate=category_membership_evidence` 的证据项；**顺带修 D0.5 §0 的
   两个旁路**（探针视图不过 subject-consistency 门、不落 lane 计数、
   `_merged_results` 不进 claim）→ 要么过门要么显式豁免，且必须进 claim 集。
4. 证据已在公开源找到：开普勒"可应用于酒店、餐厅、商场等场所"（经济观察网
   2025-05-30）；九号"飞碟 D2 酒店送物机器人/方糖配送机器人"（京东列表）。
数据补采最小范围（若走本地）：仅开普勒、九号 2 家，
`technology_route_summary`/`product_description` 的"酒店场景+具体产品"一句，
来源=上述公开报道，写入=manual recall 侧车（需同一套可见性规则，见 D-2）。
测试 RED：现状枚举首轮根本不发探针（`material_parts` 为空）。
风险：探针网络延迟（≤6 条/轮）；同名误绑（沿用 `_web_identity_forms`/domain
护栏）；探针视图入库污染门统计 → 显式标记 lane/source。

### C. 收窄归因（g2-t2）

根因三层：①t2 池=t1 提交集，`_commit_prose_scope` 只提交 `selected ∪ 正文
提及`（`knowledge_answer.py:2533-2555`，F2）→ t1 没点名的成员 t2 结构性
不可达（B2-a 未做）；②t2 claim 文本不含地址（`serving:4207-4220` 只渲染
简介/技术路线），确定性地理结论不进 claim；③提示词禁止由名称推断总部
（`serving:5153-5154`）。
修法：
- **C-1（推荐，证据层，最小）**：`_semantic_text` 公司分支加
  `注册地址：…`/`注册地：…`（值取 snippet 里的 `registered_address`、
  `geography.name`）；调用点（`serving:5901`）传"本轮含 geography 槽或
  关系帧"开关，**只在收窄/地域类轮次生效**（判据已有：`serving:2759-2765`/
  `read:4026-4036`）。
- C-2（条件性，提示词）：若 C-1 实测不够，加"对'某地企业有哪些'的筛选，
  已给出注册地址/注册地的成员应点名，表述为注册地"；提示词改动全查询生效，
  必须有 replay 门 + differential，版本号 `canonical-v2-prose-v16` bump。
- C-3（不采纳，留 residual）：per-member verdict 块 + coverage 句。
测试：三态 fixture（深圳/非深圳/null）断言地址行只在开关开时出现；关闭时
claim 文本与今日逐字节一致。
风险：全局公司类措辞漂移（先 differential G1/G4/G8/G10/G17）；
g2-t2 零冗余（安赛步不可召回 ⇒ 其余 5 家必须两次都点名）。

### D. 立场数据（g2-t3）

根因：t3 是 `product_capability` 关系帧（`serving:2943-2947`，探针词=机械臂+
按电梯），但普渡证据全是"梯控模块/乘梯/IoT"，提示词 `serving:5148-5152`
区分"机械臂直接操作物理控件"与"楼宇/物联网接口集成" → 答"无法确认"→
踩 `stance_forbid`。**GT 能力在公开源里有**：闪电匣Arm"搭载 7 自由度仿生
双臂+11 自由度灵巧手，通过机械臂直接操作电梯按钮…无需梯控改造"（新华网广东
2026-06-05；深圳新闻网 2025-04-01；百度百科"闪电匣Arm"）。
修法：
- **D-1（web 补全，推荐先做）**：让 t3 的成员探针**真正落到 claim**
  （命中绑定成员 canonical id；先例 `serving:3846-3852`），与 B-probe 共用
  可见性修复。RED 探针：sealed pack 只读副本重放 t3，断言 claims 出现
  "普渡+机械臂+按电梯"同句绑定（当前必 RED）。
- **D-2（本地补采，保险）**：manual recall 侧车加 **1 条**普渡证据点
  （canonical_ref=run14 普渡 id；内容含 `name`+`technology_route_summary`
  同句绑定闪电匣Arm；来源记新华网/深圳新闻网）。若探针验证证明侧车点在 t3
  形态被 48/16 窗吃掉（很可能），加最小可见性规则：被显示成员绑定的 manual
  证据在枚举/关系轮进入 claim 集（`serving:5824-5834` 同族先例）。
测试：探针级 RED→GREEN + 反例（云迹的探针证据不得进 claim）+
`stance_forbid` 两正则在 fixture 上不命中。
风险：侧车 `canonical_ref` 与 release 绑定，G2 审计已证每次 release 全量 id
漂移 → 换包必须重绑（并入 ADR/C6）；claim 必须"产品+动作"同句。

## 2. 落地顺序

1. **S1 = C-1**（serving 一函数+一调用点，最小、无提示词改动）。
2. **S2 = A-1**（两常量 + 单测）→ 与 S1 合并才是 g2-t2 完整前置。
3. **S3 = B-probe + 探针可见性**（serving + chat:1813-1836 挂点）→ 同时是
   A-g2 溢出与 D-1 的地基，权重最高。
4. **S4 = D-1**（复用 S3 可见性；不够再 D-2）。
5. **S5 = A-2**（等 C1 批 0 提交后动声明文件与 F1 matcher）。
6. **S6 = 验收双跑** + replay 门（每片：四文件 328 / hermetic / B1 focused /
   admin 16 / replay 7 会话；碰提示词的片加 differential）。

## 3. 与验收目标的对应

| 目标 | 现在 | 达标所需 |
|---|---|---|
| g2-t1 实体 5/5 + 关键点 ≥8/10 | 3/5、3–6/10 | B-probe（补开普勒/九号）+ 更宽展示；安赛步不可召回（8/10 无安赛步可达，但需模型稳定点名 ≥8 家） |
| g2-t2 pool ≥5/6 | 1–2/6 | A-1（锐曼#26 进窗）+ C-1（地址证据）+ B-probe（t1 点名广度）；零冗余 |
| g2-t3 立场一致 | 实体过、立场 RED | D-1 或 D-2 |
| g5-t1 3/3 | r3 2/3、r4 0/3 | A-1（窗 64：嘉立创54/则成62 进）+ A-2（一博 98/FPC）+ 深南电路（lexical 41 → 需 cut≥82 或证据补） |
| g5-t2 ≥9/12 | 1/12 | A-1+A-2（包内 8 家全进）+ C-1 + 1 个包外项；全切片最难项 |

## 4. 待裁项（产品级）与主上下文裁定（2026-09-11）

1. 枚举展示语义：保持 16+coverage 句 vs 放宽 32。
   **裁定：放宽到 32（枚举类；web 同步；cut 64）。** 依据=用户"在库内穷尽"
   + 免费拉进嘉立创/则成。TTFT 必须实测并记录。
2. coverage 句是否点名被截断成员：**裁定=维持只报数（现状）**；点名等于
   把召回命中当断言，精度风险高。若验收证明其为瓶颈再复议。
3. 注册地址能否作为"总部在深圳"依据：**裁定=可以，但表述为"注册地在
   深圳"**（如实措辞，不冒充总部判定）。
4. g5-t2 ≥9/12 是否维持：**裁定=先维持**。若 A-1+A-2 落地后天花板
   可证明为 8/12（三家包外 + FPC 词族），带证据上报用户再议。
5. 探针预算：**裁定=允许 ≤6 条/轮的成员 web 探针**（枚举/收窄/关系轮），
   与用户"web 作为补全"定位一致；延迟入 TTFT 实测。

## 5. 设计者自报的最大不确定（切片第一动作）

"补证据 → 模型就点名"的因果链：prose LLM 不可离线重放且双跑方差大
（同代码 g2-t1 r3 6/10 vs r4 3/10），系统提示同时有"总部必须明写""只答有
直接依据的主体""列表≤12"三条约束。
**前置实验（S0）**：固定 after-F4 payload，注入/不注入"注册地址：深圳市…"
两版，对同一 LLM 后端各采样 N≥5，统计 pool 点名率（目标从 ~1/6 → ≥5/6）。
若失败 → 退回确定性兜底（`required_member_ids` 接线 + 答案侧完备性自检；
`knowledge_read.py:4285-4295` per-member 分支目前是死代码），需重新规划。
次要不确定：manual/vector 证据在 t3 形态能否活过 48/16 窗（S3/S4 探针验证）。

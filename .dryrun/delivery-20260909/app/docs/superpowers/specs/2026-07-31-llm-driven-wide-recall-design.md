# LLM 驱动的宽召回架构 + 数据端长期升级路线 — 设计文档

- 日期：2026-07-31
- 状态：设计已获用户确认（拆分确定性预筛、含缺口自查单轮循环的调用预算）
- 适用范围：Canonical V2 serving 层（本轮实施）+ 数据端长期工程（路线图）

## 1. 背景与问题定义

PoC 上线在即，核心标尺为**查全、查准、好的呈现**。本轮用户实测暴露的根本问题是：
证据链被用作"准入审判"——确定性闸门（claim 绑定即生死、material part 硬判决、候选窗口/claim
上限/unsupported 降级）在 LLM 看到内容之前就把有效证据杀掉，直接造成查全率低与"未能确认"抖动。
LLM 在拿到证据时的相关性判断力（prose-v8）已经验证可用，因此方向是：

- **查全靠"宽召回 + 理解式筛选"，不靠"严闸门"。** 证据链从准入审判退居为溯源记录
  （citation / 查看依据）。
- **需要理解内容的判断全部交给 LLM**（快模型、批量、限时、fail-open）。
- **确定性代码只保留不需要理解内容的护栏**：安全门（黄赌毒类 lawful guidance）、
  完整性/哈希/身份绑定（fail-closed）、预算墙、注入与泄漏审计、会话机械记账。
- **TTFT 用并行度与批量换**：I/O 激进并行；LLM 调用只在相互独立时并行，全部批量、全部硬超时。

同时本轮必须解决 **882/1439 条教授记录被必填字段 gate 拒掉**的问题（王学谦类记录不可用）。

## 2. 查询处理路径（本轮实施）

```
query ─┬─ L0 快模型: 查询理解+改写 (~0.3-0.5s)
       ├─ L0 本地 lanes: exact/structured/lexical/vector (~0.2-1s)
       └─ L0 web 首遍: 确定性视图 bocha+serper (~2-3s, 不等改写)
             │ ≈3s 汇合
       ├─ L1 快模型批量判定: 本地+web 候选相关性 (≤10条/批, 并发 ~1s)
       ├─ L1 快模型: 补充检索规划 (person/relation/theme 探针有无 + query 生成 ~0.5s)
       ├─ L1 快模型: fetch 选页 (~0.5s)
       └─ L0' web 二遍: LLM 改写视图 (与 L1 并行 ~2-3s)
             │ ≈+2-3s
       ├─ L2 探针执行 ≤12 并发 bocha+serper + 页面抓取 ≤5 并发 (~3s)
       └─ L2' 快模型批量验收 + 实体绑定 (到一批判一批 ~1s)
             │ ≈+3s
       ├─ L2.5 快模型: fetch 正文事实提取 + 归因 (1-2 批, 替代全部抽取规则)
       ├─ L2.5 快模型: 缺口自查 → ≤2 条定向补查 (单轮, 富答案零成本跳过)
             │
       └─ L3 快模型: 答案选择 + prose-v8 生成 (~8-15s)
             ↓
        answer（证据链仅作溯源/引用）
```

关键点：

- 改写不串在 lane 前：首遍先发确定性视图，LLM 视图作为二遍与 L1 并行，重写零成本挂关键路径。
- 判定一律批量（≤10 条/次调用），多批并发；验收"到一批判一批"流水化。
- 并行纪律：I/O 激进并行；LLM 调用只在相互独立时并行（改写 ∥ 首遍、相关性批次 ∥ fetch），
  有依赖的不并行（选择 → 生成天然串行）。

## 3. LLM 调用预算（6-8 次/轮）

1. 查询改写（1）：意图分解 + ≤3 关键词视图。
2. 相关性判定（1-2 批）：本地+web 候选与问题/实体的相关性，替代
   `_web_claim_semantics`/`_relation_evidence_match`/`_person_evidence_match`/
   `_covers_person_criteria`/`_theme_evidence_covers` 全部规则族。
3. 探针规划+验收（1-2 批）：person/relation/theme 探针有无、query 生成、结果验收绑定。
4. fetch 正文事实提取（1-2 批）：LLM 读抓取正文，按问题抽取事实+归因
   （开普勒类"证据在正文里但绑定不出来"的根治点）。范围限定为 web/探针内容；
   本地 canonical 投影本身已是结构化文本，不重复提取。
5. 缺口自查（1）：生成前自问已见证据覆盖哪些子意图、还缺什么；缺则产出 ≤2 条定向补查
   query，**只补一轮**；证据充足时零成本跳过。
6. 答案选择+生成（1-2）：claim/实体取舍 + prose-v8 生成。

预算纪律：全部批量、全部硬超时（1.5-2s）、全部 fail-open（判不动按确定性保底路径放行并带
web 归因）；端点 token bucket 限入 + 429 退避抖动。补查循环限定一轮（第二轮边际收益低、
方差大，多轮 agentic 检索列入路线图评估）。

TTFT 估算：富答案 ≈18-23s（自查跳过）；触发补查 ≈25-30s。

## 4. 确定性预筛拆除与 fail-open / fail-closed 语义

- 检索侧不再以 claim 绑定/谓词抽取作为内容生死线；web/本地结果带溯源信息（URL、authority、
  observed_at、snapshot）进入 LLM 判定面。
- `unsupported_material_claim` 硬降级移除；sufficiency 降为覆盖度披露
  （enumeration_coverage 自然语言交代），不再产生与答案矛盾的 gap 句。
- fail-open：任何 LLM 判定失败（超时/异常/格式错）→ 确定性保底路径放行（带 web 归因），
  永不因判定失败而拒答。
- fail-closed 仅限护栏：安全门、完整性/哈希/身份绑定、注入与泄漏审计、预算墙。

## 5. 分层 web fetch

- **T0 直连增强**：HTTP2 + 真实 UA/Referer/locale + 正文密度抽取（段落/链接密度），~0.3s。
- **T1 无头 Chromium 兜底**：Playwright（项目基线已有依赖），单例浏览器进程 + 页面池
  （≤5 并发、单页 5s 硬超时、共享 context 复用指纹），JS 渲染 + 正文选择器等待
  （domcontentloaded，不等 networkidle）。触发条件：T0 失败、文本量低于阈值、
  JS-shell 特征、403/429/验证页特征。
- **防封（合规边界内）**：真实指纹（UA/视口/时区/locale）、每域名令牌桶限速、尊重 robots
  与 Retry-After、失败退避；不硬刚登录墙，强风控站点靠信息源多样性
  （双 provider + 改写视图召回的替代源）覆盖。
- 任何一层失败保留原 snippet（fail-open）。

## 6. 882 条教授记录解决方案（本轮实施）

- **一次性 LLM 辅助迁移**：批量可用性判定——name+institution 存在即放行；department 等
  缺失字段降级为质量信号（quality_signals / limitation），不再整批排除。王学谦类高价值记录
  用 web search 回填缺失字段，回填值带 source assertion 溯源。
- **运行时 gate 新规则**：name+institution 存在即入 release；字段完整度进 quality_signals，
  薄画像由答案层做诚实限定。消除 882/1439≈61% 的查全黑洞。
- **验收**：王学谦可答（live）；882 复核报告（放行/回填/仍拒的分布与理由）；重放相关回放题。
- **生效路径**：882 记录进入 release 需要一次候选重建（含更新后的 gate 策略）+ pack 重新生成；
  重建在隔离环境进行，验收通过前不切线上 release。

## 7. 数据端长期升级（路线图，非本轮实施）

1. 持续采集升级：爬取与清洗管线优化（新数据源、增量更新、字段补齐：公司官网/场景词/
   key_personnel/人物关系）。
2. 画像富化工程：定期对库内实体做 web 富化回填（根治开普勒类"画像无场景词"）。
3. web 抖动工程化：provider token bucket + 429 退避抖动 + 探针命中率可观测。
4. pack 生命周期：build/promote 自动产 pack、manifest sha 信任根、relationships.json gzip。
5. 预存失败清理：internal_reference×10、review-workspace×73 等独立 slice；
   多轮 agentic 检索评估（单轮补查稳定后）。

## 8. 测试与验收

- hermetic 测试族：每个新判定点（改写/相关性/探针/提取/自查/分层 fetch/gate 降级）
  RED→GREEN；全部 LLM 判定可桩化（镜像 `_timeout_prose_renderer` 约定）；fail-open 语义
  有契约测试；规则族退役有防回归测试。
- live 关键场景：酒店三连、早稻田、丁文伯跨话题、王学谦、开普勒（富化后）、概念题簇。
- 全量 Excel 回放（独立 workers=4 + 单 session 跨话题）：目标 25/25 ok、degenerate 0、
  KEY 硬失败归零；TTFT 抽样 ≤30s。
- 回归门禁：miroflow canonical_v2 套件（排除 12 个 HEAD 预存失败）+ admin canonical_v2
  套件全绿；ruff/pyright 0 错。

## 9. 风险与对策

- LLM 判定静默失败/抖动 → 批量 + 硬超时 + fail-open 带归因 + 生成侧再筛；端点 token bucket
  与 429 退避。
- 正文提取幻觉风险 → 提取输出必须带原文定位（URL+段落索引），prose 侧审计
  （`_prose_contains_structured_only_value` 扩展为事实-归因对齐检查）。
- 无头浏览器成本/稳定性 → 页面池上限、单页硬超时、T0 优先（多数页面不进 T1）。
- 882 回填质量 → 回填值强制 source assertion；低置信不回填、保持质量信号。

## 10. 不做的事（YAGNI）

- 多轮 agentic 检索循环（>1 轮）、登录墙/强风控站点硬解、新数据源接入、
  pack 生命周期自动化、预存失败清理、embedding 模型更换。均入路线图或明确排除。

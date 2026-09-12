# AQ-S7 验证文档 — 词典驱动实体链接层（检索 v2 第一块）

日期：2026-09-12。切片：close-workbook-gaps / AQ-S7（retrieval review part 2 §6/§10 派出，
change-log 2026-09-12 末两条）。工作树：`.worktrees/canonical-v2-s11-consolidation`，
分支 `codex/canonical-v2-s12a-ready`。

## 1. 问题与裁定

问句式实体查询（`大疆创新主要做什么`）在本地四车道 0 命中：exact 车道末子句要求
`_normalize(整句) ∈ (display_terms ∪ identifier_terms)`
（`knowledge_read_isolated.py:_matches_exact_request`），整句问句永远不可能等于某个
名称词，于是实体轮掉到 web-only 回答。review 裁定的落法（retrieval-review.md :61/:66/:71）：
实体名名形索引（"45k 名形索引原型已验证"）+ 最长匹配 → 实体槽，名形派生
"去法定后缀/城市前缀，最长形优先"。

本切片交付：名形索引建在 read 视图构建处（随缓存生命周期），最长形优先包含匹配 +
重叠 span 去重 + 多实体全交（歧义不合并，留给下游策略）+ 上限封顶；(a) exact 车道加
"名在查询中"子句且全部既有闸门原样保留；(b) 命中实体经既有 preferred_objects 链路出
claim（serving 侧无需新机制，加锁测试）。

## 2. 探针证据链（三探针，均在 sealed run14 pack 上）

### v1（`aq-s7-name-index-probe.json`）—— 三个决定性事实

1. 按 projection 二次校验派生名形，构建 80.1s —— 生产设计改为从
   `_PublicLookupEntry.display_terms` 派生（已是规范化名称面，标识符天然不入）。
2. 裁定公式的两级派生（法定后缀+城市前缀）**得不出锚点名形 大疆创新**：
   `深圳市大疆创新科技有限公司` 只得 {全长, 深圳市大疆创新科技, 大疆创新科技有限公司,
   大疆创新科技} —— 残留"科技"。优必选锚点"长/短形都命中"（优必选科技+优必选）
   同样需要迭代剥离。结论：原型必有第三层"尾部行业词剥离"。
3. 裸奔名形与类目词真实碰撞：`机器人`×23 实体、`送餐机器人`×1、垃圾别名
   `公司`/`深圳`（来自中建五局第三建设（深圳）有限公司别名）—— 类目查询会误链接
   （g2 回归风险），必须有防护。

### v2（`aq-s7-name-index-probe-v2.json`）—— 候选设计全量验证

设计 = display_terms 派生 + 三层剥离（法定后缀一次 → 尾部行业词一次，城市前缀对每个
变体剥一次）+ 三重防护（锚定声明 126 词 / 类目召回 stop phrases / 城市根，全部
casefold+去空格后比对）+ fan-out>4 整形丢弃。结果：**锚点 6/6 全中**（大疆创新、
优必选科技、深南电路、开普勒机器人、普渡科技、普渡），**类目/通用词查询 8/8 全空**
（激光雷达/PCB 打板/酒店送餐机器人/机器人公司/机器人前景/深圳历史/公司注册/送餐机器人品牌）。
构建 1.50s 是在 tracemalloc 开启下测得（探针开销）；峰值内存 29.0MB。

### v3（`aq-s7-name-index-probe-v3.json`）—— 生产实现实测

直接测入库的 `knowledge_read_isolated._build_entity_name_index` /
`_entity_link_entry_indexes`（视图构建内联生产索引）：

- **构建 0.247–0.258s**（3 次无 tracemalloc 重建；视图 66.7s 既有成本内含索引），
  低于 1s 阈值，无需记录-给方案例外；峰值内存 29.0MB（< 100MB）。
- 索引规模：**76,075 形**（四域全覆盖：company 36,941 形标记 / paper 24,524 /
  patent 11,064 / professor 4,199；fan-out 丢弃 46 形；blocklist 224 词）。
  与 review 所述"45k 原型"同量级；差异来源 = 原型按公司域估计（本索引公司形
  36.9k），本实现四域全建（纸/专利/教授只有全长形，不参与剥离）。
- 锚点 6/6、类目 8/8 与 v2 完全一致；匹配时延 8–14ms/查询（exact 车道本身每次请求
  已对 47k 条目逐项评估，此开销同量级以下）。

## 3. 实现（全部在 `knowledge_read_isolated.py` + pack 镜像一处）

- 常量与派生（`knowledge_read_isolated.py:8655` 起 AQ-S7 块）：
  `_ENTITY_LINK_MAX_ENTITIES=8`、`_ENTITY_LINK_MAX_FORM_FANOUT=4`、
  `_ENTITY_LINK_CITY_ROOTS`（37 城，镜像 serving `_CITY_NAMES`，serving 套件有钉）、
  城市前缀/行业词预编译正则、`_ENTITY_LINK_FORM_BLOCKLIST`（锚定词 ∪ stop phrases
  ∪ 城市根±市，构建时一次算好）。
- `_entity_name_forms(domain, display_terms)`：去空格、≥2 字；company 三层剥离
  （`_entity_link_strip_legal_suffix` → `_entity_link_strip_industry_word`，每个变体
  再过 `_entity_link_strip_city_prefix`）；非 company 域只全长（论文题/人名是完整表面，
  城市剥离会发明没人用的形）；防护过滤在入库前。
- `_EntityNameIndex` + `_build_entity_name_index(entries)`（fan-out>4 整形丢弃）+
  `_entity_link_entry_indexes(index, query_text, cap=8)`（规范化+去空格；最长形优先；
  重叠 span 去重；按 span 起点序；cap）。
- `_AuditedLookupView` 加 `name_index` 字段；`_create_audited_lookup_view` 构建时一次
  建好，随视图缓存生命周期共享给所有车道（serving 路径 `documents is view.documents`
  恒成立，经 `_BOUND_DOCUMENT_CACHE` 同一对象）。
- `_entity_link_indexes_for_view(*, view, entries, query_text)`：`entries is
  view.public_entries` 用预建索引；否则对传入 entries 现建（hermetic 路径），
  杜绝位置静默错位。
- `_matches_exact_request(..., name_linked=False)`：末子句改为
  `name_linked or 整句 ∈ searchable_terms`；domain / displayed-set 收窄 /
  excluded terms / protected slots 四道闸门逐字不动。
- 两个 exact 适配器（iso `create_isolated_exact_lookup_adapter`、pack
  `_create_pack_exact_lookup_adapter`）同形改 `enumerate(entries)` 并传
  `name_linked=position in linked`。
- `_EXACT_ADAPTER_VERSION` → `canonical-v2-isolated-exact-lookup-v2`（两处测试文件里的
  v1 字面量是 mock 夹具输入，非断言，未改）。

### 与裁定公式的偏差（明示）

裁定公式写的是"去法定后缀/城市前缀"。**本实现加了第三层"尾部行业词剥离"**
（科技/技术/电子/智能/信息/机器人/实业/控股/集团/国际/发展/网络/通信/生物/医疗/
新能源，每层只剥一次）。依据 = v1 探针反推：两级派生对 `深圳市大疆创新科技有限公司`
永远产出"大疆创新科技"而非锚点名形"大疆创新"；优必选"长/短形都命中"亦需迭代剥离。
行业词表是本切片拍定的最小集合（锚点全中 + 类目全空为验收），原型真实词表未知 ——
若后续锚点失手，先查此表。

另有一处收紧：探针的城市前缀剥离对所有域生效，生产实现只对 company 域（非 company
域只全长）—— v2 证据是在超集索引上取得（类目全空在更多形下成立，收紧后只会更少
误链），锚点全为公司，收紧不影响锚点证据。

## 4. 测试分层（本切片新增 17 个，全绿）

1. **名形派生**（test_knowledge_read_isolated.py，构造场景）：大疆六形等式钉
   （三层剥离全链）；别名同派生（优必选科技→优必选）；<2 字拒绝；非 company 域
   不剥离（paper 题含"公司"不剥、professor 英文空格名 space-strip）。
2. **防护**（构造场景）：锚定词"机器人"/stop phrase"公司"/城市根"深圳"/带市"深圳市"
   永不入索引（先钉"机器人 ∈ 锚定声明"前提）；fan-out 5 家共享别名整形丢弃、
   4 家保留（发明词"测试共振词"/"四渡共振"，不可能撞上任何策展词表）。
3. **匹配器**（构造场景）：最长形优先+重叠去重（全名吃整段，短形不重报）；多实体
   全交（普渡科技 ×2）；span 序封顶（9 品牌取前 8）；无命中/单字查询为空。
4. **反例矩阵**（构造场景 + 真实词形）：三条类目查询（酒店送餐机器人供应商/激光雷达
   /PCB 打板）+ "机器人的发展前景" 全空；携带垃圾别名"机器人"/"深圳"的实体不被类目
   词链接；标识符/哈希永不入索引（credit-code、64 位哈希查询为空）。
5. **闸门保持**（构造场景）：`name_linked=True` 下 domain 闸门、displayed-set 收窄、
   excluded terms、quoted explicit_name 保护槽逐一仍否决；默认参数维持整句语义。
6. **车道级**（pack 夹具，真实构建链）：`test_pack_exact_lane_links_name_embedded_in_question`
   —— "robotics co 怎么样" 在 iso+pack 双适配器一致命中 company-robotics（整句子句
   不可能命中该类文本），无名问句双侧为空；`test_pack_lane_adapters_match_upstream`
   既有等价钉继续通过。
7. **serving (b) 锁**（test_knowledge_serving_isolated.py）：
   `test_selector_prefers_exact_linked_entity_claim_on_question_turn` —— exact 车道项
   在问句轮经 preferred_objects 出 claim（简介+技术路线全文钉），证明 (b) 无需新机制；
   `test_entity_link_city_roots_mirror_serving_city_names` 钉双拷贝城市表一致
   （read 不能 import serving 的既有先例同 marker 钉）。

## 5. 回归数字（本 session 实跑）

- 四门 + scrub（read_isolated / serving_isolated / turn_trace_reporting /
  serving_pack_loader / placeholder_scrub）：**369 passed** = S2d 基线 352 + 本切片
  新增 17，零失败。
- multiturn 文件：**33 passed + 1 failed**；唯一失败
  `test_off_anchor_correction_exhaustion_falls_back_without_refusal` 为存量
  （S2c/S2d 同源同断言）。
- 波及面六文件：**70 passed + 3 failed**；3 个失败全部位于 implementation_closure
  （prose-renderer audit 类，S2b/S5/S2c/S2d 基线同名同数），存量。
- 16 文件 import 触及面（S2d 基线 218+3s+4）：拆两批实跑 = D15 十五文件
  **156 passed + 1 skipped + 4 failed** + internal_reference 合同文件
  **62 passed + 2 skipped** = **218 passed + 3 skipped + 4 failed**，逐数对齐；
  4 个失败（founder_red×1、llm_query_rewrite×2、web_page_fetch×1）与 S2d
  基线同名，且在本切片 HEAD（e3fb8527）上复跑同败（stash 对照）。
- 本切片新增直接触及面 3 文件（fast_boot / knowledge_build_isolated /
  manual_recall_points，S2d 列表外）：**163 passed，0 失败**（1h27m，
  fast_boot 的 Milvus 物化主导）。
- 19 文件聚合跑 3600s 超时（tail 缓冲无输出），以逐文件/小批覆盖取代 ——
  与 S2d 记录的目录级聚合超时同因。
- 复验：主上下文于 15:11 提交本切片（5552d85d）后叠加 perf 提交 e3d7d0b2
  （教授向量显示名索引化，与 AQ-S7 路径无交集）；在 e3d7d0b2 树上重跑
  四门+scrub+multiturn = **402 passed + 1 failed（存量 off_anchor）**，切片
  行为在最新树上保持。
- lint/format：`ruff check` 五文件 0 违规（HEAD 基线同 0）；`ruff format --diff`
  hunk 数与 HEAD 逐一相等（read_isolated 4=4、pack_loader 2=2、serving 测试 46=46、
  pack 测试 0=0、read 测试 1=1），本切片引入的 hunk 已全部手工修齐，存量漂移未碰。

## 6. 保真边界

- exact 车道既有语义：整句命中、protected slots（explicit_name / exact_identifier）
  硬约束、identifier 匹配、候选排序与 `max_candidates` 截断逐字不动；
  `name_linked` 只是末子句的一个析取项。
- 名形索引只读 `display_terms`（规范化名称面）：标识符/哈希/内容词不入索引
  （结构保证 + 测试钉）。
- 类目召回（F1）路径、词汇车道、向量车道、关系车道、内部引用车道逐字不动；
  类目查询在名形索引下仍全空（反例矩阵 + 真实 pack 8/8）。
- serving 回答侧零改动：preferred_objects 链路是既有行为，本切片只加锁测试。
- 无 schema/存储/契约改动；serving pack 格式不变（索引是运行时派生物，不落盘）。

## 7. 遗留风险与观察项

- **行业词表是锚点反推的最小集合**（16 词）：新行业词尾（如"材料""光电"）的公司短形
  剥不出来时表现为该别名缺席锚点 —— 加词即可，防护不变。
- 匹配时延 8–14ms/查询（76k 形全扫描）：当前可接受（exact 车道自身逐条目评估同量级），
  若未来成为热点，升级路径 = 首字分桶或按位扫描（语义保持最长形优先需另议，
  见代码注释的 span 语义）。
- 多实体全交最多 8 个（`_ENTITY_LINK_MAX_ENTITIES`）：超过时按 span 序截断，
  歧义裁决留给下游策略，本层不猜。
- 未做（切片外）：关系穿越是 planner 层改动（`subject_candidates` 在 canonical_v2
  不存在，`bound_entity_ids/names` 只有 web 车道消费）；live 重放门与 18188 部署归
  主上下文窗口（本切片禁网络、不碰 18188）。
- 回滚 = 还原本提交五个文件；索引为运行时派生，无数据迁移。

## 8. 产物

- 探针：`d0-probe/aq_s7_name_index_probe{,_v2,_v3}.py` + 三份 JSON
  （v1 差异分析 / v2 设计验证 / v3 生产实测）。
- 代码+测试：本切片提交（`knowledge_read_isolated.py`、`serving_pack_loader.py`、
  `test_knowledge_read_isolated.py`、`test_knowledge_serving_isolated.py`、
  `test_serving_pack_loader.py`）。
- 本文档：`.agents/runs/close-workbook-gaps/aq-s7-verify.md`。

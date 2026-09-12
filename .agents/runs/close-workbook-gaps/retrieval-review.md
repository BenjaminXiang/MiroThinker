# 检索实现 Review（2026-09-12）——对照"分词 + 关键词/向量/SQL 混合检索"目标

> 范围：canonical-v2 serving 线（s11 worktree）的检索实现：五车道、数据表示、
> 匹配算法、融合与截断。结论 + 差距表 + 建议路线。行号为当前树。

## 0. 总览：五车道 + 桶融合 + 双窗截断

```
query → planner（LLM，选域/视图/车道）
      → read 层五车道并行：
         exact      整句=名称（display/identifier 词）
         structured 仅"限显示集"（narrowing）
         lexical    整句子串 + 枚举双字组兜底（F1 类目）
         vector     Qwen3-8B 4096d → Milvus/持久矩阵 top-k
         web        bocha+serper 双通道 + 缓存 + 抓页 + judge + refine/follow-up
      → reranker：local/web/mixed 分桶，桶内 -raw_score 稳定序（F4），1:1 交错
      → cut=64 截断 → selector claims/displayed（local 32 / web 32）
      → answer（claim 绑定 + 散文合成 + 覆盖句）
```

## 1. 关键词通道（exact + lexical + 类目召回）——**最弱的一环**

| 事实 | 证据 |
|---|---|
| exact = **整句等于名称**：`_normalize(request.query_text) in display_terms` | `knowledge_read_isolated.py:8313` |
| lexical 主路径 = **整句子串**：`any(query_phrase in term for term in content_terms)`（+ 公司名转置匹配） | `:8327-8350` |
| 类目兜底（F1）= 枚举触发词命中时，**字符双字组**匹配（伪词：光雷/器人/店送）+ 字段分层打分 | `:8350+`，术语抽取 `:8493-8524` |
| `content_terms` = 投影**全部字符串标量**（名称/别名/标签/地址/摘要/产品/SHA/决策 ID 不分层） | `:8264-8285` |
| 无任何倒排索引：`_BOUND_DOCUMENT_CACHE` 全量文档驻内存，逐文档 `in` 扫描 | `:8100-8108`、`:8535+` |
| 无分词器：自述"deterministic (no segmenter dependency)"，长 CJK 串一律拆重叠双字组 | `:8493` 注释 |

**实测后果**（本日 trace）：问句式实体查询（`大疆创新主要做什么`/`优必选科技怎么样`）四车道全 0 命中（实体在库！）；组合词查询（`激光雷达`）被拆成 `激光/光雷/雷达` → 激光器与毫米波雷达公司混入（泛化 P2：17/32 离题）；噪声词入表（`我想找` 权重 2）。

## 2. 向量通道——唯一"真索引"

- Qwen3-Embedding-8B，4096d；Milvus Lite（或持久化向量矩阵）top-k；查询嵌入实测 0.04s。
- 问题：`raw_score`（cosine<1.0）与文档车道（一律 1.0）**不可比** → 结构性排后（`knowledge_read_isolated.py:7799` vs `:8756`）；无任何过滤能力（纯语义近邻）。

## 3. SQL/结构化通道——名义存在，实质为零

| 事实 | 证据 |
|---|---|
| `StructuredConstraints` 仅三字段：`displayed_entity_ids / geography / excluded_terms` | `knowledge_read.py:652-655` |
| `structured` 车道 = **只做"文档 ∈ 显示集"约束**，与字段值无关 | `knowledge_read_isolated.py:8320-8329` |
| `geography` 被组装（来自 geography 槽）但 **read/serving 全链零消费者** | 组装 `knowledge_read.py:4798-4803`；grep 无消费者 |
| 库内结构化字段（industry / industry_tags / tech_tags / geography.name / registered_address / quality_status / website 域）**没有任何字段过滤查询路径** | 文档模型 `domain_projection_models.py`；五车道均无字段谓词 |

**含义**："深圳做机器人的公司"这类本可一击命中的结构化查询，如今走模糊子串/双字组路径——召回靠运气（噪声与漏召同源；安赛步/锐曼/嘉立创的 rank 波动即其表现）。

## 4. 融合与截断

- reranker 分桶后 1:1 交错（`knowledge_serving_isolated.py:2578-2588`）；**是位置交错，不是分数融合**。
- 跨通道分数不可比（见 §2）→ 交错比例被人为固定，通道真实质量不参与排序。
- 截断/窗口已分层（枚举 64/32/32；非枚举 8/3/8）；F4 已去随机决胜。
- 无 RRF/无加权融合/无通道配额策略（除固定 1:1）。

## 5. 差距表（对照"分词 + 关键词/向量/SQL 混合"目标）

| 目标能力 | 现状 | 差距 |
|---|---|---|
| **查询分词** | 无（整句匹配 / 字符双字组） | 词典驱动切分：实体名（45k 名形索引原型已验证）+ 概念词（锚定声明词表 + tags 词表）最大匹配，双字组降级为 OOV 兜底 |
| **关键词检索** | 整句子串 + 枚举双字组；无索引/无词权重 | 词项化 + 字段加权（或 FTS5/倒排 + BM25）；字段分层（标签×8/产品×2/摘要×1 已有概念但只用于类目打分） |
| **向量检索** | 有（Milvus + Qwen，快） | 分数可比化（归一/标准分）；可加权融合 |
| **SQL/结构化检索** | 仅显示集约束；geography 死字段 | 结构化字段谓词通道：industry/tech_tags/geography/domain/时间——按字段过滤（干净、快、可解释） |
| **混合融合** | 位置交错（1:1） | 分数归一 + 加权（或 RRF）；通道配额与降级策略 |
| **实体识别/链接** | 无 | 名形索引 + 最长匹配 → 实体槽（exact explicit_name 路径已存在）/ 关系车道 |

## 6. 建议路线（按投入产出排序）

1. **词典驱动查询理解（AQ-S7，已排队）**——查询侧分词落地方式：实体名索引
   （去法定后缀/城市前缀，最长形优先）+ 概念词最大匹配（整词优先，双字组兜底）。
   同时修复：实体问句 0 命中（大疆类）、组合词泄漏（激光雷达类）、噪声词。
   供给方：exact/类目/向量请求/关系探针。零新依赖（库内词典）。
2. **结构化过滤通道（新切片，小-中）**——把库内字段接成 `StructuredConstraints`
   的真实谓词（industry/tech_tags/geography/域），在 structured 车道实现字段过滤；
   与 C1 锚定声明的 tier-S（确定性过滤）天然衔接。"深圳+机器人"直接字段命中。
3. **关键词检索升级（新切片，中）**——用打包侧已有 SQLite 建词项/倒排
   （term→doc，或 FTS5），替代逐文档子串扫描；词项权重 = 字段分层 × 词权
   （复用 F1 的 8/4/2 概念），可选 BM25。可解释、可回归。
4. **融合升级（新切片，中）**——通道分数归一（或直接 RRF 位置融合），替换固定
   1:1 交错；保留 local/web 配额语义的降级路径。
5. **保持不动**：向量通道、F4 稳定序、窗口分层、web 车道与缓存。

**优先顺序**：1 → 2 →（3/4 依验收表现决定）；1+2 可合为「检索 v2」切片族，
以 g2/g5 验收 + 泛化探针（P1/P2）+ 时延（TTFT ≤30s）三套门做验收。

## 7. 附：与已发现缺口的对应

- 大疆/优必选实体问句 → §6.1
- 激光雷达组合词泄漏（泛化 P2）→ §6.1（整词优先）
- 安赛步/锐曼/嘉立创 rank 波动 → §6.2（字段过滤）+ §6.3（词项权重）
- 时延（检索段 11–73s）→ 本 review 不覆盖（离线分解 harness 进行中）；
  §6.2/6.3 预期降低对 web/探针的依赖


---

# 第二部分：本地库设计 ↔ 检索（2026-09-12 补充）

## 8. 本地库（serving pack）的设计事实

| 组件 | 设计 | 关键数字 |
|---|---|---|
| `lookup.sqlite3` | 表 `lookup_document(document_id, release_id, projection_id, canonical_object_id, document_json)`；**唯一索引 (release_id, projection_id, canonical_object_id)——无任何内容索引** | 55,071 行：paper 24,520 / patent 11,504 / company 7,089 / professor 3,958 |
| 文档 = 去规范化投影 JSON | 公司 43 字段：结构化（industry{ref}、industry_tags[]、tech_tags[]、geography{ref}、registered_address、founded_at、registered_capital、website、legal_representative、key_personnel[]、financing_events[]、products[]）；文本（profile_summary、technology_route_summary、product_description、team_description）；审计（evidence[]、field_lineage[]、quality_status、content_sha256…） | 填充率（300 抽样）：结构字段 73–93%；**aliases 仅 4%**；key_personnel 14%；tags 多数单值 |
| `milvus.db` | 向量点按"视图"组织（professor 有 identity/research 两视图；company/paper/patent 默认视图）；**embed 内容是精选字段**（name/aliases/profile/product/tech_route/team[:600]/industry/tech_tags + _supplementary） | 干净、无哈希噪声 |
| `relationships.json`（3.3GB） | 构建权威：candidate / eligibility / relationship / internal-reference projections + 构建请求 + path-eligibility 政策 | B1 直扫与关系车道的数据源 |
| 多值增强 | `_supplementary`（多值断言拓宽搜索面）、`_quality_tier`（anchored/enriched 排序信号） | 设计良好：词法+向量两侧都享用 |
| 封印 | manifest 全文件哈希 + release 绑定 | **不可就地改**：数据修正必须重建包 |

## 9. 库设计 ↔ 检索的错配（核心结论）

| 库的**设计意图** | 检索**实际用法** | 错配后果（已观测） |
|---|---|---|
| 结构化字段供精确筛选 | 全部摊平进 `content_terms` 字符串池（含 SHA/决策 ID），无字段谓词 | "深圳+机器人"无法精确命中；激光雷达泄漏（激光/雷达词面） |
| 多值字段（tags[]/products[]/key_personnel[]）供倒排/面元 | 仅 F1 类目打分用了字段分层（8/4/2），其余场景无消费者 | 多值信息召回价值未兑现（安赛步/锐曼 rank 波动） |
| `aliases` 供实体链接 | 填充率 4%，且**实体链接通道根本不存在** | 问句实体 0 命中（大疆/优必选） |
| 向量侧 embed **精选文本** | 词法侧却是**全字符串池** | 两通道信息面不一致；词法侧有噪声、无权重 |
| `relationships`/eligibility（3.3GB 图：岗位/论文/专利/投资/路径资格） | 仅 B1 直扫与少量关系车道消费 | 关系价值基本未进默认检索 |
| 封印不可就地改 | 任何数据修正走重建包 | 数据侧修复周期长（C6 议题；四家包外公司 backlog） |
| **无内容索引**（SQLite 只有一个大 JSON 表，无 FTS/倒排） | 全量文档驻内存、逐文档子串扫描 | O(N) 扫描是当前"关键词检索"的全部；能力上限低 |

**一句话**：库是按"结构化实体 + 精选向量视图 + 关系权威"设计的；检索却主要把它当成"一堆 JSON 字符串"在扫——结构化字段、多值面元、别名、关系图这四类设计资产都没有被检索兑现。

## 10. 设计层建议（库侧，与 §6 检索侧配对）

1. **读视图侧派生索引（不改包）**：视图构建时生成 ① term→doc 倒排 ② facet 表
   （domain/industry/tags/geography/founded_year/quality_tier）→ 关键词通道与 SQL
   通道直接落在索引上（内存或临时 SQLite）。与 AQ-S7 合为「检索 v2」最小集。
2. **打包侧持久化派生索引**（下一版包）：把倒排+facet 作为**派生文件**随包封印
   （manifest 一并哈希、可校验），检索零扫描、启动即可用；周期更新时一次生成。
3. **字段契约收口**：按 G1 字段契约明确"可检索字段清单"（进词法池/向量/面元/仅展示），
   终结"全字符串扁平池"（含哈希入池的问题顺手解决）。
4. **别名填充**：aliases 4%→目标值（G2 stable_uid + 别名闭包，C1 批 2）。
5. **关系图接线**：把 relationships 的常用关系（company↔patent/professor↔paper 等）
   接入默认检索的过滤/扩展路径（C3/C4 的正题）。
6. 保持：向量精选视图、`_supplementary`、封印一致性、稳定序与窗口分层。

**排序**：1（与 AQ-S7 同批）→ 3（契约收口）→ 2（持久化）→ 4/5（数据与关系侧长期项）。

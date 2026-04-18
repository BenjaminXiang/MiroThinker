# Paper Collection 多源学术数据采集设计（修订稿）

- **状态**: 可执行修订稿
- **日期**: 2026-04-08
- **前置问题**: Professor Pipeline V3 曾长期出现“教授已发布但无论文数据”的系统性缺口
- **修订原因**: 原设计方向正确，但首版把 ORCID、institution registry、DOI enrichment、DBLP、合同扩展、验证体系一次性打包，超出了当前代码和验证口径可承受的范围

## 0. 当前仓库状态

这份修订稿先承认当前现实，再定义下一步怎么走。

当前仓库已经具备的能力：

- `homepage_crawler.py` 已能从主页内容中抽取或推断 `name_en`
- `paper/openalex.py`、`paper/semantic_scholar.py`、`paper/crossref.py` 已有 source-specific client
- `paper/hybrid.py` 已实现 `OpenAlex -> Semantic Scholar -> Crossref` 的 fallback 链路
- `professor/paper_collector.py` 已优先走新 hybrid 路径，而不是默认走旧 `academic_tools`

当前仓库尚未具备的能力：

- ORCID client 与 ORCID 锚定
- 深圳 9 校 OpenAlex institution ID registry
- DOI 级别的 Crossref / Semantic Scholar 元数据补全
- DBLP 条件触发补充
- 真正的多源论文融合模型
- 与上述补全字段对应的 Paper contract / release 承载位

因此，本设计不再假设“完整多源融合”可以一步到位，而是拆成 **Phase A 可交付首期** 与 **Phase B 完整增强**。

## 1. 设计目标

### 1.1 最终目标

最终形态仍保持原始目标不变：

- 论文覆盖率：>80% 教授应有 `top_papers`
- 身份准确率：>95%，且人工抽检不允许出现明显同名误采
- `h_index` / `citation_count` 填充率：>70%

### 1.2 Phase A 首期交付目标

Phase A 的目标不是“做完所有多源增强”，而是先稳定交付可用的 paper-backed professor 数据：

- OpenAlex 成为稳定主路径
- `name_en` 与机构约束进入 author 解析
- OpenAlex 无结果时，保留当前 `Semantic Scholar / Crossref` fallback
- `ready` 教授必须有论文相关信号
- 在真实 E2E 中，把“有 paper-backed professor”从个别 URL 扩展到大多数教授样本

Phase A 验收指标：

- 9 校真实 E2E 抽样中，`paper_count > 0` 的教授比例达到可持续提升，并显著优于当前基线
- `quality_status="ready"` 的教授中，`top_papers=[]` 且 `paper_count/h_index/citation_count` 全空的数量为 0
- 50-100 名教授分层人工抽检中，明显误采数为 0，人工确认精度 ≥95%

## 2. 数据源定位

修订后的数据源角色不是“一次全开”，而是分阶段启用。

| 数据源 | Phase A 角色 | Phase B 角色 | 备注 |
|--------|--------------|--------------|------|
| OpenAlex | 主数据源 | 主数据源 | 作者解析、works、`h_index`、`citation_count`、`paper_count` |
| Semantic Scholar | author-search fallback | DOI 级语义补全 | 当前先作为降级源，后续才承担 `tldr` / graph 补全 |
| Crossref | author-search fallback | DOI 级元数据补全 | 当前不做全量补全，后续只对 top papers 按 DOI enrich |
| ORCID | 不进入 Phase A 主链路 | 身份锚点 | 进入 Phase B 后成为消歧增强器，而不是首期阻塞项 |
| DBLP | 不进入 Phase A | CS 条件补充源 | 仅对 CS 学者补 venue / 论文覆盖，不参与首期指标 |

## 3. 中文教授姓名消歧策略

中文教授消歧是整个设计的核心风险。修订后的策略是先保证保守可用，再逐步增强。

### 3.1 Phase A：保守可用策略

Phase A 不引入 ORCID 作为主路径前提，而采用以下顺序：

1. 从主页抽取或推断 `name_en`
2. 使用深圳高校英文别名表得到机构英文名
3. 走 OpenAlex author search
4. 优先选择“姓名匹配 + 机构匹配”最优候选
5. OpenAlex 无法确认时，降级到当前 hybrid fallback
6. 若仍无稳定论文信号，则不填 `top_papers`，让教授对象保持 `needs_enrichment`

Phase A 的原则是：

- **宁可少采，不误采**
- **不引入新的共享 `quality_status`**
- **identity uncertainty 不直接映射成对外新状态，而是映射为“不给 paper 信号”**

### 3.2 Phase B：ORCID-Anchored Multi-Signal Verification

ORCID 锚定仍然是推荐终态，但它属于增强阶段，而不是首期阻塞项。

Phase B 的身份确认信号如下：

| 信号 | 建议权重 |
|------|----------|
| ORCID 匹配 | 0.40 |
| 机构匹配 | 0.25 |
| 研究方向重叠 | 0.20 |
| email / homepage 线索 | 0.15 |

建议阈值：

- `confidence >= 0.8` 才将 author 视为 verified
- `< 0.8` 不进入 paper-backed ready 路径

## 4. 修订后的采集流水线

### Phase A 流水线

#### Stage A0: `name_en` 与 institution registry 准备

输入：

- `name`
- `institution`
- `homepage/profile_url`

输出：

- `name_en`
- `institution_openalex_id` 或 `None`

规则：

- `name_en` 继续由 homepage crawl 负责，不再额外引入一个脱离现有代码的“虚构 Stage 3.5”
- institution registry 是 **Phase A 的阻塞前置项**；未命中的学校允许降级到机构别名打分，但该学校不能被视为完成

#### Stage A1: OpenAlex 主路径

优先策略：

1. 若有 `institution_openalex_id`，使用 `search=name_en` + `filter=last_known_institutions.id:<id>`
2. 若 registry 未命中，则使用现有 author search，并结合机构别名打分
3. 成功选中 author 后，拉取 works

输出字段：

- `h_index`
- `citation_count`
- `paper_count`
- `top_papers`
- 原始 works 列表（内部）

#### Stage A2: Author-search fallback

仅当 OpenAlex 未确认 author 或未拉到论文时启用：

- Semantic Scholar author search
- Crossref `query.author`

这一步的目标不是“补全所有元数据”，而是尽量为教授建立最低限度的 paper signal。

#### Stage A3: 研究方向反哺

沿用当前策略：

- 用拉到的论文标题/摘要生成研究方向
- 与官网研究方向合并

#### Stage A4: 质量门与发布

发布规则必须与当前质量门保持一致：

- 有稳定 paper signal 才可能进入 `ready`
- paper unresolved 的教授保持 `needs_enrichment`
- 在未扩展共享 contract 前，不新增对外 `low_confidence` 状态

### Phase B 流水线

Phase B 在 Phase A 稳定后再做：

- ORCID identity lookup
- Crossref DOI enrichment
- Semantic Scholar DOI enrichment / batch
- DBLP 条件触发
- 多源 DOI merge
- 扩展 Paper contract 承载 funder / license / graph / tldr 等字段

## 5. 数据融合策略

### 5.1 Phase A：不做完整多源 merge

Phase A 明确不承诺“按论文字段级别融合所有来源”。首期只做：

- 单教授层面选择一个最佳 source result
- 论文 release 层按 DOI / arXiv / title+year 做去重

这样做的原因是：当前 `DiscoveredPaper` 和 `PaperRecord` 模型还没有 funder / license / tldr / reference / fieldsOfStudy 等承载位，先做完整融合只会把数据在 release 时丢掉。

### 5.2 Phase B：DOI-anchored merge

只有在 contract 扩展完成后，才实现真正的多源融合：

1. OpenAlex 作为基础论文对象
2. Crossref 通过 DOI 补 `abstract / funder / license / reference`
3. Semantic Scholar 通过 DOI 补 `tldr / fieldsOfStudy / citation graph`
4. DBLP 仅补无 DOI 的 CS 条目或更规范的 venue

## 6. Contract 与质量门集成

### 6.1 Phase A 不扩共享 Paper contract

当前 `PaperRecord` / `DiscoveredPaper` 可稳定承载的字段只有：

- `title`
- `authors`
- `year`
- `venue`
- `doi`
- `abstract`
- `publication_date`
- `citation_count`
- `summary_zh`

因此，Phase A 只在当前 contract 范围内交付，不引入额外 paper 字段。

### 6.2 Phase B 需要 contract 扩展

进入 Phase B 前，必须先完成 contract 设计，否则以下字段无法安全落地：

- `funder`
- `license`
- `reference`
- `fields_of_study`
- `tldr`
- `oa_status`
- `enrichment_sources`

### 6.3 与教授质量门的映射

当前教授质量门只有：

- `ready`
- `incomplete`
- `shallow_summary`
- `needs_enrichment`

因此修订方案规定：

- Phase A 不增加新的共享 `quality_status`
- identity 未确认、paper 未确认、source 结果冲突时，都不要填充可发布的 paper signal
- 让这些记录自然停留在 `needs_enrichment`

## 7. institution registry 作为阻塞交付物

深圳 9 校 OpenAlex ID 不能继续停留在“待查询”状态。这个表必须在 Phase A 完成前填满。

| 高校 | 中文名 | 建议搜索词 | OpenAlex ID | 状态 |
|------|--------|-----------|-------------|------|
| sustech | 南方科技大学 | Southern University of Science and Technology | 待填 | 阻塞 |
| tsinghua_sigs | 清华大学深圳国际研究生院 | Tsinghua Shenzhen International Graduate School | 待填 | 阻塞 |
| pkusz | 北京大学深圳研究生院 | Peking University Shenzhen Graduate School | 待填 | 阻塞 |
| szu | 深圳大学 | Shenzhen University | 待填 | 阻塞 |
| suat | 深圳理工大学 | Shenzhen University of Technology | 待填 | 阻塞 |
| hitsz | 哈尔滨工业大学（深圳） | Harbin Institute of Technology Shenzhen | 待填 | 阻塞 |
| sysu | 中山大学（深圳） | Sun Yat-sen University | 待填 | 阻塞 |
| sztu | 深圳技术大学 | Shenzhen Technology University | 待填 | 阻塞 |
| cuhksz | 香港中文大学（深圳） | Chinese University of Hong Kong Shenzhen | 待填 | 阻塞 |

附加规则：

- 若深圳校区与母校共用 OpenAlex ID，需在 registry 中显式备注
- 任何校区映射不明确时，该学校只能走 alias scoring fallback，不能被标记为“主路径已完成”

## 8. 速率限制与吞吐估算

原稿里的总调用量估算过于乐观。修订后不再给“10 分钟全量完成”这种未经验证的承诺，而改用预算公式。

### 8.1 Phase A 调用预算

按 9 校 × 100 教授 = 900 教授估算：

- OpenAlex author search：最多 900 次
- OpenAlex works fetch：仅对成功 author 解析的教授调用，最多 900 次
- Semantic Scholar fallback：仅对 OpenAlex unresolved 子集调用
- Crossref fallback：仅对 OpenAlex 与 S2 都 unresolved 的子集调用

因此：

- **OpenAlex 基线预算**：约 1800 次
- **fallback 预算**：取决于 unresolved 比例，不能在设计阶段假设为常数

### 8.2 Phase B 调用预算

Phase B 的 DOI enrichment 必须根据“paper-backed professor 比例 × top_papers_count”计算，不能按学校数粗估。

例如：

- 若 900 名教授中有 400 名进入 paper-backed 集合
- 每人 enrich top 5 papers
- 则仅 Crossref DOI enrichment 就是约 2000 次调用

因此，Phase B 必须在 Phase A 之后，根据真实 hit rate 重算预算。

## 9. 验证方案

### 9.1 自动化验证

必须同时做三类自动化检查：

1. 单元测试
2. source-specific client 测试
3. 真实教授 URL E2E

### 9.2 人工精度审计

以下指标不能只靠系统自证，必须人工抽检：

| 指标 | 样本 | 标准 |
|------|------|------|
| 身份准确率 | 50-100 名教授，覆盖 9 校 | 人工确认 author 是否为同一人 |
| 论文相关性 | 每名教授抽 3 篇 top papers | 论文作者、机构、研究方向不明显冲突 |
| 误采率 | 全样本 | 明显误采数为 0 |

### 9.3 系统验收口径

Phase A 完成必须满足：

- `ready` 教授中无“空 paper signal”
- 9 校真实 E2E 中，多数学校可稳定产出 paper-backed professor
- `docs/教授 URL.md` 抽样 rerun 后，不再依赖单点手工修补才能得到 paper-backed ready 结果

Phase B 完成必须额外满足：

- DOI enrichment 字段在 release 产物中可见且可追溯
- ORCID / OpenAlex / S2 的 identity disagreement 有清晰降级处理

## 10. 实施路线

### P0：先把首期交付面锁死

1. 把这份设计稿修订为分阶段版本
2. 明确 Phase A 不扩 contract
3. 明确 Phase A 不引入新的共享 `quality_status`

### Phase A（2-4 天）：稳定主路径

1. 补齐 9 校 OpenAlex institution registry
2. 固化 `name_en` 解析策略，并补失败回退规则
3. 让 OpenAlex author search 优先使用 institution ID
4. 保留当前 `Semantic Scholar / Crossref` author-search fallback
5. 统一内部 identity confidence 记录方式
6. 真实 E2E + 人工抽检

### Phase B（3-6 天）：补完整增强

7. 实现 ORCID client 与 identity verifier
8. 实现 Crossref DOI enrichment
9. 实现 Semantic Scholar DOI enrichment / batch
10. 实现 DBLP 条件触发
11. 扩展 Paper contract 与 release schema
12. 实现真正的 DOI-anchored merge

## 11. API Key 与凭据策略

不要把“待申请 API Key”写成首期阻塞。

| 服务 | Phase A | Phase B |
|------|---------|---------|
| OpenAlex | 可先无 key 运行，必要时补 key | 建议使用 key 控制预算 |
| Semantic Scholar | 当前 fallback 可无 key 试跑，但稳定性不足 | DOI / batch 增强建议 key |
| Crossref | 无需 key，只需规范 mailto | 继续沿用 |
| ORCID | Phase A 不依赖 | Phase B 直接使用 public API |
| DBLP | Phase A 不启用 | Phase B 按条件启用 |

## 12. 决策摘要

这份修订稿的核心决策只有四条：

1. **首期先做可交付，不追求一次完成完整多源融合**
2. **institution registry 是 Phase A 阻塞项，不再允许停留在“待查询”**
3. **Phase A 不扩共享 contract，不新增共享 `quality_status`**
4. **Phase B 只在 Phase A 的真实 E2E 与人工精度审计稳定后再启动**

如果后续代码实现与本设计冲突，以这四条为优先裁决原则。

# 论文采集清洗智能体 — 产品需求文档

> 本文档定义论文域的特有需求。通用架构、MiroThinker 实现映射、质量维度、更新发布规则见 [共享技术规范](./Data-Agent-Shared-Spec.md)。术语定义见 [术语表](./index.md#术语表)。

## 一、定位

`Paper-Data-Agent` 是一个**教授锚定型**论文采集与清洗智能体，不是开放式全文献抓取器。

它承担两个并列目标：

1. 为用户提供可检索、可理解的论文知识对象
2. 为教授画像提供持续更新的新鲜度信号

换句话说，论文域既是独立数据域，也是教授域的重要输入。

---

## 二、核心目标

### 2.1 一句话目标

从深圳教授 roster 出发，持续构建与这些教授相关联的本地论文知识库，生成可直接用于用户回答的摘要字段，并反向补强教授的研究方向与近期研究画像。

### 2.2 核心成功标准

论文域必须支持：

- 论文语义检索
- 按教授检索论文
- 按时间范围检索论文
- 显式论文标题精确查询
- 论文对教授画像的持续反哺

实现方式见 [共享技术规范 §3](./Data-Agent-Shared-Spec.md#三与当前-mirothinker-实现的映射)。

---

## 三、范围边界

### 3.1 周期性采集范围

周期性论文采集必须从以下输入出发：

- 深圳教授 roster
- 教授 ID
- 姓名 / 英文名
- 所属机构
- 可选 scholar / semantic scholar 标识

这意味着：

- 论文域的离线主流程是“教授锚定型”
- 不是按全网关键词长期扫库
- 不是全城市、全领域、全作者开放式抓取

### 3.2 实时外部 fallback

用户显式给出论文标题时：

- 先查本地论文库
- 本地库命中则直接回答
- 本地库未命中时，允许线上服务走实时外部 fallback

因此：

- 本地论文库不需要承诺覆盖所有全球论文
- 但本地论文库必须尽量覆盖深圳教授相关论文

### 3.3 论文对教授域的责任

论文域必须明确承担对教授域的反哺责任：

- 更新教授 `research_directions`
- 更新教授 `top_papers`
- 参与教授 `profile_summary`
- 支撑“最近在做什么”的回答

---

## 四、数据模型与对外契约

### 4.1 最低发布字段

发布层至少应包含：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 稳定主键，建议 `PAPER-*` |
| `title` | 是 | 原始标题 |
| `title_zh` | 否 | 中文标题 |
| `authors` | 是 | 作者列表 |
| `professor_ids` | 否 | 关联教授 ID 列表 |
| `year` | 是 | 年份 |
| `venue` | 否 | 会议 / 期刊 |
| `doi` | 否 | DOI |
| `arxiv_id` | 否 | Arxiv ID |
| `abstract` | 否 | 原始摘要 |
| `summary_zh` | 是 | 结构化中文摘要 |
| `summary_text` | 是 | 用于 embedding 的完整摘要文本 |
| `keywords` | 否 | 关键词 |
| `citation_count` | 否 | 引用数 |
| `pdf_path` | 否 | PDF 存储引用；具体格式由 `paper-pdf-fulltext-ingest` 约定（见 §5.4.1） |
| `evidence` | 是 | 来源列表 |
| `last_updated` | 是 | 最后更新时间 |

### 4.2 `summary_zh`

> 2026-05-10 更新：本节按 `docs/Paper-Requirement-Review-2026-05-10.md §3.1 P2`
> 重写，从 JSON 4-key 形态改为中文段落形态。

`summary_zh` 是论文域最重要的用户向字段之一。

形态：

- **中文段落 200-400 字**
- 可选包含内部 4-段意涵 markers（如「【方法】… 【结果】…」），但不强制结构化为 JSON
- 由 LLM 从 abstract（或 preprint case 仅 title）生成

要求：

- 面向中文用户可直接阅读
- 尽量保留学术术语准确性
- 避免空泛套话；boilerplate-detection LLM judge 不通过 → `quality_status=rejected`

历史说明：早期 PRD 曾建议 JSON `{what, why, how, result}` 四键对象；该形态从未在代码层落地（实现层始终输出段落）。Paper Review §3.1 P2 锁定为段落形态。

### 4.3 `summary_text`

`summary_text` 在内存 `PaperRecord` 与 release-time output 中等同于 `summary_zh` 内容（不是独立第二份摘要）。

具体语义：

- Postgres 不存独立 `summary_text` 列；只有 `summary_zh` 列
- 内存 `PaperRecord.summary_text` = `summary_zh` 字符串值
- Milvus `paper_chunks` collection embed `summary_text` 即等同 embed `summary_zh`
- admin / chat API 返回 `summary_text` 字段 = `paper.summary_zh` 列值（per Paper Review §3.1 P3 + 已 ship 的 `paper-summary-text-contract-fix` change）

主要用途：

- 语义检索（Milvus embedding 输入）
- 相似论文推荐
- 作为线上回答的压缩上下文

### 4.4 存储要求

论文域独立 PostgreSQL 库 + Milvus collection。详见 [共享技术规范 §6](./Data-Agent-Shared-Spec.md#六物理存储与向量化建议)。

---

## 五、采集与清洗流程

### 5.1 总体流程

```text
深圳教授 roster
  -> 获取每位教授候选论文
  -> 归属判断与去重
  -> 获取 abstract / PDF / 全文
  -> 生成 summary_zh / summary_text / keywords
  -> 写入 paper domain PostgreSQL + Milvus
  -> 反哺教授 research_directions / top_papers / profile_summary
```

### 5.2 候选论文发现

> 2026-05-10 重写：本节按 `docs/Paper-Requirement-Review-2026-05-10.md §3.1 P7`
> + Professor Review Theme 7.1 重写。原版本曾把 Google Scholar / Semantic
> Scholar / DBLP / Arxiv / Web Search 列为候选发现源；当前架构下这些都已
> 降级为 enrichment-only（见 §5.2.2）。

#### 5.2.1 Discovery：仅来自教授页面

候选论文发现 **仅** 从教授 Tier 2 / Tier 3 页面 Publications 区段抽取：

- Tier 2：教授学校官网主页（school official homepage）
- Tier 3：教授个人维护主页 / 课题组主页（personal / lab homepage）
- 抽取由 per-school adapter 解析；未注册 adapter 的学校 → 阻断采集（不爬）

不允许：

- ❌ 全网关键词扫库
- ❌ 从 OpenAlex / Crossref / Semantic Scholar / DBLP / arXiv / Web Search **主动拉取教授作者维度的论文列表**

#### 5.2.2 Enrichment：拿到 title 后的字段补齐

候选论文从 prof 页面发现后，pipeline 异步从外部数据库补齐 metadata。**优先级**：

| 字段 | 优先级 |
|---|---|
| `abstract` | OpenAlex → Crossref → Semantic Scholar → arXiv（first available wins） |
| `citation_count` | OpenAlex（唯一权威） |
| `venue / year` | OpenAlex `publication_date` / `host_venue.name` |
| `authors` | OpenAlex 作者列表（带 ORCID 优先） |
| `doi / arxiv_id` | 跨源 cross-check；不一致 → 写 pipeline_issue |

Enrichment 是 fire-and-forget 异步：discovery + canonical upsert 完成即可视为 seed-run 成功，enrichment 后续在背景任务里跑。详细行为见 OpenSpec change `prof-paper-patent-from-page-flow` `paper-patent-from-prof-page` capability。

#### 5.2.3 chat 实时 fallback（运行时，不入库）

用户在 chat 中给出显式论文标题：

1. 先查本地 paper 表
2. 本地命中 → 返回
3. 本地未命中 → chat 服务实时调 OpenAlex / Crossref，运行时返回 metadata，**不写入本地 paper 表**

此 fallback 与 §5.2.1 的离线 discovery 边界严格隔离。

### 5.3 归属与消歧

> 2026-05-10 简化：原节列出 5 个信号（姓名/机构/scholar id/合作者网络/方向一致性）。
> 新架构下教授页面声明的论文 **完全 trust**——见 Paper Review §3.1 P9 + meta-原则
> "系统是科创检索系统，不对真实性兜底"。

每篇论文的归属判断逻辑：

- **从教授页面发现的论文**：直接归属该教授（confidence=1.0；写 `professor_paper_link.match_reason="prof_page_declaration"`），无需多信号验证。
- **enrichment 后发现同名作者冲突**（如 OpenAlex 返回多位 "Smith, J." 同名作者）：`paper_identity_gate` 介入，仅判定"同人 vs 同名"——不判定论文是否真实存在 / 内容是否真实。

`paper_identity_gate` 阈值：

- confidence ≥ 0.8 → 自动接受
- confidence ∈ [0.5, 0.8) → LLM judge fallback
- confidence < 0.5 → 拒绝 + 写 pipeline_issue (`stage="identity_gate"`)

`professor_ids` 写入原则：

- 教授页面声明 → 置信度 1.0 写入
- enrichment 同名冲突时由 gate 决定
- 不确定时不关联，待 admin 复核

### 5.4 全文与摘要生成

优先级建议如下：

1. 有 PDF 或可抓取全文时，优先基于全文生成摘要
2. 无全文时，可基于 abstract 生成降级摘要
3. 不论全文还是 abstract，都要产出用户可读的 `summary_zh`

### 5.4.1 全文抓取扩展：教授主页 PDF

> 2026-05-13 增。锁定 *来源优先级* 与 *MVP 用途*；下载、存储、解析、
> 失败处置、成本上限等实现细节由 OpenSpec change
> `paper-pdf-fulltext-ingest` 约定。

**现状**：`V011 paper_full_text` + `paper/full_text_fetcher.py` 已能从
PDF URL 抽 abstract / intro 入库（默认源为 arXiv，30 MB 上限，速率限制
3 秒/次）。教授主页直接挂出的 PDF 链接尚未作为发现源。

**全文来源优先级**（高→低）：

1. **教授主页直挂 PDF**：Tier 2 / Tier 3 页面 `<a href="*.pdf">` 或
   `Content-Type: application/pdf` 的链接。最高优先级 —— 作者公开承认的
   代表作，归属信号最强。
2. **enrichment 阶段外部源**：arXiv / OpenAlex / Crossref。`full_text_
   fetcher.py` 现役覆盖此层。
3. **不主动**走 sci-hub 或第三方镜像 —— 法务红线。

**MVP 用途**：`summary_zh` 与 `professor.profile_summary` 生成时全文优于
abstract；Milvus `paper_chunks` 全文重切片 / 引文图谱抽取放 Phase 2 评估。

**存储**：抽取出的结构化文本与 metadata 入 Postgres（沿用 `paper_full_text`，
未来按 design 扩 sections）；原始 PDF 按内容哈希（`pdf_sha256`）持久化到
filesystem 或对象存储；DB 不存 bytea。

**实现细节由 `paper-pdf-fulltext-ingest` 约定**——包括但不限于：

- 解析器选型 —— pdfminer 现役保留；是否换 PyMuPDF / GROBID 由 design 决定
- size / count / total run cap 的具体数值（design 起步建议：单 PDF ≤ 50 MB，
  单 professor ≤ 20 篇，单 run total ≤ 5 GB）
- `pipeline_issue.stage='pdf_fetch'` 新增（与 `data_quality_flag` 区分）
- 触发时机：异步 enrichment 路径，不阻塞 seed trigger

### 5.5 LLM 与 Python 清洗分工

建议分工：

- LLM 负责：
  - 论文内容理解
  - `summary_zh`
  - `keywords`
  - 技术主题归纳
- Python / 离线脚本负责：
  - DOI / arxiv / 标题标准化
  - 时间字段规整
  - 去重
  - 作者列表规范化

### 5.6 降级策略

| 场景 | 处理方式 |
| --- | --- |
| PDF 不可获取 | 基于 abstract 生成摘要 |
| 摘要生成失败 | 重试后标记低质量，进入后续补采 |
| 归属不明确 | 暂不写 `professor_ids`，待验证 |
| 本地库无该显式标题 | 由线上服务走实时外部 fallback |

---

## 六、去重策略

论文去重优先级建议：

1. DOI
2. Arxiv ID
3. 标题高相似度 + 作者高重叠

典型重复场景包括：

- Arxiv 多版本
- 预印本与正式版
- 多平台返回同一论文

原则是：

- 尽量保留最完整、最稳定的一条记录
- 重要标识（DOI、Arxiv ID、venue）尽量合并保留

---

## 七、对教授画像的反哺

### 7.1 `research_directions`

从近 5 年关联论文的：

- 标题
- 摘要
- 关键词

归纳 3-7 个精细研究方向标签。

### 7.2 `top_papers`

根据关联论文生成代表成果列表，建议优先考虑：

- 引用数
- 时间新近性
- 与教授当前方向的代表性

### 7.3 `profile_summary`

论文域必须为教授画像提供：

- 近期研究主题
- 更细粒度的方向描述
- 代表成果支撑

这部分是教授 `profile_summary` 的必选输入，不是可有可无的增强项。

### 7.4 新鲜度信号

教授官网可能几个月甚至几年不更新，而 paper 更快反映：

- 新方向切换
- 新方法路线
- 最近发力主题

因此，论文域是教授画像的持续新鲜度信号源。

---

## 八、质量保证

通用质量维度和验证流程见 [共享技术规范 §7](./Data-Agent-Shared-Spec.md#七数据质量与验证)。

### 8.1 论文域特有校验

1. `title`、`authors`、`year` 不得缺失
2. `summary_zh` 不得缺失
3. `summary_text` 不得缺失
4. DOI / Arxiv ID 格式合法时应被标准化
5. `professor_ids` 存在时，作者归属应合理

### 8.2 重点验证对象

- 同名高风险作者
- 本地摘要质量差的论文
- 教授新近论文
- 代表成果候选论文
- 本地未命中但用户高频显式查询的标题

---

## 九、配置项

> 2026-05-10 标记为 **Phase 2 候选 · 当前不实现**。
>
> 原版本本节列出了 7-key YAML 配置面（`professor_roster_path` / `scholar_enabled` / `semantic_scholar_enabled` / `dblp_enabled` / `arxiv_enabled` / `full_text_preferred` / `explicit_title_realtime_fallback`），但这些 key 在代码中 0 hits（`apps/miroflow-agent/conf/` / `src/` 都没有），且 `*_enabled` 系列 toggle 在 §5.2 重写为 enrichment-only 后语义已变。
>
> Per `docs/Paper-Requirement-Review-2026-05-10.md §3.1 P8`：本节作为
> Phase 2 候选保留；具体 toggle 逻辑随 Theme 7.1 enrichment-only 改变后
> 需重新设计；当前不要求实现。
>
> 历史 YAML 块（仅作参考，**不要据此实现**）：
>
> ```yaml
> # Phase 2 候选，当前不实现
> # paper:
> #   professor_roster_path: "data/professor_roster.jsonl"
> #   scholar_enabled: true             # 旧含义；新架构下 Scholar 不参与 discovery
> #   semantic_scholar_enabled: true    # enrichment-only 语义待重设计
> #   dblp_enabled: true                # 同上
> #   arxiv_enabled: true               # enrichment-only 语义待重设计
> #   full_text_preferred: true         # enrichment 阶段 PDF 抓取偏好
> #   explicit_title_realtime_fallback: true  # 对应 §5.2.3 chat fallback
> ```

---

## 十、更新策略

- 周期性采集：随教授 roster 更新而更新
- 已有关联教授：持续增量补充论文
- 本地摘要：随论文新增或变更重新生成
- 显式标题 fallback：由线上服务实时处理，不要求离线库全覆盖

---

## 十一、验收标准

| 指标 | 要求 | 测试集 | 样本量 | 评判标准 |
| --- | --- | --- | --- | --- |
| 关联论文覆盖 | 已覆盖教授有稳定的本地关联论文集合 | 有 Scholar 的教授子集 | ≥ 30 名 | 人工抽检论文完整度 |
| `summary_zh` 完整率 | ≥ 90% | 全量论文 | 全量 | 自动化校验 |
| `summary_text` 完整率 | ≥ 90% | 全量论文 | 全量 | 自动化校验 |
| 归属准确率 | ≥ 90% | 教授-论文关联标注集 | ≥ 100 篇 | 人工判定作者归属 |
| 去重准确率 | ≥ 95% | 含已知重复对的标注集 | ≥ 100 对 | 人工判定 |
| 教授反哺有效性 | 可见改善教授画像 | 有论文关联的教授子集 | ≥ 30 名 | 人工对比更新前后 |
| 检索效果 | Top-5 相关率 ≥ 85% | Agentic-RAG 测试集中论文类 query | ≥ 50 条 | 人工评估相关性 |

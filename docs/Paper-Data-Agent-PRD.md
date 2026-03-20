# 论文采集清洗智能体 — 产品需求文档

## 一、定位与双重角色

论文采集智能体（Paper-Data-Agent）独立于教授采集智能体运行，但通过教授 ID 与教授库紧密关联。它服务于两个目标：

**角色一：面向用户的论文查询与解读。** 下游 RAG 智能体的论文模块需要一个完整的论文库来支撑用户的论文检索需求——"最近有什么关于人形机器人运动控制的论文""丁文伯教授最近发了什么论文"。每篇论文需要提供中文全文深度摘要，让非学术背景的用户也能理解论文在做什么。

**角色二：教授画像的关键数据源。** 教授官网上的研究方向描述通常过于笼统（"人工智能""计算机科学"），无法支撑精准的语义检索。论文是推断教授真实研究方向的最可靠数据源——从近 5 年论文的关键词中聚类，可以得到"触觉传感器设计""柔性电子皮肤""力控操作学习"这样的精细标签。这些标签直接反哺教授库的 `research_directions` 字段和 `profile_summary` 生成。

---

## 二、论文数据模型

### 2.1 字段定义

| 字段 | 类型 | 必填 | 来源 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | TEXT | 是 | 系统生成 | 唯一标识。优先用 DOI 哈希，无则用 arxiv_id，均无则用标题哈希 |
| `title` | TEXT | 是 | 数据源 | 英文原标题 |
| `title_zh` | TEXT | 否 | LLM 翻译 | 中文翻译标题 |
| `authors` | JSONB | 是 | 数据源 | 作者列表 `[{name, institution, is_local_prof}]` |
| `professor_ids` | TEXT[] | 否 | 关联匹配 | 关联的本库教授 ID |
| `year` | INTEGER | 是 | 数据源 | 发表年份 |
| `venue` | TEXT | 否 | 数据源 | 发表会议/期刊名称 |
| `arxiv_id` | TEXT | 否 | Arxiv | Arxiv 论文 ID（不含版本号） |
| `arxiv_version` | TEXT | 否 | Arxiv | 当前版本号（如 v3） |
| `doi` | TEXT | 否 | 数据源 | DOI 标识 |
| `abstract` | TEXT | 否 | 数据源 | 英文原始摘要 |
| `summary_zh` | JSONB | **是** | LLM 生成 | 中文全文深度摘要，四段式结构 |
| `summary_text` | TEXT | **是** | 拼接生成 | 摘要四段拼接的完整文本，用于 embedding |
| `summary_type` | TEXT | 是 | 系统标记 | `full_text` / `abstract_based` / `pending` |
| `keywords` | TEXT[] | 否 | LLM 提取 | 关键词标签，用于教授研究方向聚类 |
| `pdf_path` | TEXT | 否 | 系统记录 | PDF 本地存储路径 |
| `full_text` | TEXT | 否 | VLM 解析 | 解析后的论文全文文本 |
| `citation_count` | INTEGER | 否 | 学术平台 | 引用数 |
| `summary_embedding` | VECTOR | **是** | Embedding 模型（可配置） | 摘要向量，语义检索用 |
| `status` | TEXT | 是 | 系统记录 | 处理状态 |
| `last_updated` | TIMESTAMP | 是 | 系统记录 | 最后更新时间 |

### 2.2 全文摘要格式（what/why/how/result）

每篇论文的 `summary_zh` 采用四段式结构化格式：

```json
{
  "what": "这篇论文提出了一种基于触觉反馈的机器人灵巧操作框架...",
  "why":  "现有方法依赖视觉反馈，在遮挡和透明物体场景下失效...",
  "how":  "通过多模态触觉传感器阵列采集接触力分布，结合强化学习...",
  "result": "在真实机器人上验证，抓取成功率达到 95.3%，比视觉基线提升 12.7%..."
}
```

- **what**：这篇论文做了什么（1-2 句）
- **why**：为什么重要 / 解决了什么问题（1-2 句）
- **how**：核心方法是什么（2-3 句）
- **result**：效果如何（1-2 句，含关键数字）

`summary_text` 为四段拼接后的完整文本，格式为：`【做了什么】{what}【为什么重要】{why}【怎么做的】{how}【效果如何】{result}`，用于生成 embedding 向量。

### 2.3 处理状态

论文的处理经过多个步骤，需要记录状态以支持断点续传：

```
discovered → downloading → downloaded → parsing → parsed → summarizing → completed
                ↓              ↓            ↓
           download_failed  parse_failed  summary_failed
```

---

## 三、采集管道设计

### 3.1 数据源

| 数据源 | 覆盖范围 | 获取方式 | 说明 |
| --- | --- | --- | --- |
| Arxiv | 预印本，CS/物理/数学为主 | 免费 API + PDF 下载 | **主要数据源**，覆盖绝大多数计算机科学论文 |
| Semantic Scholar | 覆盖广，含会议/期刊 | 免费 API（100 req/5min） | 论文元数据 + 引用数 + 作者 ID |
| DBLP | CS 方向最全 | 免费 API | 补充会议/期刊论文列表 |
| 百度学术 / 知网 | 中文论文 | 爬取 / API | 中文论文源 |

**数据源融合**：以 Semantic Scholar 的作者 ID 为锚点，跨平台关联同一教授的论文。Arxiv 提供 PDF 和 LaTeX 源码，DBLP 补充元数据。

### 3.2 采集流程

```
输入: 教授 ID 列表 (来自 Professor-Data-Agent Phase 1)

for each 教授:
  1. 通过 Semantic Scholar API 查询作者 → 获取论文列表
     (用姓名+机构匹配作者 ID，处理同名消歧)
  2. 通过 Arxiv API 补充预印本论文
  3. 通过 DBLP API 补充会议/期刊论文
  4. 合并去重 → 得到该教授的完整论文列表
  5. for each 论文:
     a. 下载 PDF (Arxiv 可直接下载，其他需检查可用性)
     b. VLM 解析 PDF → 提取全文文本 (统一使用 Marker 类方案)
     c. LLM 生成四段式中文摘要 (what/why/how/result)
     d. LLM 提取关键词标签
     e. 写入 papers.jsonl
  6. 保存 PDF 到 pdfs/ 目录
```

### 3.3 PDF 解析方案

统一使用 VLM（视觉语言模型）解析方案，如 Marker：

- **输入**：论文 PDF 文件
- **输出**：Markdown 格式文本，保留章节结构、公式、表格
- **优势**：无需针对不同 PDF 格式编写规则，VLM 统一处理双栏排版、数学公式、图表
- **LLM 部署**：本地部署，不受 API 成本限制

### 3.4 降级策略

| 场景 | 降级方案 |
| --- | --- |
| PDF 下载失败 | 重试 3 次 → 标记 `status=download_failed`，下次补采 |
| PDF 解析失败（加密/扫描版） | 标记 `status=parse_failed`，降级为仅用 abstract 生成摘要 |
| LLM 摘要生成失败 | 重试 2 次 → 标记 `status=summary_failed` |
| 无法获取全文 | 基于 abstract 生成摘要，`summary_type=abstract_based` |

---

## 四、论文去重策略

### 4.1 Arxiv 多版本

同一 arxiv_id 的多个版本（v1, v2, v3）只保留最新版本。去版本号后的 arxiv_id 作为论文标识的一部分。

### 4.2 预印本与正式版

当预印本被正式发表时：
- 通过 DOI 匹配 → 合并为一条记录
- 保留正式版信息（venue、publish_date），同时记录预印本日期

### 4.3 跨平台重复

同一论文可能从 Semantic Scholar、Arxiv、DBLP 多个源返回：
- 优先按 DOI 去重
- 无 DOI 时按标题相似度 > 0.95 且作者重叠 > 80% 判定为同一论文

---

## 五、论文反哺教授画像

论文采集完成后，从论文数据中提取信息反哺教授库：

### 5.1 研究方向精细化

**输入**：教授近 5 年所有论文的 `keywords` 列表

**处理**：由 LLM 从关键词集合中聚类归纳出 3-7 个精细研究方向标签

**输出**：写入教授记录的 `research_directions` 字段

**示例**：
- 论文关键词池：`[tactile sensing, grasping, robotic manipulation, flexible electronics, MEMS, force control, reinforcement learning, sim-to-real]`
- 归纳后的方向标签：`["触觉传感器设计", "柔性电子皮肤", "机器人灵巧操作", "力控强化学习"]`

### 5.2 学术指标更新

- `recent_paper_count`：从论文库中按 `professor_ids` 统计近 5 年论文数
- `top_papers`：按引用数排序取 Top-3

---

## 六、验收标准

### 6.1 数据完整度

| 指标 | 要求 |
| --- | --- |
| 每位教授平均论文数 | ≥ 10 篇（剔除非学术岗教师） |
| `summary_zh` 完成率 | ≥ 90% 的论文有全文摘要 |
| PDF 下载成功率 | ≥ 80%（Arxiv 论文 ≥ 95%） |
| 全文解析成功率 | ≥ 85%（已下载的 PDF 中） |

### 6.2 摘要质量

| 指标 | 要求 |
| --- | --- |
| 四段结构完整性 | 100% 的摘要包含 what/why/how/result 四段 |
| 通俗可读性 | 人工抽样评估 ≥ 4.0/5.0（非学术背景评估者） |
| 内容准确性 | 人工抽样核对摘要与论文内容一致性 ≥ 90% |

### 6.3 去重准确性

| 指标 | 要求 |
| --- | --- |
| 无重复论文 | 同一论文不存在两条记录 |
| 无误删 | 不将不同论文误判为重复 |

### 6.4 RAG 端到端验证

| 测试查询 | 验收标准 |
| --- | --- |
| "最近有什么关于人形机器人运动控制的新论文" | Top-5 结果语义相关率 ≥ 85% |
| "丁文伯教授最近发了什么论文" | 返回论文列表与 Scholar 一致 |
| "2025 年以来的具身智能论文" | 时间筛选结果正确 |

### 6.5 采集性能

| 指标 | 要求 |
| --- | --- |
| 全量首次采集 | 25 万篇论文在 7 天内完成（含 PDF 下载和摘要生成） |
| 月度增量更新 | 48 小时内完成 |

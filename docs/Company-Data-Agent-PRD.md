# 企业数据采集智能体 — 产品需求文档

## 一、为什么需要独立的企业数据采集智能体

测试集分析表明，>50% 的查询需要企业关联数据（Q1 教授关联企业、Q4 企业信息查询、Q8/Q10 企业详情、Q2/Q5/Q14-Q16 行业知识问答）。教授数据中的 `company_roles` 字段依赖企业基础数据存在——没有企业库，教授关联企业就是无根之木。

因此，**企业数据采集必须先于教授数据采集完成（Phase 0）**，确保教授 Agent 在采集时能通过企名片 API 关联企业信息。

---

## 二、核心目标

**一句话目标：** 构建深圳科创企业全景数据库，为教授关联企业、专利关联企业、行业知识问答提供数据基础。

**约束一：数据是给 RAG 和下游 Agent 用的。** 企业数据既要支持向量语义检索（"做手术机器人的公司"），也要支持结构化筛选（注册资本、融资轮次），还要作为教授 `company_roles` 的关联锚点。

**约束二：数据来源以全深圳企业列表为主干，Web Crawling 为主要充实手段。** 全深圳企业列表提供基础骨架（企业名称、统一社会信用代码），Web Crawling 从企业官网、PR 稿件、行业报告中提取高价值描述信息。

---

## 三、数据来源

| 数据源 | 角色 | 可获取内容 | 获取方式 | 更新频率 |
| --- | --- | --- | --- | --- |
| 全深圳企业列表 | **主干** | 企业名称、统一社会信用代码、注册地址、行业分类 | 批量导入（Excel/CSV） | 月度 |
| 企名片 API | **结构化补充** | 工商注册、股东、融资、法律风险 | API 实时调用（缓存 7 天） | 实时/日更 |
| Web Crawling | **主要充实** | 产品描述、技术栈、PR 稿件、团队介绍 | 爬取企业官网、行业媒体 | 月度批量 |
| Web Search | **补充/发现** | 最新动态、融资新闻、产品发布 | 搜索 API | 按需 |

**数据融合**：通过统一社会信用代码关联各数据源。

---

## 四、数据模型

### 4.1 企业表字段定义

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | TEXT | 是 | 唯一标识，格式 `COMP-{统一社会信用代码哈希}` |
| `name` | TEXT | 是 | 企业名称 |
| `credit_code` | TEXT | 是 | 统一社会信用代码（去重锚点） |
| `legal_representative` | TEXT | 否 | 法定代表人 |
| `registered_capital` | TEXT | 否 | 注册资本 |
| `establishment_date` | DATE | 否 | 成立日期 |
| `registered_address` | TEXT | 否 | 注册地址 |
| `industry` | TEXT | 否 | 行业分类 |
| `business_scope` | TEXT | 否 | 经营范围 |
| `product_description` | TEXT | 否 | 产品/服务描述（LLM 摘要 2-3 句） |
| `tech_tags` | TEXT[] | 否 | 技术栈标签 |
| `industry_tags` | TEXT[] | 否 | 行业标签 |
| `financing_round` | TEXT | 否 | 最新融资轮次 |
| `financing_amount` | TEXT | 否 | 融资金额 |
| `investors` | TEXT[] | 否 | 投资方 |
| `patent_count` | INTEGER | 否 | 专利数量 |
| `team_description` | TEXT | 否 | 核心团队描述 |
| `key_personnel` | JSONB | 否 | 关键人员信息，格式 `[{name, role, education: [{institution, degree, year, field}]}]`，Agent 从官网/企名片/Web Search 提取，支撑企业家教育背景筛选查询 |
| `website` | TEXT | 否 | 企业官网 |
| `profile_summary` | TEXT | 是 | 200-300 字企业画像摘要（语义检索用） |
| `profile_embedding` | VECTOR | 是 | 画像摘要向量 |
| `sources` | TEXT[] | 是 | 数据来源列表 |
| `completeness_score` | INTEGER | 是 | 数据完整度评分 0-100 |
| `last_updated` | TIMESTAMP | 是 | 最后更新时间 |
| `raw_data_path` | TEXT | 是 | 原始数据存储路径 |

### 4.2 profile_summary 规范

200-300 字中文自然语言段落，包含：企业定位、核心技术/产品、应用场景、团队亮点、融资情况。禁止模糊表述，用具体技术词汇。

---

## 五、采集流程

### 5.1 整体流程

```
Phase 0: 企业数据采集 (Company-Data-Agent)
  输入 → 全深圳企业列表 (Excel/CSV) + 企名片 API
  过程 → 批量导入企业骨架 → 企名片 API 补充工商数据 → Web Crawling 充实描述 → LLM 生成画像
  输出 → companies.jsonl + raw/

Phase 0 完成后 → Phase 1 (教授采集) 可启动
Phase 1 完成后 → Phase 2 (论文采集)
Phase 1 + Phase 2 完成后 → Phase 3 (合并反哺)
Phase 3 完成后 → Phase 4 (验证补采)
```

### 5.2 详细流程

#### 5.2.1 企业列表批量导入

```
1. 读取全深圳企业列表 (Excel/CSV)
2. 按统一社会信用代码去重（已有则更新，无则新增）
3. 填充基础字段：name, credit_code, registered_address, industry
4. 生成导入报告：新增 N 条、更新 N 条、失败 N 条
```

#### 5.2.2 企名片 API 数据补充

```
for each 企业 (from companies.jsonl):
  1. 调用企名片 API 查询企业详情
  2. 合并工商数据：legal_representative, registered_capital, establishment_date, business_scope
  3. 合并融资数据：financing_round, financing_amount, investors
  4. 缓存结果（7 天有效）
  5. API 限速：遵守企名片 API 调用频率限制
```

**降级策略**：企名片 API 额度用完时，仅保留全深圳企业列表的基础数据 + Web Crawling 充实。

#### 5.2.3 Web Crawling 充实

```
for each 企业 (有 website 字段):
  1. 爬取企业官网首页 + 产品页 + 关于我们页
  2. LLM 从页面中提取：product_description, tech_tags, team_description, key_personnel
  3. 搜索 PR 稿件（企业名 + "融资"/"发布"/"合作"）
  4. 合并到企业记录
```

**限速**：per-site 3 并发，间隔 2-5 秒随机延迟。

#### 5.2.4 LLM 生成画像摘要

```
输入：企业名称 + 行业 + 产品描述 + 技术标签 + 团队描述 + 融资信息
输出：200-300 字 profile_summary
批量处理：支持并发 LLM API 调用
```

#### 5.2.5 计算 embedding + 入库

```
1. 使用 Embedding 模型对 profile_summary 做向量化
2. 计算 completeness_score
3. 写入 PostgreSQL + pgvector（UPSERT by id）
```

---

## 六、与教授 Agent 的协作

### 6.1 Phase 0 → Phase 1 数据契约

| 交接点 | 生产方 | 消费方 | 数据格式 | 必含字段 |
| --- | --- | --- | --- | --- |
| Phase 0 → Phase 1 | Company-Data-Agent | Professor-Data-Agent | companies 表 | `id`, `name`, `credit_code` |

### 6.2 教授 Agent 如何使用企业数据

教授 Agent 在采集过程中，通过以下方式关联企业：

1. **企名片 API 反向查询**：输入教授姓名 + 机构，查询其在企业中的角色（法人/股东/高管）
2. **写入 `company_roles` 字段**：格式 `[{company_id, role, source_url}]`
3. **消歧**：通过机构、研究方向交叉验证企业关联是否属于同一人

---

## 七、质量保证

### 7.1 completeness_score 权重

| 字段 | 权重 |
| --- | --- |
| name + credit_code | 20（必填） |
| profile_summary | 15（必填） |
| product_description + tech_tags | 15 |
| financing_round + investors | 15 |
| legal_representative + registered_capital | 10 |
| team_description + key_personnel | 10 |
| website + patent_count | 10 |
| 其他 | 5 |

### 7.2 自动化校验

1. `credit_code` 格式校验（18 位）
2. `name` 不能为空
3. `profile_summary` 长度 150-400 字
4. 融资金额格式校验

---

## 八、配置

```yaml
# config.yaml 企业数据相关配置

company:
  # 全深圳企业列表文件路径
  company_list_path: "data/shenzhen_company_list.xlsx"

  # 企名片 API
  qimingpian:
    api_key: "${QIMINGPIAN_API_KEY}"
    endpoint: "https://api.qimingpian.com"
    cache_ttl_days: 7
    rate_limit: "100 req/min"

  # Web Crawling
  crawling:
    max_concurrency: 3
    delay_range: [2, 5]  # 秒
    timeout: 30  # 秒
```

---

## 九、更新策略

- **频率**：月度执行，与教授采集同步
- **增量逻辑**：
  - 全深圳企业列表重新导入，按 `credit_code` 去重
  - 新增企业：全流程采集
  - 已有企业：企名片数据刷新 + Web Crawling 增量更新
- **企名片 API**：实时调用，7 天缓存

---

## 十、验收标准

| 指标 | 要求 |
| --- | --- |
| 企业总数 | ≥ 全深圳企业列表的 95% |
| 必填字段完整率 | `name` + `credit_code` + `profile_summary` 100% |
| `completeness_score` ≥ 60 | ≥ 85% 的企业记录 |
| 企名片数据覆盖率 | ≥ 70% 的企业有企名片补充数据 |
| 全量首次采集 | 6000+ 企业在 24 小时内完成 |
| 月度增量更新 | 8 小时内完成 |

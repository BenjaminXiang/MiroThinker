# 企业数据采集智能体 — 产品需求文档

> 本文档定义企业域的特有需求。通用架构、MiroThinker 实现映射、质量维度、更新发布规则见 [共享技术规范](./Data-Agent-Shared-Spec.md)。术语定义见 [术语表](./index.md#术语表)。

## 一、为什么需要独立的企业数据采集智能体

测试集和总 PRD 都表明，企业数据不是一个附属模块，而是系统中的核心数据域之一：

- 企业本身就是高频查询对象
- 教授 `company_roles` 需要企业库做关联锚点
- 专利申请人需要与企业库做映射
- 行业知识问答经常需要调用企业画像、技术路线、关键人物信息

因此，需要一个独立的 `Company-Data-Agent` 负责企业数据的导入、清洗、去重、摘要生成和发布。

这个 Agent 的目标不是“尽可能实时调用外部 API”，而是构建一个**可持续更新、可追溯、可供线上稳定消费**的企业知识库。

---

## 二、核心目标

### 2.1 一句话目标

构建深圳科创企业全景数据库，为企业检索、教授关联企业、专利关联企业、行业知识问答和技术路线对比提供稳定数据支撑。

### 2.2 成功标准

企业域必须同时支持：

- 语义检索
  - 如“做手术机器人的公司”
- 结构化筛选
  - 如“融过 A 轮以上”“深圳本地”“创始人有海外教育背景”
- 画像化回答
  - 如企业简介、事实性评价、技术路线总结
- 关联跳转
  - 教授 → 企业
  - 企业 → 专利
  - 企业 → 关键人物

实现方式见 [共享技术规范 §3](./Data-Agent-Shared-Spec.md#三与当前-mirothinker-实现的映射)。

---

## 三、数据来源与去重策略

### 3.1 主数据来源

企业域主骨架数据以：

- `企名片导出 xlsx`

为准。

它提供企业基础骨架，包括但不限于：

- 企业名称
- 行业
- 融资轮次 / 金额 / 投资方
- 注册资本
- 法人
- 团队信息
- 专利数量
- 网址

### 3.2 补充来源

辅助来源包括：

- 企业官网
- 产品页 / 关于页 / 新闻页
- 行业媒体与 PR 稿件
- Web Search 结果

使用原则：

- 自写爬虫与确定性导入为主
- Web Search 为辅助发现、补充和事实校验
- 不把 Web Search 作为企业主骨架来源

### 3.3 去重主锚点

企业主去重锚点应为：

- 标准化公司名称

辅助信号包括：

- `credit_code`
- 企业官网
- 法人
- 注册地
- 融资信息

`credit_code` 的定位是：

- 可选补充字段
- 用于一致性校验时很有价值
- 不是主去重锚点
- 不是对外契约必填字段

### 3.4 数据融合原则

企业域的融合顺序建议为：

1. 先导入 xlsx 骨架
2. 再做标准化名称和去重
3. 再用官网 / PR / Web Search 做补充
4. 再生成用户向摘要字段和结构化关键人物字段

---

## 四、数据模型与对外契约

### 4.1 最低发布字段

发布层至少应包含：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 稳定主键，建议 `COMP-*` |
| `name` | 是 | 企业名称 |
| `normalized_name` | 是 | 标准化名称，作为主去重锚点 |
| `credit_code` | 否 | 补充校验字段 |
| `industry` | 否 | 行业分类 |
| `legal_representative` | 否 | 法定代表人 |
| `registered_capital` | 否 | 注册资本 |
| `website` | 否 | 企业官网 |
| `key_personnel` | 否 | 结构化关键人物信息 |
| `profile_summary` | 是 | 企业画像摘要 |
| `evaluation_summary` | 是 | 事实性评价摘要 |
| `technology_route_summary` | 是 | 技术路线摘要 |
| `patent_count` | 否 | 专利数量 |
| `evidence` | 是 | 来源列表 |
| `last_updated` | 是 | 最后更新时间 |

### 4.2 必要用户向摘要字段

企业域必须预生成以下字段：

- `profile_summary`
  - 面向语义检索和基础介绍
- `evaluation_summary`
  - 面向“技术实力怎么样”“值不值得关注”这类事实性判断
- `technology_route_summary`
  - 面向“这家公司走什么路线”“和别家有什么差异”这类问题

### 4.3 `key_personnel` 必须可检索

`key_personnel` 不能只是展示文本，必须是结构化、可检索字段。

最低结构建议：

```json
[
  {
    "name": "张三",
    "role": "创始人 / CEO",
    "education_structured": [
      {
        "institution": "某大学",
        "degree": "硕士",
        "field": "自动化",
        "year": "2018"
      }
    ],
    "work_experience": [
      {
        "organization": "某公司",
        "role": "算法负责人",
        "start_year": "2018",
        "end_year": "2022",
        "description": "负责机器人感知算法"
      }
    ],
    "description": "创业者背景简介"
  }
]
```

### 4.4 存储要求

企业域独立 PostgreSQL 库 + Milvus collection。详见 [共享技术规范 §6](./Data-Agent-Shared-Spec.md#六物理存储与向量化建议)。

---

## 五、采集与清洗流程

### 5.1 总体流程

```text
企名片导出 xlsx
  -> 表头识别与原始解析
  -> 标准化名称与去重
  -> 官网 / PR / Web Search 补充
  -> 关键人物结构化
  -> 生成 profile_summary / evaluation_summary / technology_route_summary
  -> 向量化
  -> 发布到 company domain PostgreSQL + Milvus
```

### 5.2 xlsx 导入

导入阶段至少完成：

1. 读取企名片导出文件
2. 自动识别真实表头
3. 处理多行续写记录
4. 抽取基础字段
5. 生成 `normalized_name`
6. 按标准化名称去重
7. 生成导入报告

### 5.3 Web 补充

对有官网或可发现官网的企业，补充采集：

- 企业官网首页
- 产品页
- 关于页
- 新闻页
- 重要 PR / 媒体稿件

主要提取内容：

- `product_description`
- `tech_tags`
- `industry_tags`
- `team_description`
- `key_personnel`
- 最新公开动态

### 5.4 LLM 与 Python 清洗分工

建议分工如下：

- LLM 负责：
  - 非结构化网页理解
  - 摘要生成
  - 技术路线归纳
  - 人物简介抽取
- Python / 离线脚本负责：
  - 标准化名称
  - 融资金额、日期、网址规范化
  - 去重辅助规则
  - 字段格式校验

### 5.5 向量化

主向量文本建议采用：

- `profile_summary`

如果后续确有需要，可追加：

- `technology_route_summary`

作为第二类向量对象，但不是一期硬要求。

---

## 六、与其他数据域和服务层的协作

### 6.1 与教授域的关系

企业域是教授 `company_roles` 的重要锚点，但不再要求：

- “教授基础采集必须等企业域全量完成才能开始”

新的协作原则是：

- 教授基础采集可以独立进行
- 教授与企业的关联步骤优先消费企业域发布层
- 若企业域当期未覆盖到某家公司，可先记录候选文本证据，后续再回填 `company_id`

### 6.2 与专利域的关系

企业域需要支持：

- 通过标准化企业名与专利申请人做关联
- 在企业卡片中展示专利数量或相关专利入口

### 6.3 与线上服务层的关系

企业域对服务层暴露的能力至少包括：

- 企业搜索
- 企业详情获取
- 企业相关专利获取
- 关键人物结构化筛选

线上服务层负责：

- 多域编排
- 结果融合
- rerank
- 实时外部 fallback

---

## 七、质量保证

通用质量维度和验证流程见 [共享技术规范 §7](./Data-Agent-Shared-Spec.md#七数据质量与验证)。

### 7.1 企业域特有校验

1. `name` 不为空
2. `normalized_name` 可生成
3. `credit_code` 若存在则校验格式（18 位统一社会信用代码）
4. `profile_summary`、`evaluation_summary`、`technology_route_summary` 不为空
5. `key_personnel` 若存在，字段结构必须合法

### 7.2 重点验证对象

- 同名或近名企业
- 关键人物背景信息丰富的企业
- 融资字段变化较大的企业
- 技术路线高度相近、容易混淆的企业

---

## 八、配置项

### 8.1 推荐配置项

```yaml
company:
  source_xlsx_path: "data/qimingpian_export.xlsx"
  crawling_max_concurrency: 3
  crawling_delay_range: [2, 5]
  crawling_timeout_seconds: 30
  web_search_enabled: true
  require_technology_route_summary: true
```

---

## 九、更新策略

- 主更新节奏：月度
- xlsx 骨架：月度全量导入并去重
- 官网 / PR 补充：月度或按需增量更新
- Web Search：按需触发，不作为主更新机制

允许企业域独立更新，不要求和教授/论文/专利完全同步。

---

## 十、验收标准

| 指标 | 要求 | 测试集 | 样本量 | 评判标准 |
| --- | --- | --- | --- | --- |
| 企业总数覆盖 | ≥ 当期企名片导出企业数的 95% | 企名片导出 xlsx | 全量 | 自动化比对 |
| 必填字段完整率 | `name` + `normalized_name` + `profile_summary` + `evaluation_summary` + `technology_route_summary` 100% | 全量发布数据 | 全量 | 自动化校验 |
| 关键人物结构化可用率 | 有团队信息的企业中 ≥ 80% | 有团队信息的企业子集 | 全量 | 自动化结构校验 |
| 去重准确率 | ≥ 95% | 含已知重复对的标注集 | ≥ 100 对 | 人工判定 |
| 检索效果 | Top-5 相关率 ≥ 85% | Agentic-RAG 测试集中企业类 query | ≥ 50 条 | 人工评估相关性 |
| 更新效率 | 1000+ 企业月度更新在可接受窗口内 | 月度导入批次 | 全量 | 自动化计时 |

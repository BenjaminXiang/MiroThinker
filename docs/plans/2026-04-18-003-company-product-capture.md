---
title: Company Product Information Capture Plan
date: 2026-04-18
status: active
owner: claude
extends:
  - docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
  - docs/plans/2026-04-18-002-real-data-e2e-and-db-separation.md
---

# 企业产品信息捕获规划

## 0. 起因

用户明确：**企业产品信息是投研用户最关心的维度之一**，但**企名片 xlsx 中并无产品字段**。现有 `company_snapshot` 仅有 `business` 和 `description` 两个自由文本字段，对"云鲸智能有哪些型号的扫地机"、"普渡有哪些送餐机器人产品、各自配什么技术"这种具体投研问题无法回答。

## 1. 数据来源与采集链路

产品信息不走 xlsx seed，必须**从外部抓取 + 结构化提取**。优先级从高到低：

| 源 | 结构化程度 | 覆盖率 | 投研可用性 |
|---|---|---|---|
| 公司官网产品页（`/products`, `/solutions`, `/about`） | 中（HTML） | 高（大部分公司都有） | ✅ 主力 |
| 公司公众号 "产品" 菜单 | 中 | 中 | ✅ 补充 |
| 行业媒体深度报道（36kr、钛媒体） | 低（自由文本） | 中 | ✅ 补充（带事件时间） |
| 天眼查 / 企查查的 "产品信息" 字段 | 高（结构化） | 中等（B 端公司多） | ✅ 但可能有付费接口 |
| 京东/天猫商品详情页（toC 公司） | 高 | 低（只有 toC） | ⚠ 仅 toC |
| 专利说明书（已在 patent 表） | 高 | 对研发型公司高 | ✅ 已有 |

**Phase 1 scope**：公司官网抓取。其他源作为 Phase 2 补充。

## 2. Schema 设计（V008 migration）

### 2.1 `company_product` 主表

```sql
product_id              TEXT PRIMARY KEY                    -- PROD-{12hex}
company_id              TEXT NOT NULL FK company(company_id) ON DELETE CASCADE
canonical_name          TEXT NOT NULL                       -- 产品标准名（如"小胖胖1号"）
product_name_en         TEXT                                 -- 英文名
aliases                 TEXT[] NOT NULL DEFAULT '{}'        -- 昵称/简称
product_category        TEXT                                 -- 受控词，FK taxonomy_vocabulary('industry:robotics.service.food_delivery')
product_line            TEXT                                 -- 产品线（如"送餐系列"）
status                  TEXT NOT NULL DEFAULT 'unknown'      -- enum: on_sale | rnd | discontinued | unknown
short_description       TEXT                                 -- ≤80 字一句话介绍
long_description        TEXT                                 -- ≤1000 字详细介绍
target_customer         TEXT                                 -- 客户类型（酒店/医院/家用...）
technology_routes       TEXT[] NOT NULL DEFAULT '{}'        -- FK codes to taxonomy_vocabulary (namespace=technology_route)
data_route_codes        TEXT[] NOT NULL DEFAULT '{}'        -- FK codes to taxonomy_vocabulary (namespace=data_route)
launch_date             DATE                                 -- 首次发布日期
discontinued_date       DATE
price_tier              TEXT                                 -- enum: consumer | commercial | enterprise | unknown
key_features            TEXT[]                               -- bullet list（≤10 条）
key_specs               JSONB                                -- 开放字段：续航、载重、速度等
official_product_url    TEXT
cover_image_url         TEXT
first_seen_at           TIMESTAMPTZ NOT NULL DEFAULT now()
last_refreshed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()

UNIQUE (company_id, canonical_name)
CHECK status IN ('on_sale','rnd','discontinued','unknown')
CHECK price_tier IS NULL OR price_tier IN ('consumer','commercial','enterprise','unknown')
INDEX on (company_id, status)
INDEX GIN on technology_routes
INDEX GIN on data_route_codes
```

### 2.2 `company_product_evidence`（per-field provenance）

每个产品字段的抓取源可能不同（name 来自 /products 页、launch_date 来自新闻），需要**字段级 provenance**。简化方案：

```sql
evidence_id             UUID PRIMARY KEY DEFAULT gen_random_uuid()
product_id              TEXT NOT NULL FK company_product(product_id) ON DELETE CASCADE
field_name              TEXT NOT NULL                       -- e.g. 'canonical_name', 'launch_date'
source_page_id          UUID FK source_page(page_id) ON DELETE SET NULL
source_url              TEXT NOT NULL
evidence_span           TEXT NOT NULL                        -- 原文片段 ≤400 字
confidence              NUMERIC(3,2) NOT NULL
extractor_version       TEXT NOT NULL                        -- 抽取器版本 hash
created_at              TIMESTAMPTZ NOT NULL DEFAULT now()

INDEX on (product_id, field_name)
```

### 2.3 与 `company_fact` 的关系

- `company_fact.fact_type='product_tag'` 保留作为"公司维度"的 product 汇总（例如"该公司主营服务机器人"），粒度粗；
- `company_product` 是**单个产品级**的细粒度；
- `company_fact` 的 product_tag 可通过 materialized view 从 `company_product.product_category` 聚合得到。

## 3. Crawler 架构

### 3.1 目录新增

```
apps/miroflow-agent/src/data_agents/company/
├── official_site_crawler.py    ← 新：抓 company.website 及其子路径
├── product_extractor.py        ← 新：HTML → ParsedProduct (LLM + regex 混合)
├── product_canonical_writer.py ← 新：写 company_product + evidence
└── ...
```

### 3.2 抓取流程

```
for each company in miroflow_real.company (has website):
    with rate_limit_per_host(5s):
        pages = official_site_crawler.crawl(website, max_depth=2,
                 url_patterns=['/product', '/solutions', '/about'])
        for page in pages:
            # pages 先写 source_page（page_role='company_official_site'）
            page_id = upsert_source_page(url=page.url, ...)
        for page in product_pages:  # 过滤出产品候选页
            parsed_products: list[ParsedProduct] = product_extractor.extract(
                html=page.html, company_id=company.company_id,
                llm_provider=...
            )
            for p in parsed_products:
                product_canonical_writer.upsert(
                    conn=...,
                    product=p,
                    evidence_page_id=page_id,
                )
```

### 3.3 提取规则

优先级：
1. **Rule-based 先行**：`/products` 页面常见结构（`<h2>产品名</h2>` + `<p>描述</p>`）用正则/CSS selector 抓
2. **LLM fallback**：正则抓不到时调 LLM；提示词严格约束输出 Pydantic `ParsedProduct` 结构
3. **多页合并**：同一产品在 `/products/xxx` 详情页 vs `/about` 里的介绍，按产品名 normalized 合并

### 3.4 调度

- Phase 1：`scripts/run_real_e2e_company_product_crawl.sh` 可手动跑；初始 scope = top 50 公司（按 reported_patent_count 或已知知名度）
- Phase 2：接入 APScheduler，月级全量 + 增量（按 `last_refreshed_at`）

## 4. 与现有工作的整合

### 4.1 依赖

- ✅ V001/V002（company 表存在）
- ✅ `source_page` 表（crawler 写的页面落 source layer）
- ⚠ LLM provider（miroflow-agent 现有 Anthropic/OpenAI/Qwen 配置可复用）
- ⚠ Rate limiting / retry infrastructure（基础 httpx + tenacity 够用）

### 4.2 不依赖

- 不需要 Phase 2 news_refresh
- 不需要 Phase 3 professor pipeline
- 不需要 chat-app

因此可以**平行于其他 Rounds 推进**。

## 5. 数据质量约束

投研用户看 product 要能回答："这家公司**真的**卖 X 产品吗？还是 PPT 产品？"

为此必须硬约束：

1. **evidence 必须可追溯**：每条 product 记录 ≥1 个 evidence，`source_url` 指向可 HTTP 访问的公司官网页（不是新闻转述）
2. **`status='on_sale'` 要有下列至少一种证据**：
   - 官网有 "立即购买" / "咨询" 按钮
   - 京东/天猫有在售 listing
   - 近 90 天内有该产品的新闻（新品发布、客户签约、融资公告）
3. **`status='rnd'` 要有**：官网公开技术方案页 OR 专利（company_patent_link）OR 近期 demo 新闻
4. **LLM 输出必须 grounded**：若 LLM 提取不到明确产品名/描述 → 降级为 `status='unknown'`，不编造

## 6. Rounds 分解

| Round | 内容 | 前置 | 预估产出 |
|---|---|---|---|
| **Round A1** | V008 migration（`company_product` + evidence）+ Pydantic contracts | 无 | ~400 行 |
| **Round A2** | `official_site_crawler.py` + httpx rate limiter + robots.txt 尊重 | Round A1 | ~300 行 |
| **Round A3** | `product_extractor.py`（rule + LLM 混合）+ 合成数据单测 | Round A2 + LLM 可用 | ~500 行 |
| **Round A4** | 真实运行 top 50 公司爬虫 + 人工抽检 ≥ 10 家样本准确率 | Round A3 | 数据 + 报告 |
| **Round A5** | 接入 company_answer_pack / Chat v1 渲染 product 卡片 | Round A4 + Chat v1 就绪 | 前端组件 |

## 7. 验收指标

Phase A 完成的可感知交付：

- `miroflow_real.company_product` ≥ 200 行（覆盖 50+ 公司）
- 至少 80% product 有 ≥1 条 evidence 且 `source_url` 指向 company.website_host 域内
- 抽样 20 个产品人工判定准确率 ≥ 85%（产品名、核心功能、状态是否正确）
- Chat API 问 "普渡科技有哪些产品" 能返回 ≥3 个型号，每个带短介绍

## 8. 与已知数据的 gap 盘点

现有 1024 家公司里：
- `company.website` 非空率约 80%+（实际数字跑 `SELECT count(*) FROM company WHERE website IS NOT NULL`）
- 即使有 website，官网可能：无 /products 页、全 JS 渲染难抓、已下线
- 估计能稳定抓到产品信息的公司 ~ 400-600 家

**不能覆盖的公司** 通过 `company_fact.fact_type='product_tag'` 从 `business` 字段 LLM 归类作为兜底。

## 9. 下一步

若 Round 7+（Professor 整合）已在进行，Round A1/A2 可以作为**独立平行 track** 启动——它只动新文件和新迁移，不碰教授 pipeline。建议：**先跑完 Round 7.5 真实教授 E2E**（验证教授链路），再启动 Round A1（产品捕获）。

# Issue 10 实现说明：配置模型与产物路径约定

本文档说明 `Issue #10` 已完成的内容，包括：

1. 实现了什么
2. 如何使用
3. 如何验证

核心代码位于：

- `src/company_data_agent/config/settings.py`
- `tests/test_config_settings.py`

---

## 一、这次实现了什么

`Issue #10` 的目标不是接入真实 provider，也不是开始导入企业数据，而是先把“配置 contract”和“产物路径 contract”固定下来，让后续 issue 都围绕同一套配置结构和路径规则工作。

本次实现主要包含四部分。

### 1. 建立了顶层配置模型 `CompanyDataAgentConfig`

当前顶层配置分成这些部分：

- `company_list_path`
- `qimingpian`
- `crawling`
- `llm`
- `embedding`
- `postgres`
- `artifacts`

这意味着后续所有阶段都不需要再自行约定配置字段名，只需要消费这个统一结构。

### 2. 建立了 provider 配置块

实现了以下配置模型：

- `QimingpianConfig`
- `CrawlConfig`
- `LLMConfig`
- `EmbeddingConfig`
- `PostgresConfig`

这些模型做了两件事：

- 保证字段存在且类型正确
- 把明显错误的配置在启动前就拦截掉

例如：

- `cache_ttl_days` 必须大于 0
- `rate_limit_per_minute` 必须大于 0
- `dimensions` 必须大于 0
- `delay_max_seconds` 不能小于 `delay_min_seconds`
- `base_url` 必须是合法 URL

这样后续执行阶段不会在跑到一半时才发现配置是坏的。

### 3. 建立了环境变量引用对象 `EnvVarRef`

为了满足“密钥来源于环境变量，而不是硬编码在配置里”的要求，这次没有直接把真实密钥放进配置模型，而是定义了：

```python
EnvVarRef(env_var="QIMINGPIAN_API_KEY")
```

这个对象负责两件事：

- 校验环境变量名是否符合大写蛇形命名
- 在真正运行前检查对应环境变量是否存在

这样做的好处是：

- 配置文件可以被安全提交，不包含敏感值
- 缺失密钥时会在 provider 调用前失败，而不是运行到中途才报错

### 4. 建立了产物路径解析器 `ArtifactLayout`

这是本次最重要的 contract 之一。它统一定义了以下路径：

- 标准化输出路径
- 原始 payload 存储路径
- Qimingpian 缓存路径
- 爬取缓存路径
- 运行报告路径

当前约定包括：

#### 标准输出

```text
artifacts/company-data-agent/runs/<run_id>/normalized/companies.jsonl
```

#### 原始数据

```text
artifacts/company-data-agent/raw/companies/<credit_code>/<source>/<filename>
```

#### Qimingpian 缓存

```text
artifacts/company-data-agent/cache/qimingpian/<credit_code>.json
```

#### Crawl 缓存

```text
artifacts/company-data-agent/cache/crawl/<hostname>/<filename>
```

#### 报告路径

```text
artifacts/company-data-agent/reports/<run_id>/<report_name>
```

同时，这些 helper 会拒绝简单的路径穿越风险，例如：

- `../detail.json`
- 带路径分隔符的非法文件名

这样后续阶段不会在不同模块里手工拼路径，也不会出现同一个 artifact 被写到多个位置的情况。

---

## 二、怎么使用

### 1. 解析配置

可以直接从字典构造：

```python
from company_data_agent.config import CompanyDataAgentConfig

config = CompanyDataAgentConfig.model_validate(
    {
        "company_list_path": "data/shenzhen_company_list.xlsx",
        "qimingpian": {
            "api_key": {"env_var": "QIMINGPIAN_API_KEY"},
            "endpoint": "https://api.qimingpian.com",
            "cache_ttl_days": 7,
            "rate_limit_per_minute": 100,
        },
        "crawling": {
            "max_concurrency": 3,
            "delay_min_seconds": 2,
            "delay_max_seconds": 5,
            "timeout_seconds": 30,
        },
        "llm": {
            "api_key": {"env_var": "SUMMARY_LLM_API_KEY"},
            "base_url": "https://llm.internal.example/v1",
            "model_name": "summary-model",
        },
        "embedding": {
            "api_key": {"env_var": "EMBEDDING_API_KEY"},
            "base_url": "https://embedding.internal.example/v1",
            "model_name": "embedding-model",
            "dimensions": 1024,
        },
        "postgres": {
            "dsn": {"env_var": "POSTGRES_DSN"},
            "schema": "public",
            "companies_table": "companies",
        },
        "artifacts": {
            "root_dir": "artifacts/company-data-agent",
        },
    }
)
```

### 2. 在运行前检查环境变量

```python
config.validate_required_environment(os.environ)
```

如果某个必须的密钥不存在，会直接抛错。例如：

- `QIMINGPIAN_API_KEY`
- `SUMMARY_LLM_API_KEY`
- `EMBEDDING_API_KEY`
- `POSTGRES_DSN`

这一步应该在任何 provider 调用之前执行。

### 3. 解析固定路径

可以通过 `ArtifactLayout` 生成后续阶段需要的路径：

```python
layout = config.artifacts

normalized_path = layout.normalized_companies_path("full-2026-03")
raw_path = layout.raw_payload_path(
    "91440300MA5FUTURE1",
    "qimingpian",
    "detail.json",
)
cache_path = layout.qimingpian_cache_path("91440300MA5FUTURE1")
report_path = layout.run_report_path("full-2026-03", "import-summary.json")
```

这意味着：

- `#11/#13` 可以复用标准输出与报告路径
- `#14/#15` 可以复用 Qimingpian cache path
- `#16/#17/#18` 可以复用 raw/crawl cache path
- `#23` 可以复用 run report path

---

## 三、怎么验证

### 1. 自动化测试

当前新增了 `test_config_settings.py`，覆盖：

- 合法配置 fixture 是否能通过解析
- 环境变量名是否符合要求
- delay window 是否非法
- 缺失密钥是否能在运行前失败
- 路径解析是否稳定且确定
- path traversal 是否被拒绝
- URL 或 secret contract 非法时是否失败

在 `apps/company-data-agent` 目录下执行：

```bash
UV_CACHE_DIR=.uv-cache uv run pytest
```

当前结果：

```text
16 passed
```

其中包含：

- `Issue #9` 的 9 个模型测试
- `Issue #10` 的 7 个配置/路径测试

### 2. 手工验证建议

建议 review 时重点看下面三类行为。

#### 验证点 A：坏配置是否能在启动前失败

比如：

- `base_url = "not-a-url"`
- `delay_min_seconds = 5, delay_max_seconds = 2`
- `dimensions = 0`

这些都应该在配置解析阶段失败。

#### 验证点 B：密钥引用是否不依赖硬编码

当前 contract 要求 API key 和 DSN 都通过 `EnvVarRef` 引用环境变量，而不是把真实值塞进配置。

这意味着配置文件里应出现：

```python
{"env_var": "QIMINGPIAN_API_KEY"}
```

而不是：

```python
{"api_key": "real-secret"}
```

#### 验证点 C：路径是否稳定

相同输入必须生成完全相同的路径，例如：

```python
layout.normalized_companies_path("full-2026-03")
```

应该稳定得到：

```text
artifacts/company-data-agent/runs/full-2026-03/normalized/companies.jsonl
```

这保证后续 pipeline 可以安全复跑，而不会把同类产物写到不同位置。

---

## 四、当前实现的边界

这次完成的是 contract，不包含真实业务执行：

- 不会读取 Excel/CSV
- 不会发起 Qimingpian 请求
- 不会抓网页
- 不会生成 summary / embedding
- 不会连接 PostgreSQL

也就是说，这一层的职责只有两件事：

1. 让配置先变成强约束对象
2. 让产物路径先变成统一 contract

后续 issue 才在这个基础上往上叠业务逻辑。

---

## 五、对后续任务的直接价值

这次实现会直接服务于：

- `#11`
  使用 `company_list_path`

- `#14/#15`
  使用 `QimingpianConfig` 与 `qimingpian_cache_path`

- `#16/#17/#18`
  使用 `CrawlConfig` 与 crawl/raw path helper

- `#19/#20`
  使用 `LLMConfig` 和 `EmbeddingConfig`

- `#22`
  使用 `PostgresConfig`

- `#23`
  使用 `normalized_companies_path` 和 `run_report_path`

因此，`Issue #10` 的价值不是“多写了一层配置对象”，而是把后续所有模块共享的启动参数和路径规则提前固定下来，避免后面继续分叉。

# 教授数据采集 Pipeline V2 — 使用说明

> 最后更新：2026-04-05

## 一、概览

教授数据采集 Pipeline V2 是一个端到端的教授信息采集系统，从深圳高校官网自动发现教授名单，抓取个人主页，提取结构化字段，并通过论文采集和 LLM 补全生成完整的教授画像。最终数据同时写入：

- **教授专用向量库**（Milvus，4096 维 Qwen3-Embedding-8B，支持画像语义检索和研究方向精确检索）
- **共享检索服务存储**（SQLite + Milvus 64 维，供 Agentic RAG 智能体跨域检索使用）

### 当前数据规模

| 高校 | 教授数 |
|------|--------|
| 深圳大学 | 1,097 |
| 南方科技大学 | 983 |
| 哈尔滨工业大学（深圳） | 760 |
| 清华大学深圳国际研究生院 | 272 |
| 深圳理工大学 | 90 |
| 北京大学深圳研究生院 | 63 |
| 香港中文大学（深圳） | 9 |
| **合计** | **3,274** |

---

## 二、Pipeline 架构

```
Stage 1: 名单发现        Stage 2a: 正则预提取     Stage 2b: 论文采集
seed URL ──> 递归爬取 ──> HTML regex extract ──> Semantic Scholar
             学院/教师页                         DBLP / arXiv
                                                 ↓ 论文驱动研究方向

Stage 2c: Agent 补全      Stage 3: 摘要生成       Stage 4: 质量门控 + 入库
Local LLM (Qwen) ──────> LLM profile_summary ──> L1/L2 质量检查
 ↓ 失败 → DashScope       evaluation_summary     向量化 (Milvus)
                                                   发布 (SQLite + JSONL)
```

### 各阶段说明

| 阶段 | 功能 | 输入 | 输出 |
|------|------|------|------|
| Stage 1 | 从高校官网递归发现教授个人页 URL | `教授 URL.md`（种子文档） | 教授名单 + 个人页 HTML |
| Stage 2a | 正则提取姓名/院系/职称/邮箱/研究方向 | HTML | `MergedProfessorProfileRecord` |
| Stage 2b | 从 Semantic Scholar/DBLP/arXiv 采集论文，生成研究方向 | 教授姓名 + 机构 | 论文列表、h-index、研究方向 |
| Stage 2c | LLM 补全教育经历、工作经历、奖项等缺失字段 | HTML + 已有画像 | 完整 `EnrichedProfessorProfile` |
| Stage 3 | 生成用户可读的画像摘要和评估摘要 | 完整画像 | `profile_summary` + `evaluation_summary` |
| Stage 4 | 质量门控 → 向量化 → 发布到检索存储 | 完整画像 | Milvus + SQLite + JSONL |

---

## 三、快速开始

### 3.1 环境准备

```bash
cd apps/miroflow-agent

# 安装依赖（如果 uv 因镜像 SSL 问题失败，见"常见问题"）
uv sync

# 安装 Milvus Lite 依赖
uv pip install milvus-lite
uv pip install "setuptools==74.1.3"  # milvus-lite 需要 pkg_resources
```

### 3.2 环境变量

```bash
# 必需
export API_KEY="your-sglang-api-key"          # 内部 LLM + 嵌入模型的 API Key

# 可选（用于 LLM 补全降级和在线搜索）
export DASHSCOPE_API_KEY="your-dashscope-key"  # DashScope qwen3.6-plus
export SERPER_API_KEY="your-serper-key"         # Web search（当前未启用）

# 默认不需要修改的端点
# LOCAL_LLM_BASE_URL=http://star.sustech.edu.cn/service/model/qwen35/v1
# EMBEDDING_BASE_URL=http://100.64.0.27:18005/v1
```

### 3.3 运行完整 Pipeline

```bash
# 完整运行（从种子文档 → 发现 → 提取 → 向量化）
.venv/bin/python scripts/run_professor_enrichment_v2_e2e.py

# 限制处理数量（测试用）
.venv/bin/python scripts/run_professor_enrichment_v2_e2e.py --limit 10

# 仅处理某所高校
.venv/bin/python scripts/run_professor_enrichment_v2_e2e.py --institution 南方科技大学

# 仅发现阶段（不做提取和向量化）
.venv/bin/python scripts/run_professor_enrichment_v2_e2e.py --dry-run

# 跳过向量化（当嵌入服务不可用时）
.venv/bin/python scripts/run_professor_enrichment_v2_e2e.py --skip-vectorize
```

### 3.4 将已有数据发布到检索服务

如果已有 `enriched.jsonl`，可以直接发布到共享检索服务：

```bash
# 发布并运行测试查询
.venv/bin/python scripts/run_professor_publish_to_search.py --test-queries

# 指定输入文件
.venv/bin/python scripts/run_professor_publish_to_search.py \
  --enriched-jsonl path/to/enriched.jsonl \
  --output-dir path/to/output/
```

---

## 四、输出文件说明

Pipeline 运行后在 `logs/data_agents/professor/` 下生成以下文件：

| 文件 | 说明 |
|------|------|
| `enriched.jsonl` | 所有教授的完整画像（`EnrichedProfessorProfile` 格式），每行一条 JSON |
| `milvus.db` | 教授专用 Milvus Lite 向量库（4096 维双向量：画像 + 研究方向） |
| `quality_report.json` | 质量门控报告（released/blocked 统计） |
| `paper_staging.jsonl` | 论文暂存记录，供论文域后续消费 |
| `search_service/released_objects.sqlite3` | 共享 SQLite 存储（`DataSearchService` 使用） |
| `search_service/released_objects_milvus.db` | 共享 Milvus 向量存储（64 维哈希向量） |
| `search_service/professor_released_objects.jsonl` | `ReleasedObject` 格式导出，可导入其他系统 |
| `search_service/publish_report.json` | 发布统计报告 |

### enriched.jsonl 字段说明

每条记录包含：

```json
{
  "name": "教授姓名",
  "name_en": "英文名（可选）",
  "institution": "所属高校",
  "department": "院系",
  "title": "职称",
  "email": "邮箱",
  "homepage": "主页 URL",
  "research_directions": ["研究方向1", "研究方向2"],
  "research_directions_source": "paper_driven | official_only | merged",
  "h_index": 42,
  "citation_count": 1234,
  "top_papers": [{"title": "...", "year": 2024, "venue": "...", "citation_count": 88}],
  "profile_summary": "200-300 字画像摘要",
  "evaluation_summary": "100-150 字评估摘要",
  "enrichment_source": "regex_only | paper_enriched | agent_local | agent_online",
  "evidence_urls": ["https://..."],
  "profile_url": "教授个人页 URL",
  "roster_source": "教师目录页 URL",
  "extraction_status": "structured | partial | failed"
}
```

---

## 五、检索服务集成

发布到共享存储后，可通过 `DataSearchService` 进行跨域检索：

```python
from src.data_agents.service.search_service import DataSearchService
from src.data_agents.storage.milvus_store import MilvusVectorStore
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

# 初始化存储
sql_store = SqliteReleasedObjectStore("logs/data_agents/professor/search_service/released_objects.sqlite3")
vector_store = MilvusVectorStore(
    uri="logs/data_agents/professor/search_service/released_objects_milvus.db",
    collection_name="released_objects",
)
service = DataSearchService(sql_store=sql_store, vector_store=vector_store)

# 搜索教授
result = service.search("南方科技大学 教授 机器学习", limit=5)
for professor in result.results:
    print(f"{professor.display_name} — {professor.core_facts['institution']}")
    print(f"  研究方向: {professor.core_facts.get('research_directions', [])}")

# 获取单个教授详情
detail = service.get_object("professor", "PROF-0188D2B7702D")

# 按院系精确过滤
filtered = service.search("教授 计算机", filters={"institution": "南方科技大学"}, limit=10)
```

### 查询路由关键词

`DataSearchService` 根据查询中的关键词自动路由到相应域：

| 关键词 | 路由域 |
|--------|--------|
| 教授、老师、导师、院系、研究方向 | `professor` |
| 企业、公司、厂商、融资、法人、业务 | `company` |
| 论文、paper、doi、arxiv | `paper` |
| 专利、发明人、申请人、专利号 | `patent` |

查询中包含多个域的关键词时，会触发跨域联合检索。

---

## 六、教授专用向量检索

除共享检索服务外，教授域还有专用的 Milvus 向量库，支持更精细的语义检索：

```python
from src.data_agents.professor.vectorizer import EmbeddingClient, ProfessorVectorizer

# 初始化
embedding_client = EmbeddingClient(
    base_url="http://100.64.0.27:18005/v1",
    api_key="your-api-key",
)
vectorizer = ProfessorVectorizer(
    embedding_client=embedding_client,
    milvus_uri="logs/data_agents/professor/milvus.db",
)

# 按画像语义搜索（匹配 profile_summary）
ids = vectorizer.search_by_profile("做深度学习和计算机视觉的教授", limit=10)

# 按研究方向精确搜索（匹配 research_directions）
ids = vectorizer.search_by_direction("蛋白质结构预测", limit=10)

# 按机构过滤
ids = vectorizer.search_by_profile("机器学习", institution="南方科技大学", limit=10)
```

**双向量设计说明：**

| 向量字段 | 来源文本 | 用途 |
|----------|----------|------|
| `profile_vector` | `profile_summary`（200-300 字画像摘要） | 宽泛语义搜索 |
| `direction_vector` | `research_directions`（逗号拼接） | 研究方向精确匹配 |

---

## 七、断点续跑

Pipeline 支持断点续跑：

- `enriched.jsonl` 采用追加写入模式
- 重启时自动按 `profile_url` 去重，跳过已处理的教授
- HTML 抓取结果缓存在 `logs/debug/professor_fetch_cache/`（SHA256(url) 命名），避免重复请求

```bash
# 第一次运行被中断后，再次运行会自动跳过已完成的教授
.venv/bin/python scripts/run_professor_enrichment_v2_e2e.py
```

---

## 八、种子文档格式

种子文档（默认为 `docs/教授 URL.md`）使用 Markdown 格式，以一级标题标注高校名，下方列出教师目录 URL：

```markdown
# 南方科技大学

https://www.sustech.edu.cn/zh/letter/

# 深圳大学

https://cmce.szu.edu.cn/jxky/szll.htm
https://csse.szu.edu.cn/pages/teacher/teacher.html
```

每所高校可以列多个种子 URL（不同学院的教师目录）。Pipeline 会自动递归发现子页面中的教授个人页链接。

---

## 九、LLM 调用层级

Pipeline 使用两级 LLM 兜底策略：

```
Tier 1: 本地 Qwen3.5-35B（快速、免费）
  ↓ 失败
Tier 2: DashScope qwen3.6-plus（在线、付费）
  ↓ 失败
Tier 3: 规则兜底（模板生成摘要）
```

- **Stage 2c（Agent 补全）**：先尝试本地 LLM → 失败则尝试 DashScope → 均失败则保留原有字段
- **Stage 3（摘要生成）**：先尝试 LLM 生成 → 失败则使用规则模板
- 所有 LLM 调用均非必需，Pipeline 在 LLM 全部不可用时仍能产出基础数据

---

## 十、质量门控

每个教授在发布前通过两级质量检查：

### L1 检查（硬性阻断，不通过则不发布）

- 姓名不为空
- 所属机构匹配深圳高校关键词
- 至少有一条 `official_site` 类型证据
- `profile_summary` 长度 >= 200 字
- `evaluation_summary` 长度 >= 100 字
- 摘要不包含模板占位符

### L2 检查（标记 quality_status，不阻断发布）

| 状态 | 含义 |
|------|------|
| `ready` | 数据完整，可直接用于检索回答 |
| `needs_review` | 存在可疑字段（如摘要过短或缺少研究方向） |
| `low_confidence` | 消歧置信度低或多项关键字段缺失 |

---

## 十一、常见问题

### Q: `uv run` 或 `uv sync` 报 SSL 错误

SUSTech PyPI 镜像偶发 SSL 证书问题。解决方案：

```bash
# 方案 1：直接使用 .venv/bin/python
.venv/bin/python scripts/run_professor_enrichment_v2_e2e.py

# 方案 2：临时切换 PyPI 源
UV_INDEX_URL=https://pypi.org/simple/ uv sync
```

### Q: Milvus 报错 `invalid index type: HNSW`

Milvus Lite 不支持 HNSW 索引。代码中已使用 `AUTOINDEX`，如遇此错误请确认使用最新版代码。

### Q: 嵌入接口返回 401/404

- **401**：确认 `API_KEY` 环境变量已设置
- **404**：确认模型 ID 为 `Qwen/Qwen3-Embedding-8B`（完整 HuggingFace 格式），而非短名

### Q: 大量教授被跳过（validation_failed）

检查日志中的 `skip_reasons`。常见原因：
- `no_official_evidence`：教授的 URL 域名不在官方域名列表中。需在 `_OFFICIAL_DOMAIN_SUFFIXES` 中添加缺失域名
- `missing_name_or_institution`：HTML 解析未能提取姓名或机构

### Q: 外部网站抓取报 SSL 错误

环境使用了 HTTP 代理（`100.64.0.15:7893`），部分 HTTPS 站点会因 SSL 握手失败。Pipeline 会自动使用 `logs/debug/professor_fetch_cache/` 中的缓存页面。如需更新缓存，请在无代理环境下运行一次抓取。

### Q: 如何添加新高校

1. 在种子文档中添加高校名（一级标题）和教师目录 URL
2. 在 `src/data_agents/professor/roster.py` 中添加站点特定的链接提取器（如果默认提取器不工作）
3. 在 `scripts/run_professor_publish_to_search.py` 的 `_OFFICIAL_DOMAIN_SUFFIXES` 中添加新高校的域名
4. 运行 `--limit 5 --institution 新高校名` 测试

---

## 十二、相关文档

| 文档 | 说明 |
|------|------|
| [教授数据采集 PRD](./Professor-Data-Agent-PRD.md) | 产品需求和数据模型定义 |
| [共享技术规范](./Data-Agent-Shared-Spec.md) | 四域共享架构、质量标准 |
| [Agentic RAG PRD](./Agentic-RAG-PRD.md) | 检索增强智能体服务层 |
| [部署经验文档](./solutions/professor-pipeline-v2-deployment-patterns-2026-04-05.md) | 基础设施和集成问题记录 |

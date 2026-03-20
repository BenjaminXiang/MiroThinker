# `jina_scrape_llm_summary.py` -- 网页抓取+LLM信息提取 MCP 服务器

## 文件概述

`jina_scrape_llm_summary.py` 是一个"抓取+提取"一体化的开发版 MCP 服务器。它将网页抓取（Jina AI）和信息提取（LLM 总结）组合为单一工具调用：先用 Jina 抓取网页内容，然后用 LLM 从内容中提取用户指定的信息。这比分别调用搜索和阅读工具更高效，特别适合需要从特定 URL 提取特定信息的场景。

## 关键代码解读

### 1. 核心工具：抓取并提取

```python
@mcp.tool()
async def scrape_and_extract_info(
    url: str, info_to_extract: str, custom_headers: Dict[str, str] = None
):
    # 第一步：用 Jina 抓取
    scrape_result = await scrape_url_with_jina(url, custom_headers)
    # Jina 失败则回退到直接 HTTP 抓取
    if not scrape_result["success"]:
        scrape_result = await scrape_url_with_python(url, custom_headers)
    # 第二步：用 LLM 提取信息
    extracted_result = await extract_info_with_llm(
        url=url, content=scrape_result["content"],
        info_to_extract=info_to_extract, model=SUMMARY_LLM_MODEL_NAME,
    )
```

两阶段流水线设计：
1. **抓取阶段**：优先使用 Jina AI（专业网页转文本服务），失败后回退到直接 HTTP 请求
2. **提取阶段**：将抓取的内容和提取需求一起发送给 LLM，由 LLM 完成信息提取

### 2. Jina 抓取（主方案）

```python
async def scrape_url_with_jina(url, custom_headers=None, max_chars=102400*4):
    jina_url = f"{JINA_BASE_URL}/{url}"
    headers = {"Authorization": f"Bearer {JINA_API_KEY}"}
    retry_delays = [1, 2, 4, 8]
    for attempt, delay in enumerate(retry_delays, 1):
        async with httpx.AsyncClient() as client:
            response = await client.get(jina_url, headers=headers, ...)
```

- 使用 `httpx` 异步 HTTP 客户端
- 最多 4 次重试，退避延迟 1s, 2s, 4s, 8s
- 内容限制为 409,600 字符（约 400KB），避免超长内容消耗过多 LLM token
- 检测 Jina 余额不足错误（`InsufficientBalanceError`）

### 3. Python 直接抓取（回退方案）

```python
async def scrape_url_with_python(url, custom_headers=None, max_chars=102400*4):
    headers = {"User-Agent": "Mozilla/5.0 ..."}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, ...)
```

当 Jina 不可用时，直接用 HTTP 请求抓取原始 HTML。虽然不如 Jina 的文本提取质量高，但作为回退方案可以保证基本可用性。

### 4. LLM 信息提取

```python
EXTRACT_INFO_PROMPT = """You are given a piece of content and the requirement...
INFORMATION TO EXTRACT: {}
CONTENT TO ANALYZE: {}
EXTRACTED INFORMATION:"""

async def extract_info_with_llm(url, content, info_to_extract, model, max_tokens=4096):
    prompt = get_prompt_with_truncation(info_to_extract, content)
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
```

- 使用结构化 prompt 指导 LLM 提取信息
- 当内容超过模型上下文长度时，自动截断末尾内容并重试（每次截断 40,960 字符）
- 支持 GPT-5 的 `service_tier` 和 `reasoning_effort` 参数，节省成本
- 检测重复输出（response 尾部重复超过 5 次则重试）

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `scrape_and_extract_info` | MCP 工具 | 抓取 URL 内容并用 LLM 提取指定信息 |
| `scrape_url_with_jina` | 异步函数 | 使用 Jina AI 抓取网页 |
| `scrape_url_with_python` | 异步函数 | 直接 HTTP 抓取网页（回退方案） |
| `extract_info_with_llm` | 异步函数 | 使用 LLM 从内容中提取信息 |
| `get_prompt_with_truncation` | 函数 | 构建带截断的提取 prompt |
| `_is_huggingface_dataset_or_space_url` | 函数 | HuggingFace 防护检查 |

## 与其他模块的关系

- **与 `searching_google_mcp_server.py` 的 `scrape_website` 不同**：此工具多了 LLM 信息提取步骤
- **需要三组环境变量**：Jina API（抓取）、Summary LLM（提取）的 URL/Key/Model
- **属于 dev_mcp_servers**：开发中的增强版工具，可能用于特定 Agent 配置

## 总结

`jina_scrape_llm_summary.py` 实现了"抓取-提取"两阶段流水线，将网页内容获取和信息提取合并为单一工具调用。双重抓取方案（Jina + Python 回退）、自动内容截断、重复检测等设计确保了在各种条件下的可靠性。这是一个比简单 `scrape_website` 更智能的信息获取工具。

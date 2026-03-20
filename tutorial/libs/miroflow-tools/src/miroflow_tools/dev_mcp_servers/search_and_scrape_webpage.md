# `search_and_scrape_webpage.py` -- 搜索与抓取一体化 MCP 服务器

## 文件概述

`search_and_scrape_webpage.py` 是一个开发版 MCP 服务器，将 Google 搜索（Serper API）和搜狗搜索（腾讯云 SearchPro API）整合到同一个服务器中。与正式版搜索工具相比，它包含一些增强功能，如搜索结果为空时自动去除引号重试、更细粒度的 URL 过滤等。

## 关键代码解读

### 1. 异步 Serper 请求

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(
        (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)
    ),
)
async def make_serper_request(payload, headers) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{SERPER_BASE_URL}/search", json=payload, headers=headers)
        response.raise_for_status()
        return response
```

与 `serper_mcp_server.py` 不同，此处使用 `httpx`（异步 HTTP 库）代替 `requests`（同步 HTTP 库）。`tenacity` 的 `@retry` 装饰器同样适用于异步函数。

### 2. 增强的 URL 过滤

```python
def _is_banned_url(url: str) -> bool:
    banned_list = [
        "unifuncs",
        "huggingface.co/datasets",
        "huggingface.co/spaces",
    ]
    return any(banned in url for banned in banned_list)
```

比标准版多了 `unifuncs` 域名的过滤，采用更通用的"禁止列表"设计，方便扩展。

### 3. 自动去引号重试

```python
organic_results, search_params = await perform_search(original_query)

# 如果结果为空且查询包含引号，去掉引号重试
if not organic_results and '"' in original_query:
    query_without_quotes = original_query.replace('"', "").strip()
    if query_without_quotes:
        organic_results, search_params = await perform_search(query_without_quotes)
```

这是一个实用的搜索优化：带引号的精确匹配查询如果没有结果，自动退回到模糊匹配。Agent 有时会在查询中加入不必要的引号，导致搜索结果为空。

### 4. 搜狗搜索集成

```python
@mcp.tool()
async def sogou_search(q: str, num: int = 10) -> str:
```

与 `searching_sogou_mcp_server.py` 中的实现类似，但整合到了同一个服务器中。验证 `num` 参数只能为 10/20/30/40/50。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `make_serper_request` | 异步函数 | 带重试的异步 Serper API 请求 |
| `make_sogou_request` | 异步函数 | 带重试的腾讯云搜索 API 请求 |
| `_is_banned_url` | 函数 | 检查 URL 是否在禁止列表中 |
| `google_search` | MCP 工具 | 执行 Google 搜索（带去引号重试） |
| `sogou_search` | MCP 工具 | 执行搜狗搜索 |

## 与其他模块的关系

- **是 `searching_google_mcp_server.py` 和 `searching_sogou_mcp_server.py` 的整合增强版**
- **依赖 `mcp_servers/utils/url_unquote.py`**：通过相对导入使用 URL 解码工具
- **属于 dev_mcp_servers**：开发版工具，包含实验性的增强功能
- **需要 Serper 和腾讯云 API 凭证**

## 总结

`search_and_scrape_webpage.py` 将 Google 搜索和搜狗搜索整合到单一 MCP 服务器中，并加入了自动去引号重试、扩展的 URL 过滤等增强功能。使用 `httpx` 异步 HTTP 库和 `tenacity` 重试库确保了性能和可靠性。作为开发版工具，它代表了搜索功能的演进方向。

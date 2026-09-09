# `serper_mcp_server.py` -- Serper API 底层搜索服务器

## 文件概述

`serper_mcp_server.py` 是 Google 搜索功能的底层实现，直接与 Serper API 通信。它被 `searching_google_mcp_server.py` 作为子进程调用（MCP 嵌套），也可以独立使用。与上层封装不同，此文件负责构建 HTTP 请求、处理 API 响应、过滤 HuggingFace 链接和解码 URL 编码。

## 关键代码解读

### 1. 带重试的 API 请求

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(
        (requests.ConnectionError, requests.Timeout, requests.HTTPError)
    ),
)
def make_serper_request(payload, headers) -> requests.Response:
    response = requests.post(f"{SERPER_BASE_URL}/search", json=payload, headers=headers)
    response.raise_for_status()
    return response
```

使用 `tenacity` 库实现声明式重试：
- `stop_after_attempt(3)`：最多 3 次尝试
- `wait_exponential(multiplier=1, min=4, max=10)`：指数退避，等待 4~10 秒
- `retry_if_exception_type`：仅在网络错误和 HTTP 错误时重试

### 2. HuggingFace 链接过滤

```python
organic_results = []
if "organic" in data:
    for item in data["organic"]:
        if _is_huggingface_dataset_or_space_url(item.get("link", "")):
            continue
        organic_results.append(item)
```

从搜索结果中移除指向 HuggingFace 数据集和空间的链接。这是防止 Agent 直接从评测数据集获取答案的多层防护之一（ToolManager 中也有检查）。

### 3. URL 解码

```python
response_data = decode_http_urls_in_dict(response_data)
```

调用 `utils/url_unquote.py` 中的工具函数，将搜索结果中 URL 编码的中文字符（如 `%E4%B8%AD%E6%96%87`）解码为可读文本，同时保留不能解码的保留字符（如 `%2F` 表示的 `/`）。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `make_serper_request` | 函数 | 带自动重试的 Serper API HTTP 请求 |
| `_is_huggingface_dataset_or_space_url` | 函数 | 检查 URL 是否指向 HuggingFace 数据集 |
| `google_search` | MCP 工具 | 执行 Google 搜索并返回处理后的结果 |

## 与其他模块的关系

- **被 `searching_google_mcp_server.py` 嵌套调用**：作为子进程通过 MCP 协议通信
- **依赖 `utils/url_unquote.py`**：使用 URL 解码工具
- **依赖 `tenacity`**：用于声明式重试逻辑
- **需要 `SERPER_API_KEY`**：Serper 是一个商业 Google 搜索 API 服务

## 总结

`serper_mcp_server.py` 是 Google 搜索的直接 API 对接层。它通过 `tenacity` 实现了声明式重试，通过 URL 解码提升了搜索结果的可读性，并通过 HuggingFace 链接过滤增强了评测安全性。作为底层服务器，它被上层的 `searching_google_mcp_server.py` 封装和增强。

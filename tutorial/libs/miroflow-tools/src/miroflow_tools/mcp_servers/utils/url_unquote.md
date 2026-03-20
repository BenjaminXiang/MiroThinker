# `url_unquote.py` -- URL 解码与 Markdown 清理工具

## 文件概述

`url_unquote.py` 提供了三个文本处理工具函数，被搜索和抓取相关的 MCP 服务器广泛使用。它解决两个问题：一是将搜索结果中的 URL 编码字符（如中文的百分号编码）解码为可读文本；二是从网页抓取结果中移除 Markdown 链接和图片语法，减少传递给 LLM 的 token 数量。

## 关键代码解读

### 1. 安全 URL 解码 `safe_unquote`

```python
RESERVED_PERCENT_ENCODINGS = frozenset({
    "%2f", "%2F",  # /  路径分隔符
    "%3f", "%3F",  # ?  查询字符串起始
    "%23",         # #  片段标识符
    "%26",         # &  查询参数分隔符
    "%3d", "%3D",  # =  键值分隔符
    "%25",         # %  百分号本身
    "%20",         # 空格
    # ... 更多 RFC 3986 保留字符
})

def safe_unquote(url: str) -> str:
```

这个函数的设计考量很精妙。标准的 `urllib.parse.unquote` 会解码所有百分号编码，但这可能破坏 URL 结构。例如：
- `%2F` 解码为 `/` 会改变路径层级
- `%3F` 解码为 `?` 会引入虚假的查询字符串
- `%25` 解码为 `%` 可能导致二次解码问题

`safe_unquote` 只解码不会改变 URL 语义的字符（如中文字符 `%E4%B8%AD` -> `中`），保留所有 RFC 3986 保留字符的编码形式。

### 2. UTF-8 多字节序列处理

```python
# 收集连续的百分号编码序列
encoded_sequence = percent_encoded
j = i + 3
while j + 2 < n and url[j] == "%":
    next_hex = url[j + 1 : j + 3]
    if all(c in "0123456789ABCDEFabcdef" for c in next_hex):
        next_encoded = url[j : j + 3]
        if next_encoded in RESERVED_PERCENT_ENCODINGS:
            break
        encoded_sequence += next_encoded
        j += 3
# 整体解码
decoded = unquote(encoded_sequence)
```

中文等多字节 UTF-8 字符在 URL 中由多个 `%XX` 序列表示（如"中"= `%E4%B8%AD`）。代码先收集连续的编码序列，然后一次性解码，确保多字节字符正确还原。

### 3. 递归字典 URL 解码

```python
def decode_http_urls_in_dict(data):
    if isinstance(data, str):
        if "%" in data and "http" in data:
            return safe_unquote(data)
        else:
            return data
    elif isinstance(data, list):
        return [decode_http_urls_in_dict(item) for item in data]
    elif isinstance(data, dict):
        return {key: decode_http_urls_in_dict(value) for key, value in data.items()}
    else:
        return data
```

递归遍历搜索结果的嵌套数据结构（字典、列表、字符串），只对包含 `%` 和 `http` 的字符串应用 `safe_unquote`。这避免了对非 URL 字符串的误处理。

### 4. Markdown 链接剥离

```python
md = MarkdownIt("commonmark")

def strip_markdown_links(markdown: str) -> str:
    tokens = md.parse(markdown)
    def render(ts):
        for tok in ts:
            if t == "link_open" or t == "link_close":
                continue  # 跳过链接标签，保留链接文本
            if t == "image":
                continue  # 完全移除图片
            # ... 处理其他 token
    text = render(tokens)
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"
    return text.strip()
```

使用 `markdown-it` 解析器将 Markdown 解析为 token 树，然后选择性渲染：
- **链接**：移除链接语法 `[text](url)`，只保留 `text`
- **图片**：完全移除 `![alt](url)`
- **换行和段落**：保留结构，规范化多余空行

这大幅减少了网页抓取结果的 token 数量，因为 URL 通常很长但对 LLM 理解内容没有帮助。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `RESERVED_PERCENT_ENCODINGS` | 常量集合 | RFC 3986 保留字符的百分号编码，解码时跳过 |
| `safe_unquote` | 函数 | 安全地解码 URL，只解码非保留字符 |
| `decode_http_urls_in_dict` | 函数 | 递归遍历数据结构，对所有 URL 字符串应用安全解码 |
| `strip_markdown_links` | 函数 | 从 Markdown 文本中移除链接和图片语法 |

## 与其他模块的关系

- **被 `serper_mcp_server.py` 使用**：解码搜索结果中的 URL
- **被 `searching_google_mcp_server.py` 使用**：清理网页抓取内容
- **被 `searching_sogou_mcp_server.py` 使用**：清理网页抓取内容
- **被 `dev_mcp_servers/search_and_scrape_webpage.py` 使用**：解码搜索结果 URL
- **通过 `utils/__init__.py` 导出**：`safe_unquote`、`decode_http_urls_in_dict`、`strip_markdown_links`

## 总结

`url_unquote.py` 是一个精心设计的文本处理工具集。`safe_unquote` 通过维护 RFC 3986 保留字符集实现了语义安全的 URL 解码，解决了标准库 `unquote` 可能破坏 URL 结构的问题。`strip_markdown_links` 通过 AST 级别的 Markdown 解析实现了精确的链接剥离，避免了正则表达式方案的边界问题。这两个工具共同提升了搜索结果的可读性和 token 效率。

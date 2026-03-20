# utils -- 工具函数库

## 模块概述

`utils/` 目录包含被多个 MCP 服务器共享的工具函数。当前只有一个文件 `url_unquote.py`，提供 URL 解码和 Markdown 文本清理功能。这些函数通过 `utils/__init__.py` 统一导出，方便其他模块导入使用。

## 架构图

```
utils/
├── __init__.py          # 统一导出接口
│   导出: safe_unquote
│         decode_http_urls_in_dict
│         strip_markdown_links
│
└── url_unquote.py       # 实现文件
    │
    ├── safe_unquote()               ←── serper_mcp_server.py
    │   安全URL解码                       search_and_scrape_webpage.py
    │   (保留RFC3986保留字符)
    │
    ├── decode_http_urls_in_dict()   ←── serper_mcp_server.py
    │   递归遍历数据结构解码URL            search_and_scrape_webpage.py
    │
    └── strip_markdown_links()       ←── searching_google_mcp_server.py
        移除Markdown链接和图片              searching_sogou_mcp_server.py
```

## 文件总览表

| 文件 | 导出函数 | 用途 | 被使用于 | 文档 |
|------|----------|------|----------|------|
| `url_unquote.py` | `safe_unquote` | 安全解码 URL 中的百分号编码字符 | serper, search_and_scrape | [详情](url_unquote.md) |
| `url_unquote.py` | `decode_http_urls_in_dict` | 递归遍历字典/列表，解码所有 URL | serper, search_and_scrape | [详情](url_unquote.md) |
| `url_unquote.py` | `strip_markdown_links` | 从 Markdown 中移除链接和图片语法 | searching_google, searching_sogou | [详情](url_unquote.md) |

## 导入方式

```python
# 从 utils 包导入（推荐）
from .utils import strip_markdown_links
from .utils import decode_http_urls_in_dict

# 从具体文件导入
from .utils.url_unquote import safe_unquote
```

## 设计原则

- **单一职责**：每个函数只做一件事
- **无副作用**：所有函数都是纯函数，不修改输入参数
- **防御性编程**：`safe_unquote` 对空字符串、无效编码等边界情况都有处理
- **语义安全**：URL 解码不会改变 URL 的结构语义

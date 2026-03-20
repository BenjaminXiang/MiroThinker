# `searching_sogou_mcp_server.py` -- 搜狗搜索与网页抓取 MCP 服务器

## 文件概述

`searching_sogou_mcp_server.py` 是搜索工具的中文优化版本。它通过腾讯云 SearchPro API（搜狗搜索引擎）执行网页搜索，在中文查询场景下比 Google 搜索能返回更好的结果。同时也包含一个与 Google 搜索版相同的网页抓取工具（基于 Jina AI）。

## 关键代码解读

### 1. 腾讯云 API 调用

```python
@mcp.tool()
async def sogou_search(Query: str, Cnt: int = 10) -> str:
    cred = credential.Credential(TENCENTCLOUD_SECRET_ID, TENCENTCLOUD_SECRET_KEY)
    httpProfile = HttpProfile()
    httpProfile.endpoint = "wsa.tencentcloudapi.com"
    clientProfile = ClientProfile()
    clientProfile.httpProfile = httpProfile

    params = f'{{"Query":"{Query}","Mode":0, "Cnt":{Cnt}}}'
    common_client = CommonClient("wsa", "2025-05-08", cred, "", profile=clientProfile)
    result = common_client.call_json("SearchPro", json.loads(params))["Response"]
```

使用腾讯云 SDK 调用 SearchPro API 的标准流程：
1. 创建凭证对象（需要 `TENCENTCLOUD_SECRET_ID` 和 `TENCENTCLOUD_SECRET_KEY`）
2. 配置 HTTP 端点
3. 通过 `CommonClient` 发送请求
4. API 版本为 `2025-05-08`，服务标识为 `wsa`

### 2. 搜索结果精简

```python
for page in result["Pages"]:
    page_json = json.loads(page)
    new_page = {}
    new_page["title"] = page_json["title"]
    new_page["url"] = page_json["url"]
    new_page["passage"] = page_json["passage"]
    new_page["date"] = page_json["date"]
    new_page["site"] = page_json["site"]
    pages.append(new_page)
```

API 返回的原始数据包含很多字段（content、favicon 等），但工具只保留 5 个核心字段：标题、URL、摘要、日期、站点。这减少了传递给 LLM 的数据量。

### 3. 网页抓取工具

此文件中的 `scrape_website` 与 `searching_google_mcp_server.py` 中的实现完全相同（使用 Jina AI），两个服务器各自内置了抓取功能，避免了跨服务器依赖。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `sogou_search` | MCP 工具 | 通过腾讯云 SearchPro API 执行搜狗搜索 |
| `scrape_website` | MCP 工具 | 通过 Jina AI 抓取网页内容 |

## 与其他模块的关系

- **与 `searching_google_mcp_server.py` 互补**：Google 搜索擅长英文，搜狗搜索擅长中文
- **依赖腾讯云 SDK**：需要 `tencentcloud-sdk-python` 包
- **依赖 Jina AI**：网页抓取功能需要 `JINA_API_KEY`
- **调用 `utils/strip_markdown_links`**：清理抓取内容中的 Markdown 链接

## 总结

`searching_sogou_mcp_server.py` 为 MiroThinker 提供了中文搜索能力。通过腾讯云 SearchPro API 接入搜狗搜索引擎，配合内置的 Jina 网页抓取工具，形成了完整的中文信息获取链。搜索结果经过精简处理，只保留 LLM 需要的核心字段。

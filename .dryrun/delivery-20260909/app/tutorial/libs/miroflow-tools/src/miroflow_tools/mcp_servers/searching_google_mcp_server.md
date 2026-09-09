# `searching_google_mcp_server.py` -- Google 搜索与网页抓取 MCP 服务器

## 文件概述

`searching_google_mcp_server.py` 是 MiroThinker 最重要的信息获取工具之一。它提供了四个工具：Google 搜索（通过 Serper API）、网页抓取（通过 Jina AI）、Wikipedia 页面查询和修订历史查询、以及 Wayback Machine 网页存档查询。这些工具共同构成了 Agent 的"信息获取层"。

## 关键代码解读

### 1. Google 搜索结果过滤

```python
REMOVE_SNIPPETS = os.environ.get("REMOVE_SNIPPETS", "").lower() in ("true", "1", "yes")
REMOVE_KNOWLEDGE_GRAPH = os.environ.get("REMOVE_KNOWLEDGE_GRAPH", "").lower() in ("true", "1", "yes")
REMOVE_ANSWER_BOX = os.environ.get("REMOVE_ANSWER_BOX", "").lower() in ("true", "1", "yes")

def filter_google_search_result(result_content: str) -> str:
    data = json.loads(result_content)
    if REMOVE_KNOWLEDGE_GRAPH and "knowledgeGraph" in data:
        del data["knowledgeGraph"]
    if REMOVE_ANSWER_BOX and "answerBox" in data:
        del data["answerBox"]
    if REMOVE_SNIPPETS:
        if "organic" in data:
            for item in data["organic"]:
                if "snippet" in item:
                    del item["snippet"]
```

这个过滤机制通过环境变量控制，可以移除搜索结果中的代码片段（snippets）、知识图谱（Knowledge Graph）和答案框（Answer Box）。在基准测试场景中，这些直接答案可能会"泄露"答案，因此需要过滤。

### 2. Google 搜索工具

```python
@mcp.tool()
async def google_search(q, gl="us", hl="en", location=None, num=10, tbs=None, page=1):
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "miroflow_tools.mcp_servers.serper_mcp_server"],
        env={"SERPER_API_KEY": SERPER_API_KEY, "SERPER_BASE_URL": SERPER_BASE_URL},
    )
```

注意这里的架构：`searching_google_mcp_server` 内部启动了另一个 MCP 服务器 `serper_mcp_server` 作为子进程。这是 MCP 嵌套调用的又一个例子。参数包括地区代码（gl）、语言（hl）、位置（location）和时间过滤（tbs）。

### 3. 网页抓取工具

```python
@mcp.tool()
async def scrape_website(url: str) -> str:
    # 防止重复 Jina URL 前缀
    if url.startswith("https://r.jina.ai/") and url.count("http") >= 2:
        url = url[len("https://r.jina.ai/"):]
    # 阻止抓取 HuggingFace 数据集
    if "huggingface.co/datasets" in url or "huggingface.co/spaces" in url:
        return "You are trying to scrape a Hugging Face dataset..."
    # 使用 Jina Reader API 抓取
    jina_url = f"{JINA_BASE_URL}/{url}"
    headers = {"Authorization": f"Bearer {JINA_API_KEY}"}
    response = requests.get(jina_url, headers=headers, timeout=60)
    content = strip_markdown_links(content)
```

Jina Reader API 的使用方式很简洁：将目标 URL 拼接到 Jina 基地址后面即可。Jina 会自动渲染 JavaScript、提取主要内容、转换为适合 LLM 阅读的文本格式。最后通过 `strip_markdown_links` 移除 Markdown 链接语法，减少 token 消耗。

### 4. Wikipedia 和 Wayback Machine 工具（已注释）

```python
# @mcp.tool()  -- 被注释，但代码保留
async def wiki_get_page_content(entity, first_sentences=10):
async def search_wiki_revision(entity, year, month, max_revisions=50):
async def search_archived_webpage(url, year, month, day):
```

这三个工具当前被注释掉（`@mcp.tool()` 前加了 `#`），说明在当前配置中未启用，但代码完整保留供需要时使用。它们分别提供 Wikipedia 页面内容获取、修订历史查询和 Wayback Machine 存档查询。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `filter_google_search_result` | 函数 | 根据环境变量过滤搜索结果中的特定字段 |
| `google_search` | MCP 工具 | 通过 Serper API 执行 Google 搜索 |
| `scrape_website` | MCP 工具 | 通过 Jina AI 抓取网页内容 |
| `wiki_get_page_content` | 函数（未启用） | 获取 Wikipedia 页面内容 |
| `search_wiki_revision` | 函数（未启用） | 查询 Wikipedia 修订历史 |
| `search_archived_webpage` | 函数（未启用） | 查询 Wayback Machine 存档 |

## 与其他模块的关系

- **调用 `serper_mcp_server.py`**：Google 搜索通过嵌套 MCP 调用实现
- **调用 `utils/url_unquote.py`**：使用 `strip_markdown_links` 清理抓取的内容
- **需要 `SERPER_API_KEY` 和 `JINA_API_KEY`**：分别用于搜索和网页抓取
- **与 `searching_sogou_mcp_server.py` 互补**：前者用于英文搜索，后者用于中文搜索

## 总结

`searching_google_mcp_server.py` 是 Agent 的核心信息获取工具。它将 Google 搜索和网页抓取封装为 MCP 工具，并提供了可配置的结果过滤、HuggingFace 防护和 Markdown 清理等功能。Wikipedia 和 Wayback Machine 工具虽暂未启用，但为时间敏感型研究任务保留了能力。

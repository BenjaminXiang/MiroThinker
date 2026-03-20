# dev_mcp_servers -- 开发版 MCP 工具服务器

## 模块概述

`dev_mcp_servers/` 目录包含处于开发或实验阶段的 MCP 工具服务器。这些服务器通常是正式版工具的增强版、组合版或替代方案。它们可能被特定的 Agent 配置使用（通过 Hydra 配置选择），但不是默认启用的。

## 架构图

```
                    ToolManager (manager.py)
                           │
                    ┌──────▼──────┐
                    │ dev_mcp_    │
                    │ servers/    │
                    └──┬──┬──┬──┬┘
                       │  │  │  │
    ┌──────────────────┘  │  │  └──────────────────┐
    │                     │  │                     │
    ▼                     ▼  ▼                     ▼
┌──────────────┐ ┌────────────────┐ ┌──────────┐ ┌──────────────┐
│jina_scrape_  │ │search_and_     │ │stateless_│ │task_planner  │
│llm_summary   │ │scrape_webpage  │ │python_   │ │.py           │
│.py           │ │.py             │ │server.py │ │              │
│              │ │                │ │          │ │ 任务计划管理  │
│ 抓取+LLM    │ │ Google+搜狗    │ │ 无状态   │ │ CRUD操作     │
│ 信息提取     │ │ 整合搜索       │ │ Python   │ │ JSON持久化   │
│              │ │ 去引号重试     │ │ 执行     │ │ 并发隔离     │
└──────┬───────┘ └───────┬────────┘ └────┬─────┘ └──────┬───────┘
       │                 │               │              │
       ▼                 ▼               ▼              ▼
   Jina AI +        Serper API +      E2B 沙箱      JSON 文件
   自定义 LLM       腾讯云 API       (一次性)
```

## 文件总览表

| 文件 | 工具 | 功能定位 | 对应的正式版 | 文档 |
|------|------|----------|-------------|------|
| `jina_scrape_llm_summary.py` | `scrape_and_extract_info` | 抓取网页 + LLM 提取信息 | `scrape_website`（仅抓取） | [详情](jina_scrape_llm_summary.md) |
| `search_and_scrape_webpage.py` | `google_search`, `sogou_search` | 整合双搜索引擎 + 增强功能 | 分离的 google/sogou 服务器 | [详情](search_and_scrape_webpage.md) |
| `stateless_python_server.py` | `python` | 无状态一次性代码执行 | `python_mcp_server.py`（有状态） | [详情](stateless_python_server.md) |
| `task_planner.py` | `add_todo`, `list_todos`, `complete_todo`, `delete_todo` | Agent 工作流管理 | 无对应正式版 | [详情](task_planner.md) |

## 与正式版的区别

### jina_scrape_llm_summary vs scrape_website
正式版的 `scrape_website` 只负责抓取网页内容返回原文。开发版多了一个 LLM 提取步骤，能直接回答"这个网页中关于 X 的信息是什么"，减少 Agent 需要处理的上下文量。

### search_and_scrape_webpage vs searching_google/sogou
正式版将 Google 搜索和搜狗搜索分在两个独立服务器中。开发版将它们整合到一个服务器，并增加了自动去引号重试等增强功能。

### stateless_python_server vs python_mcp_server
正式版提供完整的沙箱生命周期管理（创建、执行、文件传输、销毁）。开发版极简化为单一工具，每次调用自动创建和销毁沙箱。

### task_planner（独有）
任务计划工具是开发版独有的元工具，帮助 Agent 组织多步骤任务的执行流程。

## 环境变量汇总

| 变量名 | 用途 | 使用文件 |
|--------|------|----------|
| `JINA_API_KEY/BASE_URL` | 网页抓取 | jina_scrape_llm_summary |
| `SUMMARY_LLM_BASE_URL/MODEL_NAME/API_KEY` | 信息提取 LLM | jina_scrape_llm_summary |
| `SERPER_API_KEY/BASE_URL` | Google 搜索 | search_and_scrape_webpage |
| `TENCENTCLOUD_SECRET_ID/KEY` | 搜狗搜索 | search_and_scrape_webpage |
| `E2B_API_KEY` | 代码沙箱 | stateless_python_server |
| `TASK_ID` | 任务隔离标识 | task_planner |
| `TODO_DATA_DIR` | 任务数据存储目录 | task_planner |

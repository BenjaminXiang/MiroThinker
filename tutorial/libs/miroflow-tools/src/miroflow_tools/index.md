# miroflow_tools -- MiroThinker 工具库总览

## 模块概述

`miroflow_tools` 是 MiroThinker 项目的共享工具库，为 Agent 提供与外部世界交互的全部能力。它基于 MCP（Model Context Protocol）标准化工具调用协议，将搜索、抓取、代码执行、视觉理解、音频处理、推理增强等能力封装为独立的 MCP 服务器，由核心的 `ToolManager` 统一管理和调度。

## 架构图

```
                        ┌──────────────────────────────┐
                        │       miroflow-agent         │
                        │  (Orchestrator / Pipeline)   │
                        └─────────────┬────────────────┘
                                      │ 调用
                        ┌─────────────▼────────────────┐
                        │        ToolManager           │
                        │       (manager.py)           │
                        │  统一管理 MCP 服务器连接/调用  │
                        └──┬──────┬──────┬──────┬──────┘
                           │      │      │      │
              ┌────────────┤      │      │      ├────────────┐
              │            │      │      │      │            │
    ┌─────────▼──┐ ┌──────▼───┐ ┌▼──────▼┐ ┌──▼────────┐ ┌─▼──────────┐
    │ mcp_servers │ │ 搜索服务 │ │代码执行│ │ 视觉/音频 │ │dev_mcp_    │
    │            │ │          │ │        │ │           │ │servers     │
    │ - browser  │ │ - google │ │-python │ │ - vision  │ │ - scrape+  │
    │   session  │ │ - sogou  │ │-reading│ │ - audio   │ │   extract  │
    │ - serper   │ │          │ │        │ │ - reason  │ │ - search+  │
    │            │ │          │ │        │ │           │ │   scrape   │
    │   utils/   │ │          │ │        │ │           │ │ - stateless│
    │-url_unquote│ │          │ │        │ │           │ │   python   │
    │            │ │          │ │        │ │           │ │ - task     │
    │            │ │          │ │        │ │           │ │   planner  │
    └────────────┘ └──────────┘ └────────┘ └───────────┘ └────────────┘
```

## 目录结构

```
miroflow_tools/
├── __init__.py              # 包入口，导出 ToolManager
├── manager.py               # 核心工具管理器
├── mcp_servers/             # 正式版 MCP 服务器
│   ├── audio_mcp_server.py        # 音频处理（OpenAI）
│   ├── audio_mcp_server_os.py     # 音频处理（自部署 Whisper）
│   ├── browser_session.py         # Playwright 持久化浏览器会话
│   ├── python_mcp_server.py       # Python 沙箱（E2B，有状态）
│   ├── reading_mcp_server.py      # 文档格式转换
│   ├── reasoning_mcp_server.py    # 深度推理（Anthropic Claude）
│   ├── reasoning_mcp_server_os.py # 深度推理（自部署模型）
│   ├── searching_google_mcp_server.py  # Google 搜索 + 网页抓取
│   ├── searching_sogou_mcp_server.py   # 搜狗搜索 + 网页抓取
│   ├── serper_mcp_server.py       # Serper API 底层搜索
│   ├── vision_mcp_server.py       # 视觉问答（OpenAI GPT-4o）
│   ├── vision_mcp_server_os.py    # 视觉问答（自部署 VLM）
│   └── utils/
│       └── url_unquote.py         # URL 解码与 Markdown 清理
└── dev_mcp_servers/         # 开发版 MCP 服务器
    ├── jina_scrape_llm_summary.py    # 抓取+LLM 信息提取
    ├── search_and_scrape_webpage.py  # 整合搜索（Google+搜狗）
    ├── stateless_python_server.py    # 无状态 Python 执行
    └── task_planner.py               # 任务计划管理
```

## 文件总览表

| 文件 | 功能 | 关键依赖 | 文档 |
|------|------|----------|------|
| `manager.py` | 统一管理所有 MCP 服务器的连接和工具调用 | mcp SDK | [manager.md](manager.md) |
| `mcp_servers/audio_mcp_server.py` | 音频转录和问答（OpenAI） | openai, mutagen | [audio_mcp_server.md](mcp_servers/audio_mcp_server.md) |
| `mcp_servers/audio_mcp_server_os.py` | 音频转录（自部署 Whisper） | openai, mutagen | [audio_mcp_server_os.md](mcp_servers/audio_mcp_server_os.md) |
| `mcp_servers/browser_session.py` | 持久化 Playwright 浏览器会话 | mcp SDK | [browser_session.md](mcp_servers/browser_session.md) |
| `mcp_servers/python_mcp_server.py` | 有状态 Python 沙箱（E2B） | e2b_code_interpreter | [python_mcp_server.md](mcp_servers/python_mcp_server.md) |
| `mcp_servers/reading_mcp_server.py` | 文档格式转 Markdown | markitdown-mcp | [reading_mcp_server.md](mcp_servers/reading_mcp_server.md) |
| `mcp_servers/reasoning_mcp_server.py` | 深度推理（Claude 扩展思考） | anthropic | [reasoning_mcp_server.md](mcp_servers/reasoning_mcp_server.md) |
| `mcp_servers/reasoning_mcp_server_os.py` | 深度推理（自部署模型） | requests | [reasoning_mcp_server_os.md](mcp_servers/reasoning_mcp_server_os.md) |
| `mcp_servers/searching_google_mcp_server.py` | Google 搜索 + 网页抓取 | serper, jina | [searching_google_mcp_server.md](mcp_servers/searching_google_mcp_server.md) |
| `mcp_servers/searching_sogou_mcp_server.py` | 搜狗搜索 + 网页抓取 | 腾讯云 SDK, jina | [searching_sogou_mcp_server.md](mcp_servers/searching_sogou_mcp_server.md) |
| `mcp_servers/serper_mcp_server.py` | Serper API 底层搜索 | requests, tenacity | [serper_mcp_server.md](mcp_servers/serper_mcp_server.md) |
| `mcp_servers/vision_mcp_server.py` | 视觉问答（GPT-4o） | openai | [vision_mcp_server.md](mcp_servers/vision_mcp_server.md) |
| `mcp_servers/vision_mcp_server_os.py` | 视觉问答（自部署 VLM） | aiohttp, requests | [vision_mcp_server_os.md](mcp_servers/vision_mcp_server_os.md) |
| `mcp_servers/utils/url_unquote.py` | URL 解码与 Markdown 清理 | markdown-it | [url_unquote.md](mcp_servers/utils/url_unquote.md) |
| `dev_mcp_servers/jina_scrape_llm_summary.py` | 抓取+LLM 信息提取 | httpx, jina | [jina_scrape_llm_summary.md](dev_mcp_servers/jina_scrape_llm_summary.md) |
| `dev_mcp_servers/search_and_scrape_webpage.py` | 整合搜索（Google+搜狗） | httpx, tenacity | [search_and_scrape_webpage.md](dev_mcp_servers/search_and_scrape_webpage.md) |
| `dev_mcp_servers/stateless_python_server.py` | 无状态 Python 执行 | e2b_code_interpreter | [stateless_python_server.md](dev_mcp_servers/stateless_python_server.md) |
| `dev_mcp_servers/task_planner.py` | 任务计划管理 | (无外部依赖) | [task_planner.md](dev_mcp_servers/task_planner.md) |

## 核心设计理念

### 1. MCP 协议标准化
所有工具通过 MCP 协议暴露，ToolManager 只需要知道 MCP 协议就能与任何工具通信。添加新工具不需要修改 ToolManager 代码。

### 2. 双版本策略（标准版 + _os 版）
音频、视觉、推理三类工具都提供标准版（使用商业 API）和开源版（使用自部署模型）。通过 Hydra 配置切换，无需修改代码。

### 3. 多层安全防护
- ToolManager 级别的工具黑名单
- 各服务器级别的 HuggingFace 数据集抓取阻止
- 沙箱路径检测，防止跨环境访问
- 结果截断，防止上下文溢出

### 4. 鲁棒性设计
- 所有网络请求都有重试机制（指数退避 + 随机抖动）
- 抓取工具有回退方案（Jina -> 直接 HTTP）
- scrape 失败时回退到 MarkItDown
- 无效 sandbox_id 检测

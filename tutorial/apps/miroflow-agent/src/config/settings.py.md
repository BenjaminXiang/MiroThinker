# `settings.py` — 配置管理与 MCP 服务器参数生成

## 文件概述

`settings.py` 是 MiroThinker 智能体框架的**核心配置文件**。它承担三个关键职责：

1. **加载环境变量**：从 `.env` 文件中读取所有外部服务的 API 密钥和 Base URL
2. **生成 MCP 服务器参数**：根据 Hydra 配置动态创建每个工具对应的 MCP 服务器启动配置
3. **管理子智能体和环境信息**：将子智能体暴露为工具定义，收集运行时环境信息

在项目中，这个文件是系统启动的"第一站"——`Pipeline`（流水线）模块在初始化时会调用这里的函数来准备所有工具。

## 关键代码解读

### 第一部分：环境变量加载

```python
from dotenv import load_dotenv
load_dotenv()

# API for Google Search
SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
SERPER_BASE_URL = os.environ.get("SERPER_BASE_URL", "https://google.serper.dev")

# API for Web Scraping
JINA_API_KEY = os.environ.get("JINA_API_KEY")
JINA_BASE_URL = os.environ.get("JINA_BASE_URL", "https://r.jina.ai")

# API for Linux Sandbox
E2B_API_KEY = os.environ.get("E2B_API_KEY")
```

**解释**：

- `load_dotenv()` 从项目根目录的 `.env` 文件加载环境变量到 `os.environ` 中
- 每个外部服务都有一对变量：API 密钥（必需）和 Base URL（可选，有默认值）
- 这些变量作为**模块级常量**定义，在模块被导入时就会立即求值
- 涵盖的服务包括：Google 搜索（Serper）、网页抓取（Jina）、代码沙箱（E2B）、语音转写（Whisper）、视觉问答（Vision）、推理模型（Reasoning）、商业 LLM（Anthropic/OpenAI）等

### 第二部分：MCP 服务器参数生成

```python
def create_mcp_server_parameters(cfg: DictConfig, agent_cfg: DictConfig):
    configs = []

    if (
        agent_cfg.get("tools", None) is not None
        and "tool-google-search" in agent_cfg["tools"]
    ):
        if not SERPER_API_KEY:
            raise ValueError(
                "SERPER_API_KEY not set, tool-google-search will be unavailable."
            )
        configs.append(
            {
                "name": "tool-google-search",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "miroflow_tools.mcp_servers.searching_google_mcp_server"],
                    env={
                        "SERPER_API_KEY": SERPER_API_KEY,
                        "SERPER_BASE_URL": SERPER_BASE_URL,
                        "JINA_API_KEY": JINA_API_KEY,
                        "JINA_BASE_URL": JINA_BASE_URL,
                    },
                ),
            }
        )
    # ... 类似的 if 块为每种工具生成配置 ...

    blacklist = set()
    for black_list_item in agent_cfg.get("tool_blacklist", []):
        blacklist.add((black_list_item[0], black_list_item[1]))
    return configs, blacklist
```

**解释**：

- 该函数接收 Hydra 全局配置 `cfg` 和智能体特定配置 `agent_cfg`
- 遍历 `agent_cfg["tools"]` 中列出的每个工具名称，为其生成 `StdioServerParameters`
- `StdioServerParameters` 是 MCP 协议的标准启动参数，包含：
  - `command`：执行命令（当前 Python 解释器）
  - `args`：命令行参数（`-m` 模式运行对应的 MCP 服务器模块）
  - `env`：传递给子进程的环境变量（仅传递该工具需要的密钥）
- 如果必需的 API 密钥缺失，会抛出 `ValueError` 而不是静默失败
- 最后处理 `tool_blacklist`，返回一个 `(server_name, tool_name)` 元组集合，用于屏蔽某些工具

**支持的工具类型**（共 14 种）：

| 工具名 | 对应的 MCP 服务器模块 |
|--------|----------------------|
| `tool-google-search` | `searching_google_mcp_server` |
| `tool-sogou-search` | `searching_sogou_mcp_server` |
| `tool-python` | `python_mcp_server` |
| `tool-vqa` / `tool-vqa-os` | `vision_mcp_server` / `vision_mcp_server_os` |
| `tool-transcribe` / `tool-transcribe-os` | `audio_mcp_server` / `audio_mcp_server_os` |
| `tool-reasoning` / `tool-reasoning-os` | `reasoning_mcp_server` / `reasoning_mcp_server_os` |
| `tool-reader` | `markitdown_mcp` |
| `tool-reading` | `reading_mcp_server` |
| `search_and_scrape_webpage` | `search_and_scrape_webpage` |
| `jina_scrape_llm_summary` | `jina_scrape_llm_summary` |
| `stateless_python` | `stateless_python_server` |
| `task_planner` | `task_planner`（每次生成唯一 UUID 实现隔离） |

### 第三部分：子智能体暴露为工具

```python
def expose_sub_agents_as_tools(sub_agents_cfg: DictConfig):
    sub_agents_server_params = []
    for sub_agent in sub_agents_cfg.keys():
        if "agent-browsing" in sub_agent:
            sub_agents_server_params.append(
                dict(
                    name="agent-browsing",
                    tools=[
                        dict(
                            name="search_and_browse",
                            description="This tool is an agent that performs the subtask of searching and browsing the web...",
                            schema={
                                "type": "object",
                                "properties": {
                                    "subtask": {"title": "Subtask", "type": "string"}
                                },
                                "required": ["subtask"],
                            },
                        )
                    ],
                )
            )
    return sub_agents_server_params
```

**解释**：

- 这个函数实现了 MiroThinker 的**层级智能体架构**：主智能体可以将子智能体当作工具来调用
- 目前支持 `agent-browsing`（浏览智能体），它被包装成一个名为 `search_and_browse` 的工具
- 子智能体的工具定义包含 `name`、`description` 和 JSON Schema 格式的 `schema`，与 MCP 工具的格式完全一致
- 这样主智能体无需知道子智能体的内部实现，只需像调用普通工具一样传入 `subtask` 参数

### 第四部分：环境信息收集

```python
def get_env_info(cfg: DictConfig) -> dict:
    return {
        "llm_provider": cfg.llm.provider,
        "llm_model_name": cfg.llm.model_name,
        "llm_temperature": cfg.llm.temperature,
        # ...
        "has_serper_api_key": bool(SERPER_API_KEY),
        "has_jina_api_key": bool(JINA_API_KEY),
        # ...
        "openai_base_url": OPENAI_BASE_URL,
        "anthropic_base_url": ANTHROPIC_BASE_URL,
        # ...
    }
```

**解释**：

- 收集 LLM 配置（提供商、模型、温度等采样参数）、智能体配置（最大轮次）、API 密钥可用性（布尔值，不暴露实际密钥）、服务 Base URL
- 这些信息被写入任务日志，用于事后调试和分析

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `create_mcp_server_parameters(cfg, agent_cfg)` | 函数 | 根据智能体配置动态生成 MCP 服务器启动参数和工具黑名单 |
| `expose_sub_agents_as_tools(sub_agents_cfg)` | 函数 | 将子智能体配置转换为工具定义，实现层级智能体架构 |
| `get_env_info(cfg)` | 函数 | 收集当前运行环境的配置信息用于日志记录 |
| 模块级常量 | 常量 | `SERPER_API_KEY`、`JINA_API_KEY`、`E2B_API_KEY` 等，在模块加载时从环境变量读取 |

## 与其他模块的关系

- **`core/Pipeline`**：调用 `create_mcp_server_parameters()` 获取工具配置，调用 `expose_sub_agents_as_tools()` 获取子智能体定义
- **`logging/TaskLog`**：通过 `get_env_info()` 获取环境信息并记录到任务日志
- **`libs/miroflow-tools/`**：本文件生成的 `StdioServerParameters` 指向该库中的 MCP 服务器模块
- **Hydra 配置系统**：`conf/agent/*.yaml` 中定义了 `tools` 和 `tool_blacklist`，本文件据此生成对应的服务器参数

## 总结

`settings.py` 是 MiroThinker 的配置枢纽。它将分散的环境变量、Hydra YAML 配置、MCP 协议参数统一管理，为整个系统提供了一个干净的配置接口。理解这个文件是理解 MiroThinker 工具生态的入口。

# 智能体配置总览 -- `conf/agent/` 全部 13 个变体详解

## 文件概述

`conf/agent/` 目录包含 13 个 YAML 配置文件，定义了 MiroThinker 智能体的不同运行模式。这些配置控制三个核心维度：**架构模式**（单智能体 vs 多智能体）、**工具集合**（搜索抓取工具 vs MCP 专用工具）和**上下文管理策略**（保留历史数量、压缩重试次数、最大轮数）。

## 关键配置参数解读

每个配置文件都包含以下核心字段：

```yaml
main_agent:
  tools: [...]           # 主智能体可用工具列表
  tool_blacklist: [...]  # 工具互斥规则（可选）
  max_turns: N           # 最大推理轮数

sub_agents:              # 子智能体定义（空表示纯单智能体模式）
  agent-browsing:
    tools: [...]
    max_turns: N

keep_tool_result: N      # 保留最近 N 次工具调用结果（-1 = 全部保留）
context_compress_limit: N # 上下文压缩/格式重试上限（0 = 禁用）
retry_with_summary: bool  # 是否在重试时使用摘要（可选，默认 true）
```

## 全部 13 个变体对比表

| 配置文件 | 架构模式 | 工具集 | max_turns | keep_tool_result | context_compress_limit | 特殊设置 |
|---|---|---|---|---|---|---|
| `default.yaml` | 多智能体 | MCP 工具 | 20 | -1（全部） | 0（禁用） | 基础配置 |
| `demo.yaml` | 单智能体 | 搜索+抓取 | 20 | -1 | 0 | 有工具黑名单 |
| `single_agent.yaml` | 单智能体 | 搜索+抓取 | 600 | -1 | 0 | -- |
| `single_agent_keep5.yaml` | 单智能体 | 搜索+抓取 | 600 | 5 | 5 | 启用上下文压缩 |
| `multi_agent.yaml` | 多智能体 | MCP 工具 | 50 | -1 | 0 | 含 browsing 子智能体 |
| `multi_agent_os.yaml` | 多智能体 | MCP 开源工具 | 50 | -1 | 0 | 使用 `-os` 后缀工具 |
| `mirothinker_v1.0.yaml` | 单智能体 | 搜索+抓取 | 600 | -1 | 0 | -- |
| `mirothinker_v1.0_keep5.yaml` | 单智能体 | 搜索+抓取 | 600 | 5 | 5 | 启用上下文压缩 |
| `mirothinker_v1.5.yaml` | 单智能体 | 搜索+抓取 | 600 | -1 | 0 | **主力配置** |
| `mirothinker_v1.5_keep5_max200.yaml` | 单智能体 | 搜索+抓取 | 200 | 5 | 5 | 适合短任务 |
| `mirothinker_v1.5_keep5_max400.yaml` | 单智能体 | 搜索+抓取 | 400 | 5 | 5 | 中等长度任务 |
| `mirothinker_1.7_keep5_max200.yaml` | 单智能体 | 搜索+抓取 | 200 | 5 | 5 | 禁用摘要重试 |
| `mirothinker_1.7_keep5_max300.yaml` | 单智能体 | 搜索+抓取 | 300 | 5 | 5 | 禁用摘要重试 |

## 三大架构模式详解

### 模式一：多智能体（default / multi_agent / multi_agent_os）

```yaml
main_agent:
  tools: [tool-python, tool-vqa, tool-transcribe, tool-reasoning, tool-reader]

sub_agents:
  agent-browsing:
    tools: [tool-google-search, tool-vqa, tool-reader, tool-python]
```

主智能体使用 MCP 协议工具（`tool-python` 代码执行、`tool-vqa` 视觉问答、`tool-transcribe` 语音转文字、`tool-reasoning` 推理、`tool-reader` 文档阅读），并将网页搜索/浏览任务委托给 `agent-browsing` 子智能体。

- **`multi_agent_os.yaml`** 是开源版本，使用 `-os` 后缀的工具（如 `tool-vqa-os`），通常对应本地部署的模型而非 API 服务。

### 模式二：单智能体 - 搜索抓取型（single_agent / mirothinker 系列）

```yaml
main_agent:
  tools: [search_and_scrape_webpage, jina_scrape_llm_summary, tool-python]
  tool_blacklist:
    - ["search_and_scrape_webpage", "sogou_search"]
    - ["tool-python", "download_file_from_sandbox_to_local"]

sub_agents:   # 空，无子智能体
```

主智能体直接使用搜索和网页抓取工具，不使用子智能体。工具黑名单（`tool_blacklist`）防止特定工具组合同时被调用：
- `search_and_scrape_webpage` 和 `sogou_search` 互斥（避免重复搜索）
- `tool-python` 和 `download_file_from_sandbox_to_local` 互斥（避免安全风险）

### 模式三：演示模式（demo）

与单智能体相同的工具集，但 `max_turns` 限制为 20，适合快速演示和测试。

## 上下文管理策略详解

| 参数 | 值 | 行为 |
|---|---|---|
| `keep_tool_result: -1` | 保留全部历史 | 所有工具调用结果都保留在上下文中，消耗更多 token 但信息完整 |
| `keep_tool_result: 5` | 只保留最近 5 次 | 丢弃较早的工具结果，减少 token 消耗，适合长任务 |
| `context_compress_limit: 0` | 禁用压缩重试 | 格式错误时不重试 |
| `context_compress_limit: 5` | 最多重试 5 次 | 格式错误时最多重试 5 次，每次携带之前的失败经验 |
| `retry_with_summary: False` | 禁用摘要重试 | v1.7 新增，重试时不生成摘要（减少开销） |

## 版本演进脉络

```
v1.0 → v1.5 → v1.7
  │      │      └── 新增 retry_with_summary: False
  │      └── 主力版本，与 v1.0 工具集相同，版本号用于区分 prompt/pipeline 版本
  └── 初始版本
```

每个版本都有 `_keep5_maxN` 变体，代表启用上下文压缩并限制最大轮数。轮数从 200 到 600 不等，越大的轮数适合越复杂的任务（如 BrowseComp 需要深度搜索），但消耗更多 API 调用。

## 与其他模块的关系

- **`src/config/settings.py`**：工具名称（如 `tool-python`、`search_and_scrape_webpage`）在此文件中映射为实际的 MCP 服务器配置。
- **`src/utils/prompt_utils.py`**：子智能体名称（如 `agent-browsing`）在此文件中映射为系统提示词。
- **`src/core/pipeline.py`**：`create_pipeline_components()` 读取 agent 配置，创建 `ToolManager` 实例。
- **`conf/config.yaml`**：通过 `agent: default` 指定默认使用哪个变体。

## 总结

13 个智能体配置覆盖了从快速演示到深度研究的各种场景。核心选择维度是：单智能体 vs 多智能体、全量上下文 vs 压缩上下文、最大轮数上限。`mirothinker_v1.5` 是主力配置，其 `_keep5_max200/400` 变体通过上下文压缩和轮数限制，在 token 效率和任务质量之间取得平衡。

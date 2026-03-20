# 背景知识：理解 MiroThinker 的核心概念

本文档面向零基础读者，帮助你从头理解 MiroThinker 项目涉及的核心概念。阅读完本文后，你将能够理解项目的架构设计动机和各组件的职责。

---

## 目录

1. [什么是深度研究 Agent](#1-什么是深度研究-agent)
2. [MCP（Model Context Protocol）核心概念](#2-mcpmodel-context-protocol核心概念)
3. [多 Agent 架构](#3-多-agent-架构)
4. [Hydra 配置系统基础](#4-hydra-配置系统基础)
5. [LLM Provider 抽象](#5-llm-provider-抽象)
6. [工具生态系统](#6-工具生态系统)
7. [整体架构总览](#7-整体架构总览)

---

## 1. 什么是深度研究 Agent

### 从搜索引擎到深度研究

传统搜索引擎的工作方式是：你输入关键词，它返回一组网页链接，然后你自己逐一阅读、筛选、综合信息。这个过程对于简单问题足够了，但当问题变得复杂时（比如"某个晦涩的历史事件的具体细节"或"某项技术在不同场景下的对比"），你需要：

- 多次搜索不同关键词
- 打开数十个网页逐一阅读
- 从不同来源交叉验证信息
- 综合所有信息得出结论

**深度研究 Agent**（Deep Research Agent）就是自动化这个过程的系统。它不是简单地调用一次大语言模型（LLM），而是让 LLM 像一个研究员一样，**主动规划搜索策略、调用各种工具、多轮迭代地收集和验证信息，最终生成经过充分论证的答案**。

### MiroThinker 的定位

MiroThinker 是一个深度研究 Agent 框架，在 BrowseComp 基准测试上达到了 88.2 分。BrowseComp 是 OpenAI 发布的一个专门测试 Agent 浏览和信息综合能力的基准——题目设计得让简单搜索无法直接找到答案，必须通过多步骤的深入研究才能解决。

### Agent 的核心循环

一个深度研究 Agent 的工作循环可以用以下步骤概括：

```
1. 接收用户问题
2. LLM 分析问题，决定需要调用哪些工具（搜索、浏览网页、执行代码等）
3. 执行工具调用，获取结果
4. LLM 阅读工具返回的结果，决定是否需要继续研究
5. 如果信息不足 → 回到步骤 2，换个角度继续搜索
6. 如果信息充分 → 综合所有收集到的信息，生成最终答案
```

这个循环可能执行几十轮甚至上百轮，直到 Agent 认为收集到了足够的信息。

---

## 2. MCP（Model Context Protocol）核心概念

### 为什么需要 MCP

假设你要让 LLM 使用搜索工具。最直接的做法是在代码里硬编码一个函数：

```python
def search(query: str) -> str:
    # 调用搜索 API
    return results
```

但当你有 13 种以上的工具（搜索、浏览、代码执行、视觉分析、音频处理、推理……）时，问题出现了：

- 每个工具的接口格式不同
- 工具的生命周期管理（启动、关闭）各不相同
- 不同的 Agent 可能需要不同的工具子集
- 工具需要能独立开发和测试

**MCP（Model Context Protocol）** 是 Anthropic 提出的一个标准化协议，它定义了 LLM 与工具之间的通信方式。你可以把它理解为"LLM 工具的 USB 接口"——只要工具实现了 MCP 协议，任何支持 MCP 的 Agent 都能直接使用它。

### MCP 的核心概念

- **MCP Server**：一个独立运行的工具服务。每个 MCP Server 提供一组相关的工具。例如，搜索 MCP Server 提供 `search` 工具，Python MCP Server 提供 `execute_python` 工具。
- **MCP Client**：Agent 端的客户端，负责连接到 MCP Server、发现可用工具、发送调用请求、接收结果。
- **传输方式**：MCP 支持两种传输方式：
  - **stdio**：通过标准输入/输出通信，Server 作为子进程运行。适合本地部署。
  - **SSE（Server-Sent Events）**：通过 HTTP 通信，Server 可以远程运行。适合分布式部署。

### 在 MiroThinker 中的体现

MiroThinker 的 `ToolManager`（位于 `libs/miroflow-tools/`）负责管理所有 MCP Server 的生命周期：

```
ToolManager
├── 连接到各个 MCP Server（stdio 或 SSE）
├── 收集所有 Server 提供的工具定义
├── 将工具定义提供给 LLM（让 LLM 知道有哪些工具可用）
└── 执行 LLM 发出的工具调用请求，路由到正确的 Server
```

---

## 3. 多 Agent 架构

### 为什么需要多个 Agent

一个 Agent 能做所有事情吗？理论上可以，但实际中有问题：

- **上下文窗口限制**：LLM 的上下文窗口是有限的。如果一个 Agent 既要搜索又要浏览网页又要执行代码，所有的工具结果都会挤在同一个上下文里，很快就会超出限制。
- **工具冲突**：某些工具组合在一起会导致 LLM 行为混乱。例如，当搜索工具和浏览工具同时可用时，LLM 可能会跳过搜索直接尝试浏览一个 URL。
- **专注度**：让一个 Agent 同时处理太多类型的任务，会降低每个任务的完成质量。

### MiroThinker 的层级 Agent 设计

MiroThinker 采用**主 Agent + 子 Agent** 的层级架构：

```
主 Agent（Main Agent）
├── 拥有自己的工具集（如搜索工具）
├── 可以委托任务给子 Agent
│
├── 子 Agent: 浏览 Agent（Browsing Agent）
│   ├── 拥有独立的工具集（如网页抓取工具）
│   └── 拥有独立的上下文窗口
│
└── 子 Agent: 其他专用 Agent...
    └── ...
```

关键设计决策：

- **工具黑名单（Tool Blacklisting）**：主 Agent 不能使用某些工具（比如网页抓取），这些工具只对子 Agent 开放。这避免了工具冲突。
- **独立上下文**：每个子 Agent 有自己的对话上下文，不会占用主 Agent 的上下文窗口。子 Agent 完成任务后，只将摘要结果返回给主 Agent。
- **子 Agent 作为工具**：从主 Agent 的视角，调用子 Agent 就像调用一个普通工具——发送指令、等待结果。

### 配置示例

在 `conf/agent/` 目录下，你会看到不同的 Agent 配置：

- `single_agent.yaml`：单 Agent 模式，所有工具集中在一个 Agent
- `multi_agent.yaml`：多 Agent 模式，主 Agent + 浏览子 Agent
- `mirothinker_v1.5.yaml`：MiroThinker 的主力配置

---

## 4. Hydra 配置系统基础

### 为什么需要 Hydra

MiroThinker 有大量可配置项：

- 使用哪个 LLM 提供商（Anthropic、OpenAI、Qwen）？
- 使用哪种 Agent 架构（单 Agent、多 Agent）？
- 运行哪个基准测试（BrowseComp、GAIA、HLE……）？
- Agent 的最大轮数、超时时间、重试策略？

如果用传统的配置文件或命令行参数，组合爆炸会让管理变得极其困难。

### Hydra 的核心思想

[Hydra](https://hydra.cc/) 是 Facebook Research 开发的配置框架，核心思想是**配置的组合与覆盖**：

```
conf/
├── config.yaml          ← 主配置文件，定义默认值
├── agent/               ← Agent 配置组
│   ├── mirothinker_v1.5.yaml
│   ├── single_agent.yaml
│   └── multi_agent.yaml
├── llm/                 ← LLM 提供商配置组
│   ├── claude-3-7.yaml
│   ├── gpt-5.yaml
│   └── qwen-3.yaml
└── benchmark/           ← 基准测试配置组
    ├── browsecomp.yaml
    ├── gaia-validation.yaml
    └── hle.yaml
```

使用方式：

```bash
# 使用默认配置运行
python main.py

# 组合不同配置
python main.py agent=mirothinker_v1.5 llm=claude-3-7 benchmark=browsecomp

# 在命令行覆盖单个参数
python main.py agent.max_turns=100 llm.temperature=0.5
```

### 为什么这很重要

在研究项目中，你需要频繁进行实验：同一个 Agent 架构搭配不同的 LLM，或者同一个 LLM 在不同基准上测试。Hydra 让你可以自由组合配置，而不需要为每种组合创建单独的配置文件。

---

## 5. LLM Provider 抽象

### 问题：不同 LLM 的 API 差异

Anthropic（Claude）和 OpenAI（GPT）的 API 接口差异显著：

| 方面 | Anthropic | OpenAI |
|------|-----------|--------|
| 消息格式 | `messages` + 独立的 `system` 参数 | `messages` 中包含 `system` 角色 |
| 工具调用格式 | `tool_use` 类型的 content block | `tool_calls` 字段 |
| 流式响应 | 事件流格式 | SSE chunk 格式 |

### MiroThinker 的解决方案

`src/llm/` 模块通过抽象层屏蔽了这些差异：

```
BaseClient（抽象基类）
├── 定义统一接口：create_message(), get_response() 等
│
├── AnthropicClient
│   └── 实现 Anthropic API 的调用细节
│
├── OpenAIClient
│   └── 实现 OpenAI API 的调用细节（也兼容 Qwen 等 OpenAI 兼容 API）
│
└── ClientFactory（工厂函数）
    └── 根据配置中的 provider 字段，创建对应的客户端实例
```

对于 Orchestrator 和其他上层模块来说，它们只和 `BaseClient` 接口打交道，完全不需要知道底层用的是哪家 LLM。这意味着切换 LLM 只需要改一行配置：

```yaml
llm:
  provider: anthropic  # 改成 openai 即可切换
  model: claude-3-7-sonnet
```

---

## 6. 工具生态系统

### MiroThinker 的工具分类

MiroThinker 在 `libs/miroflow-tools/` 中提供了丰富的 MCP Server，覆盖深度研究所需的各类能力：

| 类别 | MCP Server | 功能 |
|------|-----------|------|
| **搜索** | `serper_mcp_server` | 通过 Serper API 进行 Google 搜索 |
| **搜索** | `searching_google_mcp_server` | Google 搜索（备选方案） |
| **搜索** | `searching_sogou_mcp_server` | 搜狗搜索（中文优化） |
| **浏览** | `browser_session` | 基于 Playwright 的浏览器自动化 |
| **浏览** | `jina_scrape_llm_summary` | 网页抓取与 LLM 摘要 |
| **代码执行** | `python_mcp_server` | 安全的 Python 代码执行（E2B 沙箱） |
| **文档阅读** | `reading_mcp_server` | 文档解析与阅读 |
| **推理** | `reasoning_mcp_server` | 辅助推理能力 |
| **视觉** | `vision_mcp_server` | 图像分析与理解 |
| **音频** | `audio_mcp_server` | 音频处理与分析 |
| **规划** | `task_planner` | 任务规划与分解 |

### 工具如何被使用

一次典型的工具调用流程如下：

```
1. LLM 输出中包含工具调用请求（如 "调用 search 工具，参数为 query='MiroThinker BrowseComp'")
2. Orchestrator 检测到工具调用请求
3. ToolExecutor 接收请求，进行参数修正和去重检测
4. ToolExecutor 通过 ToolManager 路由到对应的 MCP Server
5. MCP Server 执行实际操作（如调用 Serper API）
6. 结果返回给 ToolExecutor，经过截断/格式化处理
7. 处理后的结果作为工具响应追加到对话上下文
8. LLM 在下一轮看到工具结果，继续推理
```

### 工具的开发模式

如果你想添加新工具，你需要：

1. 在 `libs/miroflow-tools/src/miroflow_tools/mcp_servers/` 下创建新的 MCP Server
2. 使用 `fastmcp` 库定义工具接口
3. 在配置中注册该 Server

每个 MCP Server 是独立的 Python 模块，可以单独开发和测试。

---

## 7. 整体架构总览

### 系统架构图

```
用户查询
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│                     Pipeline (入口与工厂)                      │
│  - 解析 Hydra 配置                                            │
│  - 创建 ToolManager、LLM Client、OutputFormatter             │
│  - 启动任务执行                                               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Orchestrator (核心调度)                     │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐    │
│  │  LLM Client │  │ ToolExecutor │  │  ToolManager    │    │
│  │ (Anthropic/ │  │ (调用执行/    │  │  (MCP Server   │    │
│  │  OpenAI)    │  │  重试/去重)   │  │   生命周期管理) │    │
│  └──────┬──────┘  └──────┬───────┘  └───────┬─────────┘    │
│         │                │                   │              │
│         │         ┌──────┴───────┐           │              │
│         │         │  子 Agent    │           │              │
│         │         │ (独立上下文/  │           │              │
│         │         │  独立工具集)  │           │              │
│         │         └──────────────┘           │              │
└─────────┼───────────────────────────────────┼──────────────┘
          │                                   │
          ▼                                   ▼
┌──────────────────┐    ┌─────────────────────────────────────┐
│    LLM API       │    │         MCP Servers                 │
│ (Claude/GPT/Qwen)│    │                                     │
└──────────────────┘    │  搜索    浏览    代码执行   推理     │
                        │  文档阅读  视觉   音频     规划     │
                        └──────────────────┬──────────────────┘
                                           │
                                           ▼
                        ┌─────────────────────────────────────┐
                        │          外部服务与资源               │
                        │  Google/Serper  网页  E2B沙箱  文件  │
                        └─────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                  AnswerGenerator (答案生成)                    │
│  - 综合所有收集到的上下文                                       │
│  - 生成最终答案（支持重试）                                     │
│  - 可选：LLM-as-Judge 验证                                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
                       最终答案
```

### 数据流简化版

```
用户查询 → Pipeline → Orchestrator → [LLM Client + ToolExecutor + ToolManager]
                                          │
                                          ▼
                                    MCP Servers (搜索/浏览/代码/推理/视觉/音频)
                                          │
                                          ▼
                                    AnswerGenerator → 最终答案
```

### 关键源码位置

| 组件 | 路径 |
|------|------|
| 入口 | `apps/miroflow-agent/main.py` |
| Pipeline | `apps/miroflow-agent/src/core/pipeline.py` |
| Orchestrator | `apps/miroflow-agent/src/core/orchestrator.py` |
| ToolExecutor | `apps/miroflow-agent/src/core/tool_executor.py` |
| AnswerGenerator | `apps/miroflow-agent/src/core/answer_generator.py` |
| LLM 工厂 | `apps/miroflow-agent/src/llm/factory.py` |
| LLM 基类 | `apps/miroflow-agent/src/llm/base_client.py` |
| ToolManager | `libs/miroflow-tools/src/miroflow_tools/manager.py` |
| MCP Servers | `libs/miroflow-tools/src/miroflow_tools/mcp_servers/` |
| Hydra 配置 | `apps/miroflow-agent/conf/` |
| 环境变量 | `apps/miroflow-agent/.env.example` |

---

## 下一步

理解了这些背景知识后，建议阅读 [阅读指南](./00_reading_guide.md)，选择适合你的学习路径开始深入源码。

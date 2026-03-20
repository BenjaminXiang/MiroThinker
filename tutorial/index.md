# MiroThinker 代码教程

欢迎来到 MiroThinker 代码教程！本教程将带你逐文件深入理解这个在 BrowseComp 基准测试中取得 88.2 分的深度研究 Agent 框架。

---

## 项目简介

MiroThinker 是一个基于 MCP（Model Context Protocol）的深度研究 Agent 框架，专为复杂研究和预测任务设计。它采用多 Agent 架构，主 Agent 可以委托子 Agent 执行特定任务，通过搜索、浏览、代码执行、文档阅读等 13+ 工具自主完成深度研究。

---

## 整体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MiroThinker 系统架构                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────┐    ┌──────────────────────────────────────────────┐  │
│  │  用户查询  │───→│           apps/miroflow-agent                │  │
│  └───────────┘    │                                              │  │
│                   │  main.py (Hydra入口)                         │  │
│                   │     │                                        │  │
│                   │     ▼                                        │  │
│                   │  Pipeline (create_pipeline_components)       │  │
│                   │     │                                        │  │
│                   │     ▼                                        │  │
│                   │  ┌─────────────────────────────────────┐     │  │
│                   │  │         Orchestrator (核心)          │     │  │
│                   │  │                                     │     │  │
│                   │  │  ┌──────────┐  ┌───────────────┐   │     │  │
│                   │  │  │LLM Client│  │ ToolExecutor  │   │     │  │
│                   │  │  │(Anthropic│  │   (工具执行)   │   │     │  │
│                   │  │  │ /OpenAI) │  └───────┬───────┘   │     │  │
│                   │  │  └──────────┘          │           │     │  │
│                   │  │                        ▼           │     │  │
│                   │  │              ┌─────────────────┐   │     │  │
│                   │  │              │   ToolManager    │   │     │  │
│                   │  │              │  (miroflow-tools)│   │     │  │
│                   │  │              └────────┬────────┘   │     │  │
│                   │  │                       │            │     │  │
│                   │  │  ┌────────────────┐   │            │     │  │
│                   │  │  │AnswerGenerator │   │            │     │  │
│                   │  │  │  (答案生成)     │   │            │     │  │
│                   │  │  └────────────────┘   │            │     │  │
│                   │  └───────────────────────│────────────┘     │  │
│                   └──────────────────────────│─────────────────┘  │
│                                              │                     │
│  ┌───────────────────────────────────────────▼──────────────────┐  │
│  │                    MCP Servers (13+)                          │  │
│  │                                                              │  │
│  │  ┌─────────┐ ┌─────────┐ ┌────────┐ ┌─────────┐ ┌────────┐│  │
│  │  │  搜索   │ │  浏览器  │ │  代码  │ │  推理   │ │  视觉  ││  │
│  │  │Google   │ │Playwright│ │Python  │ │Extended │ │ 图像   ││  │
│  │  │Sogou    │ │ Session  │ │E2B沙箱 │ │Thinking │ │ 处理   ││  │
│  │  │Serper   │ │          │ │        │ │         │ │        ││  │
│  │  └─────────┘ └─────────┘ └────────┘ └─────────┘ └────────┘│  │
│  │  ┌─────────┐ ┌──────────────────────────────────────────────┐│  │
│  │  │  音频   │ │           文档阅读 (PDF/PPTX/...)           ││  │
│  │  └─────────┘ └──────────────────────────────────────────────┘│  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────── 辅助应用 ────────────────────────────┐  │
│  │  collect-trace │ gradio-demo │ visualize-trace │ lobehub     │  │
│  │  (训练数据收集) │ (Web UI)    │ (追踪可视化)    │ (LobeChat) │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 主工作流程图

```
步骤1          步骤2           步骤3          步骤4          步骤5
用户输入 ──→ Pipeline ──→ Orchestrator ──→ 多轮推理 ──→ 生成答案
  查询       初始化组件      启动主循环      循环执行       返回结果
              │                │              │              │
              ▼                ▼              ▼              ▼
         创建LLM客户端    解析用户意图   ┌──────────┐   AnswerGenerator
         创建ToolManager  规划搜索策略   │ 调用LLM  │   汇总所有上下文
         创建Formatter    分配工具调用   │    ↓     │   可选LLM-as-judge
                                        │ 执行工具 │   格式化输出
                                        │    ↓     │
                                        │ 收集结果 │
                                        │    ↓     │
                                        │ 判断是否 │
                                        │ 需要继续 │
                                        └──────────┘
                                         (最多N轮)
```

---

## 代码-流程映射表

| 流程步骤 | 源文件 | 教程文档 |
|---------|--------|---------|
| 1. 程序入口 (Hydra配置加载) | `apps/miroflow-agent/main.py` | [main.py 教程](apps/miroflow-agent/main.md) |
| 2. Pipeline 初始化 | `apps/miroflow-agent/src/core/pipeline.py` | [pipeline.py 教程](apps/miroflow-agent/src/core/pipeline.md) |
| 3. Orchestrator 主循环 | `apps/miroflow-agent/src/core/orchestrator.py` | [orchestrator.py 教程](apps/miroflow-agent/src/core/orchestrator.md) |
| 4a. LLM 调用 | `apps/miroflow-agent/src/llm/` | [LLM 模块](apps/miroflow-agent/src/llm/index.md) |
| 4b. 工具执行 | `apps/miroflow-agent/src/core/tool_executor.py` | [tool_executor.py 教程](apps/miroflow-agent/src/core/tool_executor.md) |
| 4c. 工具管理 | `libs/miroflow-tools/src/miroflow_tools/manager.py` | [ToolManager 教程](libs/miroflow-tools/src/miroflow_tools/manager.md) |
| 4d. MCP 服务器 | `libs/miroflow-tools/src/miroflow_tools/mcp_servers/` | [MCP 服务器](libs/miroflow-tools/src/miroflow_tools/mcp_servers/index.md) |
| 5. 答案生成 | `apps/miroflow-agent/src/core/answer_generator.py` | [answer_generator.py 教程](apps/miroflow-agent/src/core/answer_generator.md) |
| 配置系统 | `apps/miroflow-agent/conf/` | [配置系统](apps/miroflow-agent/conf/index.md) |
| 流式处理 | `apps/miroflow-agent/src/core/stream_handler.py` | [stream_handler.py 教程](apps/miroflow-agent/src/core/stream_handler.md) |
| 日志系统 | `apps/miroflow-agent/src/logging/` | [日志模块](apps/miroflow-agent/src/logging/index.md) |

---

## 模块索引

| 模块 | 文档数 | 说明 |
|------|--------|------|
| [核心引擎 (core)](apps/miroflow-agent/src/core/index.md) | 6 | Orchestrator、Pipeline、ToolExecutor 等核心组件 |
| [LLM 客户端 (llm)](apps/miroflow-agent/src/llm/index.md) | 6 | 多 LLM 提供商抽象（Anthropic、OpenAI） |
| [配置系统 (config)](apps/miroflow-agent/src/config/index.md) | 2 | 环境变量与 MCP 服务器配置 |
| [输入输出 (io)](apps/miroflow-agent/src/io/index.md) | 3 | 输入处理与输出格式化 |
| [日志系统 (logging)](apps/miroflow-agent/src/logging/index.md) | 3 | 任务日志与时间统计 |
| [工具函数 (utils)](apps/miroflow-agent/src/utils/index.md) | 4 | 解析、提示词、包装器工具 |
| [Hydra 配置 (conf)](apps/miroflow-agent/conf/index.md) | 5 | Agent/Benchmark/LLM 配置文件详解 |
| [基准测试 (benchmarks)](apps/miroflow-agent/benchmarks/index.md) | 6 | BrowseComp、GAIA、HLE 等评测系统 |
| [工具管理库 (miroflow-tools)](libs/miroflow-tools/src/miroflow_tools/index.md) | 19 | ToolManager + 13 个 MCP 服务器 |
| [数据收集 (collect-trace)](apps/collect-trace/index.md) | 10 | 训练数据采集与格式转换 |
| [Web 演示 (gradio-demo)](apps/gradio-demo/index.md) | 4 | Gradio Web UI 界面 |
| [可视化 (visualize-trace)](apps/visualize-trace/index.md) | 6 | Flask 追踪分析仪表板 |
| [LobeChat 集成](apps/lobehub-compatibility/index.md) | 4 | LobeChat 适配器 |

---

## 快速开始

- **零基础入门？** 先阅读 [背景知识](00_background_knowledge.md)
- **想快速了解项目？** 按照 [阅读指南](00_reading_guide.md) 的快速路径
- **想深入某个模块？** 直接点击上方模块索引中的链接

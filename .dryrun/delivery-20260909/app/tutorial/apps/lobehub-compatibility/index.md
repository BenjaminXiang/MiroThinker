# `lobehub-compatibility` -- LobeChat 集成适配器

## 文件概述

`lobehub-compatibility` 是 MiroThinker 与 LobeChat（一个开源 AI 聊天客户端）集成的适配器模块。它的核心组件是一个 **vLLM 工具解析器插件** (`MirothinkerToolParser`)，负责将 MiroThinker 使用的 MCP XML 格式工具调用转换为 OpenAI 兼容的结构化工具调用格式，使得通过 vLLM 部署的 MiroThinker 模型能够与 LobeChat 等使用 OpenAI API 格式的客户端无缝协作。

## 架构概览

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│  LobeChat (客户端)                                   │
│  ├── 发送：OpenAI tool_calls 格式请求                │
│  └── 接收：OpenAI tool_calls 格式响应                │
│                                                      │
│         ▲                    │                        │
│         │ OpenAI API         │                        │
│         │                    ▼                        │
│  ┌──────────────────────────────────────────────┐    │
│  │              vLLM 推理服务                    │    │
│  │                                              │    │
│  │  MirothinkerToolParser                       │    │
│  │  ├── extract_tool_calls()                    │    │
│  │  │   模型输出 MCP XML → OpenAI ToolCall      │    │
│  │  └── extract_tool_calls_streaming()          │    │
│  │      流式输出 → 逐 token 解析 → DeltaToolCall│    │
│  └──────────────────────────────────────────────┘    │
│         ▲                    │                        │
│         │                    ▼                        │
│  ┌──────────────────────────────────────────────┐    │
│  │         MiroThinker 模型                     │    │
│  │  输出格式：                                   │    │
│  │  <use_mcp_tool>                              │    │
│  │    <server_name>...</server_name>            │    │
│  │    <tool_name>...</tool_name>                │    │
│  │    <arguments>{...}</arguments>              │    │
│  │  </use_mcp_tool>                             │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

## 目录结构

```
apps/lobehub-compatibility/
├── MiroThinkerToolParser.py    # vLLM 工具解析器插件（核心）
├── test_tool_parser.py         # 正则表达式测试 + 代码分析
└── unit_test.py                # Jinja2 聊天模板单元测试
```

## 核心问题与解决方案

**问题**：MiroThinker 模型输出的是 MCP XML 格式的工具调用（`<use_mcp_tool>` 标签），而 LobeChat 等客户端期望的是 OpenAI 格式的结构化 `tool_calls`。

**解决方案**：实现一个 vLLM 工具解析器插件，在 vLLM 推理服务层进行格式转换，对上游客户端完全透明。插件支持：
- **非流式**：从完整模型输出中提取所有 MCP 工具调用，转换为 `ToolCall` 列表。
- **流式**：逐 token 解析，使用状态机追踪是否在工具调用块内，实时生成 `DeltaToolCall`。

## 与其他模块的关系

- 解析的 MCP XML 格式与 `libs/miroflow-tools/` 和 `apps/miroflow-agent/` 中定义的工具调用格式一致。
- 依赖 vLLM 框架的 `ToolParser` 基类和协议类型。
- `unit_test.py` 测试的 Jinja2 模板（`chat_template.jinja`，未包含在仓库中）定义了模型的输入格式。

## 总结

`lobehub-compatibility` 是一个专注于格式桥接的适配层，通过 vLLM 插件机制将 MCP XML 格式无缝转换为 OpenAI 兼容格式。它是 MiroThinker 模型在生产环境中通过标准 API 对外服务的关键组件。

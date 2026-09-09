# utils 模块概览

## 模块简介

`utils` 模块是 MiroThinker 的**通用工具箱**，提供三类基础能力：

1. **解析工具**（parsing_utils）：从 LLM 响应中提取工具调用、修复错误的服务器名称、安全解析 JSON
2. **提示工具**（prompt_utils）：生成系统提示、智能体特定目标提示、最终总结提示
3. **包装工具**（wrapper_utils）：提供类型安全的错误和响应包装器

这些工具函数被 `llm`、`core`、`io` 等多个模块广泛使用。

## 架构图

```
┌──────────────────────────────────────────────────┐
│                   调用方                          │
│                                                   │
│  llm/AnthropicClient  llm/OpenAIClient           │
│  core/Orchestrator    core/ToolExecutor           │
│  io/OutputFormatter                               │
└───────┬──────────────────┬───────────────┬───────┘
        │                  │               │
        ▼                  ▼               ▼
┌───────────────┐ ┌────────────────┐ ┌──────────────┐
│parsing_utils  │ │ prompt_utils   │ │wrapper_utils │
│               │ │                │ │              │
│修复服务器名称  │ │MCP系统提示生成  │ │ErrorBox      │
│解析工具调用    │ │智能体目标提示   │ │ResponseBox   │
│安全JSON解析   │ │总结提示模板     │ │              │
│提取失败经验   │ │失败经验模板     │ │              │
│提取响应文本   │ │MCP标签常量     │ │              │
└───────────────┘ └────────────────┘ └──────────────┘
        │                  │
        │      ┌───────────┘
        ▼      ▼
   LLM 响应处理流程:

   LLM原始响应
       │
       ├──→ fix_server_name_in_text()     修正错误的server_name
       │
       ├──→ extract_llm_response_text()   提取纯文本（去除工具调用）
       │
       ├──→ parse_llm_response_for_tool_calls()  提取工具调用信息
       │         支持三种格式：
       │         - OpenAI Response API (dict)
       │         - OpenAI Completion API (list)
       │         - MCP XML 格式 (string)
       │
       └──→ extract_failure_experience_summary()  提取失败经验
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `parsing_utils.py` | LLM 响应解析、工具调用提取、JSON 安全解析、服务器名称修复 |
| `prompt_utils.py` | 系统提示和智能体提示的模板与生成函数 |
| `wrapper_utils.py` | 类型安全的 ErrorBox 和 ResponseBox 包装器 |
| `__init__.py` | 包初始化，统一导出所有工具函数和类 |

## 设计理念

这个模块遵循**纯函数优先**的原则：大部分工具函数是无状态的纯函数，输入确定则输出确定，不依赖外部状态。唯一的例外是 `_tool_server_mapping` 模块级缓存，它在系统启动时被设置一次，之后只被读取。

这种设计使得这些工具函数易于测试、易于理解、不会引入隐式依赖。

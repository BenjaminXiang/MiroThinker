# `system_prompts.py` -- 系统提示词模板

## 文件概述

本文件定义了三个字符串常量，作为 OAI 格式转换时重建系统提示词的模板组件。当 `convert_oai_to_chatml.py` 将 OpenAI 格式日志转换为 ChatML 时，需要重新构造系统提示词，本文件提供了这些模板。

## 关键代码解读

### 1. Agent 前言模板

```python
main_system_prompt_foreword = """In this environment you have access to a set of tools you can use to answer the user's question. \n    \nYou only have access to the tools provided below. You can only use one tool per message, and will receive the result of that tool in the user's next response. You use tools step-by-step to accomplish a given task, with each tool-use informed by the result of the previous tool-use."""

sub_agent_system_prompt_foreword = """In this environment you have access to a set of tools..."""
```

**逐步解释**：
- `main_system_prompt_foreword`：主 Agent 的系统提示词前言，说明 Agent 可以使用工具、每次只能用一个工具、逐步推理。
- `sub_agent_system_prompt_foreword`：子 Agent（如浏览 Agent）的前言，内容与主 Agent 相同。
- 这两个变量当前值相同，但分开定义是为了支持未来可能的差异化。

### 2. 工具使用格式说明

```python
system_prompt_tool_instrcutions = """# Tool-Use Formatting Instructions \n\nTool-use is formatted using XML-style tags. The tool-use is enclosed in <use_mcp_tool></use_mcp_tool>...\n\nParameters:\n- server_name: (required)...\n- tool_name: (required)...\n- arguments: (required)...\n\nUsage:\n<use_mcp_tool>\n<server_name>server name here</server_name>\n<tool_name>tool name here</tool_name>\n<arguments>\n...\n</arguments>\n</use_mcp_tool>\n..."""
```

**逐步解释**：
- 详细描述了 MCP 工具调用的 XML 格式规范。
- 说明了三个必需参数：`server_name`、`tool_name`、`arguments`。
- 提供了完整的使用示例和注意事项（工具调用必须放在响应末尾、参数必须是合法 JSON 等）。
- 这段文本会被插入到重建的系统提示词中，紧跟在工具定义列表之前。

## 核心类/函数表格

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `main_system_prompt_foreword` | `str` | 主 Agent 系统提示词前言 |
| `sub_agent_system_prompt_foreword` | `str` | 子 Agent 系统提示词前言 |
| `system_prompt_tool_instrcutions` | `str` | MCP 工具调用格式说明（含 XML 标签规范） |

## 与其他模块的关系

- 被 `convert_oai_to_chatml.py` 导入，用于重建系统提示词。
- 提供的格式规范与 `apps/miroflow-agent/` 中实际使用的 MCP 工具调用格式一致。

## 总结

本文件是纯常量定义文件，提供三段固定文本用于在 OAI 格式转换时重建完整的系统提示词。这些模板确保转换后的 ChatML 数据中的系统提示词与 MiroThinker Agent 的实际运行时格式保持一致，从而保证训练数据的质量。

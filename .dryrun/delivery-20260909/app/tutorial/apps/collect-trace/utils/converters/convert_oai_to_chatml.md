# `convert_oai_to_chatml.py` -- OpenAI 格式日志转 ChatML

## 文件概述

本文件负责将 **OpenAI 格式**（含 `tool_calls` 字段）的 Agent 运行日志转换为 ChatML 格式。这是整个转换器中最复杂的模块，因为它需要将 OpenAI 的结构化工具调用（JSON 格式的 `function.name` + `function.arguments`）转换为 MCP XML 标签格式（`<use_mcp_tool>` 包裹的工具调用），同时还需要重建系统提示词并合并连续的 `user/tool` 消息。

## 关键代码解读

### 1. OAI 工具调用转 MCP XML 格式

```python
def convert_oai_tool_call_to_mcp_tool_call_str(oai_tool_call):
    mcp_tool_call_templates = []
    for each_oai_tool_call in oai_tool_call:
        server_name, tool_name = each_oai_tool_call["function"]["name"].rsplit(
            "-", maxsplit=1
        )
        arguments = json.loads(each_oai_tool_call["function"]["arguments"])
        mcp_tool_call_template = (
            f"<use_mcp_tool>\n<server_name>{server_name}</server_name>\n"
            f"<tool_name>{tool_name}</tool_name>\n<arguments>\n"
            f"{json.dumps(arguments)}\n</arguments>\n</use_mcp_tool>"
        )
        mcp_tool_call_templates.append(mcp_tool_call_template)
    return "\n\n".join(mcp_tool_call_templates)
```

**逐步解释**：
- OpenAI 格式中，工具名形如 `server_name-tool_name`（用最后一个 `-` 分隔）。
- 将其拆分为 `server_name` 和 `tool_name`，解析 `arguments` 为 JSON 对象。
- 构造 MCP XML 格式字符串：`<use_mcp_tool>` 内嵌 `<server_name>`、`<tool_name>`、`<arguments>` 标签。
- 多个工具调用之间用双换行分隔。

### 2. 消息流转换主逻辑

```python
def oai_tool_message_to_chat_message(oai_messages, agent_type, tool_definition):
    chat_messages = []
    pending_user_tool_contents = []

    for idx, msg in enumerate(oai_messages):
        if msg["role"] in ["developer", "system"]:
            # 重建系统提示词（前言 + 时间 + 工具定义 + 原始 prompt）
            ...
        elif msg["role"] in ["user", "tool"]:
            pending_user_tool_contents.append(content)
        elif msg["role"] == "assistant" and "tool_calls" in msg:
            # 先刷新待处理的 user/tool 消息
            pending_user_tool_contents = flush_pending(...)
            # 拼接思考文本 + MCP 格式工具调用
            chat_messages.append({
                "role": "assistant",
                "content": content + convert_oai_tool_call_to_mcp_tool_call_str(msg["tool_calls"]),
            })
```

**逐步解释**：
- 使用"缓冲-刷新"模式处理消息流：连续的 `user` 和 `tool` 消息被收集到 `pending_user_tool_contents` 中。
- 当遇到 `assistant` 消息时，先将缓冲的 `user/tool` 消息合并为一条 `user` 消息刷入结果。
- `assistant` 消息如果包含 `tool_calls`，则将思考文本和 MCP 格式工具调用拼接在一起。
- 系统消息被重建：用预定义前言 (`system_prompts.py`) + 当前日期 + 工具定义 + 原始 prompt 的 `# General Objective` 部分组合而成。

### 3. 工具定义字符串生成

```python
def generate_mcp_servers_str(tool_definition):
    mcp_servers_str = ""
    for server in tool_definition:
        mcp_servers_str += f"## Server name: {server['name']}\n"
        for tool in server["tools"]:
            if "error" in tool and "name" not in tool:
                continue
            mcp_servers_str += f"### Tool name: {tool['name']}\n"
            mcp_servers_str += f"Description: {tool['description']}\n"
            mcp_servers_str += f"Input JSON schema: {tool['schema']}\n"
```

**逐步解释**：
- 从日志的 `step_logs` 中提取工具定义信息。
- 遍历每个 MCP 服务器及其工具，生成结构化的文本描述。
- 跳过加载失败的工具（只有 `error` 键没有 `name` 键的条目）。

## 核心类/函数表格

| 函数名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `oai_tool_message_to_chat_message` | `oai_messages, agent_type, tool_definition` | `List[Dict]` | 将 OAI 格式消息流转换为 ChatML 格式 |
| `extract_message_history_from_log` | `log_data: Dict` | `Dict` 含 `main_agent` 和 `sub_agents` | 从日志中提取并转换所有 Agent 的消息历史 |
| `save_chatml_to_files` | `chatml_data, output_dir, input_filename` | `None` | 将转换结果保存为 JSON 文件 |
| `extract_step_message` | `data, target_step_name` | `Any` | 从 step_logs 中提取指定步骤的消息（如工具定义） |
| `process_log_file` | `log_file_path, output_dir` | `None` | 处理单个日志文件的完整流程 |

## 与其他模块的关系

- 被 `convert_to_chatml_auto_batch.py` 作为子进程调用（当 LLM Provider 是 OpenAI/Claude/DeepSeek 时）。
- 依赖 `system_prompts.py` 提供系统提示词前言模板。
- 通过 `__init__.py` 导出核心函数供外部使用。
- 输出文件可被 `merge_chatml_msgs_to_one_json.py` 合并。

## 总结

这是转换器中最核心的模块，解决了从 OpenAI 结构化工具调用格式到 MCP XML 文本格式的转换问题。关键设计包括：用"缓冲-刷新"模式合并连续 user/tool 消息、从日志 step_logs 中提取工具定义来重建完整系统提示词，以及将 `server_name-tool_name` 命名约定映射回 MCP XML 结构。

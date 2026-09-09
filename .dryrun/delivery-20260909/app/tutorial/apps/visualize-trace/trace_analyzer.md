# `trace_analyzer.py` -- Trace 分析引擎

## 文件概述

本文件定义了 `TraceAnalyzer` 类，是 `visualize-trace` 的核心业务逻辑。它负责加载 Trace JSON 文件、解析消息历史、识别工具调用（支持新旧两种格式）、分析执行流程、以及生成各种统计摘要。

## 关键代码解读

### 1. 工具调用格式兼容

```python
class TraceAnalyzer:
    """
    支持两种工具调用格式：
    1. 旧格式 (MCP): 在 content 中使用 XML 标签格式
    2. 新格式: 在 message 的 tool_calls 字段中直接存储
    """
```

**逐步解释**：
- **旧格式（MCP XML）**：工具调用嵌入在 `assistant` 消息的 `content` 文本中，用 `<use_mcp_tool>...</use_mcp_tool>` 标签包裹。
- **新格式（OpenAI 兼容）**：工具调用存储在 `message.tool_calls` 列表中，每项包含 `function.name` 和 `function.arguments`。
- 分析器同时支持两种格式，确保兼容不同版本的日志。

### 2. 新格式工具名解析

```python
def _parse_new_format_tool_name(self, tool_name: str) -> tuple[str, str]:
    if tool_name.startswith("agent-browsing-"):
        server_name = "agent-browsing"
        actual_tool_name = tool_name[len("agent-browsing-"):]
        return server_name, actual_tool_name
    elif tool_name.startswith("agent-"):
        last_dash = tool_name.rfind("-")
        server_name = tool_name[:last_dash]
        actual_tool_name = tool_name[last_dash + 1:]
    elif tool_name.startswith("tool-"):
        parts = tool_name.split("-", 2)
        server_name = parts[1]
        actual_tool_name = parts[2]
```

**逐步解释**：
- 新格式的工具名是复合的，需要拆分为 `server_name` 和 `tool_name`。
- 三种命名约定：
  - `agent-browsing-*`：浏览 Agent 调用，前缀固定为 `agent-browsing`。
  - `agent-*`：其他 Agent 调用。
  - `tool-*-*`：普通工具调用，格式为 `tool-{server}-{name}`。

### 3. 执行流程分析

```python
def analyze_conversation_flow(self) -> List[Dict[str, Any]]:
    flow_steps = []
    main_messages = self.get_main_agent_messages()
    sub_agent_sessions = self.get_browser_agent_sessions()
    sub_agent_call_count = 0

    for i, message in enumerate(main_messages):
        role = message.get("role")
        step = {
            "step_id": i, "agent": "main_agent", "role": role,
            "content_preview": text_content[:200] + "...",
            "full_content": text_content, "tool_calls": [],
            "browser_session": None, "browser_flow": [],
        }

        if role == "assistant":
            # 检查新格式 tool_calls
            if "tool_calls" in message:
                for tool_call in message["tool_calls"]:
                    server_name, actual_tool_name = self._parse_new_format_tool_name(...)
                    step["tool_calls"].append(parsed_tool_call)
                    # 如果是 Agent 调用，关联浏览器子会话
                    if server_name.startswith("agent-"):
                        sub_agent_call_count += 1
                        session_id = f"{server_name}_{sub_agent_call_count}"
                        step["browser_flow"] = self.analyze_browser_session_flow(session_id)

            # 检查旧格式 MCP 工具调用
            mcp_tool_call = self.parse_mcp_tool_call(text_content)
            if mcp_tool_call:
                step["tool_calls"].append(mcp_tool_call)
```

**逐步解释**：
- 遍历主 Agent 的消息列表，为每条消息构建步骤对象。
- 对 `assistant` 消息，同时检查新格式和旧格式的工具调用。
- 如果工具调用的目标是子 Agent（`server_name` 以 `agent-` 开头），则递增计数器生成 `session_id`，并递归分析该子 Agent 的会话流程。
- 子 Agent 的会话流程作为 `browser_flow` 嵌套在主步骤中。

### 4. MCP XML 解析

```python
def parse_mcp_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
    pattern = r"<use_mcp_tool>\s*<server_name>(.*?)</server_name>\s*<tool_name>(.*?)</tool_name>\s*<arguments>\s*(.*?)\s*</arguments>\s*</use_mcp_tool>"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return {
            "server_name": match.group(1).strip(),
            "tool_name": match.group(2).strip(),
            "arguments": json.loads(arguments_str),
        }
```

**逐步解释**：
- 使用正则表达式从文本中提取 MCP XML 格式的工具调用。
- 解析出 `server_name`、`tool_name` 和 `arguments`（JSON 解析）。
- 这是旧格式兼容的关键方法。

### 5. 统计摘要

```python
def get_execution_summary(self) -> Dict[str, Any]:
    flow_steps = self.analyze_conversation_flow()
    tool_usage = {}
    for tool in tool_calls:
        if tool.get("format") == "new":
            key = f"{tool['server_name']}.{tool['tool_name']}"
        else:
            key = f"{tool['server_name']}.{tool['tool_name']}"
        tool_usage[key] = tool_usage.get(key, 0) + 1
    return {
        "total_steps": total_steps,
        "total_tool_calls": len(tool_calls),
        "tool_usage_distribution": tool_usage,
    }
```

**逐步解释**：
- 基于执行流程分析结果，统计总步骤数、总工具调用数。
- 生成工具使用分布（每个工具被调用的次数）。
- 同时统计主 Agent 和所有子 Agent 的工具调用。

## 核心类/函数表格

| 方法 | 说明 |
|------|------|
| `__init__(json_file_path)` | 加载并解析 JSON 文件 |
| `get_basic_info()` | 获取任务状态、ID、时间、答案、判定结果 |
| `get_performance_summary()` | 获取 trace_data 中的性能摘要 |
| `get_main_agent_messages()` | 获取主 Agent 消息列表 |
| `get_browser_agent_sessions()` | 获取所有子 Agent 会话（兼容两种键名） |
| `parse_mcp_tool_call(text)` | 从文本中解析 MCP XML 格式工具调用 |
| `_parse_new_format_tool_name(name)` | 解析新格式的复合工具名 |
| `analyze_conversation_flow()` | 分析主 Agent 的完整执行流程 |
| `analyze_browser_session_flow(session_id)` | 分析子 Agent 会话的执行流程 |
| `get_execution_summary()` | 生成执行统计摘要 |
| `get_spans_summary()` | 生成 Spans 统计摘要 |
| `get_step_logs_summary()` | 生成步骤日志统计摘要 |

## 与其他模块的关系

- 被 `app.py` 实例化并调用（所有 API 端点最终调用本类的方法）。
- 解析的 JSON 数据结构与 `apps/miroflow-agent/` 输出的日志格式对应。
- 解析的 MCP XML 格式与 `libs/miroflow-tools/` 中的工具调用格式一致。

## 总结

`TraceAnalyzer` 是整个仪表板的大脑，封装了所有 Trace 数据的解析和分析逻辑。最重要的设计决策是同时支持新旧两种工具调用格式，确保对不同版本日志的兼容性。通过将解析逻辑与 Web 层分离，`TraceAnalyzer` 也可以在非 Web 场景下（如脚本、Notebook）独立使用。

# `parsing_utils.py` — LLM 响应解析与工具调用提取

## 文件概述

`parsing_utils.py` 是 MiroThinker 中最关键的工具模块之一。它负责解析 LLM 的原始响应，从中提取工具调用信息（支持三种不同格式）、修复 LLM 输出中常见的服务器名称错误、以及安全地解析可能格式不正确的 JSON 字符串。

在项目中，每一轮 LLM 推理后，`AnthropicClient` 和 `OpenAIClient` 都会调用这里的函数来处理响应。

## 关键代码解读

### 服务器名称修复机制

LLM 在输出 MCP 工具调用时，有时会把 `server_name` 写错。这个模块通过两步机制来修复：

**第一步：解析系统提示建立映射**

```python
def parse_tool_server_mapping(system_prompt: str) -> dict:
    TARGET_TOOLS = {"run_python_code", "google_search", "scrape_and_extract_info"}
    mapping = {}
    current_server = None
    for line in system_prompt.split("\n"):
        server_match = re.match(r"## Server name:\s*(.+)", line)
        if server_match:
            current_server = server_match.group(1).strip()
            continue
        tool_match = re.match(r"### Tool name:\s*(.+)", line)
        if tool_match and current_server:
            tool_name = tool_match.group(1).strip()
            if tool_name in TARGET_TOOLS:
                mapping[tool_name] = current_server
    return mapping
```

**解释**：

- 从系统提示中解析 `## Server name:` 和 `### Tool name:` 标记
- 只关注三个最常被 LLM 搞错的工具：`run_python_code`、`google_search`、`scrape_and_extract_info`
- 构建 `{tool_name: correct_server_name}` 映射表

**第二步：在响应中修复错误**

```python
def fix_server_name_in_text(text: str) -> str:
    mapping = _tool_server_mapping
    if not mapping: return text

    # 修复 tool_name=python → run_python_code
    if "run_python_code" in mapping:
        for wrong_name in ("python", "python_code"):
            tag = f"<tool_name>{wrong_name}</tool_name>"
            if tag in text:
                text = text.replace(tag, "<tool_name>run_python_code</tool_name>")

    # 修复 server_name
    for tool_name, correct_server in mapping.items():
        tool_tag = f"<tool_name>{tool_name}</tool_name>"
        if tool_tag not in text: continue
        correct_server_tag = f"<server_name>{correct_server}</server_name>"
        if correct_server_tag in text: continue
        text = re.sub(
            r"<server_name>[^<]+</server_name>(\s*" + re.escape(tool_tag) + r")",
            correct_server_tag + r"\1",
            text,
        )
    return text
```

**解释**：

- 处理两类常见错误：
  1. 工具名错误：LLM 写 `python` 或 `python_code`，实际应为 `run_python_code`
  2. 服务器名错误：`<server_name>` 标签内容不正确
- 使用正则表达式定位 `<server_name>...<tool_name>` 的组合并替换

### 多格式工具调用解析

```python
def parse_llm_response_for_tool_calls(llm_response_content_text):
    # 格式1：OpenAI Response API (dict with 'output')
    if isinstance(llm_response_content_text, dict):
        for item in llm_response_content_text.get("output") or []:
            if item.get("type") == "function_call":
                name = item.get("name", "")
                server_name, tool_name = name.rsplit("-", maxsplit=1)
                arguments = safe_json_loads(item.get("arguments"))
                # ...

    # 格式2：OpenAI Completion API (list of tool_call objects)
    if isinstance(llm_response_content_text, list):
        for tool_call in llm_response_content_text:
            name = tool_call.function.name
            server_name, tool_name = name.rsplit("-", maxsplit=1)
            arguments = json.loads(tool_call.function.arguments)
            # ...

    # 格式3：MCP XML 格式 (string)
    tool_call_patterns = re.findall(
        r"<use_mcp_tool>\s*<server_name>(.*?)</server_name>\s*<tool_name>(.*?)</tool_name>\s*<arguments>\s*([\s\S]*?)\s*</arguments>\s*</use_mcp_tool>",
        llm_response_content_text,
        re.DOTALL,
    )
    for match in tool_call_patterns:
        server_name, tool_name = match[0].strip(), match[1].strip()
        arguments = safe_json_loads(match[2].strip())
        # ...

    return tool_calls
```

**解释**：

- 支持三种完全不同的工具调用格式：
  1. **OpenAI Response API**：工具调用是字典中 `output` 数组里的 `function_call` 条目
  2. **OpenAI Completion API**：工具调用是对象列表，每个对象有 `function.name` 和 `function.arguments`
  3. **MCP XML 格式**：工具调用嵌入在文本中的 `<use_mcp_tool>` XML 标签内
- 三种格式通过输入类型（dict / list / string）自动识别
- 工具名称使用 `server_name-tool_name` 拼接格式（用最后一个 `-` 分割）

### 安全 JSON 解析

```python
def safe_json_loads(arguments_str: str) -> Dict[str, Any]:
    # 第一步：标准 json.loads
    try:
        return json.loads(arguments_str)
    except json.JSONDecodeError:
        pass

    # 第二步：使用 json_repair 修复常见问题
    try:
        repaired = repair_json(arguments_str, ensure_ascii=False)
        return json.loads(repaired)
    except Exception:
        pass

    # 第三步：放弃，返回错误信息
    return {"error": "Failed to parse arguments", "raw": arguments_str}
```

**解释**：

- LLM 输出的 JSON 经常有各种格式问题（未转义的反斜杠、单引号、尾逗号等）
- 三层回退策略：标准解析 -> `json_repair` 修复 -> 返回原始字符串供人工检查
- `_fix_backslash_escapes()` 辅助函数专门处理 Windows 路径等常见的反斜杠问题

### 失败经验提取

```python
def extract_failure_experience_summary(text: str) -> str:
    think_content = ""
    content = ""

    think_match = re.search(r"<think>([\s\S]*?)</think>", text)
    if think_match:
        think_content = think_match.group(1).strip()
        after_think = text[think_match.end():]
    else:
        after_think = text

    mcp_match = re.search(r"<use_mcp_tool>[\s\S]*", after_think)
    if mcp_match:
        content = after_think[:mcp_match.start()].strip()
    else:
        content = after_think.strip()

    return content if content else think_content
```

**解释**：

- 从 LLM 响应中提取失败经验总结，用于重试机制
- 响应可能包含 `<think>` 思考块和 `<use_mcp_tool>` 工具调用块
- 优先返回思考块之后、工具调用之前的内容（这是 LLM 的实际分析）
- 如果该部分为空，回退到思考块内容

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `parse_llm_response_for_tool_calls()` | 函数 | 从三种格式的 LLM 响应中提取工具调用信息 |
| `fix_server_name_in_text()` | 函数 | 修复 LLM 输出中错误的 server_name 和 tool_name |
| `set_tool_server_mapping()` | 函数 | 解析系统提示并缓存工具-服务器映射 |
| `safe_json_loads()` | 函数 | 安全解析 JSON 字符串，含多层回退 |
| `extract_llm_response_text()` | 函数 | 提取 LLM 响应的纯文本部分（排除工具调用） |
| `extract_failure_experience_summary()` | 函数 | 提取失败经验总结用于重试 |
| `filter_none_values()` | 函数 | 从字典中移除值为 None 的键 |
| `_fix_backslash_escapes()` | 函数 | 修复 JSON 中的反斜杠转义问题 |

## 与其他模块的关系

- **`llm/providers/anthropic_client.py`** 和 **`llm/providers/openai_client.py`**：
  - 调用 `fix_server_name_in_text()` 修复响应中的服务器名称
  - 调用 `parse_llm_response_for_tool_calls()` 提取工具调用
  - 调用 `set_tool_server_mapping()` 初始化映射缓存
- **`core/Orchestrator`**：调用 `extract_failure_experience_summary()` 获取失败分析

## 总结

`parsing_utils.py` 是连接 LLM 输出和工具执行之间的关键桥梁。它的多格式工具调用解析器使得同一套核心逻辑可以支持不同的 LLM 提供商和调用方式。服务器名称自动修复机制是一个务实的工程决策——与其要求 LLM 完美遵循格式，不如在后处理中容错修复。

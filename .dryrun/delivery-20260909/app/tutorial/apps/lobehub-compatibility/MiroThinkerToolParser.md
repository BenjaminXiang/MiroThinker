# `MiroThinkerToolParser.py` -- vLLM 工具解析器插件

## 文件概述

本文件实现了 `MirothinkerToolParser`，一个注册到 vLLM 框架的工具解析器插件。它的核心任务是将 MiroThinker 模型输出的 MCP XML 格式工具调用（`<use_mcp_tool>` 标签）实时转换为 OpenAI 兼容的 `ToolCall`/`DeltaToolCall` 格式。支持非流式和流式两种模式。

## 关键代码解读

### 1. 正则表达式定义

```python
class MirothinkerToolParser(ToolParser):
    def __init__(self, tokenizer):
        super().__init__(tokenizer)
        # 完整匹配：所有标签都必须存在
        self.tool_call_regex = re.compile(
            r"<use_mcp_tool>\s*"
            r"<server_name>(.*?)</server_name>\s*"
            r"<tool_name>(.*?)</tool_name>\s*"
            r"<arguments>\s*(.*?)\s*</arguments>\s*"
            r"</use_mcp_tool>",
            re.DOTALL,
        )
        # 部分匹配（流式用）：各部分都是可选的
        self.partial_tool_regex = re.compile(
            r"<use_mcp_tool>\s*"
            r"(?:<server_name>(.*?)</server_name>\s*)?"
            r"(?:<tool_name>(.*?)</tool_name>\s*)?"
            r"(?:<arguments>(\s*.*))?",
            re.DOTALL,
        )
        # 完整块匹配（流式终结用）
        self._complete_tool_block_regex = re.compile(...)
```

**逐步解释**：
- **`tool_call_regex`**：用于非流式模式，严格匹配完整的 MCP XML 工具调用块。
- **`partial_tool_regex`**：用于流式模式中间状态，各子标签用 `(?:...)?` 设为可选。
- **`_complete_tool_block_regex`**：用于流式模式中检测到完整块后的最终解析。
- 所有正则使用 `re.DOTALL` 标志，使 `.` 匹配换行符。

### 2. 工具名解析

```python
def _resolve_tool_name(self, server_name, tool_name, request):
    if not server_name or server_name == "default":
        return tool_name

    cache_key = (server_name, tool_name)
    cached = self._resolved_tool_name_cache.get(cache_key)
    if cached:
        return cached

    candidates = []
    for tool in request.tools:
        name = tool.function.name
        if tool_name in name:
            candidates.append(name)

    for candidate in candidates:
        if server_name in candidate:
            self._resolved_tool_name_cache[cache_key] = candidate
            return candidate
    return tool_name
```

**逐步解释**：
- MCP 格式中的 `server_name` + `tool_name` 需要映射回 OpenAI 格式的单一 `function.name`。
- 遍历请求中注册的工具列表，找到同时包含 `tool_name` 和 `server_name` 的候选工具。
- 使用缓存避免重复查找。

### 3. 非流式提取

```python
def extract_tool_calls(self, model_output, request):
    if self.tool_call_start_token not in model_output:
        return ExtractedToolCallInformation(tools_called=False, content=model_output)

    tool_calls = []
    for match in self.tool_call_regex.finditer(model_output):
        server_name = match.group(1).strip()
        tool_name = match.group(2).strip()
        arguments_str = match.group(3).strip()

        tool_name = self._resolve_tool_name(server_name, tool_name, request)
        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError:
            repaired = json_repair.repair_json(arguments_str)
            arguments = json.loads(repaired)

        tool_calls.append(ToolCall(
            type="function",
            function=FunctionCall(name=tool_name, arguments=json.dumps(arguments)),
        ))

    content = model_output[:model_output.find(self.tool_call_start_token)]
    return ExtractedToolCallInformation(tools_called=True, tool_calls=tool_calls, content=content)
```

**逐步解释**：
- 快速检查：如果输出不包含 `<use_mcp_tool>`，直接返回无工具调用。
- 用 `finditer` 找到所有完整的工具调用匹配。
- JSON 解析失败时使用 `json_repair` 库尝试修复（处理模型输出的格式瑕疵）。
- 提取工具调用前的文本作为 `content`。
- 任何解析错误都会导致回退到"无工具调用"模式，避免丢失内容。

### 4. 流式提取（状态机）

```python
def extract_tool_calls_streaming(self, previous_text, current_text, delta_text, ...):
    # 状态机：text 模式和 tool 模式
    chunk = delta_text

    while chunk:
        if self._stream_mode == "text":
            start_idx = chunk.find(self.tool_call_start_token)
            if start_idx < 0:
                # 未找到开始标签，检查是否有前缀匹配
                prefix = _longest_token_prefix_at_end(chunk, self.tool_call_start_token)
                if prefix:
                    safe = chunk[:-len(prefix)]
                    emitted_text_parts.append(safe)
                    self._text_token_prefix = prefix  # 保存可能的前缀
                else:
                    emitted_text_parts.append(chunk)
                break

            # 找到开始标签，切换到 tool 模式
            emitted_text_parts.append(chunk[:start_idx])
            chunk = chunk[start_idx + len(self.tool_call_start_token):]
            self._stream_mode = "tool"
            continue

        # tool 模式：累积直到找到结束标签
        end_idx = chunk.find(self.tool_call_end_token)
        if end_idx < 0:
            self._tool_block_buffer += chunk
            break

        # 找到完整的工具块
        self._tool_block_buffer += chunk[:end_idx]
        tool_block = self.tool_call_start_token + self._tool_block_buffer + self.tool_call_end_token
        # 解析并生成 DeltaToolCall
        ...
```

**逐步解释**：
- 使用两状态机：`text`（普通文本）和 `tool`（工具调用块内部）。
- **text 模式**：正常输出文本，检测到 `<use_mcp_tool>` 时切换到 tool 模式。
- **tool 模式**：累积内容到缓冲区，检测到 `</use_mcp_tool>` 时解析完整块并生成 `DeltaToolCall`。
- **前缀匹配**：处理标签被 token 分割的情况（如 `<use_mcp` 在一个 chunk，`_tool>` 在下一个）。
- `_longest_token_prefix_at_end` 检查 chunk 末尾是否可能是标签的前缀。

### 5. 插件注册

```python
ToolParserManager.register_module("mirothinker", True, MirothinkerToolParser)
```

**逐步解释**：
- 将解析器注册到 vLLM 的 `ToolParserManager`，名称为 `"mirothinker"`。
- 启动 vLLM 时通过 `--tool-parser-plugin` 参数指定本文件即可激活。

## 核心类/函数表格

| 方法 | 说明 |
|------|------|
| `__init__` | 初始化正则表达式、状态变量 |
| `_resolve_tool_name` | 将 MCP 的 server_name + tool_name 映射为 OpenAI 的 function.name |
| `adjust_request` | 调整请求参数（禁用 skip_special_tokens） |
| `extract_tool_calls` | 非流式：从完整输出中提取所有工具调用 |
| `extract_tool_calls_streaming` | 流式：逐 token 解析，实时生成 DeltaToolCall |
| `_ensure_tool_id_valid` | 确保工具 ID 数组大小足够（辅助方法） |

## 与其他模块的关系

- 解析的 MCP XML 格式与 `system_prompts.py`（collect-trace）和 `trace_analyzer.py`（visualize-trace）中使用的格式一致。
- 依赖 vLLM 的 `ToolParser` 基类、协议类型（`ToolCall`、`DeltaToolCall` 等）。
- 依赖 `json_repair` 库处理模型输出的 JSON 格式瑕疵。

## 总结

`MirothinkerToolParser` 是一个精密的格式转换引擎，解决了 MCP XML 格式到 OpenAI 结构化格式的实时转换问题。流式模式的状态机设计是最复杂的部分——它必须正确处理标签被 token 边界分割的情况，同时确保普通文本不被延迟输出。非流式模式则通过正则匹配 + JSON 修复实现了鲁棒的提取逻辑。

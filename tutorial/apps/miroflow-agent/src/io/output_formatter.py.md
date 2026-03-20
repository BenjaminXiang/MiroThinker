# `output_formatter.py` — 输出格式化与答案提取

## 文件概述

`output_formatter.py` 负责 MiroThinker 智能体的**输出后处理**，主要包括三个功能：

1. 格式化工具调用结果，使其适合作为 LLM 的下一轮输入
2. 从 LLM 最终回答中提取 `\boxed{}` 包裹的答案
3. 生成包含 Token 使用统计的最终摘要

在项目中，`Orchestrator`（编排器）在每轮工具调用后使用它格式化结果，在任务结束时使用它提取最终答案。

## 关键代码解读

### 工具结果截断常量

```python
TOOL_RESULT_MAX_LENGTH = 100_000  # 100k 字符 ≈ 25k tokens
```

**解释**：工具返回的结果可能非常长（例如网页抓取），如果全部送入 LLM 会导致上下文溢出。这个常量设定了单个工具结果的最大长度限制。

### `\boxed{}` 内容提取

```python
def _extract_boxed_content(self, text: str) -> str:
    _BOXED_RE = re.compile(r"\\boxed\b", re.DOTALL)
    last_result = None
    i = 0
    n = len(text)

    while True:
        m = _BOXED_RE.search(text, i)
        if not m:
            break
        j = m.end()
        # 跳过空白
        while j < n and text[j].isspace():
            j += 1
        # 要求下一个字符是 '{'
        if j >= n or text[j] != "{":
            i = j
            continue
        # 手动解析大括号，处理嵌套和转义
        depth = 0
        k = j
        escaped = False
        found_closing = False
        while k < n:
            ch = text[k]
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    last_result = text[j + 1 : k]
                    found_closing = True
                    break
            k += 1
        # 处理未闭合的情况...

    black_list = ["?", "??", "???", "？", "……", "…", "...", "unknown", None]
    return last_result.strip() if last_result not in black_list else ""
```

**解释**：

- MiroThinker 要求 LLM 将最终答案包裹在 `\boxed{}` 中（类似 LaTeX 数学公式格式）
- 这个方法手动解析大括号匹配，而不是使用简单的正则表达式，因为需要处理：
  - 任意层级的嵌套大括号
  - 转义字符 `\{` 和 `\}`
  - `\boxed` 和 `{` 之间的空白
  - 不完整的（未闭合的）boxed 表达式
- 总是取**最后一个** `\boxed{}` 的内容（因为 LLM 可能在推理过程中输出多个中间 boxed 结果）
- 黑名单过滤掉无意义的答案（如 "?"、"unknown" 等）

### 工具结果格式化

```python
def format_tool_result_for_user(self, tool_call_execution_result: dict) -> dict:
    server_name = tool_call_execution_result["server_name"]
    tool_name = tool_call_execution_result["tool_name"]

    if "error" in tool_call_execution_result:
        content = f"Tool call to {tool_name} on {server_name} failed. Error: {tool_call_execution_result['error']}"
    elif "result" in tool_call_execution_result:
        content = tool_call_execution_result["result"]
        if len(content) > TOOL_RESULT_MAX_LENGTH:
            content = content[:TOOL_RESULT_MAX_LENGTH] + "\n... [Result truncated]"
    else:
        content = f"Tool call to {tool_name} on {server_name} completed, but produced no specific output."

    return {"type": "text", "text": content}
```

**解释**：

- 将工具执行结果转换为 LLM 消息格式 `{"type": "text", "text": ...}`
- 三种情况分别处理：错误、正常结果、无输出
- 超过 100K 字符的结果会被截断并附加提示

### 最终摘要生成

```python
def format_final_summary_and_log(self, final_answer_text, client=None):
    summary_lines = []
    summary_lines.append("\n" + "=" * 30 + " Final Answer " + "=" * 30)
    summary_lines.append(final_answer_text)

    boxed_result = self._extract_boxed_content(final_answer_text)

    if boxed_result:
        summary_lines.append(boxed_result)
    elif final_answer_text:
        summary_lines.append("No \\boxed{} content found.")
        boxed_result = FORMAT_ERROR_MESSAGE

    if client and hasattr(client, "format_token_usage_summary"):
        token_summary_lines, log_string = client.format_token_usage_summary()
        summary_lines.extend(token_summary_lines)

    return "\n".join(summary_lines), boxed_result, log_string
```

**解释**：

- 生成包含最终答案、提取结果、Token 使用量的完整摘要
- 如果没有找到 `\boxed{}` 内容，标记为格式错误（这会触发重试机制）
- Token 统计由 LLM 客户端提供，支持不同提供商的统计格式

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `OutputFormatter` | 类 | 输出格式化器，包含所有输出处理方法 |
| `_extract_boxed_content(text)` | 方法 | 从文本中提取最后一个 `\boxed{}` 的内容，支持嵌套和转义 |
| `format_tool_result_for_user(result)` | 方法 | 将工具执行结果格式化为 LLM 消息格式，含截断逻辑 |
| `format_final_summary_and_log(text, client)` | 方法 | 生成最终摘要，包含答案提取和 Token 统计 |
| `TOOL_RESULT_MAX_LENGTH` | 常量 | 工具结果的最大长度（100,000 字符） |

## 与其他模块的关系

- **`core/Orchestrator`**：在推理循环中调用 `format_tool_result_for_user()` 格式化工具结果；在任务结束时调用 `format_final_summary_and_log()` 生成摘要
- **`utils/prompt_utils.py`**：导入 `FORMAT_ERROR_MESSAGE` 常量，用于标记无 `\boxed{}` 的情况
- **`llm/` 模块**：通过 `client.format_token_usage_summary()` 获取 Token 使用统计

## 总结

`output_formatter.py` 是 MiroThinker 输出管道的关键组件。它的 `\boxed{}` 提取算法是一个精心设计的括号匹配解析器，能够处理各种边界情况。工具结果截断机制有效防止了上下文溢出问题。整体设计确保了从 LLM 的自由文本输出中可靠地提取出结构化的最终答案。

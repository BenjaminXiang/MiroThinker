# `example_usage.py` -- 转换器使用示例

## 文件概述

本文件提供了 `converters` 模块的使用示例代码，演示如何通过 Python API 调用转换函数。它构造了一个模拟的日志数据结构，分别展示 OAI 和 Non-OAI 两种转换方式的用法。

## 关键代码解读

### 示例：基本转换

```python
def example_1_basic_conversion():
    log_data = {
        "main_agent_message_history": {
            "system_prompt": "You are a helpful assistant.",
            "message_history": [
                {"role": "developer", "content": [{"type": "text", "text": "You are a helpful assistant."}]},
                {"role": "user", "content": [{"type": "text", "text": "Hello, how are you?"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "I'm doing well, thank you!"}]},
            ],
        },
        "browser_agent_message_history_sessions": { ... },
        "env_info": {"llm_provider": "openai"},
    }

    # OAI 方式
    chatml_data = extract_message_history_from_log(log_data)

    # Non-OAI 方式
    with tempfile.TemporaryDirectory() as temp_dir:
        extract_and_save_chat_history(log_data, Path(temp_dir), "example")
```

**逐步解释**：
- 构造一个包含主 Agent 和浏览 Agent 消息历史的模拟日志数据。
- **OAI 方式**：调用 `extract_message_history_from_log` 返回内存中的 ChatML 字典（包含 `main_agent` 和 `browser_agents` 键）。
- **Non-OAI 方式**：调用 `extract_and_save_chat_history` 直接写入临时目录，然后读取验证。
- 注意日志数据结构中的关键字段：`main_agent_message_history.message_history`（消息列表）和 `main_agent_message_history.system_prompt`（系统提示词）。

## 核心类/函数表格

| 函数名 | 说明 |
|--------|------|
| `example_1_basic_conversion` | 演示基本的 OAI 和 Non-OAI 转换流程 |

## 与其他模块的关系

- 导入 `converters` 包中的 `extract_and_save_chat_history`（Non-OAI）和 `extract_message_history_from_log`（OAI）。
- 作为参考代码，帮助开发者理解日志数据结构和 API 用法。

## 总结

这是一个教学性质的文件，展示了转换器的最小可运行示例。通过它可以快速理解日志数据的结构（`main_agent_message_history`、`sub_agent_message_history_sessions`）以及两种转换函数的调用方式。

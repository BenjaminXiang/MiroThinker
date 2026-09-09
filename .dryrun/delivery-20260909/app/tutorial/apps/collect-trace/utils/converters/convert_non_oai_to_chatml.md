# `convert_non_oai_to_chatml.py` -- 非 OpenAI 格式日志转 ChatML

## 文件概述

本文件负责将**非 OpenAI 格式**的 Agent 运行日志转换为标准的 ChatML JSON 格式。与 OAI 转换器不同，这个转换器处理的是不包含 `tool_calls` 字段的日志，转换逻辑相对简单：过滤掉 `tool` 和 `system` 角色的消息，将剩余消息标准化为 `{role, content}` 格式。

## 关键代码解读

### 1. 消息格式标准化

```python
def convert_to_json_chatml(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    chatml_list = []
    for message in messages:
        role = message.get("role", "")
        if role == "tool":
            continue  # 跳过工具消息
        if role == "system":
            continue  # 跳过系统消息
        content = message.get("content", "")
        if content is None:
            content = ""
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = " ".join(text_parts)
```

**逐步解释**：
- 遍历所有消息，跳过 `tool` 和 `system` 角色（这些不属于训练对话的一部分）。
- 处理 `content` 的多种格式：`None` 转为空字符串，列表格式（如 `[{"type": "text", "text": "..."}]`）提取文本并拼接，其他类型强制转字符串。
- 输出为统一的 `{"role": "...", "content": "..."}` 格式。

### 2. 日志提取与保存

```python
def extract_and_save_chat_history(
    log_data: Dict[str, Any], output_dir: Path, input_filename: str
):
    # 1. 提取 main_agent_message_history
    main_agent_history = log_data.get("main_agent_message_history", {})
    if main_agent_history and "message_history" in main_agent_history:
        main_messages = main_agent_history["message_history"]
        if main_messages:
            chatml_list = convert_to_json_chatml(main_messages)
            chatml_list.insert(0, {
                "role": "system",
                "content": main_agent_history.get("system_prompt", ""),
            })
```

**逐步解释**：
- 从日志数据中分别提取主 Agent 和子 Agent 的消息历史。
- 对主 Agent，先用 `convert_to_json_chatml` 转换消息，再在头部插入系统提示词。
- 对子 Agent（如浏览 Agent），遍历 `sub_agent_message_history_sessions` 中的每个会话，执行相同操作。
- 每个转换结果保存为独立的 JSON 文件，文件名包含原始任务名和 Agent 类型。

## 核心类/函数表格

| 函数名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `convert_to_json_chatml` | `messages: List[Dict]` | `List[Dict[str, str]]` | 过滤并标准化消息列表为 ChatML 格式 |
| `extract_and_save_chat_history` | `log_data, output_dir, input_filename` | `None` | 从日志中提取对话并保存为 JSON 文件 |
| `main` | 无 | `None` | CLI 入口，解析命令行参数并调用提取函数 |

## 与其他模块的关系

- 被 `convert_to_chatml_auto_batch.py` 作为子进程调用（当 LLM Provider 不是 OpenAI 时）。
- 通过 `__init__.py` 导出 `convert_to_json_chatml` 和 `extract_and_save_chat_history` 供其他模块直接导入使用。
- 输出的 JSON 文件可被 `merge_chatml_msgs_to_one_json.py` 合并。

## 总结

这是一个简单直接的消息格式转换器，核心逻辑是过滤非对话角色、统一 `content` 格式，然后分别保存主 Agent 和子 Agent 的对话历史。适用于不使用 OpenAI 工具调用格式的 LLM Provider。

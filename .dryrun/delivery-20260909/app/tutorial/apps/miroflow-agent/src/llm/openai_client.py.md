# `openai_client.py` — OpenAI 兼容 API 客户端

## 文件概述

`openai_client.py` 实现了与 OpenAI API（以及所有 OpenAI 兼容接口，如 vLLM、Qwen、DeepSeek 等）交互的客户端 `OpenAIClient`。它继承自 `BaseClient`，实现了包含**自适应重试**、**重复检测**、**长度限制处理**在内的健壮调用逻辑。

当 Hydra 配置的 `llm.provider` 为 `"openai"` 或 `"qwen"` 时，`ClientFactory` 会创建此客户端。

## 关键代码解读

### 发送消息（自适应重试循环）

```python
async def _create_message(self, system_prompt, messages_history, tools_definitions, keep_tool_result=-1):
    messages_for_llm = [m.copy() for m in messages_history]

    # 将 system_prompt 插入消息列表的开头
    if system_prompt:
        if messages_for_llm and messages_for_llm[0]["role"] in ["system", "developer"]:
            messages_for_llm[0] = {"role": "system", "content": system_prompt}
        else:
            messages_for_llm.insert(0, {"role": "system", "content": system_prompt})

    messages_for_llm = self._remove_tool_result_from_messages(messages_for_llm, keep_tool_result)

    max_retries = 10
    current_max_tokens = self.max_tokens

    for attempt in range(max_retries):
        params = {
            "model": self.model_name,
            "temperature": self.temperature,
            "messages": messages_for_llm,
            "stream": False,
            "top_p": self.top_p,
            "extra_body": {},
        }

        # GPT-5 使用不同的参数名
        if "gpt-5" in self.model_name:
            params["max_completion_tokens"] = current_max_tokens
        else:
            params["max_tokens"] = current_max_tokens

        response = await self.client.chat.completions.create(**params)

        # 响应被截断？增加 max_tokens 并重试
        if response.choices[0].finish_reason == "length":
            current_max_tokens = int(current_max_tokens * 1.1)
            continue

        # 检测严重重复（最后50字符出现5次以上）
        if resp_content and len(resp_content) >= 50:
            tail_50 = resp_content[-50:]
            if resp_content.count(tail_50) > 5:
                continue  # 重试

        return response, messages_history
```

**解释**：

这是 `OpenAIClient` 最核心的方法，与 `AnthropicClient` 相比有几个关键区别：

1. **系统提示位置不同**：OpenAI 的系统提示放在消息列表中（`role: "system"`），而非单独的参数
2. **自适应重试**：最多 10 次重试，每次因长度截断时将 `max_tokens` 增加 10%
3. **重复检测**：检查响应最后 50 个字符是否在全文中出现超过 5 次——这是开源模型常见的退化现象
4. **模型适配**：GPT-5 使用 `max_completion_tokens` 参数名，DeepSeek V3.1 需要启用 `thinking` 模式
5. **继续生成**：如果最后一条消息是 assistant，自动设置 `continue_final_message=True`

### 响应处理

```python
def process_llm_response(self, llm_response, message_history, agent_type="main"):
    if llm_response.choices[0].finish_reason == "stop":
        assistant_response_text = llm_response.choices[0].message.content or ""
        assistant_response_text = fix_server_name_in_text(assistant_response_text)
        message_history.append({"role": "assistant", "content": assistant_response_text})

    elif llm_response.choices[0].finish_reason == "length":
        # 长度截断的响应仍然可用
        assistant_response_text = llm_response.choices[0].message.content or ""
        if "Context length exceeded" in assistant_response_text:
            return assistant_response_text, True, message_history  # 需要退出循环
        message_history.append({"role": "assistant", "content": assistant_response_text})

    return assistant_response_text, False, message_history
```

**解释**：

- `finish_reason == "stop"` 表示正常完成，`"length"` 表示被截断
- 即使被截断的响应也会被使用（而不是丢弃），让推理循环继续进行
- 特殊处理上下文长度超出错误：返回 `True` 标记需要退出循环

### Token 使用量追踪

```python
def _update_token_usage(self, usage_data):
    if usage_data:
        input_tokens = getattr(usage_data, "prompt_tokens", 0)
        output_tokens = getattr(usage_data, "completion_tokens", 0)
        prompt_tokens_details = getattr(usage_data, "prompt_tokens_details", None)
        cached_tokens = getattr(prompt_tokens_details, "cached_tokens", None) or 0

        self.token_usage["total_input_tokens"] += input_tokens
        self.token_usage["total_output_tokens"] += output_tokens
        self.token_usage["total_cache_read_input_tokens"] += cached_tokens
```

**解释**：

- OpenAI 的用量字段名称与 Anthropic 不同：`prompt_tokens` 而非 `input_tokens`
- 缓存 Token 信息在 `prompt_tokens_details.cached_tokens` 中
- OpenAI 不提供 `cache_creation_tokens`（缓存写入是免费的）

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `OpenAIClient` | 数据类 | OpenAI 及兼容 API 的具体实现 |
| `_create_client()` | 方法 | 创建同步或异步的 OpenAI 客户端 |
| `_create_message()` | 异步方法 | 发送消息（含自适应重试和重复检测） |
| `process_llm_response()` | 方法 | 解析 OpenAI 响应，处理截断和错误 |
| `_update_token_usage()` | 方法 | 更新 OpenAI 格式的 Token 使用量统计 |
| `extract_tool_calls_info()` | 方法 | 从响应中提取工具调用信息 |
| `update_message_history()` | 方法 | 将工具结果追加到消息历史（OpenAI 格式） |
| `ensure_summary_context()` | 方法 | 上下文长度管理，与 AnthropicClient 类似 |

## 与其他模块的关系

- **`base_client.py`**：继承 `BaseClient` 抽象基类
- **`factory.py`**：当 `provider` 为 `"openai"` 或 `"qwen"` 时创建此客户端
- **`utils/parsing_utils.py`**：调用 `fix_server_name_in_text()` 和 `parse_llm_response_for_tool_calls()`
- **`utils/prompt_utils.py`**：调用 `generate_mcp_system_prompt()` 生成系统提示

## 总结

`OpenAIClient` 是一个针对 OpenAI 及兼容 API 的健壮客户端实现。它的自适应重试机制（动态增加 `max_tokens`）和重复检测（尾部字符频率分析）是应对开源模型不稳定输出的实用策略。与 `AnthropicClient` 相比，它不使用 Prompt Caching 标记（OpenAI 的缓存是自动管理的），但增加了更多的异常恢复机制来处理各种模型后端的差异。

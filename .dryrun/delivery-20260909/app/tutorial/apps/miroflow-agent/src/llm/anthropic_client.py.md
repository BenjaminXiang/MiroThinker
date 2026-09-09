# `anthropic_client.py` — Anthropic Claude API 客户端

## 文件概述

`anthropic_client.py` 实现了与 Anthropic Claude API 交互的具体客户端 `AnthropicClient`。它继承自 `BaseClient`，实现了 Claude 特有的功能，包括 **Prompt Caching**（提示缓存）、Token 使用量追踪（含缓存统计）、以及 MCP 工具调用的响应解析。

在项目中，当 Hydra 配置的 `llm.provider` 为 `"anthropic"` 时，`ClientFactory` 会创建此客户端的实例。

## 关键代码解读

### 客户端创建

```python
@dataclasses.dataclass
class AnthropicClient(BaseClient):
    def __post_init__(self):
        super().__post_init__()
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cache_creation_tokens: int = 0
        self.cache_read_tokens: int = 0

    def _create_client(self):
        http_client_args = {"headers": {"x-upstream-session-id": self.task_id}}
        if self.async_client:
            return AsyncAnthropic(
                api_key=self.api_key, base_url=self.base_url,
                http_client=DefaultAsyncHttpxClient(**http_client_args),
            )
        else:
            return Anthropic(
                api_key=self.api_key, base_url=self.base_url,
                http_client=DefaultHttpxClient(**http_client_args),
            )
```

**解释**：

- 额外维护四个 Anthropic 特有的 Token 计数器
- 通过自定义 HTTP 客户端注入 `x-upstream-session-id` 头，用于在代理/负载均衡场景下追踪会话
- 支持同步（`Anthropic`）和异步（`AsyncAnthropic`）两种模式

### Prompt Caching 机制

```python
def _apply_cache_control(self, messages):
    cached_messages = []
    user_turns_processed = 0
    for turn in reversed(messages):
        if turn["role"] == "user" and user_turns_processed < 1:
            new_content = []
            for item in turn["content"]:
                if item.get("type") == "text" and len(item.get("text")) > 0:
                    text_item = item.copy()
                    text_item["cache_control"] = {"type": "ephemeral"}
                    new_content.append(text_item)
                    break
            cached_messages.append({"role": "user", "content": new_content})
            user_turns_processed += 1
        else:
            cached_messages.append(turn)
    return list(reversed(cached_messages))
```

**解释**：

- Anthropic 的 Prompt Caching 通过在消息中添加 `cache_control: {"type": "ephemeral"}` 实现
- 策略：只对**最后一条用户消息**的第一个文本块添加缓存控制
- 系统提示同样添加缓存控制（在 `_create_message` 中）
- 这使得多轮对话中，之前的消息和系统提示可以被缓存，显著减少 Token 消耗

### 发送消息（带重试）

```python
@retry(wait=wait_fixed(10), stop=stop_after_attempt(5))
async def _create_message(self, system_prompt, messages_history, tools_definitions, keep_tool_result=-1):
    messages_for_llm = self._remove_tool_result_from_messages(messages_history, keep_tool_result)
    processed_messages = self._apply_cache_control(messages_for_llm)

    response = await self.client.messages.create(
        model=self.model_name,
        temperature=self.temperature,
        top_p=self.top_p if self.top_p != 1.0 else NOT_GIVEN,
        max_tokens=self.max_tokens,
        system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        messages=processed_messages,
        stream=False,
    )
    self._update_token_usage(getattr(response, "usage", None))
    return response, messages_history  # 返回原始历史，不是过滤后的
```

**解释**：

- 使用 `tenacity` 库的 `@retry` 装饰器：失败时等待 10 秒，最多重试 5 次
- 调用流程：过滤旧工具结果 -> 应用缓存控制 -> 发送请求
- `NOT_GIVEN` 是 Anthropic SDK 的特殊值，表示不传递该参数（避免传入默认值覆盖服务端行为）
- 关键设计：返回**原始的** `messages_history`（不是过滤后的副本），确保完整的对话历史被保存到日志

### 响应处理

```python
def process_llm_response(self, llm_response, message_history, agent_type="main"):
    assistant_response_text = ""
    assistant_response_content = []

    for block in llm_response.content:
        if block.type == "text":
            assistant_response_text += block.text + "\n"
            assistant_response_content.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            assistant_response_content.append({
                "type": "tool_use", "id": block.id,
                "name": block.name, "input": block.input,
            })

    assistant_response_text = fix_server_name_in_text(assistant_response_text)
    message_history.append({"role": "assistant", "content": assistant_response_content})
    return assistant_response_text, False, message_history
```

**解释**：

- Anthropic 的响应包含多个内容块（`content blocks`），每个块可以是文本或工具调用
- 调用 `fix_server_name_in_text()` 修正 LLM 可能输出的错误服务器名称
- 将完整的助手响应（包含工具调用块）追加到消息历史中

### 上下文长度管理

```python
def ensure_summary_context(self, message_history, summary_prompt):
    last_input_tokens = self.last_call_tokens.get("input_tokens", 0)
    last_output_tokens = self.last_call_tokens.get("output_tokens", 0)
    summary_tokens = int(self._estimate_tokens(str(summary_prompt)) * 1.5)
    estimated_total = last_input_tokens + last_output_tokens + summary_tokens + self.max_tokens + 1000

    if estimated_total >= self.max_context_length:
        # 删除最后一轮助手-用户对话
        if message_history[-1]["role"] == "user": message_history.pop()
        if message_history[-1]["role"] == "assistant": message_history.pop()
        return False, message_history

    return True, message_history
```

**解释**：

- 在生成最终总结前，检查添加总结提示后是否会超出上下文长度限制
- 如果会超出，删除最后一轮对话（工具结果和对应的助手请求）来腾出空间
- 使用 `tiktoken` 估算 Token 数量，乘以 1.5 的安全系数

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `AnthropicClient` | 数据类 | Anthropic Claude API 的具体实现 |
| `_create_client()` | 方法 | 创建同步或异步的 Anthropic 客户端 |
| `_create_message()` | 异步方法 | 发送消息到 Claude API（含缓存和重试） |
| `_apply_cache_control()` | 方法 | 为消息添加 Prompt Caching 标记 |
| `_update_token_usage()` | 方法 | 更新累积 Token 使用量统计 |
| `process_llm_response()` | 方法 | 解析 Claude 响应，提取文本和工具调用 |
| `extract_tool_calls_info()` | 方法 | 从响应文本中提取 MCP 格式的工具调用 |
| `ensure_summary_context()` | 方法 | 检查并管理上下文长度，必要时回退历史 |
| `format_token_usage_summary()` | 方法 | 格式化 Token 使用量统计报告 |

## 与其他模块的关系

- **`base_client.py`**：继承 `BaseClient` 抽象基类
- **`factory.py`**：当 `provider="anthropic"` 时创建此客户端
- **`utils/parsing_utils.py`**：调用 `fix_server_name_in_text()` 和 `parse_llm_response_for_tool_calls()` 处理响应
- **`utils/prompt_utils.py`**：调用 `generate_mcp_system_prompt()` 生成系统提示

## 总结

`AnthropicClient` 是针对 Claude API 的完整客户端实现。它的核心特色是 Prompt Caching 机制——通过在系统提示和最后一条用户消息上标记 `ephemeral` 缓存控制，在多轮对话中大幅减少了重复的 Token 输入。配合 `tenacity` 重试和上下文长度管理，提供了可靠的 LLM 调用体验。

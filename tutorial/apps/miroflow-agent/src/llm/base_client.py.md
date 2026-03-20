# `base_client.py` — LLM 客户端抽象基类

## 文件概述

`base_client.py` 定义了所有 LLM 提供商客户端的**抽象基类** `BaseClient`。它提供了统一的接口和共享逻辑，包括 Token 使用量跟踪、消息历史管理、工具定义转换、以及超时控制。Anthropic 和 OpenAI 的具体客户端都继承自这个基类。

在项目中，`BaseClient` 是整个 LLM 交互层的骨架，定义了所有子类必须遵循的"合同"。

## 关键代码解读

### TokenUsage 类型定义

```python
class TokenUsage(TypedDict, total=True):
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_input_tokens: int
    total_cache_write_input_tokens: int
```

**解释**：

- 使用 `TypedDict` 定义统一的 Token 使用量数据结构
- 四个字段覆盖了 OpenAI 和 Anthropic 两种提供商的 Token 统计需求
- `cache_read` 和 `cache_write` 对应 Prompt Caching 功能（两家提供商都支持缓存，但计费方式不同）

### BaseClient 数据类

```python
@dataclasses.dataclass
class BaseClient(ABC):
    task_id: str          # 任务唯一标识
    cfg: DictConfig       # Hydra 配置对象
    task_log: Optional["TaskLog"] = None

    client: Any = dataclasses.field(init=False)
    token_usage: TokenUsage = dataclasses.field(init=False)
    last_call_tokens: Dict[str, int] = dataclasses.field(init=False)

    def __post_init__(self):
        self.provider: str = self.cfg.llm.provider
        self.model_name: str = self.cfg.llm.model_name
        self.temperature: float = self.cfg.llm.temperature
        # ... 从 cfg 中提取所有 LLM 参数 ...
        self.token_usage = self._reset_token_usage()
        self.client = self._create_client()  # 子类实现
```

**解释**：

- 使用 `@dataclasses.dataclass` 定义，既有数据类的便利（自动 `__init__`），又继承了 `ABC` 的抽象约束
- `__post_init__` 中从 Hydra 配置提取所有 LLM 参数（provider、model_name、temperature、top_p、max_tokens 等）
- `_create_client()` 是抽象方法，由子类（AnthropicClient 或 OpenAIClient）实现具体的客户端创建逻辑

### 工具结果过滤（节省 Token）

```python
def _remove_tool_result_from_messages(self, messages, keep_tool_result) -> List[Dict]:
    messages_copy = [m.copy() for m in messages]
    if keep_tool_result == -1:
        return messages_copy  # 保留所有

    # 找到所有 user/tool 消息的索引
    user_indices = [i for i, msg in enumerate(messages_copy) if msg.get("role") in ("user", "tool")]

    # 第一条 user 消息是原始任务，不是工具结果
    tool_result_indices = user_indices[1:]

    # 只保留最近 N 条工具结果
    tool_result_indices_to_keep = tool_result_indices[-keep_tool_result:] if keep_tool_result > 0 else []

    # 替换被省略的工具结果内容
    for i, msg in enumerate(messages_copy):
        if (msg.get("role") in ("user", "tool")) and i not in indices_to_keep:
            msg["content"] = "Tool result is omitted to save tokens."

    return messages_copy
```

**解释**：

- 这是一个关键的 Token 节省策略：在长对话中，旧的工具结果占据大量上下文空间
- `keep_tool_result` 参数控制保留最近几条工具结果的完整内容
- 被省略的结果替换为短文本 `"Tool result is omitted to save tokens."`，保持消息结构完整但大幅减少 Token 消耗
- 原始任务描述（第一条 user 消息）始终保留

### 核心调用方法

```python
@with_timeout(DEFAULT_LLM_TIMEOUT_SECONDS)  # 600秒超时
async def create_message(self, system_prompt, message_history, tool_definitions,
                         keep_tool_result=-1, step_id=1, task_log=None, agent_type="main"):
    try:
        response, message_history = await self._create_message(
            system_prompt, message_history, tool_definitions,
            keep_tool_result=keep_tool_result,
        )
    except Exception as e:
        self.task_log.log_step("error", f"FATAL ERROR | {agent_type} | LLM Call ERROR", ...)
        response = None
    return response, message_history
```

**解释**：

- `create_message` 是所有 LLM 调用的统一入口
- 使用 `@with_timeout(600)` 装饰器，如果 LLM 调用超过 10 分钟自动取消
- 内部调用 `_create_message()`（由子类实现），并统一处理异常
- 错误不会向上传播，而是返回 `None`，由上层的 Orchestrator 决定如何处理

### 工具定义格式转换

```python
@staticmethod
async def convert_tool_definition_to_tool_call(tools_definitions):
    tool_list = []
    for server in tools_definitions:
        for tool in server["tools"]:
            tool_def = dict(
                type="function",
                function=dict(
                    name=f"{server['name']}-{tool['name']}",
                    description=tool["description"],
                    parameters=tool["schema"],
                ),
            )
            tool_list.append(tool_def)
    return tool_list
```

**解释**：

- 将 MCP 内部的工具定义格式转换为 OpenAI Function Calling 格式
- 工具名称使用 `server_name-tool_name` 的格式拼接，确保全局唯一
- 这个方法在使用 OpenAI 原生 Function Calling（而非 MCP XML 格式）时使用

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `TokenUsage` | TypedDict | 统一的 Token 使用量数据结构 |
| `BaseClient` | 抽象数据类 | LLM 客户端的抽象基类，定义统一接口 |
| `create_message()` | 异步方法 | LLM 调用的统一入口，含超时控制和错误处理 |
| `_remove_tool_result_from_messages()` | 方法 | 过滤旧的工具结果以节省 Token |
| `convert_tool_definition_to_tool_call()` | 静态方法 | 将 MCP 工具定义转换为 OpenAI Function Calling 格式 |
| `close()` | 方法 | 关闭客户端连接，支持同步和异步两种客户端 |
| `_format_response_for_log()` | 方法 | 将 LLM 响应格式化为日志友好的字典（截断长内容） |

## 与其他模块的关系

- **`providers/anthropic_client.py`** 和 **`providers/openai_client.py`**：继承 `BaseClient` 并实现具体的 API 调用
- **`factory.py`**：使用 `BaseClient` 的子类来创建实例
- **`util.py`**：提供 `@with_timeout` 装饰器
- **`logging/task_logger.py`**：通过 `task_log` 记录 LLM 调用的各类事件
- **`core/Orchestrator`**：调用 `create_message()` 进行 LLM 交互

## 总结

`base_client.py` 是 LLM 交互层的抽象骨架。它通过 `TokenUsage` 统一了不同提供商的 Token 统计，通过 `_remove_tool_result_from_messages` 实现了智能的上下文管理策略，通过 `@with_timeout` 提供了可靠的超时保护。子类只需实现 `_create_client()` 和 `_create_message()` 两个核心方法即可支持新的 LLM 提供商。

# `stream_handler.py` -- 实时流事件管理器

## 文件概述

`stream_handler.py` 提供了 `StreamHandler` 类，负责通过 SSE（Server-Sent Events）协议向客户端实时推送智能体执行过程中的各类事件。这些事件包括工作流生命周期、智能体启动/结束、LLM 调用状态、工具调用详情等。

在 MiroThinker 中，`StreamHandler` 是实现**前端实时可视化**的基础设施。Gradio 演示界面和 LobeChat 集成都依赖这些流事件来展示智能体的推理过程。

`StreamHandler` 的设计非常简洁：它只负责将事件放入异步队列，不关心事件的消费方式（可以是 WebSocket、SSE 或其他协议）。

## 关键代码解读

### 1. 核心发送方法：`update`

```python
class StreamHandler:
    def __init__(self, stream_queue: Optional[Any] = None):
        self.stream_queue = stream_queue

    async def update(self, event_type: str, data: dict):
        if self.stream_queue:
            try:
                stream_message = {
                    "event": event_type,
                    "data": data,
                }
                await self.stream_queue.put(stream_message)
            except Exception as e:
                logger.warning(f"Failed to send stream update: {e}")
```

所有事件的发送都通过 `update` 方法。它的设计有两个关键点：

- **可选队列**: 如果 `stream_queue` 为 `None`，所有事件静默丢弃。这使得流式推送成为可选功能，不影响核心逻辑。
- **异常静默**: 发送失败只记录警告日志，不抛出异常。流事件是"尽力而为"的附加功能，不应该因为推送失败而中断智能体的执行。

### 2. 工作流生命周期事件

```python
async def start_workflow(self, user_input: str) -> str:
    workflow_id = str(uuid.uuid4())
    await self.update("start_of_workflow", {
        "workflow_id": workflow_id,
        "input": [{"role": "user", "content": user_input}],
    })
    return workflow_id

async def end_workflow(self, workflow_id: str):
    await self.update("end_of_workflow", {"workflow_id": workflow_id})
```

每次任务执行对应一个工作流（workflow）。`start_workflow` 生成唯一的 `workflow_id` 并发送开始事件，`end_workflow` 发送结束事件。客户端通过 `workflow_id` 关联同一任务的所有事件。

### 3. 智能体生命周期事件

```python
async def start_agent(self, agent_name: str, display_name: str = None) -> str:
    agent_id = str(uuid.uuid4())
    await self.update("start_of_agent", {
        "agent_name": agent_name,
        "display_name": display_name,
        "agent_id": agent_id,
    })
    return agent_id

async def end_agent(self, agent_name: str, agent_id: str):
    await self.update("end_of_agent", {
        "agent_name": agent_name,
        "agent_id": agent_id,
    })
```

智能体事件支持 `display_name` 参数，用于在 UI 上显示更友好的名称。例如，当主智能体进入总结阶段时，`Orchestrator` 会传入 `display_name="Summarizing"`，让前端显示"正在总结"而不是 "main"。

### 4. LLM 调用状态事件

```python
async def start_llm(self, agent_name: str, display_name: str = None):
    await self.update("start_of_llm", {
        "agent_name": agent_name,
        "display_name": display_name,
    })

async def end_llm(self, agent_name: str):
    await self.update("end_of_llm", {"agent_name": agent_name})
```

LLM 调用事件让客户端知道当前正在等待 LLM 回复（可以显示加载动画等）。

### 5. 流式消息推送

```python
async def message(self, message_id: str, delta_content: str):
    await self.update("message", {
        "message_id": message_id,
        "delta": {"content": delta_content},
    })
```

`message` 事件用于流式推送 LLM 回复内容的增量（delta）。`message_id` 用于将多个 delta 关联到同一条消息。这使得客户端可以逐字显示 LLM 的回复，而不需要等待完整回复。

### 6. 工具调用事件（支持流式和非流式）

```python
async def tool_call(self, tool_name: str, payload: dict,
                     streaming: bool = False, tool_call_id: str = None) -> str:
    if not tool_call_id:
        tool_call_id = str(uuid.uuid4())

    if streaming:
        # 流式模式：逐个发送 payload 的每个键值对
        for key, value in payload.items():
            await self.update("tool_call", {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "delta_input": {key: value},
            })
    else:
        # 完整模式：一次发送所有数据
        await self.update("tool_call", {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "tool_input": payload,
        })

    return tool_call_id
```

工具调用事件是最灵活的事件类型：
- **非流式模式**（默认）: 将工具名和参数/结果一次性发送，使用 `tool_input` 字段。
- **流式模式**: 将 payload 的每个键值对作为 `delta_input` 分别发送，适合大型工具输出的渐进式展示。
- **双重用途**: 同一个方法既用于发送工具调用请求（`payload` 为参数），也用于发送工具调用结果（`payload` 中包含 `result`）。通过 `tool_call_id` 将请求和结果关联。

### 7. 错误事件与流终止

```python
async def show_error(self, error: str):
    await self.tool_call("show_error", {"error": error})
    if self.stream_queue:
        try:
            await self.stream_queue.put(None)
        except Exception as e:
            logger.warning(f"Failed to send show_error: {e}")
```

错误事件有特殊处理：发送错误信息后，向队列推送 `None` 作为**流终止信号**。消费端收到 `None` 就知道流已结束，可以关闭连接。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `StreamHandler` | 类 | 实时流事件管理器 |
| `update()` | 异步方法 | 底层事件发送方法，将事件放入异步队列 |
| `start_workflow()` | 异步方法 | 发送工作流开始事件，返回 `workflow_id` |
| `end_workflow()` | 异步方法 | 发送工作流结束事件 |
| `start_agent()` | 异步方法 | 发送智能体启动事件，返回 `agent_id` |
| `end_agent()` | 异步方法 | 发送智能体结束事件 |
| `start_llm()` | 异步方法 | 发送 LLM 调用开始事件 |
| `end_llm()` | 异步方法 | 发送 LLM 调用结束事件 |
| `message()` | 异步方法 | 发送流式消息增量（用于逐字输出） |
| `tool_call()` | 异步方法 | 发送工具调用事件（支持流式和非流式） |
| `show_error()` | 异步方法 | 发送错误事件并终止流 |

### 事件类型总览

| 事件类型 | 触发时机 | 携带数据 |
|---------|---------|---------|
| `start_of_workflow` | 任务开始 | `workflow_id`, 用户输入 |
| `end_of_workflow` | 任务结束 | `workflow_id` |
| `start_of_agent` | 智能体启动 | `agent_name`, `display_name`, `agent_id` |
| `end_of_agent` | 智能体结束 | `agent_name`, `agent_id` |
| `start_of_llm` | LLM 调用开始 | `agent_name`, `display_name` |
| `end_of_llm` | LLM 调用结束 | `agent_name` |
| `message` | LLM 流式回复 | `message_id`, `delta.content` |
| `tool_call` | 工具调用/结果 | `tool_call_id`, `tool_name`, `tool_input`/`delta_input` |

## 与其他模块的关系

```
core/orchestrator.py     --> 在主循环中调用各种流事件方法
core/answer_generator.py --> 调用 show_error() 推送错误事件
core/tool_executor.py    --> 持有 StreamHandler 引用（但主要通过 Orchestrator 间接使用）

apps/gradio-demo/        <-- 消费流事件，在网页 UI 中实时展示
apps/lobehub-compatibility/ <-- 消费流事件，转换为 LobeChat 格式
```

- `Orchestrator` 是 `StreamHandler` 的主要使用者，在工作流的每个关键节点都会调用相应的事件方法。
- `AnswerGenerator` 在检测到错误响应时调用 `show_error()`。
- 下游的 Gradio 演示和 LobeChat 集成负责消费这些事件并渲染到用户界面。

## 总结

`stream_handler.py` 是一个典型的**事件发布者**实现，只有约 237 行代码，但覆盖了智能体执行过程中的所有关键事件。它的设计遵循三个原则：

1. **可选性**: 流推送是可选的，`stream_queue=None` 时所有方法变为空操作。
2. **容错性**: 发送失败只记日志，不影响核心执行逻辑。
3. **协议无关性**: 只负责将事件放入队列，不关心消费端使用什么协议（SSE、WebSocket 等均可）。

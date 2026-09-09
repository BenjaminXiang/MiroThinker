# `main.py` -- Gradio Demo 主程序

## 文件概述

本文件是 `gradio-demo` 应用的核心，包含约 700 行代码，实现了完整的 Web UI 界面和后端逻辑。它基于 Gradio 的 `ChatInterface` 构建，支持深度研究和普通对话两种模式，并集成了 MiroFlow Agent Pipeline 作为深度研究后端。

## 关键代码解读

### 1. 配置加载

```python
def load_miroflow_config(config_overrides: Optional[dict] = None) -> DictConfig:
    global _hydra_initialized
    miroflow_config_dir = Path(__file__).parent.parent / "miroflow-agent" / "conf"

    if not _hydra_initialized:
        initialize_config_dir(config_dir=str(miroflow_config_dir), version_base=None)
        _hydra_initialized = True

    overrides = ["agent=mirothinker_v1.5"]
    if config_overrides:
        for key, value in config_overrides.items():
            overrides.append(f"{key}={value}")
    cfg = compose(config_name="config", overrides=overrides)
```

**逐步解释**：
- 使用 Hydra 框架加载 `miroflow-agent/conf/` 目录下的配置。
- 全局标志 `_hydra_initialized` 确保 Hydra 只初始化一次（Hydra 的限制）。
- 默认使用 `mirothinker_v1.5` Agent 变体，支持通过 `config_overrides` 覆盖配置项。
- 返回 `DictConfig` 对象供后续使用。

### 2. 深度研究模式（核心流程）

```python
async def run_deep_research(message: str, ...) -> AsyncGenerator[str, None]:
    cfg = load_miroflow_config(config_overrides=override_dict)
    pipeline_components = await create_pipeline_components(cfg, ...)

    accumulated_text = ""
    async for event in execute_task_pipeline(pipeline_components, ...):
        event_type = event.get("type", "")
        if event_type == "thinking":
            accumulated_text += event.get("text", "")
            yield accumulated_text
        elif event_type == "text":
            accumulated_text += event.get("text", "")
            yield accumulated_text
        elif event_type == "final_answer":
            final_text = event.get("text", "")
            yield final_text
```

**逐步解释**：
- `create_pipeline_components` 创建完整的 Pipeline 组件（工具管理器、LLM 客户端、格式化器等）。
- `execute_task_pipeline` 以异步生成器方式执行任务，逐步产出事件。
- 事件类型包括：`thinking`（思考过程）、`text`（普通文本）、`final_answer`（最终答案）、`tool_call`/`tool_result`（工具调用）。
- 通过 `yield` 实现流式输出，Gradio 前端实时显示。

### 3. 普通对话模式

```python
async def run_normal_chat(message: str, ...) -> AsyncGenerator[str, None]:
    client = get_openai_compatible_client(api_base, api_key, model_name)
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=True,
        temperature=0.6,
    )
    for chunk in response:
        if chunk.choices[0].delta.content:
            accumulated += chunk.choices[0].delta.content
            yield accumulated
```

**逐步解释**：
- 使用 OpenAI 兼容客户端直接调用 LLM API。
- 支持 vLLM 本地推理和远程 API 两种后端。
- 流式输出 token，无工具调用。

### 4. 任务取消机制

```python
async def cancel_task(session_id: str):
    if session_id in active_tasks:
        task = active_tasks[session_id]
        task.cancel()
        # 使用独立线程池进行清理，避免被 asyncio.cancel 中断
        cleanup_executor.submit(_cleanup_mcp_servers, session_id)
```

**逐步解释**：
- 每个会话维护一个 `asyncio.Task`，通过 `session_id` 索引。
- 取消时调用 `task.cancel()`，然后用独立的 `ThreadPoolExecutor` 清理 MCP 服务器资源。
- 使用独立线程池是关键设计：MCP 服务器清理是阻塞操作，如果放在被取消的协程中会失败。

### 5. Gradio UI 构建

```python
with gr.Blocks(title="MiroThinker", theme=gr.themes.Soft()) as demo:
    with gr.Row():
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(type="messages", ...)
            msg_input = gr.Textbox(...)
        with gr.Column(scale=1):
            # 配置面板
            deep_research_toggle = gr.Checkbox(label="Deep Research Mode", value=True)
            model_name_input = gr.Textbox(label="Model Name", ...)
            api_base_input = gr.Textbox(label="API Base URL", ...)
```

**逐步解释**：
- 左侧为聊天界面（占 3/4 宽度），右侧为配置面板（占 1/4）。
- 配置面板包含：深度研究模式开关、模型名称、API 地址、API Key、最大迭代次数等。
- 支持多会话管理（新建、切换、删除）。

## 核心类/函数表格

| 函数名 | 说明 |
|--------|------|
| `load_miroflow_config` | 加载 Hydra 配置 |
| `run_deep_research` | 深度研究模式的异步执行流程 |
| `run_normal_chat` | 普通对话模式的流式输出 |
| `respond` | Gradio 的消息响应入口，分发到深度研究或普通对话 |
| `cancel_task` | 取消正在执行的研究任务 |
| `get_openai_compatible_client` | 创建 OpenAI 兼容客户端 |
| `create_demo` | 构建 Gradio UI 界面 |

## 与其他模块的关系

- 导入 `prompt_patch.apply_prompt_patch()` 在启动时应用提示词补丁。
- 导入 `utils.replace_chinese_punctuation` 处理中文标点。
- 依赖 `apps/miroflow-agent/src/core/pipeline` 的 `create_pipeline_components` 和 `execute_task_pipeline`。
- 依赖 `apps/miroflow-agent/src/config/settings` 的 `expose_sub_agents_as_tools`。

## 总结

`main.py` 是一个功能完整的 Web Demo 应用，将 MiroThinker 的深度研究能力封装为交互式界面。核心设计包括：双模式运行、基于异步生成器的流式输出、独立线程池的任务取消清理、以及 Hydra 配置复用。代码量虽大但职责清晰，是 Agent 能力展示的标准方案。

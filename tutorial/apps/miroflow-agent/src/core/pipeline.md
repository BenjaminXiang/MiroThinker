# `pipeline.py` -- 任务执行流水线入口与组件工厂

## 文件概述

`pipeline.py` 是整个 core 模块的**入口文件**，提供两个关键函数：

1. `create_pipeline_components()` -- 工厂函数，根据 Hydra 配置创建所有必要的组件（工具管理器、输出格式化器）。
2. `execute_task_pipeline()` -- 执行函数，接收任务描述和已创建的组件，完成一次完整的任务执行流程。

在项目中，外部调用者（如 benchmark 运行器、Gradio 演示界面）通过这两个函数启动智能体任务，无需了解内部的 Orchestrator、ToolExecutor 等细节。

## 关键代码解读

### 组件创建流程

```python
def create_pipeline_components(cfg: DictConfig):
    # 1. 为主智能体创建 MCP 服务器配置和工具黑名单
    main_agent_mcp_server_configs, main_agent_blacklist = create_mcp_server_parameters(
        cfg, cfg.agent.main_agent
    )
    # 2. 用配置初始化 ToolManager
    main_agent_tool_manager = ToolManager(
        main_agent_mcp_server_configs,
        tool_blacklist=main_agent_blacklist,
    )

    # 3. 创建输出格式化器
    output_formatter = OutputFormatter()

    # 4. 如果没有子智能体，直接返回
    if not cfg.agent.sub_agents:
        return main_agent_tool_manager, {}, output_formatter

    # 5. 为每个子智能体创建独立的 ToolManager
    sub_agent_tool_managers = {}
    for sub_agent in cfg.agent.sub_agents:
        sub_agent_mcp_server_configs, sub_agent_blacklist = (
            create_mcp_server_parameters(cfg, cfg.agent.sub_agents[sub_agent])
        )
        sub_agent_tool_manager = ToolManager(
            sub_agent_mcp_server_configs,
            tool_blacklist=sub_agent_blacklist,
        )
        sub_agent_tool_managers[sub_agent] = sub_agent_tool_manager

    return main_agent_tool_manager, sub_agent_tool_managers, output_formatter
```

这段代码的核心逻辑是：**每个智能体（主智能体和子智能体）都有自己独立的 `ToolManager`**，通过 Hydra 配置中定义的 MCP 服务器列表和黑名单来区分它们可使用的工具集。例如，主智能体可能能调用子智能体，但子智能体不能再调用其他子智能体。

### 任务执行流程

```python
async def execute_task_pipeline(cfg, task_id, task_description, ...):
    # 1. 创建任务日志
    task_log = TaskLog(log_dir=log_dir, task_id=task_id, ...)

    # 2. 为所有 ToolManager 绑定日志实例
    main_agent_tool_manager.set_task_log(task_log)

    try:
        # 3. 创建 LLM 客户端（通过工厂模式支持 Anthropic/OpenAI/自定义）
        llm_client = ClientFactory(task_id=unique_id, cfg=cfg, task_log=task_log)

        # 4. 创建编排器
        orchestrator = Orchestrator(
            main_agent_tool_manager=main_agent_tool_manager,
            sub_agent_tool_managers=sub_agent_tool_managers,
            llm_client=llm_client,
            output_formatter=output_formatter,
            cfg=cfg,
            task_log=task_log,
            ...
        )

        # 5. 执行主智能体任务
        (final_summary, final_boxed_answer, failure_experience_summary) = (
            await orchestrator.run_main_agent(
                task_description=task_description,
                task_file_name=task_file_name,
                task_id=task_id,
            )
        )

        # 6. 保存结果并返回
        task_log.final_boxed_answer = final_boxed_answer
        task_log.status = "success"
        log_file_path = task_log.save()
        return (final_summary, final_boxed_answer, log_file_path, failure_experience_summary)

    except Exception as e:
        # 7. 异常处理：记录错误、保存日志、返回错误信息
        task_log.status = "failed"
        task_log.error = traceback.format_exc()
        log_file_path = task_log.save()
        return error_message, "", log_file_path, None

    finally:
        # 8. 无论成功失败，记录结束时间
        task_log.end_time = get_utc_plus_8_time()
        task_log.save()
```

这里的关键设计：函数用 `try/except/finally` 确保**即使发生异常也能保存完整的执行日志**，不会丢失调试信息。返回的四元组 `(summary, boxed_answer, log_path, failure_summary)` 让调用者能同时获取答案和元数据。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `execute_task_pipeline()` | 异步函数 | 执行单个任务的完整流水线：创建日志 -> 初始化 LLM -> 创建编排器 -> 运行主智能体 -> 返回结果 |
| `create_pipeline_components()` | 同步函数 | 根据 Hydra 配置创建主智能体和子智能体的 ToolManager，以及 OutputFormatter |

### 参数说明

`execute_task_pipeline` 的关键参数：

| 参数 | 类型 | 说明 |
|------|------|------|
| `cfg` | `DictConfig` | Hydra 配置对象，包含 LLM、智能体、基准测试等所有配置 |
| `task_id` | `str` | 任务唯一标识符，用于日志和追踪 |
| `task_description` | `str` | 给 LLM 的任务描述文本 |
| `task_file_name` | `str` | 关联文件路径（如图片、文档），空字符串表示无文件 |
| `main_agent_tool_manager` | `ToolManager` | 主智能体的工具管理器实例 |
| `ground_truth` | `Any` | 可选的标准答案，用于基准测试评估 |
| `stream_queue` | `Any` | 可选的异步队列，用于实时流式推送执行事件 |
| `is_final_retry` | `bool` | 是否是最后一次重试，影响答案生成策略 |

## 与其他模块的关系

```
config/settings.py  ──> create_mcp_server_parameters()  ──> pipeline.py
                         get_env_info()                       |
                                                              |
llm/factory.py      ──> ClientFactory                   <──  |
io/output_formatter  ──> OutputFormatter                <──  |
logging/task_logger  ──> TaskLog                        <──  |
                                                              |
orchestrator.py      <── Orchestrator                   <──  |
```

- **上游依赖**: `config/settings.py` 提供 MCP 服务器参数和环境信息；`llm/factory.py` 提供 LLM 客户端工厂。
- **下游调用**: 创建 `Orchestrator` 并调用其 `run_main_agent()` 方法。
- **外部调用者**: benchmark 运行器、Gradio 演示界面等通过这两个函数启动任务。

## 总结

`pipeline.py` 是 core 模块的**唯一对外接口**。它将组件创建（`create_pipeline_components`）和任务执行（`execute_task_pipeline`）解耦为两个独立函数，使得调用者可以一次创建组件、多次执行不同任务（复用 ToolManager 实例）。整个文件不到 220 行，职责清晰：**组装零件，启动引擎，处理异常**。

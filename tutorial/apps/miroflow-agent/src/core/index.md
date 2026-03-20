# Core 模块概览 -- MiroThinker 智能体核心执行引擎

## 模块架构图

```
                        +------------------+
                        |   pipeline.py    |
                        | (入口 & 工厂函数) |
                        +--------+---------+
                                 |
                    创建组件 & 启动任务
                                 |
                                 v
                        +------------------+
                        | orchestrator.py  |
                        | (主执行循环编排器)|
                        +--------+---------+
                                 |
              +------------------+------------------+
              |                  |                  |
              v                  v                  v
    +-----------------+  +-----------------+  +------------------+
    | tool_executor.py|  |answer_generator |  | stream_handler.py|
    | (工具调用执行器) |  |      .py        |  | (实时流事件管理器)|
    |                 |  | (答案生成器)     |  |                  |
    +-----------------+  +-----------------+  +------------------+
```

**数据流方向**: `pipeline` -> `orchestrator` -> (`tool_executor` + `answer_generator` + `stream_handler`)

## 各文件概览表

| 文件名 | 核心职责 | 主要类/函数 | 代码行数 |
|--------|---------|------------|---------|
| `pipeline.py` | 流水线入口：创建所有组件、启动任务执行 | `execute_task_pipeline()`, `create_pipeline_components()` | ~218 |
| `orchestrator.py` | 主编排器：协调多轮推理、子智能体委派、工具管理 | `Orchestrator` | ~1203 |
| `tool_executor.py` | 工具调用执行：参数修正、重复检测、结果后处理 | `ToolExecutor` | ~357 |
| `answer_generator.py` | 最终答案生成：LLM 调用处理、重试机制、上下文压缩 | `AnswerGenerator` | ~592 |
| `stream_handler.py` | 实时流事件：通过 SSE 协议向客户端推送执行状态 | `StreamHandler` | ~237 |
| `__init__.py` | 模块导出：统一暴露核心类和函数 | - | ~20 |

## 数据流说明

### 1. 任务启动阶段

```
用户任务描述
    |
    v
pipeline.create_pipeline_components(cfg)
    |-- 创建 main_agent_tool_manager (主智能体工具管理器)
    |-- 创建 sub_agent_tool_managers (子智能体工具管理器字典)
    |-- 创建 output_formatter (输出格式化器)
    |
    v
pipeline.execute_task_pipeline(...)
    |-- 创建 TaskLog (任务日志)
    |-- 创建 ClientFactory (LLM 客户端)
    |-- 创建 Orchestrator (编排器，内部自动创建 StreamHandler, ToolExecutor, AnswerGenerator)
    |-- 调用 orchestrator.run_main_agent(...)
```

### 2. 主循环执行阶段

```
orchestrator.run_main_agent()
    |
    v
[循环开始] turn_count < max_turns
    |
    |-- answer_generator.handle_llm_call()  --> 调用 LLM，获取回复和工具调用
    |       |
    |       |-- stream_handler.start_llm()  --> 推送 LLM 开始事件
    |       |-- llm_client.create_message() --> 实际 API 调用
    |       |-- 解析回复文本 & 工具调用信息
    |
    |-- [如果有工具调用]
    |       |-- tool_executor.fix_tool_call_arguments()  --> 修正参数
    |       |-- orchestrator._check_duplicate_query()    --> 重复检测
    |       |-- tool_manager.execute_tool_call()         --> 执行工具
    |       |-- tool_executor.post_process_tool_call_result() --> 后处理
    |       |-- stream_handler.tool_call()               --> 推送工具调用事件
    |
    |-- [如果是子智能体调用]
    |       |-- orchestrator.run_sub_agent()  --> 启动子智能体独立循环
    |
    |-- llm_client.update_message_history()  --> 更新对话历史
    |-- llm_client.ensure_summary_context()  --> 检查上下文长度
    |
    v
[循环结束]
```

### 3. 答案生成阶段

```
answer_generator.generate_and_finalize_answer()
    |
    |-- [根据上下文管理设置决定策略]
    |       |
    |       |-- 上下文管理关闭 --> generate_final_answer_with_retries() --> 中间答案回退
    |       |-- 上下文管理开启 + 未达最大轮次 --> generate_final_answer_with_retries() --> 不回退
    |       |-- 上下文管理开启 + 达到最大轮次 --> 跳过生成 --> generate_failure_summary()
    |
    v
返回 (final_summary, final_boxed_answer, failure_experience_summary)
```

### 4. 流事件生命周期

```
start_of_workflow
  |-- start_of_agent("main")
  |     |-- start_of_llm("main")
  |     |     |-- tool_call(...)    (可能多次)
  |     |     |-- message(...)      (流式内容)
  |     |-- end_of_llm("main")
  |     |
  |     |-- [子智能体场景]
  |     |     start_of_agent("browsing")
  |     |       |-- start_of_llm / tool_call / end_of_llm
  |     |     end_of_agent("browsing")
  |     |
  |-- end_of_agent("main")
  |-- start_of_agent("Final Summary")
  |     |-- start_of_llm / end_of_llm
  |-- end_of_agent("Final Summary")
end_of_workflow
```

### 核心设计原则

1. **分层委派**: 主智能体可以将子任务委派给专门的子智能体（如浏览智能体），每个子智能体拥有独立的工具集和轮次限制。
2. **回滚保护**: 当检测到格式错误、LLM 拒绝回答、重复查询或工具执行错误时，系统会回滚当前轮次并重试，最多连续回滚 5 次。
3. **上下文压缩**: 当对话历史超出上下文窗口时，系统可以生成"失败经验摘要"，将整个对话压缩为结构化信息供下次重试使用。
4. **实时流式通信**: 通过 SSE 协议，客户端可以实时观察智能体的推理过程、工具调用和中间结果。

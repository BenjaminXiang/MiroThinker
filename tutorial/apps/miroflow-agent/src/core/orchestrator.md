# `orchestrator.py` -- 智能体任务执行的核心编排器

## 文件概述

`orchestrator.py` 是整个 MiroThinker 智能体框架中**最核心、最复杂**的文件（约 1200 行）。它包含 `Orchestrator` 类，负责：

- 管理主智能体的**多轮推理循环**（主循环）
- 管理子智能体的独立执行循环
- 协调 LLM 调用、工具执行、流事件推送
- 处理格式错误、LLM 拒绝、重复查询等异常情况
- 在循环结束后生成最终答案

可以把 `Orchestrator` 理解为一个**指挥官**：它不直接执行具体操作（那是 `ToolExecutor` 和 `AnswerGenerator` 的工作），而是决定"接下来做什么"、"出了问题怎么办"。

## 关键代码解读

### 1. 初始化：组装三大辅助组件

```python
class Orchestrator:
    def __init__(self, main_agent_tool_manager, sub_agent_tool_managers,
                 llm_client, output_formatter, cfg, task_log, ...):
        # 保存依赖
        self.main_agent_tool_manager = main_agent_tool_manager
        self.llm_client = llm_client
        self.cfg = cfg

        # 跟踪中间答案和已用查询（去重）
        self.intermediate_boxed_answers: List[str] = []
        self.used_queries: Dict[str, Dict[str, int]] = {}

        # 创建三大辅助组件
        self.stream = StreamHandler(stream_queue)
        self.tool_executor = ToolExecutor(
            main_agent_tool_manager=main_agent_tool_manager,
            sub_agent_tool_managers=sub_agent_tool_managers,
            ...
        )
        self.answer_generator = AnswerGenerator(
            llm_client=llm_client,
            intermediate_boxed_answers=self.intermediate_boxed_answers,
            ...
        )
```

`Orchestrator` 在初始化时创建了三个辅助组件：`StreamHandler`（事件推送）、`ToolExecutor`（工具执行）、`AnswerGenerator`（答案生成）。这三个组件各自封装了独立的职责，`Orchestrator` 负责在正确的时机调用它们。

### 2. 工具定义缓存：`_list_tools` 工厂函数

```python
def _list_tools(sub_agent_tool_managers: Dict[str, ToolManager]):
    cache = None

    async def wrapped():
        nonlocal cache
        if cache is None:
            result = {
                name: await tool_manager.get_all_tool_definitions()
                for name, tool_manager in sub_agent_tool_managers.items()
            }
            cache = result
        return cache

    return wrapped
```

这是一个**闭包缓存模式**：第一次调用 `wrapped()` 时，异步获取所有子智能体的工具定义并缓存；后续调用直接返回缓存结果。这避免了每次子智能体启动时重复请求 MCP 服务器获取工具列表。

### 3. 主循环核心逻辑：`run_main_agent`

```python
async def run_main_agent(self, task_description, task_file_name=None, task_id="default_task"):
    # ---- 准备阶段 ----
    # 处理输入、获取工具定义、生成系统提示词
    initial_user_content, processed_task_desc = process_input(task_description, task_file_name)
    message_history = [{"role": "user", "content": initial_user_content}]
    tool_definitions = await self.main_agent_tool_manager.get_all_tool_definitions()
    system_prompt = self.llm_client.generate_agent_system_prompt(...)

    # ---- 主循环 ----
    max_turns = self.cfg.agent.main_agent.max_turns
    turn_count = 0
    consecutive_rollbacks = 0

    while turn_count < max_turns and total_attempts < max_attempts:
        turn_count += 1

        # 安全阀：连续回滚次数过多则强制退出
        if consecutive_rollbacks >= self.MAX_CONSECUTIVE_ROLLBACKS:
            break

        # 1) 调用 LLM
        (assistant_response_text, should_break, tool_calls, message_history
        ) = await self.answer_generator.handle_llm_call(...)

        # 2) 提取中间boxed答案
        boxed_content = self.output_formatter._extract_boxed_content(assistant_response_text)
        if boxed_content:
            self.intermediate_boxed_answers.append(boxed_content)

        # 3) 如果没有工具调用 -> 检查格式问题或正常结束
        if not tool_calls:
            (should_continue, should_break_loop, ...) = await self._handle_response_format_issues(...)
            ...

        # 4) 执行工具调用
        for call in tool_calls:
            if server_name.startswith("agent-"):
                # 子智能体调用
                sub_agent_result = await self.run_sub_agent(server_name, arguments["subtask"])
            else:
                # 普通工具调用
                tool_result = await self.main_agent_tool_manager.execute_tool_call(...)

        # 5) 更新对话历史、检查上下文长度
        message_history = self.llm_client.update_message_history(...)
        pass_length_check, message_history = self.llm_client.ensure_summary_context(...)

    # ---- 最终答案生成 ----
    (final_summary, final_boxed_answer, failure_experience_summary, usage_log, message_history
    ) = await self.answer_generator.generate_and_finalize_answer(...)

    return final_summary, final_boxed_answer, failure_experience_summary
```

主循环的每一轮都遵循相同的流程：**LLM 推理 -> 解析工具调用 -> 执行工具 -> 更新历史 -> 检查上下文**。循环在以下情况退出：
- LLM 不再请求工具调用（任务完成）
- 达到最大轮次
- 上下文窗口耗尽
- 连续回滚次数过多

### 4. 回滚保护机制

```python
async def _handle_response_format_issues(self, assistant_response_text, message_history,
                                          turn_count, consecutive_rollbacks, ...):
    # 检查 MCP 标签格式错误
    if any(mcp_tag in assistant_response_text for mcp_tag in mcp_tags):
        if consecutive_rollbacks < self.MAX_CONSECUTIVE_ROLLBACKS - 1:
            turn_count -= 1            # 回退轮次计数
            consecutive_rollbacks += 1
            message_history.pop()      # 移除错误回复
            return True, False, ...    # should_continue=True -> 重试
        else:
            return False, True, ...    # should_break=True -> 放弃

    # 检查 LLM 拒绝关键词
    if any(keyword in assistant_response_text for keyword in refusal_keywords):
        # 同样的回滚逻辑...
```

当 LLM 的回复包含错误的 MCP 标签格式或拒绝回答的关键词时，系统会：
1. 从 `message_history` 中移除这条错误回复
2. 将 `turn_count` 减 1（相当于"这一轮不算"）
3. 递增 `consecutive_rollbacks` 计数器
4. 如果连续回滚超过 5 次，则放弃重试

### 5. 重复查询检测

```python
async def _check_duplicate_query(self, tool_name, arguments, cache_name, ...):
    query_str = self.tool_executor.get_query_str_from_tool_call(tool_name, arguments)
    if not query_str:
        return False, False, ...

    count = self.used_queries[cache_name][query_str]
    if count > 0:
        if consecutive_rollbacks < self.MAX_CONSECUTIVE_ROLLBACKS - 1:
            message_history.pop()
            turn_count -= 1
            consecutive_rollbacks += 1
            return True, True, ...  # is_duplicate=True, should_rollback=True
```

当 LLM 试图重复执行相同的搜索查询或抓取相同的 URL 时，系统会检测到重复并回滚，避免浪费轮次。如果连续回滚次数已达上限，则允许重复执行（避免无限回滚）。

### 6. 子智能体执行：`run_sub_agent`

```python
async def run_sub_agent(self, sub_agent_name, task_description):
    # 独立的消息历史
    message_history = [{"role": "user", "content": task_description}]

    # 独立的系统提示词（包含子智能体特定指令）
    system_prompt = self.llm_client.generate_agent_system_prompt(...) + \
                    generate_agent_specific_system_prompt(agent_type=sub_agent_name)

    # 独立的轮次限制
    max_turns = self.cfg.agent.sub_agents[sub_agent_name].max_turns

    # 与主循环结构相同的执行循环
    while turn_count < max_turns:
        # LLM 调用 -> 工具执行 -> 更新历史 -> 检查上下文
        ...

    # 生成总结并返回
    summary_prompt = generate_agent_summarize_prompt(task_description, agent_type=sub_agent_name)
    ...
    return final_answer_text
```

子智能体拥有**完全独立的上下文**：独立的消息历史、系统提示词、工具集和轮次限制。这使得子智能体可以专注于子任务，不受主智能体已有上下文的干扰。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `Orchestrator` | 类 | 核心编排器，管理主智能体和子智能体的完整执行生命周期 |
| `Orchestrator.__init__()` | 方法 | 初始化编排器，创建 StreamHandler、ToolExecutor、AnswerGenerator |
| `Orchestrator.run_main_agent()` | 异步方法 | 执行主智能体的完整任务：准备 -> 多轮循环 -> 生成最终答案 |
| `Orchestrator.run_sub_agent()` | 异步方法 | 执行子智能体的独立任务循环并返回总结 |
| `Orchestrator._handle_response_format_issues()` | 异步方法 | 检测 MCP 标签错误和拒绝关键词，决定是否回滚 |
| `Orchestrator._check_duplicate_query()` | 异步方法 | 检测重复查询并决定是否回滚 |
| `Orchestrator._record_query()` | 异步方法 | 记录成功执行的查询，用于后续去重 |
| `Orchestrator._save_message_history()` | 方法 | 保存消息历史到任务日志 |
| `_list_tools()` | 模块级工厂函数 | 创建带缓存的子智能体工具定义获取函数 |

### 关键常量

| 常量 | 值 | 说明 |
|------|---|------|
| `DEFAULT_LLM_TIMEOUT` | 600 | LLM 调用超时时间（秒） |
| `DEFAULT_MAX_CONSECUTIVE_ROLLBACKS` | 5 | 最大连续回滚次数 |
| `EXTRA_ATTEMPTS_BUFFER` | 200 | 超出 max_turns 的额外尝试次数缓冲（防止回滚导致无限循环） |

## 与其他模块的关系

```
io/input_handler.py    ──> process_input()          用于预处理任务输入
io/output_formatter.py ──> OutputFormatter           用于格式化输出和提取 boxed 答案
llm/base_client.py     ──> BaseClient                用于 LLM API 调用
logging/task_logger.py ──> TaskLog                   用于结构化日志记录
utils/parsing_utils.py ──> extract_llm_response_text 用于解析 LLM 回复
utils/prompt_utils.py  ──> 各种提示词生成函数          用于构建系统/总结提示词
config/settings.py     ──> expose_sub_agents_as_tools 将子智能体暴露为可调用工具

core/answer_generator.py ──> AnswerGenerator         处理 LLM 调用和最终答案生成
core/tool_executor.py    ──> ToolExecutor            处理工具调用执行和结果后处理
core/stream_handler.py   ──> StreamHandler           处理实时流事件推送
```

`Orchestrator` 是 core 模块内部的**中心节点**，它依赖几乎所有其他 core 组件，同时也依赖 `io`、`llm`、`utils`、`config`、`logging` 等外部模块。

## 总结

`orchestrator.py` 实现了 MiroThinker 的核心执行逻辑：一个带有回滚保护和重复检测的多轮推理循环。它的设计体现了三个关键思想：

1. **层次化智能体**: 主智能体委派子任务给子智能体，每个子智能体拥有独立上下文和工具集。
2. **防御性编程**: 回滚机制、连续错误计数器、总尝试次数上限等多重保护，确保循环不会失控。
3. **职责分离**: 编排器只负责"决策和协调"，具体的 LLM 调用、工具执行、流事件推送分别委托给专门的组件。

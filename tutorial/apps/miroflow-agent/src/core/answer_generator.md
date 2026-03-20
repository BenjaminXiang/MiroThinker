# `answer_generator.py` -- 答案生成器与上下文管理

## 文件概述

`answer_generator.py` 提供了 `AnswerGenerator` 类，它是 MiroThinker 中处理**LLM 调用和最终答案生成**的核心组件。除了基础的 LLM 调用封装，它还实现了一套复杂的**上下文管理策略**，决定在不同场景下如何生成最终答案、是否使用中间答案回退、是否生成失败经验摘要供重试使用。

这个文件是理解 MiroThinker 如何在上下文窗口受限条件下保持高准确率的关键。

## 关键代码解读

### 1. 统一 LLM 调用接口：`handle_llm_call`

```python
async def handle_llm_call(self, system_prompt, message_history, tool_definitions,
                           step_id, purpose="", agent_type="main"):
    original_message_history = message_history
    try:
        # 调用 LLM API
        response, message_history = await self.llm_client.create_message(
            system_prompt=system_prompt,
            message_history=message_history,
            tool_definitions=tool_definitions,
            keep_tool_result=self.cfg.agent.keep_tool_result,
            step_id=step_id,
            task_log=self.task_log,
            agent_type=agent_type,
        )

        # 处理错误响应
        if ErrorBox.is_error_box(response):
            await self.stream.show_error(str(response))
            response = None

        # 处理带额外信息的响应（如警告消息）
        if ResponseBox.is_response_box(response):
            if response.has_extra_info():
                extra_info = response.get_extra_info()
                if extra_info.get("warning_msg"):
                    await self.stream.show_error(extra_info.get("warning_msg", ""))
            response = response.get_response()

        if response is None:
            return "", False, None, original_message_history

        # 解析 LLM 回复文本和工具调用
        assistant_response_text, should_break, message_history = (
            self.llm_client.process_llm_response(response, message_history, agent_type)
        )
        tool_calls_info = self.llm_client.extract_tool_calls_info(response, assistant_response_text)

        return (assistant_response_text, should_break, tool_calls_info, message_history)

    except Exception as e:
        return "", False, None, original_message_history
```

这个方法是整个框架中**所有 LLM 调用的统一入口**。它的设计要点：

- **错误隔离**: 使用 `ErrorBox` 和 `ResponseBox` 包装类型来区分正常响应、错误响应和带警告的响应。
- **安全回退**: 任何异常都会返回空响应和原始消息历史（`original_message_history`），确保调用者可以安全重试。
- **日志记录**: 每次调用都记录结果（成功或失败），便于调试。

### 2. 失败经验摘要生成：`generate_failure_summary`

```python
async def generate_failure_summary(self, system_prompt, message_history,
                                     tool_definitions, turn_count):
    # 复制消息历史（不影响原始数据）
    failure_summary_history = message_history.copy()
    if failure_summary_history and failure_summary_history[-1]["role"] == "user":
        failure_summary_history.pop()

    # 添加特定的失败摘要提示词
    failure_summary_history.append({"role": "user", "content": FAILURE_SUMMARY_PROMPT})
    # 添加助手前缀，引导结构化输出
    failure_summary_history.append(
        {"role": "assistant", "content": FAILURE_SUMMARY_ASSISTANT_PREFIX}
    )

    # 调用 LLM 生成摘要
    (failure_summary_text, _, _, _) = await self.handle_llm_call(
        system_prompt, failure_summary_history, tool_definitions,
        turn_count + 10, "Main Agent | Failure Experience Summary",
    )

    # 拼接前缀并提取结构化信息
    if failure_summary_text:
        failure_summary_text = FAILURE_SUMMARY_ASSISTANT_PREFIX + failure_summary_text
        failure_experience_summary = extract_failure_experience_summary(failure_summary_text)
        return failure_experience_summary
    return None
```

这是 MiroThinker 上下文压缩机制的核心。当一次任务尝试失败时（例如达到最大轮次或上下文窗口耗尽），这个方法会：

1. 将整个对话历史作为输入
2. 追加一个专门的"请总结失败经验"提示词
3. 使用 `FAILURE_SUMMARY_ASSISTANT_PREFIX` 作为前缀，引导 LLM 输出结构化的摘要
4. 提取出失败类型、尝试过的方法、有用的发现等信息

生成的摘要可以作为下次重试时的"先验知识"，避免重复犯错。

### 3. 带重试的最终答案生成

```python
async def generate_final_answer_with_retries(self, system_prompt, message_history,
                                               tool_definitions, turn_count, task_description):
    summary_prompt = generate_agent_summarize_prompt(task_description, agent_type="main")
    message_history.append({"role": "user", "content": summary_prompt})

    for retry_idx in range(self.max_final_answer_retries):
        (final_answer_text, should_break, tool_calls_info, message_history
        ) = await self.handle_llm_call(...)

        if final_answer_text:
            final_summary, final_boxed_answer, usage_log = (
                self.output_formatter.format_final_summary_and_log(
                    final_answer_text, self.llm_client
                )
            )
            # 如果成功提取到 boxed answer，则停止重试
            if final_boxed_answer != FORMAT_ERROR_MESSAGE:
                break
            else:
                # 移除错误回复，准备重试
                if message_history[-1]["role"] == "assistant":
                    message_history.pop()

    return (final_answer_text, final_summary, final_boxed_answer, usage_log, message_history)
```

最终答案生成最多重试 `max_final_answer_retries` 次（默认 3 次）。每次重试时会移除上一次的错误回复，保留用户提示词，让 LLM 重新生成。重试的目标是确保回复中包含一个有效的 `\boxed{}` 格式答案。

### 4. 上下文管理策略：`generate_and_finalize_answer`

```python
async def generate_and_finalize_answer(self, system_prompt, message_history,
                                         tool_definitions, turn_count, task_description,
                                         reached_max_turns=False, is_final_retry=False, ...):
    context_management_enabled = self.context_compress_limit > 0

    # 场景1: 上下文管理开启 + 达到最大轮次 + 非最终重试
    # -> 跳过答案生成，直接生成失败摘要
    if context_management_enabled and reached_max_turns and not is_final_retry:
        failure_experience_summary = await self.generate_failure_summary(...)
        return ("Task incomplete...", FORMAT_ERROR_MESSAGE, failure_experience_summary, ...)

    # 场景2/3/4: 生成最终答案
    (final_answer_text, final_summary, final_boxed_answer, usage_log, message_history
    ) = await self.generate_final_answer_with_retries(...)

    # 场景2: 上下文管理关闭 或 最终重试
    # -> 尝试使用中间答案回退
    if not context_management_enabled or is_final_retry:
        final_answer_text, final_summary, final_boxed_answer = (
            self.handle_no_context_management_fallback(...)
        )
        return (final_summary, final_boxed_answer, None, ...)

    # 场景3: 上下文管理开启 + 正常完成
    # -> 不使用回退，失败则生成摘要
    final_answer_text, final_summary, final_boxed_answer = (
        self.handle_context_management_no_fallback(...)
    )
    if final_boxed_answer == FORMAT_ERROR_MESSAGE:
        failure_experience_summary = await self.generate_failure_summary(...)

    return (final_summary, final_boxed_answer, failure_experience_summary, ...)
```

这是整个文件中最精妙的部分。根据两个布尔条件的组合，它实现了四种不同的策略：

| 上下文管理 | 达到最大轮次 | 行为 |
|-----------|------------|------|
| 关闭 | 否 | 生成答案，失败则用中间答案回退 |
| 关闭 | 是 | 生成答案，失败则用中间答案回退 |
| 开启 | 否 | 生成答案，失败则不回退，生成失败摘要 |
| 开启 | 是 | **跳过答案生成**，直接生成失败摘要 |

背后的逻辑是：
- **上下文管理关闭**时，只有一次机会，所以尽量"猜"一个答案（哪怕是中间答案）。
- **上下文管理开启**时，还有重试机会，所以不"猜"错误答案（错误的猜测会降低准确率），而是生成失败摘要供下次使用。
- 当**达到最大轮次**且上下文管理开启时，说明信息收集不充分，直接跳过答案生成（任何回答都是盲猜）。

### 5. 两种回退策略的对比

```python
def handle_no_context_management_fallback(self, final_answer_text, final_summary, final_boxed_answer):
    """上下文管理关闭时：用中间答案回退"""
    if (final_boxed_answer == FORMAT_ERROR_MESSAGE) and self.intermediate_boxed_answers:
        final_boxed_answer = self.intermediate_boxed_answers[-1]  # 用最后一个中间答案
    return final_answer_text, final_summary, final_boxed_answer

def handle_context_management_no_fallback(self, final_answer_text, final_summary, final_boxed_answer):
    """上下文管理开启时：不用中间答案回退"""
    if final_boxed_answer == FORMAT_ERROR_MESSAGE:
        pass  # 保持 FORMAT_ERROR_MESSAGE，不做任何替换
    return final_answer_text, final_summary, final_boxed_answer
```

这两个方法的区别只在于**是否使用中间 boxed 答案作为回退**。这个设计决策直接影响了系统在 BrowseComp 基准测试上的准确率。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `AnswerGenerator` | 类 | 答案生成器，管理 LLM 调用、最终答案生成和上下文管理策略 |
| `handle_llm_call()` | 异步方法 | 统一的 LLM 调用接口，处理错误响应和异常 |
| `generate_failure_summary()` | 异步方法 | 将完整对话历史压缩为结构化的失败经验摘要 |
| `generate_final_answer_with_retries()` | 异步方法 | 带重试机制的最终答案生成 |
| `generate_and_finalize_answer()` | 异步方法 | 根据上下文管理设置选择答案生成策略（核心决策方法） |
| `handle_no_context_management_fallback()` | 方法 | 无上下文管理时的回退策略（使用中间答案） |
| `handle_context_management_no_fallback()` | 方法 | 有上下文管理时的策略（不使用中间答案回退） |

### 关键常量和配置

| 名称 | 默认值 | 说明 |
|------|--------|------|
| `DEFAULT_MAX_FINAL_ANSWER_RETRIES` | 3 | 最终答案生成的最大重试次数 |
| `context_compress_limit` | 配置项 | 大于 0 表示启用上下文管理（多次重试机制） |
| `retry_with_summary` | `True` | 是否在失败时生成经验摘要供重试 |
| `keep_tool_result` | 配置项 | 控制保留多少工具结果在上下文中（-1 表示全部保留） |

## 与其他模块的关系

```
llm/base_client.py       <-- create_message(), process_llm_response(), extract_tool_calls_info()
io/output_formatter.py   <-- format_final_summary_and_log(), _extract_boxed_content()
utils/prompt_utils.py    <-- FAILURE_SUMMARY_PROMPT, FORMAT_ERROR_MESSAGE, generate_agent_summarize_prompt()
utils/parsing_utils.py   <-- extract_failure_experience_summary()
utils/wrapper_utils.py   <-- ErrorBox, ResponseBox (响应包装类型)
core/stream_handler.py   <-- show_error() (推送错误事件)
core/orchestrator.py     --> 调用 handle_llm_call() 和 generate_and_finalize_answer()
```

- `Orchestrator` 在每轮循环中调用 `handle_llm_call()` 处理 LLM 交互，在主循环结束后调用 `generate_and_finalize_answer()` 生成最终答案。
- `BaseClient` 提供实际的 LLM API 调用能力，`AnswerGenerator` 在其上层封装了错误处理和重试逻辑。
- `OutputFormatter` 负责从 LLM 回复中提取 `\boxed{}` 格式的答案。

## 总结

`answer_generator.py` 实现了 MiroThinker 的**答案生成和上下文管理策略**。它的核心价值在于 `generate_and_finalize_answer` 方法中的四种策略分支，这些策略根据"是否启用上下文管理"和"是否达到最大轮次"两个条件进行组合，在"尝试猜测答案"和"承认失败以便重试"之间做出最优权衡。这种设计使得 MiroThinker 能在有限的上下文窗口内，通过多次压缩重试达到高准确率。

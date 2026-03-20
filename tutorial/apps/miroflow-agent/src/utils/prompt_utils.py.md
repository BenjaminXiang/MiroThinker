# `prompt_utils.py` — 提示模板与生成工具

## 文件概述

`prompt_utils.py` 是 MiroThinker 的**提示工程中心**，包含所有系统提示、智能体目标提示、总结提示和失败经验模板的定义与生成函数。它决定了 LLM "看到"什么样的指令，直接影响智能体的行为和输出格式。

在项目中，`AnthropicClient` 和 `OpenAIClient` 的 `generate_agent_system_prompt()` 方法会调用这里的函数来构建完整的系统提示。

## 关键代码解读

### 格式错误和失败经验模板

```python
FORMAT_ERROR_MESSAGE = "No \\boxed{} content found in the final answer."

FAILURE_EXPERIENCE_HEADER = """
=== Previous Attempts Analysis ===
The following summarizes what was tried before and why it didn't work.
"""

FAILURE_EXPERIENCE_ITEM = """[Attempt {attempt_number}]
{failure_summary}
"""

FAILURE_SUMMARY_PROMPT = """The task was not completed successfully. Do NOT call any tools. Provide a summary:

Failure type: [incomplete / blocked / misdirected / format_missed]
  - incomplete: ran out of turns before finishing
  - blocked: got stuck due to tool failure or missing information
  - misdirected: went down the wrong path
  - format_missed: found the answer but forgot to use \\boxed{}
What happened: [describe the approach taken]
Useful findings: [list any facts or conclusions that should be reused]"""
```

**解释**：

- `FORMAT_ERROR_MESSAGE` 在 LLM 最终答案没有 `\boxed{}` 时使用
- 失败经验模板用于重试机制：当任务失败时，记录失败原因和有用发现，在下一次尝试时作为上下文提供给 LLM
- 失败类型分为四种：未完成、被阻塞、方向错误、格式遗漏——这种结构化分类帮助 LLM 在重试时采取不同策略
- `FAILURE_SUMMARY_ASSISTANT_PREFIX` 包含 `<think>` 标签，引导模型先思考再输出

### MCP 系统提示生成

```python
def generate_mcp_system_prompt(date, mcp_servers):
    formatted_date = date.strftime("%Y-%m-%d")

    template = f"""In this environment you have access to a set of tools...
You only have access to the tools provided below. You can only use one tool per message...
Today is: {formatted_date}

# Tool-Use Formatting Instructions
Tool-use is formatted using XML-style tags...

<use_mcp_tool>
<server_name>server name here</server_name>
<tool_name>tool name here</tool_name>
<arguments>
{{"param1": "value1", "param2": "value2 \\"escaped string\\""}}
</arguments>
</use_mcp_tool>

Important Notes:
- Tool-use must be placed **at the end** of your response...
"""

    # 添加 MCP 服务器工具定义
    for server in mcp_servers:
        template += f"\n## Server name: {server['name']}\n"
        for tool in server["tools"]:
            template += f"### Tool name: {tool['name']}\n"
            template += f"Description: {tool['description']}\n"
            template += f"Input JSON schema: {tool['schema']}\n"

    template += """
# General Objective
You accomplish a given task iteratively, breaking it down into clear steps...
"""
    return template
```

**解释**：

- 这个函数生成的系统提示是 LLM 看到的第一条指令，包含：
  1. **日期信息**：告诉 LLM 当前日期
  2. **工具使用格式**：详细说明 MCP XML 标签的使用方式
  3. **工具列表**：每个 MCP 服务器及其提供的所有工具（名称、描述、JSON Schema）
  4. **通用目标**：指导 LLM 迭代式地分步完成任务
- 关键约束："You can only use one tool per message"——每条消息只能调用一个工具
- 工具调用必须放在响应的末尾，这简化了解析逻辑

### 智能体特定目标提示

```python
def generate_agent_specific_system_prompt(agent_type=""):
    if agent_type == "main":
        return """You are a task-solving agent that uses tools step-by-step
        to answer the user's question..."""
    elif agent_type in ("agent-browsing", "browsing-agent"):
        return """You are an agent that performs the task of searching and
        browsing the web for specific information...
        Do not infer, speculate, summarize broadly..."""
```

**解释**：

- 主智能体的目标是综合使用工具来回答问题
- 浏览智能体的目标更严格：只检索事实信息，不推测、不臆造
- 这种角色分离确保了子智能体专注于信息检索而不越权

### 最终总结提示

```python
def generate_agent_summarize_prompt(task_description, agent_type=""):
    if agent_type == "main":
        return (
            "Summarize the above conversation, and output the FINAL ANSWER...\n"
            "If a clear answer has already been provided earlier, do not rethink...\n"
            f'The original question is: "{task_description}"\n\n'
            "Wrap your final answer in \\boxed{}.\n"
            "Your final answer should be:\n"
            "- a number, OR\n"
            "- as few words as possible, OR\n"
            "- a comma-separated list...\n"
            "You must absolutely not perform any MCP tool call..."
        )
    elif agent_type == "agent-browsing":
        return (
            "We are now ending this session...\n"
            "You must NOT initiate any further tool use...\n"
            "Summarize the above search and browsing history..."
        )
```

**解释**：

- 主智能体总结提示的关键要求：
  1. 如果之前已有答案，直接提取而不重新计算
  2. 答案必须用 `\boxed{}` 包裹
  3. 答案格式严格规定（数字、少量词语、逗号分隔列表）
  4. 明确禁止在总结时调用任何工具
- 浏览智能体总结提示强调：对话历史即将删除，这是最后报告机会，必须完整报告所有发现

### MCP 标签和拒绝关键词

```python
mcp_tags = [
    "<use_mcp_tool>", "</use_mcp_tool>",
    "<server_name>", "</server_name>",
    "<arguments>", "</arguments>",
]

refusal_keywords = [
    "time constraint",
    "I'm sorry, but I can't",
    "I'm sorry, I cannot solve",
]
```

**解释**：

- `mcp_tags` 用于检测 LLM 响应中是否包含工具调用
- `refusal_keywords` 用于检测 LLM 是否拒绝执行任务

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `generate_mcp_system_prompt(date, mcp_servers)` | 函数 | 生成包含工具定义的完整 MCP 系统提示 |
| `generate_no_mcp_system_prompt(date)` | 函数 | 生成无工具的简化系统提示 |
| `generate_agent_specific_system_prompt(agent_type)` | 函数 | 根据智能体类型生成角色目标提示 |
| `generate_agent_summarize_prompt(task, agent_type)` | 函数 | 生成最终总结提示，含格式要求 |
| `FORMAT_ERROR_MESSAGE` | 常量 | 无 `\boxed{}` 时的错误提示 |
| `FAILURE_EXPERIENCE_HEADER/ITEM/FOOTER` | 常量 | 失败经验模板组件 |
| `FAILURE_SUMMARY_PROMPT` | 常量 | 失败总结的结构化提示 |
| `mcp_tags` | 常量 | MCP XML 标签列表 |
| `refusal_keywords` | 常量 | LLM 拒绝响应的关键词列表 |

## 与其他模块的关系

- **`llm/providers/anthropic_client.py`** 和 **`llm/providers/openai_client.py`**：调用 `generate_mcp_system_prompt()` 构建系统提示
- **`core/Orchestrator`**：调用 `generate_agent_specific_system_prompt()` 和 `generate_agent_summarize_prompt()` 设置智能体角色
- **`io/output_formatter.py`**：导入 `FORMAT_ERROR_MESSAGE` 用于标记格式错误
- **`core/AnswerGenerator`**：使用失败经验模板在重试时提供上下文

## 总结

`prompt_utils.py` 是 MiroThinker 提示工程的核心。它通过精心设计的提示模板，控制了 LLM 的行为方式、输出格式和角色定位。MCP 系统提示的标准化格式确保了工具调用的可靠解析，而失败经验模板实现了自我改进式的重试机制。理解这个文件是理解 MiroThinker 智能体行为的关键。

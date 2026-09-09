# `unit_test.py` -- 聊天模板单元测试

## 文件概述

本文件使用 pytest 框架对 MiroThinker 的 Jinja2 **聊天模板** (`chat_template.jinja`) 进行全面的单元测试。聊天模板定义了模型的输入格式——如何将消息列表、工具定义、工具调用等转换为模型能理解的 token 序列。测试覆盖了消息格式化、思考标签处理、工具定义注入、工具调用格式化、工具响应处理以及多种边缘情况。

## 关键代码解读

### 1. 测试 Fixtures

```python
@pytest.fixture
def template():
    template_path = Path(__file__).parent / "chat_template.jinja"
    with open(template_path, "r") as f:
        template_str = f.read()
    env = Environment(loader=BaseLoader())
    env.globals["strftime_now"] = strftime_now
    return env.from_string(template_str)
```

**逐步解释**：
- 从同目录加载 `chat_template.jinja` 模板文件。
- 注入 `strftime_now` 函数（模拟 vLLM 提供的时间函数）。
- 返回编译后的 Jinja2 模板对象供测试使用。

### 2. 基本消息格式化测试

```python
class TestBasicMessageFormatting:
    def test_user_message_format(self, template):
        messages = [{"role": "user", "content": "Hello!"}]
        result = template.render(messages=messages, add_generation_prompt=False)
        assert "<|im_start|>user\nHello!<|im_end|>" in result

    def test_assistant_message_format(self, template):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = template.render(messages=messages, add_generation_prompt=False)
        assert "<|im_start|>assistant\n<think>\n\n</think>\n\nHi there!<|im_end|>" in result
```

**逐步解释**：
- 用户消息格式：`<|im_start|>user\n{content}<|im_end|>`。
- 助手消息**始终**包含 `<think>` 标签（即使思考内容为空），格式为 `<|im_start|>assistant\n<think>\n{reasoning}\n</think>\n\n{content}<|im_end|>`。
- `add_generation_prompt=True` 会在末尾添加 `<|im_start|>assistant\n` 触发模型生成。

### 3. 思考标签测试

```python
class TestThinkingContent:
    def test_reasoning_content_field(self, template):
        messages = [{
            "role": "assistant",
            "content": "The answer is 4.",
            "reasoning_content": "2+2=4 by basic arithmetic.",
        }]
        result = template.render(...)
        assert "<think>\n2+2=4 by basic arithmetic.\n</think>" in result

    def test_enable_thinking_false(self, template):
        result = template.render(messages=messages, enable_thinking=False)
        assert result.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")

    def test_enable_thinking_true(self, template):
        result = template.render(messages=messages, enable_thinking=True)
        assert result.endswith("<|im_start|>assistant\n")
```

**逐步解释**：
- `reasoning_content` 字段会被提取并包装在 `<think>` 标签中。
- `enable_thinking=False`：生成提示中包含空的 `<think>` 标签（强制不思考）。
- `enable_thinking=True`：生成提示中不包含 `<think>` 标签（让模型自主决定是否思考）。

### 4. 工具定义测试

```python
class TestToolDefinitions:
    def test_tools_trigger_system_prompt(self, template, today_date):
        tools = [{"type": "function", "function": {"name": "web_search", ...}}]
        result = template.render(messages=messages, tools=tools)
        assert "In this environment you have access to a set of tools" in result
        assert f"Today is: {today_date}" in result
        assert "# Tool-Use Formatting Instructions" in result

    def test_tool_name_format(self, template):
        assert "### Tool name: my_tool" in result

    def test_tool_server_name(self, template):
        assert "## Server name: default" in result
```

**逐步解释**：
- 当请求中包含 `tools` 时，系统提示词会自动生成，包含工具环境说明、当前日期、MCP 格式指令。
- 每个工具格式化为 `### Tool name: {name}`，归属到 `## Server name: default` 下。
- 工具描述带有 4 空格缩进，参数列表从 `parameters.properties` 自动生成。

### 5. 工具调用格式化测试

```python
class TestToolCalls:
    def test_tool_call_format(self, template):
        messages = [{
            "role": "assistant",
            "content": "Let me search.",
            "tool_calls": [{
                "id": "call_1",
                "function": {"name": "web_search", "arguments": '{"query": "AI news"}'},
            }],
        }]
        result = template.render(messages=messages, tools=tools)
        assert "<use_mcp_tool>" in result
        assert "<server_name>default</server_name>" in result
        assert "<tool_name>web_search</tool_name>" in result
        assert '{"query": "AI news"}' in result
```

**逐步解释**：
- OpenAI 格式的 `tool_calls` 被模板转换为 MCP XML 格式。
- `server_name` 默认为 `"default"`。
- 多个工具调用会在同一条助手消息中生成多个 `<use_mcp_tool>` 块。

### 6. 工具响应测试

```python
class TestToolResponses:
    def test_tool_response_in_user_message(self, template):
        messages = [
            {"role": "tool", "tool_call_id": "call_1", "content": "Search results here"},
        ]
        result = template.render(...)
        assert "<|im_start|>user\nSearch results here<|im_end|>" in result

    def test_multiple_tool_responses_merged(self, template):
        # 连续的 tool 消息被合并为一条 user 消息
        assert "Result A\n\nResult B" in result
        assert user_count == 2  # 原始 user + 合并的工具响应
```

**逐步解释**：
- `tool` 角色的消息被转换为 `user` 角色（模型只接受 user/assistant/system）。
- 连续的多个 `tool` 消息被合并为一条 `user` 消息，内容用 `\n\n` 分隔。
- 不使用 `<tool_response>` 包装标签。

## 核心类/函数表格

| 测试类 | 测试数量 | 说明 |
|--------|----------|------|
| `TestBasicMessageFormatting` | 5 | 基本消息格式：user/system/assistant、生成提示、多轮对话 |
| `TestThinkingContent` | 5 | 思考标签：reasoning_content、内容中的 think 标签、enable_thinking |
| `TestToolDefinitions` | 10 | 工具定义：系统提示触发、名称格式、描述缩进、JSON Schema、参数去重 |
| `TestToolCalls` | 4 | 工具调用：MCP XML 格式、无内容、多工具、dict 参数 |
| `TestToolResponses` | 3 | 工具响应：转为 user 消息、多响应合并、无包装标签 |
| `TestEdgeCases` | 5 | 边缘情况：空内容、Unicode、特殊字符、换行符 |
| `TestCompleteFlow` | 2 | 集成测试：完整工具使用流程、思考+工具调用组合 |

## 与其他模块的关系

- 测试目标：同目录下的 `chat_template.jinja`（Jinja2 模板文件）。
- 模板的输出格式与 `MirothinkerToolParser.py` 的解析格式互为对应关系。
- 使用 pytest 框架，可通过 `pytest unit_test.py -v` 运行。

## 总结

这是一个全面的模板测试套件（34 个测试用例），验证了聊天模板在各种场景下的正确行为。测试覆盖了从基本消息格式化到完整工具使用流程的所有关键路径。关键发现包括：助手消息始终包含 `<think>` 标签、工具响应被转换为 user 消息并可合并、以及 `enable_thinking` 对生成提示的影响。

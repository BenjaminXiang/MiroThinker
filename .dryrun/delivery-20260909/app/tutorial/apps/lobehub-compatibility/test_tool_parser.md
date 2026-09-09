# `test_tool_parser.py` -- 工具解析器正则测试

## 文件概述

本文件是 `MirothinkerToolParser` 的正则表达式测试套件，不依赖 vLLM 运行环境（通过 Mock 替换所有 vLLM 导入）。它验证了三种正则表达式的正确性，测试了多种边缘情况，并附带代码分析报告指出潜在问题。

## 关键代码解读

### 1. vLLM Mock 设置

```python
mock_vllm = MagicMock()
mock_vllm.entrypoints.chat_utils.make_tool_call_id = lambda: "call_test_123"

mock_protocol = SimpleNamespace(
    ChatCompletionRequest=MagicMock,
    ExtractedToolCallInformation=MagicMock,
    ToolCall=MagicMock,
    ...
)

sys.modules["vllm"] = mock_vllm
sys.modules["vllm.entrypoints.openai.protocol"] = mock_protocol
sys.modules["vllm.entrypoints.openai.tool_parsers.abstract_tool_parser"] = mock_tool_parser
```

**逐步解释**：
- 使用 `MagicMock` 和 `SimpleNamespace` 创建 vLLM 所有模块的 Mock 对象。
- 将 Mock 注入 `sys.modules`，使后续 `import vllm.*` 使用 Mock 而非真实模块。
- `ToolParser` 基类被替换为 `object`，使 `MirothinkerToolParser` 可以正常继承。
- 这种方法允许在没有 vLLM 安装的环境中运行测试。

### 2. 主正则测试

```python
def test_tool_call_regex():
    # 测试 1：基本工具调用
    text1 = """<use_mcp_tool>
    <server_name>my_mcp_server</server_name>
    <tool_name>web_search</tool_name>
    <arguments>{"query": "AI news"}</arguments>
    </use_mcp_tool>"""
    match = tool_call_regex.search(text1)
    assert match.group(1).strip() == "my_mcp_server"
    assert match.group(2).strip() == "web_search"

    # 测试 3：多个工具调用
    matches = list(tool_call_regex.finditer(text3))
    assert len(matches) == 2

    # 测试 4：复杂 JSON 参数（嵌套对象 + 数组）
    # 测试 5：空参数 {}
    # 测试 6：最小空白
```

**逐步解释**：
- 6 个测试用例覆盖：基本匹配、前置文本、多个调用、复杂 JSON、空参数、最小空白。
- 验证正则能正确提取 `server_name`、`tool_name` 和 `arguments`。

### 3. 部分匹配正则测试

```python
def test_partial_tool_regex():
    # 测试：只有开始标签
    text1 = "<use_mcp_tool>\n"
    match = partial_tool_regex.search(text1)
    assert match is not None

    # 测试：只有 server_name
    assert match.group(1).strip() == "my_server"
    assert match.group(2) is None  # tool_name 尚未出现

    # 测试：不完整的 arguments
    assert '{"query": "incomp' in match.group(3)
```

**逐步解释**：
- 验证部分匹配正则能处理流式场景中的不完整输入。
- 确保未出现的字段返回 `None` 而非错误。

### 4. 边缘情况测试

```python
def test_edge_cases():
    # Unicode 参数
    args = json.loads(match.group(3).strip())
    assert args["query"] == "你好世界"

    # JSON 中的换行符
    assert "line1\nline2" in args["query"]

    # HTML 标签作为参数值
    assert "<html>" in args["query"]
```

**逐步解释**：
- 测试 Unicode 字符、JSON 转义换行符、HTML 标签等特殊内容。
- 确保正则不会被参数中的特殊字符干扰。

### 5. 代码分析报告

```python
def check_unused_code():
    issues = [
        "未使用的实例变量: current_tool_name_sent, prev_tool_call_arr, ...",
        "_ensure_tool_id_valid 方法定义但从未调用",
        "partial_tool_regex 定义但从未使用",
        "_resolve_tool_name 检查 'default' 但模板使用 'my_mcp_server'",
    ]
```

**逐步解释**：
- 静态分析部分，指出解析器代码中的潜在问题。
- 识别出一些遗留代码（可能来自早期版本的流式实现）。

## 核心类/函数表格

| 函数名 | 说明 |
|--------|------|
| `test_tool_call_regex` | 测试完整匹配正则（6 个用例） |
| `test_partial_tool_regex` | 测试部分匹配正则（3 个用例） |
| `test_complete_tool_block_regex` | 测试完整块正则（2 个用例） |
| `test_edge_cases` | 测试边缘情况（3 个用例） |
| `check_unused_code` | 代码分析报告 |

## 与其他模块的关系

- 测试目标：`MiroThinkerToolParser.py` 中定义的正则表达式。
- 通过 Mock 消除对 vLLM 的运行时依赖。
- 可独立运行：`python test_tool_parser.py`。

## 总结

这是一个实用的测试文件，既验证了正则表达式的正确性（14 个测试用例，覆盖正常和边缘情况），又提供了代码质量分析。Mock 技术的使用使其可以在任何 Python 环境中运行，无需安装 vLLM。

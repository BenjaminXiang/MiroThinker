# `stateless_python_server.py` -- 无状态 Python 执行 MCP 服务器

## 文件概述

`stateless_python_server.py` 提供了一个极简的无状态 Python 代码执行工具。与 `python_mcp_server.py` 的多工具、有状态沙箱不同，此服务器只有一个工具 `python`：每次调用创建一个全新的 E2B 沙箱，执行代码，返回结果，然后销毁沙箱。适用于不需要保持状态的独立计算任务。

## 关键代码解读

### 1. 无状态执行模型

```python
@mcp.tool()
async def python(code: str) -> str:
    """Use this tool to execute STATELESS Python code in your chain of thought."""
    sandbox = Sandbox.create(
        timeout=DEFAULT_TIMEOUT,
        api_key=E2B_API_KEY,
        template="1av7fdjfvcparqo8efq6"
    )
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            execution = sandbox.run_code(code)
            break
        except Exception as e:
            if attempt == max_attempts:
                raise e
    execution = sandbox.run_code(code)
    sandbox.kill()
    return str(execution)
```

生命周期：创建 -> 执行 -> 销毁。每次调用都是完全独立的：
- 没有 `create_sandbox` 步骤——自动创建
- 没有文件传输工具——不需要
- 执行完立即 `kill()`——不保留任何状态
- 需要 `print()` 输出结果——与 Python REPL 的交互模式不同

### 2. 工具描述中的使用指南

```python
"""Use this tool to execute STATELESS Python code in your chain of thought.
The code will not be shown to the user. This tool should be used for internal
reasoning, but not for code that is intended to be visible to the user.
IMPORTANT: Your python environment is not shared between calls.
You will have to pass your entire code each time."""
```

工具描述中明确告诉 Agent 这是无状态的，每次必须传入完整代码。这种"文档即接口"的设计对 LLM 工具调用很重要。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `python` | MCP 工具 | 在一次性沙箱中执行 Python 代码 |

## 与其他模块的关系

- **与 `python_mcp_server.py` 形成对比**：有状态 vs 无状态，多工具 vs 单工具
- **依赖 E2B**：使用相同的 E2B 沙箱模板
- **属于 dev_mcp_servers**：适合特定 Agent 配置使用
- **设计用于 Agent 内部推理**：计算中间结果，不用于生成用户可见的输出

## 总结

`stateless_python_server.py` 是一个极简的代码执行工具，遵循"用完即弃"的无状态模型。它省去了沙箱管理的复杂性，适合独立的计算任务。每次调用开销较大（创建+销毁沙箱），但简化了 Agent 的工具调用流程。

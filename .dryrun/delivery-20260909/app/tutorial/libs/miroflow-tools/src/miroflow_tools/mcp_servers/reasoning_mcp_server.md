# `reasoning_mcp_server.py` -- 推理 MCP 服务器（Anthropic 版）

## 文件概述

`reasoning_mcp_server.py` 提供了一个"深度思考"工具，用于解决复杂的数学问题、谜题、智力测试等需要大量推理链的问题。底层调用 Anthropic 的 Claude 3.7 Sonnet 模型，并启用了扩展思考（Extended Thinking）功能。在 MiroThinker 中，主 Agent 遇到需要深度推理的子问题时，会委托给此工具处理。

## 关键代码解读

### 1. 扩展思考调用

```python
@mcp.tool()
async def reasoning(question: str) -> str:
    client = Anthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
    response = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=21000,
        thinking={
            "type": "enabled",
            "budget_tokens": 19000,
        },
        messages=messages_for_llm,
        stream=False,
    )
```

关键参数解析：
- `model="claude-3-7-sonnet-20250219"`：使用 Claude 3.7 Sonnet，这是一个支持扩展思考的模型
- `thinking.budget_tokens=19000`：分配 19,000 个 token 的思考预算。模型会先在内部进行大量推理，然后给出最终答案
- `max_tokens=21000`：总 token 限制包含思考 token 和回答 token

### 2. 响应处理

```python
try:
    return response.content[-1].text
except Exception:
    logger.info("Reasoning Error: only thinking content is returned")
    return response.content[-1].thinking
```

Claude 的扩展思考响应包含两部分：思考过程（thinking blocks）和最终回答（text blocks）。正常情况下返回最终回答文本。如果模型只产生了思考内容没有最终回答，则退而返回思考内容。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `reasoning` | MCP 工具 | 使用 Claude 扩展思考解决复杂推理问题 |

## 与其他模块的关系

- **被 ToolManager 管理**：作为 stdio MCP 服务器被调用
- **与主 Agent 分工**：主 Agent 负责任务分解和信息收集，遇到需要深度推理的子问题时委托给此工具
- **对比 `reasoning_mcp_server_os.py`**：本文件使用 Anthropic API，`_os` 版本使用自部署模型端点
- **需要 `ANTHROPIC_API_KEY`**：依赖 Anthropic API 服务

## 总结

`reasoning_mcp_server.py` 是一个专注于深度推理的工具服务器。通过利用 Claude 的扩展思考功能，它能在 19,000 token 的思考预算内进行充分的链式推理，适合解决数学、逻辑、谜题等高难度问题。代码简洁，核心只有一个工具函数。

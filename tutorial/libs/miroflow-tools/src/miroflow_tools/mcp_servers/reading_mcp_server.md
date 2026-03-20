# `reading_mcp_server.py` -- 文档阅读 MCP 服务器

## 文件概述

`reading_mcp_server.py` 提供了一个文档格式转换工具，能将 PDF、Word、PowerPoint、Excel、CSV、ZIP 等多种格式的文件转换为 Markdown 文本。底层依赖 `markitdown-mcp` 库。在 MiroThinker 中，当 Agent 需要阅读和理解非纯文本文档时，会使用此工具。

## 关键代码解读

### 1. 核心工具：文档转 Markdown

```python
@mcp.tool()
async def convert_to_markdown(uri: str) -> str:
    # 验证 URI 格式
    valid_schemes = ["http:", "https:", "file:", "data:"]
    if not any(uri.lower().startswith(scheme) for scheme in valid_schemes):
        return f"Error: Invalid URI scheme."

    # 启动 markitdown-mcp 子进程并通过 MCP 协议调用
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "markitdown_mcp"],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write, sampling_callback=None) as session:
            await session.initialize()
            tool_result = await session.call_tool(tool_name, arguments=arguments)
```

这个设计很有意思：`reading_mcp_server` 本身是一个 MCP 服务器，但它内部又作为 MCP **客户端**去调用另一个 MCP 服务器（`markitdown_mcp`）。这种"MCP 服务器嵌套"的模式实现了工具的组合和封装。

### 2. 多传输方式支持

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--path", type=str, default="/mcp")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", port=args.port, path=args.path)
```

此服务器同时支持两种启动方式：
- **Stdio 模式**：作为子进程被 ToolManager 通过标准输入/输出管理
- **HTTP 模式**：作为独立 HTTP 服务器运行，可以被多个客户端共享

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `convert_to_markdown` | MCP 工具 | 将文件 URI（file:、data:、http:）转换为 Markdown 文本 |

## 与其他模块的关系

- **被 ToolManager 管理**：通常以 stdio 方式被调用
- **依赖 markitdown-mcp**：内部启动 `markitdown_mcp` 子进程做实际转换
- **与搜索/抓取工具配合**：搜索工具找到文档 URL 后，此工具可将文档内容提取为 Agent 可读的文本

## 总结

`reading_mcp_server.py` 是一个轻量的 MCP 服务器封装，将 `markitdown_mcp` 的文档转换能力暴露为标准 MCP 工具。它支持多种文件格式和 URI 协议，并提供 stdio 和 HTTP 两种部署方式。MCP 嵌套调用的设计体现了 MCP 协议的可组合性。

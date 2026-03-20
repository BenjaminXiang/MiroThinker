# `manager.py` -- 核心工具管理器

## 文件概述

`manager.py` 是 miroflow-tools 库的核心文件，定义了 `ToolManager` 类。这个类负责统一管理所有 MCP (Model Context Protocol) 工具服务器的连接、工具发现和工具调用。在整个 MiroThinker 项目中，`ToolManager` 是 Agent 与外部工具之间的桥梁——Agent 不直接与各个 MCP 服务器通信，而是通过 `ToolManager` 统一调度。

简单来说，`ToolManager` 做三件事：
1. 连接到多个 MCP 服务器，获取它们提供的工具列表
2. 根据 Agent 的请求，调用指定服务器上的指定工具
3. 处理错误、超时、重试等异常情况

## 关键代码解读

### 1. 超时装饰器 `with_timeout`

```python
def with_timeout(timeout_s: float = 300.0):
    def decorator(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> R:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_s)
        return wrapper
    return decorator
```

这是一个装饰器工厂函数。它的作用是给任何异步函数加上超时控制。工作原理：
- 外层 `with_timeout(timeout_s)` 接收超时秒数，返回真正的装饰器
- `asyncio.wait_for` 会在指定时间内等待异步函数完成，超时则抛出 `asyncio.TimeoutError`
- 在本文件中，`execute_tool_call` 方法使用了 `@with_timeout(1200)`，即 20 分钟超时

### 2. 协议类 `ToolManagerProtocol`

```python
class ToolManagerProtocol(Protocol):
    async def get_all_tool_definitions(self) -> Any: ...
    async def execute_tool_call(
        self, *, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any: ...
```

这是一个 Python Protocol 类（结构化子类型），定义了工具管理器必须实现的两个方法接口。任何实现了这两个方法的类都可以作为工具管理器使用，无需显式继承。这为将来替换不同的工具管理实现提供了灵活性。

### 3. `ToolManager.__init__` 初始化

```python
def __init__(self, server_configs, tool_blacklist=None):
    self.server_configs = server_configs
    self.server_dict = {
        config["name"]: config["params"] for config in server_configs
    }
    self.browser_session = None
    self.tool_blacklist = tool_blacklist if tool_blacklist else set()
    self.task_log = None
```

初始化逻辑：
- `server_configs`：一个列表，每个元素是 `{"name": "服务器名", "params": 连接参数}` 格式的字典
- `server_dict`：将列表转换为字典，方便按名称快速查找服务器参数
- `browser_session`：Playwright 浏览器会话的持久化引用，初始为 None
- `tool_blacklist`：工具黑名单，格式为 `{(服务器名, 工具名)}` 的集合
- `task_log`：可选的结构化日志记录器

### 4. `get_all_tool_definitions` 获取工具定义

这个方法遍历所有配置的 MCP 服务器，连接后获取每个服务器提供的工具列表。核心流程：

```python
if isinstance(server_params, StdioServerParameters):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write, sampling_callback=None) as session:
            await session.initialize()
            tools_response = await session.list_tools()
```

- 支持两种连接方式：**Stdio**（标准输入/输出，用于本地进程）和 **SSE**（Server-Sent Events，用于远程 HTTP 服务器）
- 获取到工具列表后，会检查黑名单，过滤掉不允许使用的工具
- 每个工具的定义包含 `name`（名称）、`description`（描述）和 `schema`（输入参数的 JSON Schema）

### 5. `execute_tool_call` 执行工具调用

```python
@with_timeout(1200)
async def execute_tool_call(self, server_name, tool_name, arguments) -> Any:
```

这是最核心的方法，执行实际的工具调用。关键设计：

- **Playwright 特殊处理**：浏览器会话需要持久化（保持页面状态），因此单独使用 `PlaywrightSession` 管理，不是每次调用都新建连接
- **HuggingFace 防护**：检测对 HuggingFace 数据集/空间的抓取请求并阻止，防止 Agent 直接从评测数据集中获取答案
- **MarkItDown 回退**：当 scrape 工具失败时，自动尝试使用 MarkItDown 库作为备用方案
- **统一返回格式**：所有调用结果都返回 `{"server_name": ..., "tool_name": ..., "result": ...}` 或 `{"error": ...}` 格式的字典

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `with_timeout` | 装饰器工厂 | 为异步函数添加超时控制 |
| `ToolManagerProtocol` | Protocol 类 | 定义工具管理器的接口规范 |
| `ToolManager` | 类 | 核心工具管理器，管理所有 MCP 服务器连接和工具调用 |
| `ToolManager.__init__` | 方法 | 初始化服务器配置、黑名单等 |
| `ToolManager.set_task_log` | 方法 | 设置结构化日志记录器 |
| `ToolManager.get_all_tool_definitions` | 异步方法 | 从所有服务器获取工具定义列表 |
| `ToolManager.execute_tool_call` | 异步方法 | 执行指定服务器上的指定工具调用 |
| `ToolManager._should_block_hf_scraping` | 方法 | 检查是否应阻止对 HuggingFace 数据集的抓取 |

## 与其他模块的关系

- **被 `apps/miroflow-agent/src/core/` 使用**：Pipeline 创建 ToolManager 实例，ToolExecutor 通过它执行工具调用
- **依赖 `browser_session.py`**：导入 `PlaywrightSession` 用于持久化浏览器会话管理
- **依赖 MCP SDK**：使用 `mcp` 库的 `ClientSession`、`StdioServerParameters`、`stdio_client`、`sse_client` 进行 MCP 协议通信
- **与所有 MCP 服务器交互**：通过配置参数连接到 `mcp_servers/` 和 `dev_mcp_servers/` 下的各个工具服务器

## 总结

`manager.py` 是 miroflow-tools 库的调度中心。它将复杂的多服务器、多工具管理抽象为两个简洁的接口：获取工具定义和执行工具调用。通过支持 Stdio 和 SSE 两种传输方式，它能同时管理本地进程和远程服务。黑名单机制、HuggingFace 防护和 MarkItDown 回退等设计体现了在实际使用中对安全性和可靠性的考量。

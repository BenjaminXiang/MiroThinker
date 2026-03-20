# `python_mcp_server.py` -- Python 代码执行沙箱 MCP 服务器

## 文件概述

`python_mcp_server.py` 是 miroflow-tools 中功能最丰富的 MCP 服务器之一。它通过 E2B (E2B Code Interpreter) 提供远程 Linux 沙箱环境，让 Agent 能够安全地创建沙箱、执行 Python 代码、运行 shell 命令、上传/下载文件。这是 Agent 进行数据分析、数学计算、文件处理等任务的基础设施。

## 关键代码解读

### 1. 沙箱 ID 验证

```python
INVALID_SANDBOX_IDS = {
    "default", "sandbox1", "sandbox", "some_id", "new_sandbox",
    "python", "create_sandbox", "sandbox123", "temp", ...
}
```

这是一个防御性设计。LLM 在调用工具时可能会"幻觉"出虚假的 sandbox_id（如 "default"、"sandbox1"），而不是使用真正由 `create_sandbox` 返回的 ID。此集合列举了常见的无效 ID，在每个工具调用时检查，避免连接到不存在的沙箱。

### 2. 创建沙箱

```python
@mcp.tool()
async def create_sandbox(timeout: int = DEFAULT_TIMEOUT) -> str:
    sandbox = Sandbox(
        template=DEFAULT_TEMPLATE_ID,
        timeout=timeout,
        api_key=E2B_API_KEY,
    )
    info = sandbox.get_info()
    return f"Sandbox created with sandbox_id: {info.sandbox_id}"
```

使用预定义的模板 ID 创建 E2B 沙箱。模板定义了沙箱的基础环境（预装的 Python 包、系统工具等）。创建后返回唯一的 `sandbox_id`，后续所有操作都通过此 ID 引用这个沙箱。

### 3. 执行 Python 代码

```python
@mcp.tool()
async def run_python_code(code_block: str, sandbox_id: str) -> str:
    # 如果 sandbox_id 无效，回退到无状态执行
    if not sandbox_id or sandbox_id in INVALID_SANDBOX_IDS:
        sandbox = Sandbox(template=DEFAULT_TEMPLATE_ID, ...)
        try:
            execution = sandbox.run_code(code_block)
            return truncate_result(str(execution))
        finally:
            sandbox.kill()
    # 正常情况：连接到已有沙箱执行
    sandbox = Sandbox.connect(sandbox_id, api_key=E2B_API_KEY)
    execution = sandbox.run_code(code_block)
```

两种执行模式：
- **有状态执行**：连接到指定 sandbox_id 的已有沙箱，变量和文件在多次调用间保留
- **无状态回退**：当 sandbox_id 无效时，创建临时沙箱执行后立即销毁

### 4. 文件传输

```python
@mcp.tool()
async def upload_file_from_local_to_sandbox(
    sandbox_id: str, local_file_path: str, sandbox_file_path: str = "/home/user"
) -> str:

@mcp.tool()
async def download_file_from_internet_to_sandbox(
    sandbox_id: str, url: str, sandbox_file_path: str = "/home/user"
) -> str:

@mcp.tool()
async def download_file_from_sandbox_to_local(
    sandbox_id: str, sandbox_file_path: str, local_filename: str = None
) -> str:
```

三个文件传输工具覆盖了所有文件流动场景：
- 本地 -> 沙箱（上传分析文件）
- 互联网 -> 沙箱（在沙箱内用 wget 下载）
- 沙箱 -> 本地（取回处理结果，供其他工具使用）

### 5. 结果截断

```python
MAX_RESULT_LEN = 20_000

def truncate_result(result: str) -> str:
    if len(result) > MAX_RESULT_LEN:
        result = result[:MAX_RESULT_LEN] + " [Result truncated due to length limit]"
    return result
```

防止代码输出过长（如打印大量数据）导致 LLM 上下文溢出。限制为 20,000 字符。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `create_sandbox` | MCP 工具 | 创建一个远程 Linux 沙箱 |
| `run_command` | MCP 工具 | 在沙箱中执行 shell 命令 |
| `run_python_code` | MCP 工具 | 在沙箱中执行 Python 代码 |
| `upload_file_from_local_to_sandbox` | MCP 工具 | 将本地文件上传到沙箱 |
| `download_file_from_internet_to_sandbox` | MCP 工具 | 从互联网下载文件到沙箱 |
| `download_file_from_sandbox_to_local` | MCP 工具 | 从沙箱下载文件到本地 |
| `truncate_result` | 函数 | 截断过长的执行结果 |
| `looks_like_dir` | 函数 | 判断路径是否为目录 |

## 与其他模块的关系

- **被 ToolManager 管理**：作为 stdio MCP 服务器被调用
- **依赖 E2B**：使用 `e2b_code_interpreter` 库与 E2B 云沙箱通信，需要 `E2B_API_KEY`
- **与其他工具服务器协作**：沙箱中生成的文件需要先下载到本地，才能被其他工具（如视觉、音频）处理
- **对比 `stateless_python_server.py`**：本文件提供完整的有状态沙箱管理，后者仅提供一次性代码执行

## 总结

`python_mcp_server.py` 是 Agent 的"计算能力引擎"，通过 E2B 沙箱提供安全的代码执行环境。它的六个工具覆盖了沙箱创建、代码执行、命令运行和文件传输的完整生命周期。防御性的 sandbox_id 验证、指数退避重试和结果截断确保了在面对 LLM 不确定输出时的鲁棒性。

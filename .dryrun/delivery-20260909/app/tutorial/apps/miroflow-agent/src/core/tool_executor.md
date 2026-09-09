# `tool_executor.py` -- 工具调用执行器

## 文件概述

`tool_executor.py` 提供了 `ToolExecutor` 类，负责处理智能体与外部工具之间的交互。它的核心职责包括：

- **参数修正**: 自动修复 LLM 常犯的参数命名错误
- **重复查询检测**: 跟踪已执行的查询，避免浪费轮次
- **结果后处理**: 在演示模式下截断过长的抓取结果
- **错误判断**: 识别需要触发回滚的错误类型
- **统一执行接口**: 封装工具调用的执行、计时和日志记录

在 MiroThinker 的架构中，`ToolExecutor` 位于 `Orchestrator` 和 `ToolManager`（MCP 工具管理器）之间，扮演一个**预处理/后处理中间层**的角色。

## 关键代码解读

### 1. 参数自动修正

```python
def fix_tool_call_arguments(self, tool_name: str, arguments: dict) -> dict:
    fixed_args = arguments.copy()

    # 修正 scrape_and_extract_info 的参数名
    if tool_name == "scrape_and_extract_info":
        mistake_names = ["description", "introduction"]
        if "info_to_extract" not in fixed_args:
            for mistake_name in mistake_names:
                if mistake_name in fixed_args:
                    fixed_args["info_to_extract"] = fixed_args.pop(mistake_name)
                    break

    # 修正 run_python_code 的参数名: 'code' -> 'code_block'
    if tool_name == "run_python_code":
        if "code_block" not in fixed_args and "code" in fixed_args:
            fixed_args["code_block"] = fixed_args.pop("code")
        if "sandbox_id" not in fixed_args:
            fixed_args["sandbox_id"] = "default"

    return fixed_args
```

LLM 在调用工具时，经常会把参数名搞错（例如用 `description` 代替 `info_to_extract`，用 `code` 代替 `code_block`）。这个函数在工具实际执行前自动修正这些常见错误，提高工具调用的成功率。注意它使用 `arguments.copy()` 避免修改原始字典。

### 2. 查询字符串提取（用于去重）

```python
def get_query_str_from_tool_call(self, tool_name: str, arguments: dict) -> Optional[str]:
    if tool_name == "search_and_browse":
        return tool_name + "_" + arguments.get("subtask", "")
    elif tool_name == "google_search":
        return tool_name + "_" + arguments.get("q", "")
    elif tool_name == "sogou_search":
        return tool_name + "_" + arguments.get("Query", "")
    elif tool_name == "scrape_website":
        return tool_name + "_" + arguments.get("url", "")
    elif tool_name == "scrape_and_extract_info":
        return (tool_name + "_" + arguments.get("url", "") + "_"
                + arguments.get("info_to_extract", ""))
    return None
```

每种工具有不同的"查询标识"参数：搜索工具用查询文本，抓取工具用 URL。函数将工具名和关键参数拼接成唯一字符串，供 `is_duplicate_query()` 进行去重判断。对于不支持去重的工具（如 `run_python_code`），返回 `None` 表示跳过去重。

### 3. 搜索结果空检测

```python
def is_google_search_empty_result(self, tool_name: str, tool_result: dict) -> bool:
    if tool_name != "google_search":
        return False

    result = tool_result.get("result")
    if not result:
        return False

    try:
        if isinstance(result, str):
            result_dict = json.loads(result)
        else:
            result_dict = result

        organic = result_dict.get("organic", [])
        return len(organic) == 0
    except (json.JSONDecodeError, TypeError, AttributeError):
        return False
```

Google 搜索有时会返回空的 `organic` 结果列表（通常是因为查询词不佳）。这个函数检测这种情况，让 `should_rollback_result()` 可以据此触发回滚，促使 LLM 换一个搜索词。

### 4. 演示模式结果截断

```python
DEMO_SCRAPE_MAX_LENGTH = 20_000

def post_process_tool_call_result(self, tool_name: str, tool_call_result: dict) -> dict:
    if os.environ.get("DEMO_MODE") == "1":
        if "result" in tool_call_result and tool_name in ["scrape", "scrape_website"]:
            tool_call_result["result"] = self.get_scrape_result(
                tool_call_result["result"]
            )
    return tool_call_result
```

在演示模式（`DEMO_MODE=1`）下，网页抓取结果会被截断到 20,000 字符。这是因为演示模式需要支持更多轮对话，过长的抓取结果会快速耗尽上下文窗口。

### 5. 回滚条件判断

```python
def should_rollback_result(self, tool_name: str, result: Any, tool_result: dict) -> bool:
    return (
        str(result).startswith("Unknown tool:")
        or str(result).startswith("Error executing tool")
        or self.is_google_search_empty_result(tool_name, tool_result)
    )
```

三种情况会触发回滚：
- `Unknown tool:` -- 工具名不存在（LLM 幻觉出了不存在的工具）
- `Error executing tool` -- 工具执行出错
- Google 搜索返回空结果

### 6. 统一工具执行接口

```python
async def execute_single_tool_call(self, tool_manager, server_name, tool_name,
                                     arguments, agent_name, turn_count):
    call_start_time = time.time()
    try:
        tool_result = await tool_manager.execute_tool_call(server_name, tool_name, arguments)
        tool_result = self.post_process_tool_call_result(tool_name, tool_result)
        call_duration_ms = int((time.time() - call_start_time) * 1000)
        # 记录日志、构建返回数据...
        return tool_result, call_duration_ms, tool_calls_data
    except Exception as e:
        # 异常处理：记录错误、构建错误结果...
        return tool_result, call_duration_ms, tool_calls_data
```

这个方法封装了完整的工具调用流程：计时 -> 执行 -> 后处理 -> 日志记录 -> 异常处理。无论成功还是失败，都会返回结构化的结果和执行时间。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `ToolExecutor` | 类 | 工具调用执行器，管理参数修正、去重、后处理和错误处理 |
| `fix_tool_call_arguments()` | 方法 | 自动修正 LLM 常犯的参数命名错误 |
| `get_query_str_from_tool_call()` | 方法 | 从工具调用参数中提取用于去重的查询字符串 |
| `is_duplicate_query()` | 方法 | 检查某个查询是否已经执行过 |
| `record_query()` | 方法 | 记录已执行的查询 |
| `is_google_search_empty_result()` | 方法 | 检测 Google 搜索是否返回空结果 |
| `get_scrape_result()` | 方法 | 在演示模式下截断过长的抓取结果 |
| `post_process_tool_call_result()` | 方法 | 结果后处理（目前仅在演示模式下截断抓取结果） |
| `should_rollback_result()` | 方法 | 判断工具结果是否应该触发回滚 |
| `execute_single_tool_call()` | 异步方法 | 统一的工具调用执行接口（计时 + 执行 + 后处理 + 异常处理） |
| `format_tool_result_for_llm()` | 方法 | 将工具结果格式化为 LLM 可理解的格式 |

### 关键常量

| 常量 | 值 | 说明 |
|------|---|------|
| `DEMO_SCRAPE_MAX_LENGTH` | 20,000 | 演示模式下抓取结果的最大字符数 |

## 与其他模块的关系

```
miroflow_tools.manager.ToolManager  <-- 实际执行 MCP 工具调用
io/output_formatter.py              <-- 格式化工具结果供 LLM 阅读
logging/task_logger.py              <-- 记录工具调用日志
core/stream_handler.py              <-- 推送工具调用事件
core/orchestrator.py                --> 调用 ToolExecutor 的各种方法
```

- `Orchestrator` 是 `ToolExecutor` 的主要调用者，在每轮工具调用前后都会使用其方法。
- `ToolManager`（来自 `miroflow_tools` 库）是实际的 MCP 工具执行层，`ToolExecutor` 在其上层添加了预处理和后处理逻辑。
- `OutputFormatter` 负责将工具结果转换为 LLM 能理解的文本格式。

## 总结

`ToolExecutor` 是 LLM 输出与实际工具执行之间的**智能适配层**。它通过参数修正提高 LLM 工具调用的容错率，通过重复检测避免浪费执行轮次，通过结果后处理控制上下文消耗，通过错误判断触发必要的回滚。这些功能看似简单，但直接影响了智能体在实际任务中的稳定性和效率。

# `wrapper_utils.py` — 类型安全的响应与错误包装器

## 文件概述

`wrapper_utils.py` 提供了两个简单但重要的包装类：`ErrorBox` 和 `ResponseBox`。它们为工具执行结果提供类型安全的封装，使得调用方可以明确区分正常响应和错误状态，而不需要依赖异常或特殊返回值。

在项目中，这些包装器被 `ToolExecutor` 用于封装工具调用的结果。

## 关键代码解读

### ErrorBox 错误包装器

```python
class ErrorBox:
    """
    用于包装错误消息的类。
    使用示例：
        >>> error = ErrorBox("Connection failed")
        >>> if ErrorBox.is_error_box(error):
        ...     print(f"Error: {error}")
    """
    def __init__(self, error_msg: str) -> None:
        self.error_msg = error_msg

    def __str__(self) -> str:
        return self.error_msg

    def __repr__(self) -> str:
        return f"ErrorBox({self.error_msg!r})"

    @staticmethod
    def is_error_box(something: Any) -> bool:
        return isinstance(something, ErrorBox)
```

**解释**：

- `ErrorBox` 将错误消息封装为一个独立的对象类型
- `is_error_box()` 静态方法提供了类型安全的检查方式
- 为什么不直接抛出异常？因为在异步的工具执行流程中，工具调用的失败不应中断整个推理循环。工具失败是预期内的情况——LLM 应该被告知失败并尝试其他方法
- `__str__` 使得 ErrorBox 可以直接作为字符串使用，便于拼接到消息中

### ResponseBox 响应包装器

```python
class ResponseBox:
    """
    带可选附加信息的响应包装器。
    使用示例：
        >>> response = ResponseBox({"data": "value"}, {"warning_msg": "Rate limited"})
        >>> if response.has_extra_info():
        ...     print(response.get_extra_info())
    """
    def __init__(self, response: Any, extra_info: Optional[Dict[str, Any]] = None) -> None:
        self.response = response
        self.extra_info = extra_info

    @staticmethod
    def is_response_box(something: Any) -> bool:
        return isinstance(something, ResponseBox)

    def has_extra_info(self) -> bool:
        return self.extra_info is not None

    def get_extra_info(self) -> Optional[Dict[str, Any]]:
        return self.extra_info

    def get_response(self) -> Any:
        return self.response
```

**解释**：

- `ResponseBox` 不仅封装响应本身，还可以附带额外的元信息（如速率限制警告、重试次数等）
- `extra_info` 是可选的字典，调用方可以在不修改响应数据的情况下传递额外上下文
- `is_response_box()` 静态方法用于检查一个对象是否是 ResponseBox 实例
- 这种设计遵循了**开放-封闭原则**：可以通过 `extra_info` 扩展传递的信息，而不需要修改类的接口

### ErrorBox 与 ResponseBox 的配合使用

在实际使用中，工具执行的返回值可能是以下三种之一：

1. `ResponseBox(result)` — 正常结果
2. `ResponseBox(result, {"warning_msg": "..."})` — 带警告的结果
3. `ErrorBox("error message")` — 错误

调用方的处理逻辑：

```python
result = await execute_tool(...)
if ErrorBox.is_error_box(result):
    # 处理错误：告知 LLM 工具调用失败
    pass
elif ResponseBox.is_response_box(result):
    # 处理正常响应
    if result.has_extra_info():
        # 处理附加信息
        pass
    actual_result = result.get_response()
```

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `ErrorBox` | 类 | 封装错误消息，与正常响应区分开 |
| `ErrorBox.is_error_box(obj)` | 静态方法 | 检查对象是否为 ErrorBox 实例 |
| `ResponseBox` | 类 | 封装响应结果，支持附加额外元信息 |
| `ResponseBox.is_response_box(obj)` | 静态方法 | 检查对象是否为 ResponseBox 实例 |
| `ResponseBox.has_extra_info()` | 方法 | 检查是否有附加信息 |
| `ResponseBox.get_extra_info()` | 方法 | 获取附加信息字典 |
| `ResponseBox.get_response()` | 方法 | 获取实际的响应对象 |

## 与其他模块的关系

- **`core/ToolExecutor`**：使用 `ErrorBox` 和 `ResponseBox` 封装工具执行结果
- **`core/Orchestrator`**：通过 `is_error_box()` / `is_response_box()` 判断工具执行状态

## 总结

`wrapper_utils.py` 实现了一个简洁的**Result 类型模式**（类似 Rust 的 `Result<T, E>` 或 Haskell 的 `Either`）。通过将成功和失败封装为不同的类型，避免了使用异常控制流或 None 返回值带来的歧义。这在异步、多工具的执行环境中尤为重要，因为工具失败是正常的业务逻辑而非异常事件。

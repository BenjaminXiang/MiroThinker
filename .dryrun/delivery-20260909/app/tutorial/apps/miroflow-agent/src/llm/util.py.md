# `util.py` — LLM 工具函数

## 文件概述

`util.py` 提供 LLM 客户端模块使用的工具函数。目前只包含一个异步超时装饰器 `with_timeout`，用于防止 LLM API 调用无限阻塞。

## 关键代码解读

```python
T = TypeVar("T")

def with_timeout(
    timeout_s: float = 300.0,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    装饰器：用 asyncio.wait_for() 包装任意异步函数。
    用法：
        @with_timeout(20)
        async def create_message_foo(...): ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_s)
        return wrapper
    return decorator
```

**解释**：

- 这是一个**参数化装饰器**（decorator factory）：`with_timeout(600)` 返回一个装饰器，该装饰器将被装饰的异步函数包装在 `asyncio.wait_for()` 中
- `asyncio.wait_for()` 会在超时后抛出 `asyncio.TimeoutError`
- `TypeVar("T")` 和类型注解确保装饰后的函数保持原始的返回类型
- `functools.wraps(func)` 保留被装饰函数的名称和文档字符串
- 默认超时 300 秒（5 分钟），在 `base_client.py` 中被覆盖为 600 秒（10 分钟）

**使用示例**（在 `base_client.py` 中）：

```python
@with_timeout(DEFAULT_LLM_TIMEOUT_SECONDS)  # 600秒
async def create_message(self, ...):
    ...
```

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `with_timeout(timeout_s)` | 装饰器工厂 | 为异步函数添加超时控制，超时后抛出 `asyncio.TimeoutError` |

## 与其他模块的关系

- **`base_client.py`**：在 `create_message()` 方法上使用 `@with_timeout(600)` 装饰器

## 总结

`util.py` 是一个短小精悍的工具模块，通过 `with_timeout` 装饰器为所有 LLM API 调用提供了统一的超时保护。这防止了网络问题或 API 服务异常导致的无限等待，是系统可靠性的重要保障。

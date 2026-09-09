# `factory.py` — LLM 客户端工厂

## 文件概述

`factory.py` 提供了 `ClientFactory` 工厂函数，根据 Hydra 配置中的 `llm.provider` 字段自动创建对应的 LLM 客户端实例。它是上层代码（Pipeline、Orchestrator）创建 LLM 客户端的唯一入口。

## 关键代码解读

```python
SUPPORTED_PROVIDERS = {"anthropic", "openai", "qwen"}

def ClientFactory(
    task_id: str, cfg: DictConfig, task_log: Optional[TaskLog] = None, **kwargs
) -> Union[OpenAIClient, AnthropicClient]:
    provider = cfg.llm.provider
    config = OmegaConf.merge(cfg, kwargs)

    client_creators = {
        "anthropic": lambda: AnthropicClient(task_id=task_id, task_log=task_log, cfg=config),
        "qwen": lambda: OpenAIClient(task_id=task_id, task_log=task_log, cfg=config),
        "openai": lambda: OpenAIClient(task_id=task_id, task_log=task_log, cfg=config),
    }

    factory = client_creators.get(provider)
    if not factory:
        raise ValueError(
            f"Unsupported provider: '{provider}'. "
            f"Supported providers are: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
        )
    return factory()
```

**解释**：

- 使用字典映射替代 if-elif 链，代码更简洁且易于扩展
- `"qwen"` 和 `"openai"` 都映射到 `OpenAIClient`，因为 Qwen 使用 OpenAI 兼容的 API 格式
- `OmegaConf.merge(cfg, kwargs)` 允许调用者通过关键字参数覆盖配置中的特定值
- 使用 `lambda` 延迟创建——只有被选中的提供商才会实际实例化客户端
- 不支持的提供商会抛出明确的错误信息，列出所有合法选项

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `ClientFactory(task_id, cfg, task_log, **kwargs)` | 函数 | 根据配置创建对应的 LLM 客户端实例 |
| `SUPPORTED_PROVIDERS` | 常量 | 支持的提供商名称集合：`anthropic`、`openai`、`qwen` |

## 与其他模块的关系

- **`core/Pipeline`**：调用 `ClientFactory()` 创建 LLM 客户端
- **`providers/anthropic_client.py`** 和 **`providers/openai_client.py`**：被工厂函数实例化
- **Hydra 配置**：`conf/llm/*.yaml` 中的 `provider` 字段决定创建哪种客户端

## 总结

`factory.py` 是一个经典的工厂模式实现，仅 30 余行代码就完成了 LLM 客户端的动态创建。它的简洁性得益于 Qwen 等提供商与 OpenAI API 格式兼容这一事实，使得只需两个具体客户端类就能支持三种提供商。

# llm 模块概览

## 模块简介

`llm` 模块是 MiroThinker 与大语言模型交互的**统一接口层**。它通过抽象基类和工厂模式，屏蔽了不同 LLM 提供商（Anthropic Claude、OpenAI GPT、Qwen 等）之间的 API 差异，为上层的编排器（Orchestrator）提供一致的调用接口。

## 架构图

```
                    Orchestrator
                        │
                        │ create_message()
                        ▼
              ┌──────────────────┐
              │  ClientFactory   │  ← factory.py
              │  (工厂函数)       │
              └────────┬─────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
    "anthropic"    "openai"     "qwen"
          │            │            │
          ▼            │            │
  ┌───────────────┐   │            │
  │AnthropicClient│   │            │
  │(anthropic_    │   │            │
  │ client.py)    │   │            │
  └───────┬───────┘   │            │
          │            ▼            ▼
          │     ┌────────────────────┐
          │     │   OpenAIClient     │
          │     │  (openai_client.py)│
          │     └────────┬───────────┘
          │              │
          └──────┬───────┘
                 │
                 ▼
         ┌───────────────┐
         │  BaseClient   │  ← base_client.py
         │  (抽象基类)    │
         │               │
         │ - TokenUsage  │
         │ - create_msg  │
         │ - tool convert│
         │ - close()     │
         └───────────────┘
                 │
                 │ @with_timeout
                 ▼
         ┌───────────────┐
         │   util.py     │
         │  超时装饰器    │
         └───────────────┘
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `base_client.py` | 抽象基类 `BaseClient`，定义 LLM 客户端的通用接口和工具方法 |
| `factory.py` | 工厂函数 `ClientFactory`，根据配置创建对应的 LLM 客户端实例 |
| `util.py` | 工具函数，目前包含异步超时装饰器 `with_timeout` |
| `providers/anthropic_client.py` | Anthropic Claude API 的具体实现，支持 Prompt Caching |
| `providers/openai_client.py` | OpenAI API（及兼容接口如 vLLM、Qwen）的具体实现 |
| `__init__.py` | 包初始化，导出 `BaseClient`、`ClientFactory`、`AnthropicClient`、`OpenAIClient` |
| `providers/__init__.py` | 子包初始化，导出两个客户端类 |

## 设计理念

该模块采用**策略模式**（Strategy Pattern）：

- `BaseClient` 定义统一接口（消息创建、响应处理、工具调用提取、Token 统计等）
- 具体的提供商客户端（`AnthropicClient`、`OpenAIClient`）实现各自的 API 调用细节
- `ClientFactory` 根据配置字符串选择正确的实现

这样做的好处是：上层代码（Orchestrator）只需要和 `BaseClient` 接口交互，完全不需要知道底层用的是哪个 LLM 提供商。切换提供商只需修改一行配置。

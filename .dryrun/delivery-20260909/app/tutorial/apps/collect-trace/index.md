# `collect-trace` -- 训练数据收集应用

## 文件概述

`collect-trace` 是 MiroThinker 的训练数据收集工具集。它的核心任务是：从 Agent 运行产生的 JSON 日志文件中，提取对话历史并转换为 **ChatML** 格式，供下游的 SFT（监督微调）和 DPO（直接偏好优化）训练流程使用。

## 架构图

```
┌──────────────────────────────────────────────────────────────┐
│                      collect-trace                           │
│                                                              │
│  输入：Agent 运行日志（JSON 文件）                            │
│  ┌──────────────┐                                            │
│  │ process_logs │  筛选成功日志 → 复制到指定目录               │
│  └──────┬───────┘                                            │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────────────────────────────────┐            │
│  │         converters/ (格式转换器)               │            │
│  │                                              │            │
│  │  ┌─────────────────────────────────────┐     │            │
│  │  │ convert_to_chatml_auto_batch.py     │     │            │
│  │  │  自动识别 LLM Provider              │     │            │
│  │  │  批量调度转换                        │     │            │
│  │  └──────┬──────────────┬───────────────┘     │            │
│  │         │              │                     │            │
│  │         ▼              ▼                     │            │
│  │  ┌─────────────┐ ┌──────────────────┐        │            │
│  │  │ convert_oai │ │ convert_non_oai  │        │            │
│  │  │ _to_chatml  │ │ _to_chatml       │        │            │
│  │  │             │ │                  │        │            │
│  │  │ OpenAI格式  │ │ 非OpenAI格式     │        │            │
│  │  │ 工具调用转换 │ │ 简单消息过滤     │        │            │
│  │  └─────────────┘ └──────────────────┘        │            │
│  │                                              │            │
│  │  system_prompts.py  提供系统提示词模板         │            │
│  │  example_usage.py   使用示例                  │            │
│  └──────────────────────────────────────────────┘            │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────────────────────┐                        │
│  │ merge_chatml_msgs_to_one_json   │                        │
│  │ 合并多个 ChatML 文件为一个      │                         │
│  │ 训练数据集 JSON                 │                         │
│  └──────────────────────────────────┘                        │
│                                                              │
│  输出：ChatML 格式的训练数据集                                │
└──────────────────────────────────────────────────────────────┘
```

## 核心处理流程

1. **日志筛选** (`process_logs.py`)：从基准测试结果（JSONL/JSON 目录）中筛选出成功案例的日志路径，将成功日志复制到统一目录。
2. **格式自动识别与批量转换** (`converters/convert_to_chatml_auto_batch.py`)：读取每个日志文件中的 `llm_provider` 字段，自动选择 OAI 或 Non-OAI 转换器进行处理。
3. **OAI 格式转换** (`converters/convert_oai_to_chatml.py`)：将 OpenAI 兼容的工具调用消息（`tool_calls` 字段）转换为 MCP XML 格式的 ChatML 对话。
4. **Non-OAI 格式转换** (`converters/convert_non_oai_to_chatml.py`)：对非 OpenAI 格式的日志，直接过滤并提取对话历史。
5. **数据集合并** (`merge_chatml_msgs_to_one_json.py`)：将所有独立的 ChatML JSON 文件合并为单个训练数据集文件。

## 目录结构

```
apps/collect-trace/
├── utils/
│   ├── process_logs.py                          # 日志筛选与复制
│   ├── merge_chatml_msgs_to_one_json.py         # ChatML 合并
│   └── converters/
│       ├── __init__.py                          # 模块导出
│       ├── convert_oai_to_chatml.py             # OAI 格式转换
│       ├── convert_non_oai_to_chatml.py         # 非 OAI 格式转换
│       ├── convert_to_chatml_auto_batch.py      # 自动批量转换
│       ├── system_prompts.py                    # 系统提示词模板
│       └── example_usage.py                     # 使用示例
```

## 与其他模块的关系

- **输入来源**：`apps/miroflow-agent/` 运行基准测试后生成的 JSON 日志文件（包含 `main_agent_message_history`、`sub_agent_message_history_sessions` 等字段）。
- **输出用途**：生成的 ChatML 数据集可直接用于 LLM 的 SFT 和 DPO 训练流水线。
- **依赖**：仅依赖 Python 标准库（`json`、`pathlib`、`argparse` 等），无第三方依赖。

## 总结

`collect-trace` 是一个纯数据处理工具集，负责将 Agent 运行产生的原始日志转换为标准化的 ChatML 训练数据。它通过自动识别 LLM Provider 来选择正确的转换路径，支持批量处理和数据合并，是 MiroThinker 训练数据管线的关键环节。

# `converters/` -- 格式转换器模块

## 文件概述

`converters/` 是 `collect-trace` 的核心子模块，负责将 Agent 运行日志中的消息历史转换为 ChatML 训练数据格式。模块通过 `__init__.py` 统一对外导出 API，内部按 LLM Provider 的不同分为两条转换路径。

## 模块结构

```
converters/
├── __init__.py                        # 模块导出（统一 API）
├── convert_oai_to_chatml.py           # OpenAI 格式转换器
├── convert_non_oai_to_chatml.py       # 非 OpenAI 格式转换器
├── convert_to_chatml_auto_batch.py    # 自动识别 + 批量调度
├── system_prompts.py                  # 系统提示词模板常量
└── example_usage.py                   # 使用示例
```

## 导出 API

`__init__.py` 导出以下函数，分为三组：

**OAI 转换函数**（来自 `convert_oai_to_chatml.py`）：
| 函数名 | 说明 |
|--------|------|
| `oai_tool_message_to_chat_message` | 将 OAI 格式消息流转换为 ChatML |
| `extract_message_history_from_log` | 从日志中提取并转换所有 Agent 消息 |
| `save_chatml_to_files` | 将转换结果保存为 JSON 文件 |
| `process_log_file` | 处理单个日志文件的完整流程 |

**Non-OAI 转换函数**（来自 `convert_non_oai_to_chatml.py`）：
| 函数名 | 说明 |
|--------|------|
| `convert_to_json_chatml` | 过滤并标准化消息列表 |
| `extract_and_save_chat_history` | 提取对话历史并保存为文件 |

**自动批量函数**（来自 `convert_to_chatml_auto_batch.py`）：
| 函数名 | 说明 |
|--------|------|
| `get_llm_provider` | 从日志中提取 LLM Provider |
| `determine_conversion_method` | 判定使用 OAI 还是 Non-OAI 方式 |
| `process_single_file` | 自动选择转换器处理单个文件 |
| `batch_process_files` | 批量处理多个文件 |

## 两条转换路径

| 路径 | 适用 Provider | 核心差异 |
|------|--------------|----------|
| **OAI** | `openai`, `claude_newapi`, `deepseek_newapi` | 处理 `tool_calls` 字段，转换为 MCP XML 格式，重建系统提示词 |
| **Non-OAI** | 其他所有 Provider | 简单过滤 `tool`/`system` 角色消息，直接输出 |

## 与其他模块的关系

- 被 `utils/process_logs.py` 间接调用（通过 `os.system` 调用 `convert_to_chatml_auto_batch.py`）。
- 输出文件被 `utils/merge_chatml_msgs_to_one_json.py` 合并。
- 依赖 `system_prompts.py` 中的模板常量。

## 总结

`converters/` 模块是训练数据管线的核心，提供了从 Agent 日志到 ChatML 格式的完整转换能力。通过自动识别 LLM Provider，用户无需关心底层格式差异，只需调用 `batch_process_files` 即可完成批量转换。

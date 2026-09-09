# `utils/` -- 工具集概览

## 文件概述

`utils/` 目录包含 `collect-trace` 应用的所有实用工具，负责从 Agent 运行日志到训练数据集的完整处理流程。

## 目录结构

```
utils/
├── process_logs.py                     # 入口脚本：日志筛选 + 流水线编排
├── merge_chatml_msgs_to_one_json.py    # 合并多个 ChatML 文件为一个数据集
└── converters/                         # 格式转换器子模块
    ├── __init__.py
    ├── convert_oai_to_chatml.py        # OpenAI 格式转换
    ├── convert_non_oai_to_chatml.py    # 非 OpenAI 格式转换
    ├── convert_to_chatml_auto_batch.py # 自动识别 + 批量转换
    ├── system_prompts.py               # 系统提示词模板
    └── example_usage.py                # 使用示例
```

## 处理流程

```
benchmark_results.jsonl
        │
        ▼
process_logs.py ──── 筛选成功日志 ────► successful_logs/
        │
        ▼
convert_to_chatml_auto_batch.py ──── 自动转换 ────► successful_chatml_logs/
        │
        ▼
merge_chatml_msgs_to_one_json.py ──── 合并 ────► main_agent_merged.json
                                                  agent-browsing_merged.json
```

## 各文件职责

| 文件 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `process_logs.py` | 筛选成功日志，编排流水线 | JSONL/JSON 结果文件 | 成功日志副本 |
| `converters/convert_to_chatml_auto_batch.py` | 自动选择转换器，批量处理 | JSON 日志文件 | ChatML JSON 文件 |
| `converters/convert_oai_to_chatml.py` | OAI 格式日志转 ChatML | JSON 日志 | ChatML JSON |
| `converters/convert_non_oai_to_chatml.py` | Non-OAI 格式日志转 ChatML | JSON 日志 | ChatML JSON |
| `converters/system_prompts.py` | 提供系统提示词模板 | - | - |
| `converters/example_usage.py` | 转换器使用示例 | - | - |
| `merge_chatml_msgs_to_one_json.py` | 合并 ChatML 文件 | ChatML 目录 | 合并数据集 JSON |

## 总结

`utils/` 是一个完整的数据处理工具集，覆盖了从日志筛选、格式转换到数据合并的全部环节。每个工具既可独立使用（通过命令行），也可被 `process_logs.py` 串联为自动化流水线。

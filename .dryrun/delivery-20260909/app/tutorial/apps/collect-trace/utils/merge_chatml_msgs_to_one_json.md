# `merge_chatml_msgs_to_one_json.py` -- ChatML 文件合并工具

## 文件概述

本文件负责将多个独立的 ChatML JSON 文件合并为一个统一的训练数据集 JSON 文件。在转换流程的最后一步，每个日志文件会生成一个或多个 ChatML 文件（主 Agent 一个、每个子 Agent 会话一个），本工具将它们按类型合并为两个最终数据集文件。

## 关键代码解读

### 1. 合并逻辑

```python
def merge_json_files(input_dir, type="main"):
    all_conversations = []
    json_files = glob.glob(os.path.join(input_dir, f"*{type}*.json"))

    for json_file in json_files:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            conversation = {"messages": data}
            all_conversations.append(conversation)

    output_file = os.path.join(input_dir, f"{type}_merged.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_conversations, f, ensure_ascii=False, indent=2)
```

**逐步解释**：
- 使用 `glob` 匹配指定目录中文件名包含 `type` 关键字的所有 JSON 文件。
- 每个 JSON 文件的内容（消息列表）被包装在 `{"messages": [...]}` 结构中，形成一条对话记录。
- 所有对话记录组成一个列表，写入合并后的文件。
- 输出格式为：`[{"messages": [...]}, {"messages": [...]}, ...]`，这是常见的 SFT 训练数据格式。

### 2. 主函数

```python
def main():
    parser = argparse.ArgumentParser(...)
    parser.add_argument("--input_dir", type=str, required=True, ...)
    args = parser.parse_args()

    merge_json_files(args.input_dir, type="main_agent")
    merge_json_files(args.input_dir, type="agent-browsing")
```

**逐步解释**：
- 接受 `--input_dir` 参数指定输入目录。
- 分别合并两类文件：`main_agent`（主 Agent 对话）和 `agent-browsing`（浏览 Agent 对话）。
- 生成 `main_agent_merged.json` 和 `agent-browsing_merged.json` 两个文件。

## 核心类/函数表格

| 函数名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `merge_json_files` | `input_dir: str, type: str` | `None` | 合并指定类型的 ChatML 文件为单个 JSON |
| `main` | 无 | `None` | CLI 入口，解析参数并执行两次合并 |

## 与其他模块的关系

- 输入来源：`converters/` 模块生成的 ChatML JSON 文件（文件名包含 `main_agent` 或 `agent-browsing`）。
- 被 `process_logs.py` 在转换完成后调用（通过 `os.system`）。
- 输出：最终的合并训练数据集，可直接用于下游训练。

## 总结

这是数据管线的最后一步，将分散的 ChatML 文件聚合为统一数据集。输出格式为 `[{"messages": [...]}]`，符合常见 SFT 训练框架的数据输入规范。核心逻辑通过文件名中的关键字匹配来区分不同 Agent 类型的数据。

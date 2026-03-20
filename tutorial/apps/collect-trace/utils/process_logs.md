# `process_logs.py` -- 日志筛选与处理流水线

## 文件概述

本文件是 `collect-trace` 的**入口脚本**，负责从基准测试结果中筛选出成功案例的日志，将其复制到统一目录，然后依次调用格式转换和数据合并工具，完成从原始日志到训练数据集的完整流水线。

## 关键代码解读

### 1. 成功日志筛选

```python
def get_successful_log_paths(jsonl_file_path: str) -> list:
    log_paths = []

    if jsonl_file_path.endswith(".jsonl"):
        with open(jsonl_file_path, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                if data.get("final_judge_result") == "PASS_AT_K_SUCCESS":
                    log_path = data.get("log_file_path")
                    if log_path:
                        log_paths.append(log_path)
    else:
        filenames = os.listdir(jsonl_file_path)
        for filename in filenames:
            data = json.load(open(os.path.join(jsonl_file_path, filename)))
            if data["final_judge_result"] == "CORRECT":
                log_paths.append(filepath)

    return log_paths
```

**逐步解释**：
- 支持两种输入格式：
  - **JSONL 文件**（完整的基准测试结果）：逐行解析，筛选 `final_judge_result` 为 `PASS_AT_K_SUCCESS` 的记录，提取其 `log_file_path`。
  - **JSON 目录**（中断的测试，结果散落在多个文件中）：遍历目录中的 JSON 文件，筛选 `final_judge_result` 为 `CORRECT` 的记录。
- 两种格式使用不同的成功标记（`PASS_AT_K_SUCCESS` vs `CORRECT`），反映了完整运行和中断运行的不同评判逻辑。

### 2. 完整处理流水线

```python
if __name__ == "__main__":
    result = get_successful_log_paths(args.file_path)

    # 1. 复制成功日志到统一目录
    for path in result:
        shutil.copy(path, f"{success_log_dir}/{basename}")

    # 2. 批量转换为 ChatML 格式
    os.system(f"uv run utils/converters/convert_to_chatml_auto_batch.py {success_log_dir}/*.json -o {success_chatml_log_dir}")

    # 3. 合并为训练数据集
    os.system(f"uv run utils/merge_chatml_msgs_to_one_json.py --input_dir {success_chatml_log_dir}")
```

**逐步解释**：
- **步骤 1**：将筛选出的成功日志复制到 `successful_logs/` 目录。
- **步骤 2**：调用 `convert_to_chatml_auto_batch.py` 批量转换日志为 ChatML 格式，输出到 `successful_chatml_logs/` 目录。
- **步骤 3**：调用 `merge_chatml_msgs_to_one_json.py` 将所有 ChatML 文件合并为最终数据集。
- 目录结构为：`{parent_dir}/successful_logs/` 和 `{parent_dir}/successful_chatml_logs/`，均在输入文件的父目录下创建。

## 核心类/函数表格

| 函数名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `get_successful_log_paths` | `jsonl_file_path: str` | `list[str]` | 从基准测试结果中筛选成功案例的日志路径 |

## 与其他模块的关系

- 调用 `converters/convert_to_chatml_auto_batch.py` 进行格式转换。
- 调用 `merge_chatml_msgs_to_one_json.py` 进行数据合并。
- 输入来源：`apps/miroflow-agent/` 运行基准测试后生成的 `benchmark_results.jsonl` 或结果目录。

## 总结

本文件是整个训练数据收集流水线的编排者，串联了"筛选 -> 转换 -> 合并"三个步骤。它的核心价值在于自动化了从基准测试结果到可用训练数据的完整过程，只需指定一个结果文件路径即可一键完成。

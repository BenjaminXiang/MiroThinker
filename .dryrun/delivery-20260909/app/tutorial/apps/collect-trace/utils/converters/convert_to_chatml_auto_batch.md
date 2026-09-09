# `convert_to_chatml_auto_batch.py` -- 自动批量 ChatML 转换

## 文件概述

本文件是转换器的**调度中心**，负责自动识别每个日志文件使用的 LLM Provider，选择正确的转换脚本，并支持批量处理整个目录的日志文件。它是 `process_logs.py` 流程中实际调用的转换入口。

## 关键代码解读

### 1. LLM Provider 识别

```python
def get_llm_provider(json_file_path: str) -> str:
    with open(json_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    provider = data.get("env_info", {}).get("llm_provider")
    if provider:
        return provider
    else:
        return "unknown"
```

**逐步解释**：
- 打开 JSON 日志文件，从 `env_info.llm_provider` 字段读取 LLM Provider 名称。
- 如果字段不存在则返回 `"unknown"`，读取异常则返回 `"error"`。

### 2. 转换方法判定

```python
def determine_conversion_method(provider: str) -> str:
    if provider.lower() in ["openai", "claude_newapi", "deepseek_newapi"]:
        return "oai"
    else:
        return "non-oai"
```

**逐步解释**：
- `openai`、`claude_newapi`、`deepseek_newapi` 三种 Provider 使用 OAI 格式（它们的日志中包含结构化的 `tool_calls` 字段）。
- 其他所有 Provider 使用 Non-OAI 格式。
- 这个判定逻辑是整个自动化流程的核心决策点。

### 3. 单文件处理

```python
def process_single_file(json_file_path: str, output_dir: str) -> bool:
    provider = get_llm_provider(json_file_path)
    conversion_method = determine_conversion_method(provider)
    oai_script, non_oai_script = get_script_paths()

    if conversion_method == "oai":
        script_path = oai_script
    else:
        script_path = non_oai_script

    result = subprocess.run(
        [sys.executable, script_path, json_file_path, output_dir],
        capture_output=True, text=True,
    )
```

**逐步解释**：
- 获取 Provider -> 判定转换方法 -> 选择脚本路径。
- 通过 `subprocess.run` 以子进程方式调用对应的转换脚本。
- 这种设计使得每个转换脚本既可以独立运行，也可以被批量调度。

### 4. 批量处理

```python
def batch_process_files(input_paths: List[str], output_dir: str) -> Dict[str, int]:
    json_files = find_json_files(input_paths)
    success_count = 0
    failed_count = 0
    for json_file in json_files:
        if process_single_file(json_file, output_dir):
            success_count += 1
        else:
            failed_count += 1
    return {"total": len(json_files), "success": success_count, "failed": failed_count}
```

**逐步解释**：
- `find_json_files` 支持三种输入：单文件路径、目录路径、glob 模式。
- 逐个处理找到的 JSON 文件，统计成功/失败数量。
- 返回处理统计字典。

## 核心类/函数表格

| 函数名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `get_llm_provider` | `json_file_path: str` | `str` | 从日志文件中提取 LLM Provider 名称 |
| `determine_conversion_method` | `provider: str` | `"oai"` 或 `"non-oai"` | 根据 Provider 判定使用哪种转换方法 |
| `get_script_paths` | 无 | `tuple[str, str]` | 获取两个转换脚本的绝对路径 |
| `process_single_file` | `json_file_path, output_dir` | `bool` | 处理单个 JSON 文件 |
| `find_json_files` | `input_paths: List[str]` | `List[str]` | 从输入路径列表中查找所有 JSON 文件 |
| `batch_process_files` | `input_paths, output_dir` | `Dict[str, int]` | 批量处理多个文件并返回统计 |

## 与其他模块的关系

- 调用 `convert_oai_to_chatml.py` 和 `convert_non_oai_to_chatml.py` 作为子进程执行实际转换。
- 被 `process_logs.py` 通过 `os.system` 调用来批量处理成功日志。
- 通过 `__init__.py` 导出核心函数。

## 总结

本模块是"智能调度层"，解决了"不同 LLM Provider 的日志格式不同，需要用不同转换器处理"这个问题。核心价值在于自动化：用户只需指定输入目录，模块会自动识别每个文件的格式并选择正确的转换路径。

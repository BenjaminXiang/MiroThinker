# 基准测试配置总览 -- `conf/benchmark/` 全部 17 个配置详解

## 文件概述

`conf/benchmark/` 目录包含 17 个 YAML 配置文件，每个对应一个基准测试数据集。所有配置都继承自 `default.yaml`，仅覆盖名称（`name`）和数据路径（`data.data_dir`），其余参数完全一致。这种设计使得新增基准测试只需复制一个文件并修改两行即可。

## 默认配置解读（`default.yaml`）

```yaml
name: "default"

data:
  metadata_file: "standardized_data.jsonl"
  field_mapping:
    task_id_field: "task_id"
    task_question_field: "task_question"
    ground_truth_field: "ground_truth"
    file_name_field: "file_name"

execution:
  max_tasks: null       # null = 不限制
  max_concurrent: 5     # 最大并发任务数
  pass_at_k: 1          # Pass@K 评估策略
```

### 核心配置项表格

| 配置项 | 类型 | 说明 |
|---|---|---|
| `name` | 字符串 | 基准测试标识符，用于选择对应的评估器（evaluator） |
| `data.metadata_file` | 字符串 | 数据文件名，所有基准测试统一使用 `standardized_data.jsonl` |
| `data.field_mapping.task_id_field` | 字符串 | JSONL 中任务 ID 字段名 |
| `data.field_mapping.task_question_field` | 字符串 | JSONL 中问题字段名 |
| `data.field_mapping.ground_truth_field` | 字符串 | JSONL 中标准答案字段名 |
| `data.field_mapping.file_name_field` | 字符串 | JSONL 中附件文件名字段名（可选） |
| `data.data_dir` | 字符串 | 数据目录路径（相对于应用根目录） |
| `execution.max_tasks` | 整数/null | 最大运行任务数（null=全部） |
| `execution.max_concurrent` | 整数 | 最大并发进程数 |
| `execution.pass_at_k` | 整数 | 每个任务最多尝试 K 次，K 次中有一次正确即算通过 |

## 全部 17 个基准测试一览

### 研究型基准测试（10 个）

| 配置文件 | 名称 | 数据目录 | 说明 |
|---|---|---|---|
| `browsecomp.yaml` | browsecomp | `data/browsecomp` | OpenAI BrowseComp 英文版（1266 题），考察深度网页搜索能力 |
| `browsecomp_zh.yaml` | browsecomp_zh | `data/browsecomp_zh` | BrowseComp 中文版 |
| `gaia-validation.yaml` | gaia-validation | `data/gaia-2023-validation` | GAIA 2023 验证集（165 题），通用 AI 助手能力评估，含三个难度等级 |
| `gaia-validation-text-103.yaml` | gaia-validation-text-103 | `data/gaia-2023-validation-text-103` | GAIA 纯文本子集（103 题），排除了需要文件处理的题目 |
| `hle.yaml` | hle | `data/hle` | HLE 完整集（2500 题），Humanity's Last Exam |
| `hle-text-2158.yaml` | hle-text-2158 | `data/hle-text-2158` | HLE 纯文本子集（2158 题） |
| `hle-text-500.yaml` | hle-text-500 | `data/hle-text-500` | HLE 500 题采样子集 |
| `frames.yaml` | frames | `data/frames` | FRAMES 基准测试（824 题），事实推理与多步搜索 |
| `aime2025.yaml` | aime2025 | `data/aime2025` | AIME 2025 数学竞赛（30 题） |
| `deepsearchqa.yaml` | deepsearchqa | `data/deepsearchqa` | Google DeepSearchQA（900 题），集合答案型问答 |

### 其他基准测试（5 个）

| 配置文件 | 名称 | 数据目录 | 说明 |
|---|---|---|---|
| `futurex.yaml` | futurex | `data/futurex` | FutureX 预测任务 |
| `seal-0.yaml` | seal-0 | `data/seal-0` | SEAL-0 基准测试 |
| `webwalkerqa.yaml` | webwalkerqa | `data/webwalkerqa` | WebWalkerQA 网页遍历问答 |
| `xbench_deepsearch.yaml` | xbench_deepsearch | `data/xbench_deepsearch` | XBench 深度搜索（中文） |

### 特殊用途（2 个）

| 配置文件 | 名称 | 数据目录 | 说明 |
|---|---|---|---|
| `debug.yaml` | debug | `data/debug` | 调试用配置，少量测试数据 |
| `collect_trace.yaml` | collect_trace | `data/debug` | 训练数据收集模式（用于 SFT/DPO 数据采集） |

## 数据格式约定

所有基准测试的数据都统一存储为 JSONL 格式（每行一个 JSON 对象），文件名统一为 `standardized_data.jsonl`。字段映射也统一：

```json
{
  "task_id": "abc123",
  "task_question": "What is the capital of France?",
  "ground_truth": "Paris",
  "file_name": null,
  "metadata": { "Level": 1 }
}
```

这种标准化设计使得 `GenericEvaluator` 可以用同一套代码加载和处理所有基准测试的数据。

## 与其他模块的关系

- **`benchmarks/common_benchmark.py`**：`CommonBenchmark` 类读取 benchmark 配置，创建 `GenericEvaluator` 并执行评估。
- **`benchmarks/evaluators/eval_utils.py`**：`verify_answer_for_datasets()` 根据 `benchmark.name` 选择对应的评估方法（SimpleQA / HLE / GAIA / BrowseComp 等）。
- **`benchmarks/check_progress/`**：每个进度检查脚本硬编码了对应基准测试的任务数量和数据路径。
- **`conf/config.yaml`**：通过 `benchmark: default` 指定默认使用哪个基准测试。

## 总结

17 个基准测试配置采用完全统一的结构，通过继承 `default.yaml` 实现最小化重复。每个配置只定义名称和数据路径两个差异点。统一的 JSONL 数据格式和字段映射使得框架可以用通用代码处理所有基准测试。

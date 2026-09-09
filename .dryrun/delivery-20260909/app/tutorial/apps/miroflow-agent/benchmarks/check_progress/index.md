# 进度检查模块总览 -- `check_progress/` 全部检查器详解

## 文件概述

`check_progress/` 目录包含 14 个 Python 文件：1 个通用框架（`common.py`）和 13 个基准测试专属进度检查脚本。这些脚本用于在基准测试运行过程中**实时监控进度、统计准确率、预估完成时间**。每个脚本都是独立可运行的命令行工具。

## 架构设计

```
common.py（通用框架）
  ├── ProgressChecker          ←── 大多数基准测试使用
  └── GAIAProgressChecker      ←── GAIA 专用（含难度分级统计）

check_progress_browsecomp.py   → 实例化 ProgressChecker
check_progress_gaia-validation.py → 实例化 GAIAProgressChecker
check_progress_hle.py          → 实例化 ProgressChecker
check_progress_deepsearchqa.py → 实例化 ProgressChecker + 额外 F1 指标
...（其余 9 个脚本结构相同）
```

## 全部 13 个检查器一览

| 脚本文件 | 基准测试名称 | 每运行任务数 | 检查器类型 | 特殊功能 |
|---|---|---|---|---|
| `check_progress_browsecomp.py` | BrowseComp-EN | 1266 | `ProgressChecker` | -- |
| `check_progress_browsecomp_zh.py` | BrowseComp-ZH | 1266 | `ProgressChecker` | -- |
| `check_progress_gaia-validation.py` | GAIA-Val-165 | 165 | `GAIAProgressChecker` | 三级难度统计 |
| `check_progress_gaia-validation-text-103.py` | GAIA-Text-103 | 103 | `GAIAProgressChecker` | 三级难度统计 |
| `check_progress_hle.py` | HLE-2500 | 2500 | `ProgressChecker` | -- |
| `check_progress_hle-text-2158.py` | HLE-Text-2158 | 2158 | `ProgressChecker` | -- |
| `check_progress_hle-text-500.py` | HLE-Text-500 | 500 | `ProgressChecker` | -- |
| `check_progress_frames.py` | Frames | 824 | `ProgressChecker` | -- |
| `check_progress_aime2025.py` | AIME2025 | 30 | `ProgressChecker` | -- |
| `check_progress_deepsearchqa.py` | DeepSearchQA | 900 | `ProgressChecker` | F1/Precision/Recall 指标 |
| `check_progress_seal-0.py` | SEAL-0 | 256 | `ProgressChecker` | -- |
| `check_progress_webwalkerqa.py` | WebWalkerQA | 680 | `ProgressChecker` | -- |
| `check_progress_xbench_deepsearch.py` | XBench-DS | 424 | `ProgressChecker` | -- |

## `common.py` 通用框架详解

`common.py` 是整个进度检查系统的核心，约 950 行代码，包含以下关键组件：

### 数据结构

| 类 | 说明 |
|---|---|
| `TaskStats` | 单次运行的统计数据（完成数、运行数、失败数、正确数、平均轮数等） |
| `GAIATaskStats` | GAIA 专用统计（继承 `TaskStats`，增加三级难度统计） |
| `SummaryStats` | 多次运行的汇总统计 |
| `GAIASummaryStats` | GAIA 专用汇总（继承 `SummaryStats`） |

### 核心类 `ProgressChecker`

| 方法 | 说明 |
|---|---|
| `__init__(target_path, task_per_run, data_path)` | 初始化，加载基准测试数据 |
| `find_run_directories()` | 在目标路径下查找所有 `run_*` 目录 |
| `analyze_run_directory(run_dir, task_id_pattern)` | 分析单个运行目录：统计完成/运行/失败任务、计算准确率和平均轮数 |
| `run_analysis(benchmark_name_std, task_id_pattern)` | 执行完整分析：遍历所有运行目录、汇总统计、显示结果、保存日志 |

### 分析流程

```
1. find_run_directories()
   └── 查找 target_path 下所有 run_* 目录

2. 对每个 run_dir:
   ├── _get_latest_task_files()
   │   └── 找到每个 task_id 的最新日志文件（按 start_time 排序）
   ├── _is_task_completed()
   │   └── 判断任务是否完成（有 end_time 且无 error）
   ├── _is_judge_correct()
   │   └── 判断 judge 结果是否正确（支持多种格式：字符串/布尔/数字/字典）
   └── _calculate_turns()
       └── 从消息历史计算推理轮数

3. 汇总统计:
   ├── 计算 Pass@1 Acc (Avg@n) -- 多次运行的平均准确率 +/- 标准差
   ├── 计算 Pass@N -- 多次运行中至少一次正确的任务比例
   └── 预估剩余完成时间
```

### 辅助函数

| 函数 | 说明 |
|---|---|
| `create_progress_bar(percentage)` | 创建彩色终端进度条（绿>80%、黄>60%、橙>40%、红<40%） |
| `find_earliest_start_time(files)` | 从日志文件中提取最早开始时间 |
| `find_latest_end_time(files)` | 从日志文件中提取最晚结束时间 |
| `estimate_completion_time(total, completed, files)` | 基于完成速率预估剩余时间 |
| `calculate_mean_and_std(values)` | 计算均值和标准差 |

### `GAIAProgressChecker` -- GAIA 专用

继承自 `ProgressChecker`，增加了按难度等级（Level 1/2/3）统计准确率的功能。通过 `task_difficulty_map` 将 task_id 映射到难度等级，然后在分析时分别统计各等级的正确率。

## 典型检查器脚本解读（以 `check_progress_browsecomp.py` 为例）

```python
BENCHMARK_NAME = "browsecomp"
BENCHMARK_NAME_STD = "BrowseComp-EN"
TASKS_PER_RUN = 1266
DATA_PATH = f"../../data/{BENCHMARK_NAME}/standardized_data.jsonl"
TASK_ID_PATTERN = r"task_([a-f0-9]+)"

if __name__ == "__main__":
    args = parse_args()
    checker = ProgressChecker(args.path, task_per_run=TASKS_PER_RUN, data_path=DATA_PATH)
    summary = checker.run_analysis(
        benchmark_name_std=BENCHMARK_NAME_STD, task_id_pattern=TASK_ID_PATTERN
    )
```

每个检查器脚本的结构完全相同，只有 5 个常量不同：
- `BENCHMARK_NAME`：基准测试目录名
- `BENCHMARK_NAME_STD`：显示用的标准化名称
- `TASKS_PER_RUN`：每次运行的总任务数
- `DATA_PATH`：数据文件路径
- `TASK_ID_PATTERN`：从文件名提取 task_id 的正则表达式

使用方式：
```bash
python check_progress/check_progress_browsecomp.py /path/to/logs/browsecomp/experiment1
```

## `check_progress_deepsearchqa.py` -- 特殊检查器

这是唯一包含额外评估逻辑的检查器。除了标准的进度统计外，它还计算 DeepSearchQA 的官方指标：

| 指标 | 说明 |
|---|---|
| Fully Correct | 所有预期答案都正确，且没有多余答案 |
| Fully Incorrect | 没有任何正确答案 |
| Correct with Extraneous | 所有预期答案正确，但包含多余答案 |
| F1 Score | 精确率和召回率的调和平均数 |

这些指标通过解析日志文件中的 `eval_details` 字段获取，支持运行中（intermediate）和运行后（final）两种计算模式。

## 与其他模块的关系

- **`common_benchmark.py`**：产生 `task_*.json` 日志文件，进度检查脚本读取这些文件。
- **`evaluators/eval_utils.py`**：`check_progress_deepsearchqa.py` 中的 F1 计算逻辑与 `eval_utils.py` 中的 DeepSearchQA 评估逻辑对应。
- **`conf/benchmark/`**：每个检查器脚本的常量（任务数、数据路径）需要与对应的 benchmark 配置保持一致。

## 总结

进度检查模块采用"通用框架 + 薄包装脚本"的设计。`common.py` 提供了完整的分析引擎（目录扫描、日志解析、统计计算、时间预估），各检查器脚本只需配置 5 个常量。`GAIAProgressChecker` 和 `check_progress_deepsearchqa.py` 展示了如何在通用框架上扩展基准测试专属的统计逻辑。

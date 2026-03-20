# `common.py` -- 进度检查通用框架

## 文件概述

`common.py` 是 `check_progress/` 目录的核心模块，约 1050 行代码。它提供了 `ProgressChecker` 和 `GAIAProgressChecker` 两个类，以及多个辅助数据结构和工具函数，用于分析基准测试运行日志、统计进度与准确率、预估完成时间。所有 13 个进度检查脚本都依赖此文件。

## 关键代码解读

### 1. 常量定义（第 14-32 行）

```python
DEFAULT_TASK_TIME_MINUTES = 3.5    # 无有效时间数据时的默认任务耗时
PROGRESS_BAR_WIDTH = 20            # 进度条字符宽度
GREEN_THRESHOLD = 80               # >=80% 绿色
YELLOW_THRESHOLD = 60              # >=60% 黄色
ORANGE_THRESHOLD = 40              # >=40% 橙色
CORRECT_RESULTS = ["CORRECT", "SUCCESS"]
SUCCESS_PATTERNS = ["PASS_AT_K_SUCCESS"]
```

这些常量定义了进度条的颜色阈值和判定正确答案的字符串模式。

### 2. 辅助函数

| 函数 | 行数 | 说明 |
|---|---|---|
| `create_progress_bar(percentage, width)` | 35-51 | 生成带颜色的终端进度条字符串 |
| `find_earliest_start_time(files)` | 54-78 | 遍历日志文件，找到最早的 `start_time` |
| `find_latest_end_time(files)` | 81-106 | 遍历日志文件，找到最晚的 `end_time` |
| `calculate_mean_and_std(values)` | 109-123 | 计算均值和样本标准差 |
| `estimate_completion_time(total, completed, files)` | 126-162 | 基于已完成任务的速率估算剩余时间 |

时间预估逻辑：
```
剩余时间 = 剩余任务数 * (总已用时间 / 总已完成数)
```
如果没有有效的时间数据，退回到默认的 3.5 分钟/任务估算。

### 3. 统计数据结构

#### `TaskStats`（第 166-208 行）

```python
@dataclass
class TaskStats:
    completed: int = 0          # 已完成任务数
    running: int = 0            # 运行中任务数
    failed: int = 0             # 失败任务数
    judge_correct: int = 0      # Judge 判定正确数
    total: int = 0              # 总任务数
    completed_files: List[str]  # 已完成的日志文件路径
    total_turns: int = 0        # 总推理轮数
    completed_tasks_with_turns: int = 0  # 有轮数记录的任务数
    no_boxed_found: int = 0     # 未找到 \boxed{} 答案的任务数
```

计算属性：
- `judge_accuracy`：正确率 = `judge_correct / completed * 100`
- `completion_rate`：完成率 = `completed / total * 100`
- `average_turns`：平均轮数 = `total_turns / completed_tasks_with_turns`

#### `GAIATaskStats`（第 212-248 行）

继承 `TaskStats`，增加三级难度统计：
- `level1_completed/correct`、`level2_completed/correct`、`level3_completed/correct`
- 对应 `level1_accuracy`、`level2_accuracy`、`level3_accuracy` 计算属性

#### `SummaryStats` 和 `GAIASummaryStats`（第 252-340 行）

跨多次运行的汇总统计。`average_run_accuracy()` 方法计算各运行准确率的均值和标准差。

### 4. `ProgressChecker` 核心类（第 343-948 行）

#### 初始化

```python
def __init__(self, target_path, task_per_run, data_path):
    self.target_path = target_path
    self.total_tasks_per_run = task_per_run
    self._load_benchmark_data(data_path)
```

#### 目录发现

```python
def find_run_directories(self):
    # 查找 target_path 下所有 run_* 目录
    # 按运行编号排序
```

#### 日志文件处理

`_get_latest_task_files(run_dir, task_id_pattern)` 是关键方法：
1. 查找目录下所有 `task_*.json` 文件
2. 按 `task_id_pattern` 正则表达式提取 task_id
3. 对同一个 task_id 的多个文件，**按 `start_time` 取最新的**
4. 返回去重后的文件列表

#### 任务状态判断

```python
def _is_task_completed(self, data):
    return (
        (end_time != "" and error == "")
        or (status == "completed")
        or (final_answer != "" and error == "")
    )

def _is_judge_correct(self, judge_result):
    # 支持多种格式：
    # - 字符串: "CORRECT", "SUCCESS", "PASS_AT_K_SUCCESS", "true", "yes"
    # - 布尔值: True
    # - 数字: > 0
    # - 字典: {"correct": True} 或 {"is_correct": True}
```

#### 轮数计算

```python
def _calculate_turns(self, data):
    # 从 main_agent_message_history.message_history 中
    # 过滤掉 system 消息，剩余消息数 / 2 = 轮数
    # （每轮 = 1个 user + 1个 assistant）
```

#### 完整分析流程

```python
def run_analysis(self, benchmark_name_std, task_id_pattern):
    self.run_dirs = self.find_run_directories()
    summary = SummaryStats()

    for run_dir in self.run_dirs:
        stats, task_results = self.analyze_run_directory(run_dir, task_id_pattern)
        # 显示单次运行统计
        # 汇总到 summary

    self._display_summary(summary, run_stats_list, ...)
    return summary
```

#### Pass@N 计算

```python
def _calculate_pass_at_n(self, all_task_results, total_tasks):
    # 对每个 task_id，检查所有运行中是否至少有一次正确
    # pass_at_n_count = 至少有一次正确的任务数
```

#### 结果输出

`_display_summary()` 输出内容包括：
- 总任务数、已完成/运行中/失败数
- 剩余任务数和预估完成时间
- 整体准确率（带彩色进度条）
- 平均推理轮数
- 各运行的独立准确率
- Pass@1 Acc (Avg@n) -- 多运行平均准确率
- Pass@N -- 多运行至少一次正确率
- `\boxed{}` 格式未找到的比例

`_save_analysis_log()` 将分析结果保存到 `progress_analysis_*.log` 文件。

### 5. `GAIAProgressChecker`（第 950-1048 行）

继承 `ProgressChecker`，重写了：
- `_load_benchmark_data()`：从 JSONL 中提取 task_id 到难度等级的映射
- `analyze_run_directory()`：使用 `GAIATaskStats`，额外统计各难度等级的正确率

## 核心类/函数表格

| 组件 | 类型 | 说明 |
|---|---|---|
| `ProgressChecker` | 类 | 通用进度检查器（11/13 个脚本使用） |
| `GAIAProgressChecker` | 类 | GAIA 专用检查器（2 个脚本使用） |
| `TaskStats` | 数据类 | 单次运行统计 |
| `GAIATaskStats` | 数据类 | GAIA 单次运行统计（含难度分级） |
| `SummaryStats` | 数据类 | 多次运行汇总 |
| `GAIASummaryStats` | 数据类 | GAIA 多次运行汇总 |
| `create_progress_bar()` | 函数 | 彩色终端进度条 |
| `estimate_completion_time()` | 函数 | 基于速率的时间预估 |

## 与其他模块的关系

- **被依赖**：13 个 `check_progress_*.py` 脚本全部从此文件导入 `ProgressChecker` 或 `GAIAProgressChecker`。
- **读取数据**：读取 `common_benchmark.py` 产生的 `task_*.json` 日志文件。
- **数据契约**：日志文件必须包含 `start_time`、`end_time`、`status`、`final_boxed_answer`、`final_judge_result` 等字段。

## 总结

`common.py` 提供了完整的基准测试进度分析能力：目录扫描、日志解析、多格式判正、轮数统计、时间预估、多运行聚合（均值/标准差/Pass@N）。通过继承机制支持 GAIA 等需要特殊统计的基准测试。其设计目标是让检查器脚本只需 5 行常量配置即可运行完整分析。

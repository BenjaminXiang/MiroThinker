# `common_benchmark.py` -- 基准测试核心框架

## 文件概述

`common_benchmark.py` 是整个基准测试系统的**核心引擎**，约 1025 行代码。它定义了任务数据结构、抽象评估器基类、通用评估器实现，以及基准测试的完整执行流程（加载数据 -> 并行推理 -> 答案验证 -> 结果保存）。这是整个 `benchmarks/` 目录中最重要的文件。

## 关键代码解读

### 1. 数据结构定义

```python
@dataclass
class BenchmarkTask:
    task_id: str
    task_question: str
    ground_truth: str
    file_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    model_boxed_answer: str = ""
    status: str = "pending"

@dataclass
class BenchmarkResult:
    task_id: str
    task_question: str
    ground_truth: str
    file_path: Optional[str]
    status: str
    model_boxed_answer: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    final_judge_result: Optional[str] = None
    judge_type: Optional[str] = None
    log_file_path: Optional[str] = None
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    pass_at_k_success: bool = False
    k_value: int = 1
```

`BenchmarkTask` 表示一个待评估的任务输入，`BenchmarkResult` 表示评估结果。`attempts` 列表支持 Pass@K 评估：每个任务最多尝试 K 次，记录每次尝试的答案和验证结果。

### 2. 抽象基类 `BenchmarkEvaluator`

| 方法 | 说明 |
|---|---|
| `__init__(data_dir, benchmark_name, cfg)` | 初始化流水线组件（工具管理器、格式化器） |
| `run_single_task(task)` | 执行单个任务：支持 Pass@K 多次尝试，含格式错误重试、失败经验积累 |
| `run_parallel_inference(tasks, max_concurrent)` | 使用 `ProcessPoolExecutor` 多进程并行执行多个任务 |
| `save_results(output_file)` | 将结果保存为 JSONL |
| `evaluate_accuracy()` | 计算 Pass@K 准确率 |
| `prepare_task_description(task)` | **抽象方法**，子类必须实现，负责将任务对象转换为文本描述 |

### 3. `run_single_task` 的执行流程

这是最复杂的方法，其执行流程如下：

```
对于每个 attempt（1 到 pass_at_k）:
  1. 检查是否有已存在的日志文件（支持断点续跑）
  2. 如果有日志 -> 加载已有结果 -> 跳过推理
  3. 如果无结果或格式错误 -> 进入格式重试循环:
     a. 恢复之前的失败经验（从历史日志中读取）
     b. 调用 execute_task_pipeline() 执行推理
     c. 如果答案格式错误 -> 将失败经验附加到任务描述 -> 重试
     d. 重试次数由 context_compress_limit 控制
  4. 答案验证：调用 verify_answer_for_datasets() 判断正确性
  5. 如果正确 -> 提前停止（Early Stopping）
```

关键设计点：
- **断点续跑**：通过检查 `task_{id}_attempt-{n}_*.json` 日志文件，已完成的尝试不会重复执行。
- **失败经验积累**：每次格式错误重试时，之前的失败摘要（`failure_experience_summary`）会被附加到任务描述中，帮助模型避免重复同样的错误。
- **Early Stopping**：Pass@K 中一旦找到正确答案就停止后续尝试。

### 4. 多进程并行执行

```python
def run_parallel_inference(self, tasks, max_concurrent=3):
    executor = ProcessPoolExecutor(max_workers=max_concurrent)
    for args in worker_args:
        future = executor.submit(_task_worker, *args)
```

使用 `ProcessPoolExecutor` 而非 `ThreadPoolExecutor`，因为 Python GIL 限制了线程级并行。每个 worker 进程独立创建事件循环和评估器实例，任务列表会被随机打乱以均衡负载。

顶层模块函数 `_task_worker()` 是每个 worker 进程的入口，它：
1. 从序列化的字典重建 `DictConfig` 和 `BenchmarkTask`
2. 创建新的 `GenericEvaluator` 实例
3. 在新的事件循环中执行 `run_single_task()`

### 5. `GenericEvaluator` -- 通用 JSONL 评估器

继承自 `BenchmarkEvaluator`，增加了从 JSONL 文件加载任务的能力：

| 方法 | 说明 |
|---|---|
| `load_tasks(limit)` | 从 `standardized_data.jsonl` 加载任务，支持字段名映射 |
| `prepare_task_description(task)` | 返回任务问题文本和文件路径 |

### 6. `CommonBenchmark` -- 顶层编排类

```python
class CommonBenchmark:
    def run_evaluation(self):
        self.evaluator.load_tasks(limit=cfg.benchmark.execution.max_tasks)
        self.evaluator.run_parallel_inference(tasks, max_concurrent=...)
        accuracy = self.evaluator.evaluate_accuracy()
        self.evaluator.save_results(results_path)
```

这是用户直接使用的类，完整流程：加载任务 -> 并行推理 -> 计算准确率 -> 保存结果 -> 生成统计摘要。

### 7. Hydra 入口

```python
@hydra.main(config_path="../conf", config_name="config", version_base=None)
def run_benchmark(cfg: DictConfig) -> None:
    benchmark = CommonBenchmark(cfg)
    benchmark.run_evaluation()
```

可以直接运行此文件来执行基准测试：
```bash
python benchmarks/common_benchmark.py benchmark=browsecomp agent=mirothinker_v1.5
```

## 核心类/函数表格

| 类/函数 | 行数 | 说明 |
|---|---|---|
| `BenchmarkTask` | 87-97 | 任务输入数据结构 |
| `BenchmarkResult` | 100-117 | 评估结果数据结构 |
| `BenchmarkEvaluator` | 120-803 | 抽象评估器基类（含推理、验证、并行化） |
| `GenericEvaluator` | 806-926 | 通用 JSONL 评估器（继承基类） |
| `CommonBenchmark` | 929-1009 | 顶层编排类（加载 + 执行 + 保存） |
| `_task_worker()` | 34-83 | 多进程 worker 函数（模块级） |
| `run_benchmark()` | 1012-1020 | Hydra 入口函数 |

## 与其他模块的关系

```
common_benchmark.py
  ├── src/core/pipeline.py               # 创建组件 + 执行任务
  ├── evaluators/eval_utils.py           # verify_answer_for_datasets() 答案验证
  ├── src/utils/prompt_utils.py          # 失败经验提示词模板
  ├── src/logging/summary_time_cost.py   # 生成统计摘要
  ├── conf/                              # Hydra 配置系统
  └── check_progress/                    # 进度检查脚本读取此文件产生的日志
```

## 总结

`common_benchmark.py` 是基准测试系统的核心，实现了从数据加载到结果评估的完整流水线。其核心设计亮点包括：Pass@K 多次尝试评估、格式错误的智能重试与失败经验积累、基于多进程的真并行执行、以及断点续跑支持。所有具体的基准测试都通过配置文件驱动，无需修改此文件的代码。

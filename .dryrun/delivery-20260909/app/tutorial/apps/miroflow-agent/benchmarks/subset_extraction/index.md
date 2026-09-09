# 数据子集提取工具总览 -- `subset_extraction/` 全部文件详解

## 文件概述

`subset_extraction/` 目录包含 2 个 Python 脚本，专门用于从 GAIA 完整验证集中提取和重评 **GAIA-Text-103** 子集。GAIA-Text-103 是 GAIA 验证集（165 题）中排除了需要文件附件处理的 103 道纯文本题目，便于评估不具备文件处理能力的智能体。

## 文件列表

| 文件 | 行数 | 说明 |
|---|---|---|
| `gaia-to-text-103-mover.py` | 197 | 从 GAIA 完整验证集日志中提取 Text-103 子集任务文件 |
| `gaia-text-103-grader.py` | 303 | 使用 LLM Judge 对提取的 Text-103 任务重新评分 |

---

## `gaia-to-text-103-mover.py` -- 子集提取器

### 文件概述

该脚本从已运行的 GAIA 验证集日志目录中，筛选出属于 GAIA-Text-103 的任务，并复制到新的目录中保持原始目录结构。这样用户无需重新运行 103 道题，可以直接从 165 题的结果中提取子集。

### 核心类 `GAIAtoText103Copier`

| 方法 | 说明 |
|---|---|
| `__init__(gaia_text_103_data_path, output_dir)` | 加载 GAIA-Text-103 的 task_id 集合 |
| `_load_gaia_text_103_tasks()` | 从 `standardized_data.jsonl` 读取所有 Text-103 task_id |
| `copy_gaia_text_103_tasks(gaia_logs_dir)` | 遍历 GAIA 日志目录，匹配 task_id 并复制文件 |
| `print_summary()` | 打印复制统计 |

### 执行流程

```
1. 加载 GAIA-Text-103 的 task_id 集合（从 standardized_data.jsonl）
2. 遍历 GAIA 验证集日志目录下所有 task_*.json 文件
3. 从文件名提取 task_id
4. 如果 task_id 在 Text-103 集合中 → 复制文件到输出目录
5. 保持原始目录结构（run_*/task_*.json）
```

### 使用方式

```bash
python subset_extraction/gaia-to-text-103-mover.py /path/to/logs/gaia-validation \
  --gaia_text_103_data ../../data/gaia-2023-validation-text-103/standardized_data.jsonl \
  --output-dir /path/to/output/gaia-text-103-extraction
```

如果不指定 `--output-dir`，默认在 GAIA 日志目录的同级创建 `gaia-text-103-extraction/`。

---

## `gaia-text-103-grader.py` -- 子集重评分器

### 文件概述

该脚本对提取的 GAIA-Text-103 任务文件使用 LLM Judge 重新评分。因为原始 GAIA 验证集使用的是规则匹配评估（`verify_answer_gaia`），而 Text-103 子集使用更宽容的 LLM 等价性判断（`verify_answer_gaia_validation_text_103`），两者的评判标准不同。

### 核心类 `GAIAText103Grader`

| 方法 | 说明 |
|---|---|
| `__init__(extraction_dir)` | 初始化评分器 |
| `find_task_files()` | 递归查找所有 `task_*.json` 文件 |
| `extract_task_info(task_file)` | 从日志中提取问题、答案、预测答案（跳过已评分的） |
| `grade_single_task(task_info)` | 调用 `verify_answer_gaia_validation_text_103()` 评分 |
| `grade_all_tasks(max_concurrent)` | 使用 `asyncio.Semaphore` 并发评分 |
| `update_original_files()` | 将评分结果写回原始日志文件 |
| `print_summary()` | 打印评分统计 |

### 数据结构

```python
@dataclass
class GradingResult:
    task_id: str
    run_name: str
    file_path: str
    question: str
    ground_truth: str
    predicted_answer: str
    judge_result: str
    judge_type: str = "gaia_validation_text_103_scorer"
    grading_time: float = 0.0
    error_message: str = ""
```

### 执行流程

```
1. 递归查找 extraction_dir 下所有 task_*.json
2. 过滤已评分的任务（judge_type == "gaia_validation_text_103_scorer"）
3. 提取 question、ground_truth、predicted_answer
4. 并发调用 LLM Judge 评分（默认 5 并发）
5. 将 judge_result、judge_type、grading_time 写回原始文件
```

### 使用方式

```bash
python subset_extraction/gaia-text-103-grader.py /path/to/gaia-text-103-extraction \
  --max-concurrent 5
```

### 幂等性设计

通过检查 `judge_type == "gaia_validation_text_103_scorer"` 跳过已评分的任务，脚本可以安全地多次运行而不会重复评分。

---

## 核心类/函数表格

| 文件 | 类/函数 | 说明 |
|---|---|---|
| `gaia-to-text-103-mover.py` | `GAIAtoText103Copier` | 子集提取器：按 task_id 筛选并复制文件 |
| `gaia-to-text-103-mover.py` | `_load_gaia_text_103_tasks()` | 加载 Text-103 task_id 集合 |
| `gaia-to-text-103-mover.py` | `copy_gaia_text_103_tasks()` | 执行文件筛选和复制 |
| `gaia-text-103-grader.py` | `GAIAText103Grader` | 重评分器：使用 LLM Judge 重新评判 |
| `gaia-text-103-grader.py` | `GradingResult` | 评分结果数据结构 |
| `gaia-text-103-grader.py` | `grade_all_tasks()` | 并发评分主方法 |
| `gaia-text-103-grader.py` | `update_original_files()` | 将结果写回原始文件 |

## 与其他模块的关系

- **`evaluators/eval_utils.py`**：`gaia-text-103-grader.py` 直接导入 `verify_answer_gaia_validation_text_103()` 函数。
- **`common_benchmark.py`**：产生被提取的 GAIA 验证集日志文件。
- **`check_progress/check_progress_gaia-validation-text-103.py`**：在重评分后，可以使用此脚本检查 Text-103 子集的最终准确率。
- **`conf/benchmark/gaia-validation-text-103.yaml`**：定义 Text-103 子集的配置。

## 典型工作流

```bash
# 步骤 1：运行 GAIA 完整验证集
python benchmarks/common_benchmark.py benchmark=gaia-validation agent=mirothinker_v1.5

# 步骤 2：从结果中提取 Text-103 子集
python benchmarks/subset_extraction/gaia-to-text-103-mover.py logs/gaia-validation/experiment1

# 步骤 3：使用 Text-103 专属评估器重评分
python benchmarks/subset_extraction/gaia-text-103-grader.py logs/gaia-text-103-extraction

# 步骤 4：检查 Text-103 子集准确率
python benchmarks/check_progress/check_progress_gaia-validation-text-103.py logs/gaia-text-103-extraction
```

## 总结

子集提取模块解决了一个实际问题：GAIA 完整验证集（165 题）包含需要文件处理的任务，而 Text-103 子集（103 题纯文本）使用不同的评估标准。这两个脚本提供了"提取 + 重评分"的流水线，避免了重复运行 103 道题的开销。设计上注意了幂等性（跳过已评分任务）和目录结构保持。

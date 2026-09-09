# 基准测试模块总览 -- `benchmarks/` 目录结构与设计

## 文件概述

`benchmarks/` 目录是 MiroThinker 的**基准测试评估系统**，负责自动化运行多种学术基准测试、验证答案正确性、追踪运行进度和统计结果。整个目录包含约 20 个 Python 文件，分为四个功能区域。

## 目录结构

```
benchmarks/
├── __init__.py
├── common_benchmark.py              # 核心框架：任务加载、并行推理、Pass@K 评估
├── evaluators/                      # 答案评估器
│   ├── __init__.py
│   ├── eval_utils.py                # 统一评估入口 + 各基准测试的评判逻辑
│   ├── calculate_average_score.py   # 多次运行的平均分计算
│   └── extract_futurex_results.py   # FutureX 结果聚合与多数投票
├── check_progress/                  # 运行进度检查
│   ├── common.py                    # 通用进度检查框架
│   ├── check_progress_browsecomp.py # BrowseComp 进度检查
│   ├── check_progress_gaia-validation.py
│   ├── check_progress_hle.py
│   ├── check_progress_aime2025.py
│   ├── check_progress_deepsearchqa.py  # 含 DeepSearchQA 专属指标
│   ├── check_progress_frames.py
│   ├── check_progress_browsecomp_zh.py
│   ├── check_progress_gaia-validation-text-103.py
│   ├── check_progress_hle-text-2158.py
│   ├── check_progress_hle-text-500.py
│   ├── check_progress_seal-0.py
│   ├── check_progress_webwalkerqa.py
│   └── check_progress_xbench_deepsearch.py
└── subset_extraction/               # 数据子集提取工具
    ├── gaia-text-103-grader.py      # GAIA-Text-103 评分器
    └── gaia-to-text-103-mover.py    # GAIA 到 Text-103 子集提取
```

## 四大功能区域

### 1. 核心框架（`common_benchmark.py`）

整个系统的引擎。定义了 `BenchmarkTask`/`BenchmarkResult` 数据结构、`BenchmarkEvaluator` 抽象基类和 `GenericEvaluator` 通用实现。负责：
- 从 JSONL 文件加载任务数据
- 使用多进程并行执行推理
- 支持 Pass@K 评估和格式错误重试
- 断点续跑（检测已有日志跳过已完成任务）

### 2. 答案评估器（`evaluators/`）

`eval_utils.py` 是核心，包含了针对每个基准测试的专属评判逻辑：

| 评估函数 | 适用基准测试 | 评判方式 |
|---|---|---|
| `verify_answer_simpleqa` | 通用问答 | LLM Judge（GPT-4.1），三分类：CORRECT/INCORRECT/NOT_ATTEMPTED |
| `verify_answer_hle` | HLE | LLM Judge（o3-mini），结构化输出，含置信度评分 |
| `verify_answer_gaia` | GAIA | 规则匹配（数字比较、列表比较、字符串归一化） |
| `verify_answer_gaia_validation_text_103` | GAIA-Text-103 | LLM Judge（GPT-4.1），等价性判断 |
| `verify_answer_browsecomp` | BrowseComp（英文） | LLM Judge（GPT-4.1），二分类 A/B |
| `verify_answer_browsecomp_zh` | BrowseComp（中文） | LLM Judge（GPT-4.1），中文评判提示词 |
| `verify_answer_xbench_deepsearch` | XBench DeepSearch | LLM Judge（GPT-4.1），中文三段式评判 |
| `verify_answer_deepsearchqa` | DeepSearchQA | LLM Judge（GPT-4.1），JSON 结构化输出，含 F1 指标 |

辅助工具：
- `calculate_average_score.py`：从多次运行的准确率文件中计算均值、标准差、最大/最小值。
- `extract_futurex_results.py`：聚合多次运行结果，使用多数投票生成 FutureX 提交文件。

### 3. 进度检查（`check_progress/`）

13 个进度检查脚本用于监控正在运行的基准测试。`common.py` 提供通用框架（`ProgressChecker` 和 `GAIAProgressChecker`），各脚本只需配置基准测试名称、任务数量和数据路径。

功能包括：
- 统计已完成/运行中/失败的任务数
- 计算实时准确率和平均推理轮数
- 预估剩余完成时间
- 支持 Pass@N（多次运行中至少一次正确）
- 彩色进度条显示

### 4. 子集提取（`subset_extraction/`）

用于从完整基准测试结果中提取子集：
- `gaia-to-text-103-mover.py`：从 GAIA 完整验证集日志中提取属于 Text-103 子集的任务文件。
- `gaia-text-103-grader.py`：使用 LLM Judge 对提取的 Text-103 任务重新评分。

## 数据流

```
standardized_data.jsonl  ──→  common_benchmark.py  ──→  task_*.json（日志文件）
                                    │                        │
                                    ↓                        ↓
                              eval_utils.py            check_progress/
                              （答案验证）              （进度监控）
                                    │
                                    ↓
                         benchmark_results.jsonl  ──→  calculate_average_score.py
                                                       extract_futurex_results.py
```

## 与其他模块的关系

| 模块 | 关系 |
|---|---|
| `conf/benchmark/` | 提供基准测试配置（名称、数据路径、执行参数） |
| `conf/agent/` | 提供智能体配置（工具、轮数、上下文策略） |
| `conf/llm/` | 提供 LLM 模型配置 |
| `src/core/pipeline.py` | 被 `common_benchmark.py` 调用执行推理 |
| `data/` | 存放各基准测试的标准化数据文件 |
| `logs/` | 存放运行日志和结果文件 |

## 总结

`benchmarks/` 模块实现了从数据加载到结果统计的完整基准测试流水线。核心框架通过多进程并行、Pass@K 评估和断点续跑支持大规模评测。评估器模块针对不同基准测试提供了差异化的评判策略（规则匹配 vs LLM Judge）。进度检查和子集提取工具辅助日常实验管理。

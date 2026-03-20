# 答案评估器总览 -- `evaluators/` 全部文件详解

## 文件概述

`evaluators/` 目录包含 4 个 Python 文件，负责**答案正确性验证**和**结果统计**。核心文件 `eval_utils.py` 实现了针对 8 种不同基准测试的专属评判逻辑，是整个评估系统中与 LLM-as-Judge 直接交互的唯一模块。

## 文件列表

| 文件 | 行数 | 说明 |
|---|---|---|
| `eval_utils.py` | ~900 | 核心评估逻辑：8 种基准测试的答案验证函数 + 统一调度入口 |
| `calculate_average_score.py` | 153 | 多次运行的平均分统计工具 |
| `extract_futurex_results.py` | 160 | FutureX 结果聚合 + 多数投票提交生成 |
| `__init__.py` | 1 | 空文件 |

---

## `eval_utils.py` -- 核心评估逻辑

### 文件概述

该文件约 900 行，实现了 8 个评估函数和 1 个统一调度入口 `verify_answer_for_datasets()`。评估方式分为两大类：**规则匹配**和 **LLM-as-Judge**。

### 评估客户端初始化

```python
evaluation_llm_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
model_as_a_judge_client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
```

所有 LLM Judge 评估统一使用 OpenAI 兼容的异步客户端，模型为 `gpt-4.1-2025-04-14`（SimpleQA/BrowseComp/GAIA-Text-103/XBench/DeepSearchQA）或 `o3-mini-2025-01-31`（HLE）。

### 8 个评估函数详解

#### 1. `verify_answer_simpleqa` -- 通用三分类评估

- **评判模型**：GPT-4.1
- **提示词**：EVALUATION_PROMPT_SIMPLEQA（约 100 行的少样本评估提示词）
- **输出**：A(CORRECT) / B(INCORRECT) / C(NOT_ATTEMPTED)
- **特点**：提供了丰富的 CORRECT、INCORRECT、NOT_ATTEMPTED 示例，涵盖数字近似、信息省略、名字拼写容错等情况

#### 2. `verify_answer_hle` -- HLE 结构化评估

- **评判模型**：o3-mini
- **提示词**：HLE_JUDGE_PROMPT
- **输出**：Pydantic 结构化响应（`HLEExtractedAnswer`），包含：
  - `extracted_final_answer`：从回答中提取的最终答案
  - `reasoning`：评判推理过程
  - `correct`："yes" 或 "no"
  - `confidence`：0-100 置信度评分
- **特点**：使用 OpenAI 的 `response_format` 结构化输出，确保返回格式一致

#### 3. `verify_answer_gaia` -- GAIA 规则匹配评估

- **评判方式**：纯规则匹配（不使用 LLM）
- **三种比较模式**：
  - 数字比较：将答案归一化为浮点数后精确比较
  - 列表比较：按元素逐一比较（支持数字/字符串混合）
  - 字符串比较：去空格、去标点、转小写后比较
- **特点**：确定性评估，无随机性，不依赖外部 API

#### 4. `verify_answer_gaia_validation_text_103` -- GAIA-Text-103 等价性评估

- **评判模型**：GPT-4.1
- **提示词**：GAIA_VALIDATION_TEXT_103_SCORER_PROMPT（来自 WebAgent 项目）
- **输出**："Correct" 或 "Incorrect"
- **特点**：判断预测答案与标准答案是否**语义等价**，比纯规则匹配更宽容

#### 5. `verify_answer_browsecomp` -- BrowseComp 英文评估

- **评判模型**：GPT-4.1
- **提示词**：JUDGE_PROMPT_BC_en（约 70 行，来自 Tongyi DeepResearch 项目）
- **输出**：A(CORRECT) / B(INCORRECT)
- **特点**：二分类（无 NOT_ATTEMPTED），提供详细的正确/错误示例和评判规则

#### 6. `verify_answer_browsecomp_zh` -- BrowseComp 中文评估

- **评判模型**：GPT-4.1
- **提示词**：JUDGE_PROMPT_BC_zh（中文版，约 70 行）
- **特点**：与英文版逻辑相同，但提示词完全中文化，包含中文特有的评判规则（如多答案括号标记格式 `【【答案1，答案2】】`）

#### 7. `verify_answer_xbench_deepsearch` -- XBench 中文评估

- **评判模型**：GPT-4.1
- **提示词**：JUDGE_PROMPT_XBENCH（中文三段式提示词，来自 xbench-evals 项目）
- **输出**：三段式结构（最终答案 / 解释 / 结论：正确或错误）
- **特点**：通过正则表达式从自由文本中提取"结论"字段

#### 8. `verify_answer_deepsearchqa` -- DeepSearchQA JSON 结构化评估

- **评判模型**：GPT-4.1
- **提示词**：JUDGE_PROMPT_DEEPSEARCHQA（来自 Google DeepSearchQA 官方）
- **输出**：JSON 结构化响应，包含：
  - `Correctness Details`：每个预期答案的正确性字典
  - `Excessive Answers`：多余答案列表
  - `Explanation`：评判解释
- **返回值**：三元组 `(result, judge_type, details_dict)`，details_dict 包含 `num_correct`、`num_expected`、`num_excessive` 等指标
- **特点**：唯一返回详细评估细节的函数，支持集合答案（Set Answer）和单一答案（Single Answer）两种类型

### 统一调度入口

```python
async def verify_answer_for_datasets(benchmark_name, question, target, predicted_answer, metadata=None):
    # 根据 benchmark_name 选择对应的评估函数
```

该函数根据 `benchmark_name` 参数路由到对应的评估函数，返回统一格式的 `(result, judge_type, eval_details)` 三元组。

---

## `calculate_average_score.py` -- 多次运行平均分统计

### 文件概述

命令行工具，从多次运行的准确率文件中计算统计指标。

### 核心逻辑

```python
def calculate_average_scores(results_dir):
    # 1. 自动检测 pass_at_k 值（从文件名提取）
    # 2. 读取所有 run_*/benchmark_results_pass_at_K_accuracy.txt
    # 3. 计算均值、标准差、最小值、最大值
```

### 使用方式

```bash
python evaluators/calculate_average_score.py logs/browsecomp/experiment1
```

### 输出示例

```
Pass@1 Results:
Number of runs: 3
Individual scores: ['85.20%', '86.10%', '84.50%']
Standard deviation: 0.80%
Average score: 85.27%
```

---

## `extract_futurex_results.py` -- FutureX 多数投票聚合

### 文件概述

专为 FutureX 基准测试设计的结果聚合工具，使用**多数投票**（majority voting）从多次运行中选出最佳答案。

### 核心逻辑

```python
def majority_vote(preds, first_seen_order):
    # 投票规则（确定性）：
    # 1. 频率最高的答案胜出
    # 2. 频率相同 → 选择最早出现的答案
    # 3. 仍然相同 → 字典序排序
```

### 使用方式

```bash
python evaluators/extract_futurex_results.py logs/futurex/experiment1
# 输出: logs/futurex/experiment1/futurex_submission.jsonl
```

### 输出格式

```json
{"id": "task_abc123", "prediction": "The answer is ..."}
```

---

## 核心类/函数表格

| 文件 | 函数/类 | 说明 |
|---|---|---|
| `eval_utils.py` | `verify_answer_simpleqa()` | 通用三分类 LLM Judge |
| `eval_utils.py` | `verify_answer_hle()` | HLE 结构化 LLM Judge |
| `eval_utils.py` | `verify_answer_gaia()` | GAIA 规则匹配评估 |
| `eval_utils.py` | `verify_answer_gaia_validation_text_103()` | GAIA-Text-103 等价性 LLM Judge |
| `eval_utils.py` | `verify_answer_browsecomp()` | BrowseComp 英文 LLM Judge |
| `eval_utils.py` | `verify_answer_browsecomp_zh()` | BrowseComp 中文 LLM Judge |
| `eval_utils.py` | `verify_answer_xbench_deepsearch()` | XBench 中文 LLM Judge |
| `eval_utils.py` | `verify_answer_deepsearchqa()` | DeepSearchQA JSON 结构化 LLM Judge |
| `eval_utils.py` | `verify_answer_for_datasets()` | 统一调度入口 |
| `calculate_average_score.py` | `calculate_average_scores()` | 多运行平均分统计 |
| `extract_futurex_results.py` | `majority_vote()` | 多数投票决策 |
| `extract_futurex_results.py` | `discover_runs()` | 自动发现运行目录 |

## 与其他模块的关系

- **`common_benchmark.py`**：`run_single_task()` 调用 `verify_answer_for_datasets()` 进行答案验证。
- **`check_progress/check_progress_deepsearchqa.py`**：使用与 `verify_answer_deepsearchqa()` 相同的指标计算逻辑。
- **`subset_extraction/gaia-text-103-grader.py`**：直接导入 `verify_answer_gaia_validation_text_103()` 进行评分。
- **外部依赖**：需要 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 环境变量来调用评判模型。

## 总结

评估器模块实现了"一个入口，多种策略"的设计。`eval_utils.py` 通过统一调度函数将 8 种评估方式封装在一个接口后面，调用方无需关心具体评判逻辑。评判方式从纯规则匹配（GAIA）到结构化 JSON 输出（DeepSearchQA）覆盖了不同复杂度。辅助工具提供了多运行统计和投票聚合能力。

# `summary_time_cost.py` — 基准测试结果汇总统计

## 文件概述

`summary_time_cost.py` 负责在基准测试（Benchmark）完成后，汇总所有任务的执行日志，计算时间消耗和工具使用量的统计数据。它读取日志目录中的所有 JSON 文件，生成一份 `summary_time_cost.json` 汇总报告。

在项目中，它在基准测试批量运行结束后被调用，为评估智能体性能提供量化数据。

## 关键代码解读

### 汇总数据模板

```python
def _get_summary_template():
    return {
        "total_tasks": 0,
        "total_wall_time": 0.0,
        "primary_breakdown": {
            "main_agent": defaultdict(float),
            "browsing_agent": defaultdict(float),
        },
        "cross_cutting_breakdown": defaultdict(float),
        "tool_workload_breakdown": defaultdict(float),
    }
```

**解释**：

- `total_tasks`：处理的任务总数
- `total_wall_time`：所有任务的总墙钟时间
- `primary_breakdown`：按智能体类型（主智能体 / 浏览智能体）分解的时间
- `cross_cutting_breakdown`：跨智能体的横向指标（如 LLM 调用总时间、工具调用总时间）
- `tool_workload_breakdown`：按工具类型分解的工作量

使用 `defaultdict(float)` 使得可以直接累加数值而不需要预先初始化所有键。

### 数据更新

```python
def _update_summary_data(summary_block, perf_summary, tool_workload):
    summary_block["total_tasks"] += 1
    summary_block["total_wall_time"] += perf_summary.get("total_wall_time", 0.0)

    primary_breakdown = perf_summary.get("primary_breakdown", {})
    for agent, data in primary_breakdown.items():
        if agent in summary_block["primary_breakdown"]:
            for key, value in data.items():
                summary_block["primary_breakdown"][agent][key] += value

    cross_cutting_breakdown = perf_summary.get("cross_cutting_breakdown", {})
    for key, value in cross_cutting_breakdown.items():
        summary_block["cross_cutting_breakdown"][key] += value

    for key, value in tool_workload.items():
        summary_block["tool_workload_breakdown"][key] += value
```

**解释**：

- 将单个任务的性能数据累加到汇总块中
- 递归累加所有数值字段
- 同一个函数同时用于全局汇总和按评判结果分组的汇总

### 平均值计算

```python
def _calculate_averages(summary_block):
    num_tasks = summary_block["total_tasks"]
    if num_tasks == 0: return

    summary_block["average_wall_time"] = summary_block["total_wall_time"] / num_tasks

    for agent, data in summary_block["primary_breakdown"].items():
        avg_data = {f"avg_{k}": v / num_tasks for k, v in data.items()}
        summary_block["primary_breakdown"][agent].update(avg_data)
    # ... 对其他分解维度做同样的处理 ...
```

**解释**：

- 为所有数值字段计算平均值，键名前缀加 `avg_`
- 总量和平均值都保留在同一个数据结构中

### 主函数

```python
def generate_summary(log_dir: Path):
    results = []
    for log_file in log_dir.glob("*.json"):
        if log_file.name == "summary.json": continue
        with open(log_file, "r", encoding="utf-8") as f:
            results.append(json.load(f))

    overall_summary = _get_summary_template()
    summary_by_judge = defaultdict(_get_summary_template)

    for result in results:
        trace_data = result.get("trace_data")
        if not trace_data or "performance_summary" not in trace_data: continue

        perf_summary = trace_data["performance_summary"]
        tool_workload = trace_data.get("tool_workload_breakdown", {})

        _update_summary_data(overall_summary, perf_summary, tool_workload)

        judge_result = result.get("final_judge_result", "unknown")
        _update_summary_data(summary_by_judge[judge_result], perf_summary, tool_workload)

    _calculate_averages(overall_summary)
    for judge_result in summary_by_judge:
        _calculate_averages(summary_by_judge[judge_result])

    summary_data = {
        "overall_summary": overall_summary,
        "summary_by_final_judge_result": dict(summary_by_judge),
    }

    summary_file = log_dir / "summary_time_cost.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=4, ensure_ascii=False)
```

**解释**：

- 遍历日志目录中所有 JSON 文件（跳过已有的 `summary.json`）
- 同时维护两个维度的统计：全局汇总 和 按评判结果（如 "correct"/"incorrect"/"unknown"）分组
- 最终输出 `summary_time_cost.json`

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `generate_summary(log_dir)` | 函数 | 主入口，读取日志文件并生成汇总统计 |
| `_get_summary_template()` | 函数 | 创建空的汇总数据结构模板 |
| `_update_summary_data(block, perf, workload)` | 函数 | 将单个任务的数据累加到汇总块 |
| `_calculate_averages(block)` | 函数 | 为汇总块计算所有字段的平均值 |

## 与其他模块的关系

- **`task_logger.py`**：读取 `TaskLog.save()` 输出的 JSON 文件中的 `trace_data` 字段
- **基准测试运行脚本**：在批量任务完成后调用 `generate_summary()`
- **`apps/visualize-trace/`**：可以读取生成的汇总文件进行可视化

## 总结

`summary_time_cost.py` 是基准测试分析流程的最后一环。它将分散在各个任务日志中的性能数据汇总为一份紧凑的统计报告，支持按全局和按评判结果两个维度分析。这对于比较不同智能体配置的效率、发现性能瓶颈非常有价值。

# `config.yaml` -- Hydra 主配置文件

## 文件概述

`config.yaml` 是 MiroThinker 整个配置系统的**根文件**。它通过 Hydra 的 `defaults` 列表机制，将三大子配置组（LLM、Agent、Benchmark）组合在一起，形成一个完整的运行时配置。文件本身极短（仅 14 行），因为具体参数全部定义在子配置目录中。

## 关键配置解读

```yaml
defaults:
  - llm: default
  - agent: default
  - benchmark: default
  - _self_
```

**`defaults` 列表**是 Hydra 配置系统的核心机制：

| 条目 | 含义 |
|---|---|
| `llm: default` | 从 `conf/llm/default.yaml` 加载 LLM 配置（默认使用 Anthropic Claude 3.7） |
| `agent: default` | 从 `conf/agent/default.yaml` 加载智能体配置（工具列表、子智能体、上下文管理） |
| `benchmark: default` | 从 `conf/benchmark/default.yaml` 加载基准测试配置（数据路径、执行参数） |
| `_self_` | 当前文件中定义的变量优先级最低，会被子配置覆盖 |

**顶层参数**：

```yaml
hydra:
  run:
    dir: ../../logs/debug

project_name: "miroflow-agent"
debug_dir: "../../logs/debug"
```

- `hydra.run.dir`：Hydra 的工作目录（日志和输出文件存放位置）。
- `project_name`：项目标识符。
- `debug_dir`：调试日志目录，会传递给 `execute_task_pipeline` 作为 `log_dir` 参数。

## 命令行覆盖示例

Hydra 支持通过命令行参数覆盖任意配置项：

```bash
# 使用 Claude 3.7 模型 + MiroThinker v1.5 智能体 + BrowseComp 基准测试
python main.py llm=claude-3-7 agent=mirothinker_v1.5 benchmark=browsecomp

# 覆盖单个参数
python main.py llm.temperature=0.5 agent.main_agent.max_turns=100

# 运行基准测试
python benchmarks/common_benchmark.py benchmark=hle agent=mirothinker_v1.5_keep5_max200
```

## 配置合并优先级

Hydra 合并配置时遵循以下优先级（从低到高）：

1. 子配置中的 `defaults`（如 `agent/default.yaml`）
2. 子配置中显式定义的值
3. `config.yaml` 中的顶层值
4. 命令行参数（最高优先级）

## 与其他模块的关系

```
config.yaml
  ├── llm/default.yaml         # LLM 提供商与模型参数
  ├── agent/default.yaml       # 智能体工具与行为配置
  ├── benchmark/default.yaml   # 基准测试数据与执行参数
  ├── main.py                  # @hydra.main(config_name="config")
  └── benchmarks/common_benchmark.py  # @hydra.main(config_name="config")
```

## 总结

`config.yaml` 是一个极简的"配置路由器"，它本身不定义具体参数，而是通过 `defaults` 列表将 LLM、Agent、Benchmark 三个子配置组合在一起。用户可以通过命令行参数灵活切换任意子配置，实现不同实验设置的快速组合。

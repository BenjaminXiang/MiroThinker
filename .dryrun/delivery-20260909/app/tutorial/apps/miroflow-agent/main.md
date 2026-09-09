# `main.py` -- MiroThinker 智能体的程序入口

## 文件概述

`main.py` 是 MiroThinker 智能体框架（miroflow-agent 应用）的**主入口文件**。它的职责非常单一：读取 Hydra 配置，初始化流水线（pipeline）组件，然后执行一个示例任务。整个文件仅有约 54 行代码，体现了"入口文件只做编排，不做业务逻辑"的设计思想。

## 关键代码解读

### 1. 导入与日志初始化（第 1-17 行）

```python
import asyncio
import hydra
from omegaconf import DictConfig, OmegaConf

from src.core.pipeline import (
    create_pipeline_components,
    execute_task_pipeline,
)
from src.logging.task_logger import bootstrap_logger

logger = bootstrap_logger()
```

- **Hydra + OmegaConf**：Hydra 是 Facebook 开发的配置管理框架，OmegaConf 是其底层的配置对象库。Hydra 会在运行时自动从 `conf/` 目录加载 YAML 配置，合并为一个 `DictConfig` 对象传给主函数。
- **pipeline 模块**：`create_pipeline_components` 负责创建工具管理器和输出格式化器；`execute_task_pipeline` 负责执行单个任务的完整流水线（包括多轮推理、工具调用、答案生成等）。
- **bootstrap_logger()**：初始化全局日志系统，后续所有模块共用此 logger。

### 2. 异步主函数 `amain()`（第 20-45 行）

```python
async def amain(cfg: DictConfig) -> None:
    logger.info(OmegaConf.to_yaml(cfg))

    main_agent_tool_manager, sub_agent_tool_managers, output_formatter = (
        create_pipeline_components(cfg)
    )

    task_id = "task_example"
    task_description = "What is the title of today's arxiv paper in computer science?"
    task_file_name = ""

    final_summary, final_boxed_answer, log_file_path, _ = await execute_task_pipeline(
        cfg=cfg,
        task_id=task_id,
        task_file_name=task_file_name,
        task_description=task_description,
        main_agent_tool_manager=main_agent_tool_manager,
        sub_agent_tool_managers=sub_agent_tool_managers,
        output_formatter=output_formatter,
        log_dir=cfg.debug_dir,
    )
```

执行流程分三步：

1. **打印配置**：将完整的 Hydra 配置以 YAML 格式输出到日志，便于调试和复现。
2. **创建流水线组件**：根据配置创建主智能体工具管理器（`main_agent_tool_manager`）、子智能体工具管理器字典（`sub_agent_tool_managers`）和输出格式化器（`output_formatter`）。
3. **执行任务**：调用 `execute_task_pipeline`，传入任务 ID、任务描述、文件路径等参数。该函数返回四个值：最终摘要、最终答案（boxed 格式）、日志文件路径，以及一个额外返回值（此处忽略）。

### 3. Hydra 入口装饰器（第 48-54 行）

```python
@hydra.main(config_path="conf", config_name="config", version_base=None)
def main(cfg: DictConfig) -> None:
    asyncio.run(amain(cfg))

if __name__ == "__main__":
    main()
```

- `@hydra.main` 装饰器告诉 Hydra：配置文件目录为 `conf/`，主配置文件为 `config.yaml`。
- Hydra 会自动解析命令行参数，支持通过 `+agent=mirothinker_v1.5` 等方式覆盖默认配置。
- `asyncio.run()` 将异步函数包装为同步入口。

## 核心函数/组件表格

| 函数/组件 | 所在模块 | 作用 |
|---|---|---|
| `bootstrap_logger()` | `src.logging.task_logger` | 初始化全局日志系统 |
| `create_pipeline_components(cfg)` | `src.core.pipeline` | 根据配置创建工具管理器和格式化器 |
| `execute_task_pipeline(...)` | `src.core.pipeline` | 执行单个任务的完整推理流水线 |
| `@hydra.main(...)` | `hydra` | Hydra 配置入口装饰器 |

## 与其他模块的关系

```
main.py
  ├── conf/config.yaml          # Hydra 从此加载配置（含 llm、agent、benchmark 三大子配置）
  ├── src/core/pipeline.py      # 流水线核心逻辑（组件创建 + 任务执行）
  ├── src/logging/task_logger.py # 日志初始化
  └── src/config/settings.py    # 工具定义与 MCP 服务器配置
```

- `main.py` 是**用户直接运行的脚本**，适用于单任务快速测试。
- 如果需要**批量运行基准测试**，应使用 `benchmarks/common_benchmark.py` 中的 `run_benchmark()` 入口（它有自己的 `@hydra.main` 装饰器）。
- 配置系统通过 Hydra 的 `defaults` 机制实现分层覆盖，详见 `conf/config.yaml` 文档。

## 总结

`main.py` 是一个极简的入口文件，核心做了三件事：初始化日志、创建流水线组件、执行示例任务。所有复杂逻辑都委托给 `src/core/pipeline` 模块。通过 Hydra 配置系统，用户可以在命令行灵活切换 LLM 提供商、智能体变体和基准测试，而无需修改代码。

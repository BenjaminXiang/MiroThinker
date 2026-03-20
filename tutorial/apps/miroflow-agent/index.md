# miroflow-agent — 核心 Agent 框架

miroflow-agent 是 MiroThinker 的核心应用，包含完整的深度研究 Agent 实现。

## 模块概览

| 模块 | 说明 |
|------|------|
| [main.py](main.md) | Hydra 入口点，启动异步任务执行 |
| [src/core/](src/core/index.md) | 核心编排引擎：Orchestrator、Pipeline、ToolExecutor |
| [src/llm/](src/llm/index.md) | LLM 客户端抽象与多提供商支持 |
| [src/config/](src/config/index.md) | 环境变量与 MCP 服务器配置 |
| [src/io/](src/io/index.md) | 输入处理与输出格式化 |
| [src/logging/](src/logging/index.md) | 任务日志与时间统计 |
| [src/utils/](src/utils/index.md) | 解析、提示词、包装器工具函数 |
| [conf/](conf/index.md) | Hydra 配置文件（Agent/Benchmark/LLM） |
| [benchmarks/](benchmarks/index.md) | 基准测试评估系统 |

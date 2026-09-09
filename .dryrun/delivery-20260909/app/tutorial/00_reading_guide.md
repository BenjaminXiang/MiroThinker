# MiroThinker 源码阅读指南

本文档提供三条不同深度的阅读路径，帮助你根据自身目标和时间选择最合适的方式学习 MiroThinker 源码。

---

## 目录

1. [前置准备](#前置准备)
2. [快速入门路径（约 2 小时）](#路径一快速入门约-2-小时)
3. [完整学习路径（约 1-2 周）](#路径二完整学习约-1-2-周)
4. [专题路径（按兴趣选择）](#路径三专题路径按兴趣选择)
5. [推荐模块阅读顺序及理由](#推荐模块阅读顺序及理由)
6. [完整文档索引](#完整文档索引)

---

## 前置准备

在开始阅读源码之前，请确保你：

- 已阅读 [背景知识](./00_background_knowledge.md)，理解深度研究 Agent、MCP、多 Agent 架构等核心概念
- 对 Python 异步编程（`async/await`）有基本了解
- 了解大语言模型（LLM）的基本使用方式（发送消息、接收回复、工具调用）

### 关键文件速查

| 你想了解的内容 | 直接看这个文件 |
|--------------|--------------|
| 程序从哪里开始运行 | `apps/miroflow-agent/main.py` |
| 一个任务如何被执行 | `apps/miroflow-agent/src/core/pipeline.py` |
| Agent 的核心循环逻辑 | `apps/miroflow-agent/src/core/orchestrator.py` |
| 工具是如何被调用的 | `apps/miroflow-agent/src/core/tool_executor.py` |
| 最终答案是如何生成的 | `apps/miroflow-agent/src/core/answer_generator.py` |
| MCP 工具管理 | `libs/miroflow-tools/src/miroflow_tools/manager.py` |
| LLM 客户端选择 | `apps/miroflow-agent/src/llm/factory.py` |
| 配置入口 | `apps/miroflow-agent/conf/config.yaml` |

---

## 路径一：快速入门（约 2 小时）

**目标**：理解 MiroThinker 的核心执行流程，能从头到尾跟踪一个用户查询如何变成最终答案。

### 步骤 1：入口 — `main.py`（15 分钟）

**文件**：`apps/miroflow-agent/main.py`

关注点：
- Hydra 如何加载配置（`@hydra.main` 装饰器）
- 配置对象 `cfg` 的结构
- `main()` 函数如何启动整个流程

阅读技巧：不要纠结于日志、异常处理等细节代码，聚焦于主干调用链。

### 步骤 2：流水线 — `pipeline.py`（30 分钟）

**文件**：`apps/miroflow-agent/src/core/pipeline.py`

关注点：
- `create_pipeline_components()` 函数：了解都创建了哪些组件
  - `ToolManager` 的初始化（MCP Server 连接）
  - `ClientFactory` 创建 LLM 客户端
  - `OutputFormatter` 的作用
- `execute_task_pipeline()` 函数：一个任务的完整执行过程
  - 组件如何被组装到一起
  - Orchestrator 在哪里被创建和调用

### 步骤 3：核心循环 — `orchestrator.py`（45 分钟）

**文件**：`apps/miroflow-agent/src/core/orchestrator.py`

这是最重要的文件，建议花最多时间在这里。

关注点：
- 主循环结构：LLM 调用 → 解析响应 → 工具执行 → 继续或结束
- 终止条件：什么时候 Agent 决定停止研究
- 子 Agent 委托：主 Agent 如何将任务分配给子 Agent
- 上下文管理：对话历史如何被维护和截断
- 流式处理：`StreamHandler` 如何处理实时输出

### 步骤 4：工具执行 — `tool_executor.py`（30 分钟）

**文件**：`apps/miroflow-agent/src/core/tool_executor.py`

关注点：
- `ToolExecutor` 类的核心方法
- 参数修正逻辑：LLM 输出的工具参数可能有格式问题，如何自动修正
- 去重检测：如何避免重复的搜索查询
- 错误处理和重试策略
- Demo 模式下的结果截断

### 阅读完成后你应该能回答

- [ ] 一个用户查询经过了哪些组件才变成最终答案？
- [ ] Agent 的多轮循环是在哪个函数中实现的？
- [ ] 子 Agent 和主 Agent 的交互方式是什么？
- [ ] 工具调用失败时会发生什么？

---

## 路径二：完整学习（约 1-2 周）

**目标**：全面掌握 MiroThinker 的设计与实现，具备修改和扩展框架的能力。

### 阶段 1：核心模块（第 1-3 天）

按快速入门路径完成核心模块阅读，但这次深入每个文件的完整代码：

| 顺序 | 模块 | 文件 |
|------|------|------|
| 1 | 入口 | `main.py` |
| 2 | 流水线 | `src/core/pipeline.py` |
| 3 | 调度器 | `src/core/orchestrator.py` |
| 4 | 工具执行 | `src/core/tool_executor.py` |
| 5 | 答案生成 | `src/core/answer_generator.py` |
| 6 | 流式处理 | `src/core/stream_handler.py` |

### 阶段 2：LLM 层（第 4-5 天）

| 顺序 | 文件 | 关注点 |
|------|------|--------|
| 7 | `src/llm/base_client.py` | 抽象接口定义 |
| 8 | `src/llm/factory.py` | 工厂模式与 provider 路由 |
| 9 | `src/llm/providers/anthropic_client.py` | Anthropic API 的具体对接 |
| 10 | `src/llm/providers/openai_client.py` | OpenAI API 的具体对接 |
| 11 | `src/llm/util.py` | 通用工具函数 |

### 阶段 3：工具层（第 6-8 天）

| 顺序 | 文件 | 关注点 |
|------|------|--------|
| 12 | `libs/miroflow-tools/src/miroflow_tools/manager.py` | MCP 连接管理与工具路由 |
| 13 | `libs/miroflow-tools/.../serper_mcp_server.py` | 搜索工具实现 |
| 14 | `libs/miroflow-tools/.../browser_session.py` | 浏览器自动化 |
| 15 | `libs/miroflow-tools/.../python_mcp_server.py` | 代码执行沙箱 |
| 16 | 其他 MCP Server | 按兴趣选读 |

### 阶段 4：配置与辅助（第 9-10 天）

| 顺序 | 目录/文件 | 关注点 |
|------|-----------|--------|
| 17 | `conf/config.yaml` | 主配置结构 |
| 18 | `conf/agent/*.yaml` | Agent 变体配置对比 |
| 19 | `conf/llm/*.yaml` | LLM 提供商参数 |
| 20 | `conf/benchmark/*.yaml` | 基准测试配置 |
| 21 | `src/config/settings.py` | 环境变量与 MCP Server 注册 |
| 22 | `src/io/` | 输入处理与输出格式化 |
| 23 | `src/utils/` | 解析工具、Prompt 工具等 |
| 24 | `src/logging/` | 日志记录与任务追踪 |

### 阶段 5：周边应用（可选）

| 应用 | 路径 | 用途 |
|------|------|------|
| collect-trace | `apps/collect-trace/` | 训练数据采集，转化为 SFT/DPO 格式 |
| gradio-demo | `apps/gradio-demo/` | 本地 Web 演示界面 |
| visualize-trace | `apps/visualize-trace/` | Agent 推理过程可视化 |
| lobehub-compatibility | `apps/lobehub-compatibility/` | LobeChat 集成适配 |

---

## 路径三：专题路径（按兴趣选择）

如果你只对某个特定方面感兴趣，可以直接跳到对应专题。

### 专题 A：LLM 集成与 Provider 开发

适合：想要接入新的 LLM 提供商的开发者。

```
阅读顺序：
1. src/llm/base_client.py        → 理解接口约定
2. src/llm/providers/openai_client.py  → 参考实现
3. src/llm/providers/anthropic_client.py → 对比两种实现的差异
4. src/llm/factory.py            → 了解注册与路由机制
5. conf/llm/*.yaml               → 配置格式
```

### 专题 B：工具开发与 MCP Server

适合：想要为 MiroThinker 添加新工具的开发者。

```
阅读顺序：
1. libs/miroflow-tools/.../manager.py       → 工具管理全局视角
2. libs/miroflow-tools/.../serper_mcp_server.py → 最简单的 MCP Server 示例
3. libs/miroflow-tools/.../python_mcp_server.py → 稍复杂的示例（带沙箱）
4. libs/miroflow-tools/.../browser_session.py   → 有状态工具的实现
5. src/config/settings.py                        → 如何注册新的 MCP Server
```

### 专题 C：基准测试与评估

适合：想要在新基准上评估 MiroThinker 或理解评估流程的研究者。

```
阅读顺序：
1. conf/benchmark/*.yaml          → 各基准的配置格式
2. conf/config.yaml               → 基准配置如何与主配置组合
3. main.py                        → 批量任务执行入口
4. src/core/pipeline.py           → 单任务执行流程
5. src/logging/task_logger.py     → 日志格式（用于结果分析）
```

### 专题 D：多 Agent 协作机制

适合：对层级 Agent 架构感兴趣的研究者。

```
阅读顺序：
1. conf/agent/multi_agent.yaml    → 多 Agent 配置结构
2. conf/agent/single_agent.yaml   → 对比单 Agent 配置
3. src/config/settings.py         → expose_sub_agents_as_tools 机制
4. src/core/orchestrator.py       → 子 Agent 委托与结果回收
5. src/core/tool_executor.py      → 子 Agent 调用的执行细节
```

### 专题 E：训练数据采集

适合：想用 MiroThinker 的运行轨迹训练自己模型的研究者。

```
阅读顺序：
1. apps/collect-trace/            → 数据采集应用
2. src/logging/task_logger.py     → 运行轨迹的记录格式
3. conf/benchmark/collect_trace.yaml → 采集模式的配置
```

---

## 推荐模块阅读顺序及理由

下面是按照依赖关系和理解难度排列的推荐顺序，适用于想要系统学习的读者：

| 优先级 | 模块 | 理由 |
|-------|------|------|
| 1 | `core/pipeline.py` | 入口函数，展示所有组件如何被创建和组装。先看全貌再看细节。 |
| 2 | `core/orchestrator.py` | 核心循环逻辑，理解它才能理解整个系统的行为。 |
| 3 | `core/tool_executor.py` | Orchestrator 的直接依赖，理解工具调用的完整生命周期。 |
| 4 | `core/answer_generator.py` | 循环的终点——如何从收集的上下文生成最终答案。 |
| 5 | `llm/base_client.py` + `llm/factory.py` | LLM 交互的抽象层，理解后可以忽略 provider 细节。 |
| 6 | `miroflow_tools/manager.py` | MCP 工具管理的核心，理解工具如何被发现和调用。 |
| 7 | `config/settings.py` | 连接配置与运行时的桥梁，理解环境变量和 MCP Server 注册。 |
| 8 | `conf/*.yaml` | 配置即文档，阅读配置文件能快速理解系统的可调参数和变体。 |
| 9 | 具体的 MCP Server | 按需阅读，每个 Server 相对独立，可以单独理解。 |
| 10 | 周边应用 | `collect-trace`、`gradio-demo` 等，理解生态但不影响核心理解。 |

---

## 完整文档索引

### 核心框架 (`apps/miroflow-agent/`)

| 模块 | 路径 | 说明 |
|------|------|------|
| 入口 | `main.py` | Hydra 启动入口 |
| Pipeline | `src/core/pipeline.py` | 任务流水线与组件工厂 |
| Orchestrator | `src/core/orchestrator.py` | 多轮对话调度与 Agent 协作 |
| ToolExecutor | `src/core/tool_executor.py` | 工具调用执行与错误处理 |
| AnswerGenerator | `src/core/answer_generator.py` | 最终答案生成与上下文管理 |
| StreamHandler | `src/core/stream_handler.py` | 流式输出事件管理 |

### LLM 层 (`apps/miroflow-agent/src/llm/`)

| 模块 | 路径 | 说明 |
|------|------|------|
| 基类 | `base_client.py` | LLM 客户端抽象接口 |
| 工厂 | `factory.py` | Provider 路由与客户端创建 |
| Anthropic | `providers/anthropic_client.py` | Claude 系列模型对接 |
| OpenAI | `providers/openai_client.py` | GPT 系列及兼容 API 对接 |
| 工具函数 | `util.py` | Token 计算等通用工具 |

### 工具层 (`libs/miroflow-tools/`)

| 模块 | 路径 | 说明 |
|------|------|------|
| ToolManager | `src/miroflow_tools/manager.py` | MCP Server 生命周期与工具路由 |
| Serper 搜索 | `src/miroflow_tools/mcp_servers/serper_mcp_server.py` | Google 搜索 |
| Google 搜索 | `src/miroflow_tools/mcp_servers/searching_google_mcp_server.py` | Google 搜索备选 |
| 搜狗搜索 | `src/miroflow_tools/mcp_servers/searching_sogou_mcp_server.py` | 中文搜索 |
| 浏览器 | `src/miroflow_tools/mcp_servers/browser_session.py` | Playwright 浏览器自动化 |
| 网页抓取 | `src/miroflow_tools/dev_mcp_servers/jina_scrape_llm_summary.py` | Jina 抓取与摘要 |
| Python 执行 | `src/miroflow_tools/mcp_servers/python_mcp_server.py` | E2B 沙箱代码执行 |
| 文档阅读 | `src/miroflow_tools/mcp_servers/reading_mcp_server.py` | 文档解析 |
| 推理 | `src/miroflow_tools/mcp_servers/reasoning_mcp_server.py` | 辅助推理 |
| 视觉 | `src/miroflow_tools/mcp_servers/vision_mcp_server.py` | 图像理解 |
| 音频 | `src/miroflow_tools/mcp_servers/audio_mcp_server.py` | 音频处理 |
| 任务规划 | `src/miroflow_tools/dev_mcp_servers/task_planner.py` | 任务分解 |

### 配置 (`apps/miroflow-agent/conf/`)

| 配置组 | 路径 | 说明 |
|--------|------|------|
| 主配置 | `conf/config.yaml` | 默认配置与配置组声明 |
| Agent 配置 | `conf/agent/` | 13 个 Agent 变体配置 |
| LLM 配置 | `conf/llm/` | Claude、GPT、Qwen 等 Provider 配置 |
| 基准测试 | `conf/benchmark/` | 17 个基准测试配置（BrowseComp, GAIA, HLE 等） |

### 辅助模块 (`apps/miroflow-agent/src/`)

| 模块 | 路径 | 说明 |
|------|------|------|
| 配置 | `config/settings.py` | 环境变量、MCP Server 参数注册 |
| 输入处理 | `io/input_handler.py` | 任务输入的预处理 |
| 输出格式化 | `io/output_formatter.py` | 结果输出格式化 |
| 日志 | `logging/task_logger.py` | 任务执行日志记录 |
| 解析工具 | `utils/parsing_utils.py` | LLM 响应解析 |
| Prompt 工具 | `utils/prompt_utils.py` | System Prompt 生成 |

### 周边应用 (`apps/`)

| 应用 | 路径 | 说明 |
|------|------|------|
| 数据采集 | `apps/collect-trace/` | Agent 轨迹采集，转 SFT/DPO 格式 |
| Web 演示 | `apps/gradio-demo/` | Gradio + vLLM 本地演示界面 |
| 轨迹可视化 | `apps/visualize-trace/` | Flask 仪表盘，分析推理过程 |
| LobeChat 适配 | `apps/lobehub-compatibility/` | LobeChat 集成 |

---

## 阅读建议

1. **先运行再读码**：如果条件允许，先按 README 配好环境跑一个简单 demo，对系统有直觉后再读源码会事半功倍。
2. **跟踪日志**：开启 debug 日志运行一个任务，对照日志输出阅读 `orchestrator.py` 的循环逻辑。
3. **对比配置**：把 `single_agent.yaml` 和 `multi_agent.yaml` 放在一起对比，理解配置差异如何影响运行时行为。
4. **画调用图**：阅读 `orchestrator.py` 时，自己画一个函数调用关系图，标注异步调用和回调。
5. **从测试入手**：`tests/` 目录下的测试用例是很好的使用示例，能帮你理解各模块的输入输出契约。

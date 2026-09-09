# `visualize-trace` -- 可视化仪表板

## 文件概述

`visualize-trace` 是一个基于 Flask 的 Web 应用，用于可视化分析 MiroThinker Agent 的运行轨迹（Trace）。它将 Agent 执行过程中的消息历史、工具调用、浏览器会话、性能指标等信息以交互式仪表板的形式展示，帮助开发者理解和调试 Agent 的推理过程。

## 架构概览

```
┌────────────────────────────────────────────────────────┐
│                   visualize-trace                       │
│                                                        │
│  ┌──────────────────────────────────────────────┐      │
│  │               前端 (浏览器)                   │      │
│  │                                              │      │
│  │  templates/index.html    页面结构 (Bootstrap) │      │
│  │  static/js/script.js     交互逻辑 + 渲染      │      │
│  │  static/css/style.css    样式定义             │      │
│  │                                              │      │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │      │
│  │  │基本信息 │ │执行摘要  │ │ 性能摘要     │  │      │
│  │  └─────────┘ └──────────┘ └──────────────┘  │      │
│  │  ┌────────┐  ┌──────────────────────────┐   │      │
│  │  │步骤导航│  │     执行流程面板          │   │      │
│  │  │(侧边栏)│  │  主Agent消息 + 工具调用   │   │      │
│  │  │        │  │  浏览器Agent子会话       │   │      │
│  │  └────────┘  └──────────────────────────┘   │      │
│  │  ┌───────────────┐ ┌────────────────────┐   │      │
│  │  │ Spans 统计    │ │ Step Logs 统计     │   │      │
│  │  └───────────────┘ └────────────────────┘   │      │
│  └──────────────────────┬───────────────────────┘      │
│                         │ REST API                     │
│  ┌──────────────────────┴───────────────────────┐      │
│  │               后端 (Flask)                    │      │
│  │                                              │      │
│  │  app.py             路由定义 + API 端点       │      │
│  │  trace_analyzer.py  Trace JSON 解析引擎      │      │
│  │  run.py             启动脚本                 │      │
│  └──────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────┘
```

## 目录结构

```
apps/visualize-trace/
├── app.py                  # Flask 应用（路由 + API）
├── run.py                  # 启动脚本（依赖检查 + 应用启动）
├── trace_analyzer.py       # Trace 分析引擎（核心解析逻辑）
├── templates/
│   └── index.html          # 页面模板（Bootstrap 布局）
├── static/
│   ├── css/style.css       # 样式表
│   └── js/script.js        # 前端交互逻辑
├── requirements.txt        # 依赖列表
└── pyproject.toml          # 项目配置
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 主页面 |
| `/api/list_files` | GET | 列出指定目录的 JSON 文件 |
| `/api/load_trace` | POST | 加载 Trace 文件 |
| `/api/basic_info` | GET | 获取任务基本信息 |
| `/api/performance_summary` | GET | 获取性能摘要 |
| `/api/execution_flow` | GET | 获取执行流程 |
| `/api/execution_summary` | GET | 获取执行统计 |
| `/api/spans_summary` | GET | 获取 Spans 统计 |
| `/api/step_logs_summary` | GET | 获取步骤日志统计 |
| `/api/debug/raw_messages` | GET | 获取原始消息数据 |

## 与其他模块的关系

- **输入来源**：读取 `apps/miroflow-agent/` 运行生成的 Trace JSON 文件。
- **独立部署**：无代码级依赖其他 MiroThinker 模块，仅依赖 Flask。
- **数据结构**：解析 Trace JSON 中的 `main_agent_message_history`、`sub_agent_message_history_sessions`、`trace_data`、`step_logs` 等字段。

## 总结

`visualize-trace` 是一个独立的调试工具，通过 Web 仪表板将 Agent 的执行过程可视化。它支持文件浏览器（指定目录浏览 JSON 文件）、执行流程逐步展示（包含工具调用和浏览器子会话）、以及多维度统计信息，是分析 Agent 行为和调试问题的核心工具。

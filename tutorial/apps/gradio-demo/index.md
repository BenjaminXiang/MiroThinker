# `gradio-demo` -- Web UI 演示应用

## 文件概述

`gradio-demo` 是 MiroThinker 的本地 Web 演示界面，基于 Gradio 框架构建。它允许用户通过浏览器与 MiroThinker Agent 进行交互式对话，支持实时流式输出、任务取消、深度研究模式切换，以及 vLLM 和 API 两种后端。

## 架构概览

```
┌──────────────────────────────────────────────┐
│                gradio-demo                    │
│                                              │
│  ┌────────────────────────────────────┐      │
│  │         main.py (主程序)           │      │
│  │                                    │      │
│  │  Gradio UI (ChatInterface)         │      │
│  │  ├── 聊天界面（流式输出）          │      │
│  │  ├── 配置面板（模型/API/模式）     │      │
│  │  └── 会话管理（新建/删除）         │      │
│  │                                    │      │
│  │  后端引擎：                        │      │
│  │  ├── MiroFlow Pipeline（深度研究） │      │
│  │  └── Direct LLM（普通对话）        │      │
│  └─────────────┬──────────────────────┘      │
│                │                             │
│  ┌─────────────┴──────────────────────┐      │
│  │      prompt_patch.py               │      │
│  │  Monkey Patching 系统提示词        │      │
│  │  ├── 注入 MiroThinker 身份         │      │
│  │  ├── 移除 \boxed{} 格式要求        │      │
│  │  ├── 替换总结提示词                │      │
│  │  └── 禁用格式检查重试             │      │
│  └────────────────────────────────────┘      │
│                                              │
│  ┌────────────────────────────────────┐      │
│  │      utils.py                      │      │
│  │  中文标点替换、语言检测等工具       │      │
│  └────────────────────────────────────┘      │
└──────────────────────────────────────────────┘
         │
         ▼
  apps/miroflow-agent/ (核心 Agent 框架)
```

## 目录结构

```
apps/gradio-demo/
├── main.py           # 主程序：Gradio UI + 后端逻辑
├── prompt_patch.py   # 提示词猴子补丁（适配 Demo 模式）
└── utils.py          # 文本处理工具函数
```

## 核心特性

1. **双模式运行**：深度研究模式（调用完整 MiroFlow Pipeline，使用 MCP 工具进行搜索和浏览）和普通对话模式（直接调用 LLM API）。
2. **实时流式输出**：通过 `AsyncGenerator` 实现流式 token 输出，包含 `<think>` 标签的思考过程显示。
3. **Monkey Patching**：通过 `prompt_patch.py` 在不修改核心代码的情况下定制 Demo 行为——注入品牌身份、调整输出格式。
4. **任务取消**：支持用户中途取消正在运行的研究任务，包含优雅的 MCP 服务器清理逻辑。
5. **多后端支持**：支持 vLLM 本地推理和外部 API 两种后端配置。

## 与其他模块的关系

- 直接依赖 `apps/miroflow-agent/` 的核心模块：`src.core.pipeline`、`src.config.settings`、`src.llm.providers` 等。
- 使用 `apps/miroflow-agent/conf/` 下的 Hydra 配置文件。
- 通过 Monkey Patching 修改 `miroflow-agent` 的运行时行为，而非修改源码。

## 总结

`gradio-demo` 是 MiroThinker 的用户交互前端，将核心 Agent 能力封装为易用的 Web 界面。它通过 Monkey Patching 巧妙地将面向基准测试的核心框架适配为面向用户的演示体验，是理解 MiroThinker 端到端能力的最佳入口。

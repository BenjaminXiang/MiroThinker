# mcp_servers -- 正式版 MCP 工具服务器

## 模块概述

`mcp_servers/` 目录包含 MiroThinker 的所有正式版 MCP 工具服务器。这些服务器各自封装一类能力（搜索、视觉、音频、推理、代码执行等），通过 MCP 协议向 `ToolManager` 暴露标准化的工具接口。

## 架构图

```
                    ToolManager (manager.py)
                           │
          ┌────────────────┼────────────────────────────┐
          │                │                            │
    ┌─────▼─────┐   ┌─────▼─────┐               ┌─────▼─────┐
    │ Stdio 连接 │   │ SSE 连接  │               │ 持久会话  │
    │(本地进程)  │   │(远程HTTP) │               │(Playwright)│
    └─────┬─────┘   └─────┬─────┘               └─────┬─────┘
          │                │                            │
    ┌─────▼──────────────────────────────────┐   ┌─────▼─────────┐
    │            MCP 服务器群                  │   │browser_session│
    │                                        │   │  .py          │
    │  搜索类:                                │   └───────────────┘
    │  ├─ searching_google_mcp_server.py     │
    │  │   └─ (嵌套调用) serper_mcp_server   │
    │  └─ searching_sogou_mcp_server.py      │
    │                                        │
    │  多模态类:                              │
    │  ├─ vision_mcp_server.py (OpenAI)      │
    │  ├─ vision_mcp_server_os.py (自部署)   │
    │  ├─ audio_mcp_server.py (OpenAI)       │
    │  └─ audio_mcp_server_os.py (自部署)    │
    │                                        │
    │  计算类:                                │
    │  ├─ python_mcp_server.py (E2B 沙箱)    │
    │  └─ reading_mcp_server.py (文档转换)   │
    │                                        │
    │  推理类:                                │
    │  ├─ reasoning_mcp_server.py (Claude)   │
    │  └─ reasoning_mcp_server_os.py (自部署)│
    │                                        │
    │  工具函数:                              │
    │  └─ utils/url_unquote.py               │
    └────────────────────────────────────────┘
```

## 服务器分类

### 搜索与抓取

| 文件 | 工具 | 后端服务 | 文档 |
|------|------|----------|------|
| `searching_google_mcp_server.py` | `google_search`, `scrape_website` | Serper API, Jina AI | [详情](searching_google_mcp_server.md) |
| `searching_sogou_mcp_server.py` | `sogou_search`, `scrape_website` | 腾讯云 SearchPro, Jina AI | [详情](searching_sogou_mcp_server.md) |
| `serper_mcp_server.py` | `google_search` | Serper API（底层） | [详情](serper_mcp_server.md) |

### 多模态感知

| 文件 | 工具 | 后端服务 | 文档 |
|------|------|----------|------|
| `vision_mcp_server.py` | `visual_question_answering` | OpenAI GPT-4o | [详情](vision_mcp_server.md) |
| `vision_mcp_server_os.py` | `visual_question_answering` | 自部署 VLM | [详情](vision_mcp_server_os.md) |
| `audio_mcp_server.py` | `audio_transcription`, `audio_question_answering` | OpenAI gpt-4o-transcribe/audio-preview | [详情](audio_mcp_server.md) |
| `audio_mcp_server_os.py` | `audio_transcription` | 自部署 Whisper | [详情](audio_mcp_server_os.md) |

### 计算与文档

| 文件 | 工具 | 后端服务 | 文档 |
|------|------|----------|------|
| `python_mcp_server.py` | `create_sandbox`, `run_python_code`, `run_command`, 文件传输 | E2B 沙箱 | [详情](python_mcp_server.md) |
| `reading_mcp_server.py` | `convert_to_markdown` | markitdown-mcp | [详情](reading_mcp_server.md) |

### 推理增强

| 文件 | 工具 | 后端服务 | 文档 |
|------|------|----------|------|
| `reasoning_mcp_server.py` | `reasoning` | Anthropic Claude 3.7 Sonnet（扩展思考） | [详情](reasoning_mcp_server.md) |
| `reasoning_mcp_server_os.py` | `reasoning` | 自部署推理模型 | [详情](reasoning_mcp_server_os.md) |

### 会话管理

| 文件 | 用途 | 文档 |
|------|------|------|
| `browser_session.py` | 维护持久化的 Playwright 浏览器 MCP 会话 | [详情](browser_session.md) |

### 工具函数

| 文件 | 用途 | 文档 |
|------|------|------|
| `utils/url_unquote.py` | 安全 URL 解码、字典递归解码、Markdown 链接剥离 | [详情](utils/url_unquote.md) |

## 标准版与开源版对照

| 功能 | 标准版（商业 API） | 开源版（自部署） |
|------|-------------------|-----------------|
| 视觉问答 | `vision_mcp_server.py` (GPT-4o) | `vision_mcp_server_os.py` (自定义 VLM) |
| 音频处理 | `audio_mcp_server.py` (OpenAI) | `audio_mcp_server_os.py` (自定义 Whisper) |
| 深度推理 | `reasoning_mcp_server.py` (Claude) | `reasoning_mcp_server_os.py` (自定义模型) |

通过 Hydra 配置系统，可以在不修改代码的情况下切换使用标准版或开源版。

## 环境变量汇总

| 变量名 | 用途 | 使用文件 |
|--------|------|----------|
| `SERPER_API_KEY` | Google 搜索 API | searching_google, serper |
| `JINA_API_KEY` | 网页抓取 API | searching_google, searching_sogou |
| `OPENAI_API_KEY` | OpenAI 服务 | audio, vision |
| `ANTHROPIC_API_KEY` | Anthropic 服务 | reasoning |
| `E2B_API_KEY` | E2B 沙箱 | python_mcp_server |
| `TENCENTCLOUD_SECRET_ID/KEY` | 腾讯云搜索 | searching_sogou |
| `WHISPER_API_KEY/BASE_URL/MODEL_NAME` | 自部署 Whisper | audio_os |
| `VISION_API_KEY/BASE_URL/MODEL_NAME` | 自部署 VLM | vision_os |
| `REASONING_API_KEY/BASE_URL/MODEL_NAME` | 自部署推理模型 | reasoning_os |

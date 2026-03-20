# `audio_mcp_server.py` -- 音频处理 MCP 服务器（OpenAI 版）

## 文件概述

这个文件实现了一个基于 FastMCP 框架的音频处理服务器，提供两个核心工具：音频转录（speech-to-text）和音频问答。底层调用 OpenAI 的 `gpt-4o-transcribe` 和 `gpt-4o-audio-preview` 模型。在 MiroThinker 项目中，当 Agent 遇到需要理解音频内容的任务时（如播客内容提取、语音文件分析），会通过 ToolManager 调用此服务器。

## 关键代码解读

### 1. 音频格式识别

```python
def _get_audio_extension(url: str, content_type: str = None) -> str:
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()
    audio_extensions = [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"]
    for ext in audio_extensions:
        if path.endswith(ext):
            return ext
    # 如果 URL 中没有扩展名，尝试从 HTTP Content-Type 头推断
    if content_type:
        if "mp3" in content_type or "mpeg" in content_type:
            return ".mp3"
        # ... 其他格式
    return ".mp3"  # 默认回退到 mp3
```

这个辅助函数通过两种策略判断音频格式：先看 URL 路径中的文件扩展名，再看 HTTP 响应头中的 Content-Type。这在从网络下载音频时很重要，因为临时文件需要正确的扩展名才能被音频处理库识别。

### 2. 音频时长获取

```python
def _get_audio_duration(audio_path: str) -> float:
    try:
        with contextlib.closing(wave.open(audio_path, "rb")) as f:
            frames = f.getnframes()
            rate = f.getframerate()
            duration = frames / float(rate)
    except Exception:
        pass
    # 回退到 mutagen 库处理 mp3 等格式
    audio = MutagenFile(audio_path)
```

采用双重策略获取时长：先用 Python 标准库 `wave` 处理 WAV 文件（速度快），失败后用 `mutagen` 库处理 mp3 等压缩格式。

### 3. 音频转录工具

```python
@mcp.tool()
async def audio_transcription(audio_path_or_url: str) -> str:
```

核心流程：
- 判断输入是本地文件路径还是 URL
- 如果是 URL，下载到临时文件后再处理
- 检测沙箱路径（`home/user`），返回错误提示
- 调用 OpenAI 的 `gpt-4o-transcribe` 模型进行转录
- 带有指数退避重试机制（最多 3 次）

### 4. 音频问答工具

```python
@mcp.tool()
async def audio_question_answering(audio_path_or_url: str, question: str) -> str:
```

与转录不同，问答工具将音频编码为 base64 后，连同问题一起发送给 `gpt-4o-audio-preview` 多模态模型。返回结果中附带音频时长信息。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `_get_audio_extension` | 函数 | 从 URL 或 Content-Type 推断音频文件扩展名 |
| `_get_audio_duration` | 函数 | 获取音频文件时长（秒） |
| `_encode_audio_file` | 函数 | 将音频文件编码为 base64 字符串并确定格式 |
| `audio_transcription` | MCP 工具 | 将音频转录为文本 |
| `audio_question_answering` | MCP 工具 | 基于音频内容回答问题 |

## 与其他模块的关系

- **被 `ToolManager` 管理**：作为 stdio 进程启动，ToolManager 通过 MCP 协议与之通信
- **依赖 OpenAI API**：需要 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 环境变量
- **对比 `audio_mcp_server_os.py`**：本文件使用 OpenAI 官方 API，`_os` 版本使用自定义 Whisper 端点，功能更精简（仅转录，无问答）

## 总结

`audio_mcp_server.py` 通过 FastMCP 框架暴露了两个音频相关工具。它能处理本地文件和远程 URL，自动识别音频格式，并通过 OpenAI 多模态模型实现转录和问答功能。重试机制和沙箱路径检测确保了可靠性和安全性。

# `audio_mcp_server_os.py` -- 音频处理 MCP 服务器（开源/自部署版）

## 文件概述

这个文件是 `audio_mcp_server.py` 的开源替代版本。它使用自部署的 Whisper 模型端点（而非 OpenAI 官方 API）进行音频转录，适用于不方便或不想使用 OpenAI 服务的场景。文件名中的 `_os` 代表 "open source"。与标准版相比，此版本仅提供转录功能，不提供音频问答功能。

## 关键代码解读

### 1. 环境变量配置

```python
WHISPER_API_KEY = os.environ.get("WHISPER_API_KEY")
WHISPER_BASE_URL = os.environ.get("WHISPER_BASE_URL")
WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL_NAME")
```

三个环境变量指向自部署的 Whisper 兼容 API 端点。这意味着你可以使用任何兼容 OpenAI Audio API 格式的 Whisper 服务（如 faster-whisper-server、whisper.cpp 的 API 封装等）。

### 2. 与标准版的核心差异

```python
client = OpenAI(base_url=WHISPER_BASE_URL, api_key=WHISPER_API_KEY)
transcription = client.audio.transcriptions.create(
    model=WHISPER_MODEL_NAME, file=audio_file
)
```

虽然仍使用 `openai` Python 库，但 `base_url` 指向自定义端点，模型名称也由环境变量控制。这利用了 OpenAI 客户端库的兼容性——许多开源 Whisper 服务器都实现了相同的 API 格式。

### 3. 额外的内容类型验证

```python
if content_type and not any(
    media_type in content_type
    for media_type in ["audio", "video", "application/octet-stream"]
):
    return f"[ERROR]: Audio transcription failed: Invalid content type '{content_type}'."
```

相比标准版，开源版增加了对下载文件内容类型的严格验证，在发送到 Whisper 服务之前拦截明显的非音频文件。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `_get_audio_extension` | 函数 | 从 URL 或 Content-Type 推断音频文件扩展名 |
| `_get_audio_duration` | 函数 | 获取音频文件时长（秒） |
| `_encode_audio_file` | 函数 | 将音频文件编码为 base64 字符串 |
| `audio_transcription` | MCP 工具 | 使用自部署 Whisper 将音频转录为文本 |

## 与其他模块的关系

- **与 `audio_mcp_server.py` 互为替代**：两者提供相同的 MCP 工具接口（`audio_transcription`），但后端不同
- **被 ToolManager 管理**：通过 Hydra 配置选择使用哪个版本
- **需要自部署的 Whisper 服务**：通过 `WHISPER_BASE_URL` 指定端点地址

## 总结

`audio_mcp_server_os.py` 是音频转录工具的开源版本，将后端从 OpenAI API 替换为自部署 Whisper 服务。它保持了与标准版相同的 MCP 工具接口，使得在配置层面即可切换。功能上仅支持转录（不支持问答），但增加了更严格的输入验证。

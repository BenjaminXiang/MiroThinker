# `vision_mcp_server.py` -- 视觉问答 MCP 服务器（OpenAI 版）

## 文件概述

`vision_mcp_server.py` 提供了视觉问答（Visual Question Answering）工具，能分析图片和视频并回答相关问题。底层使用 OpenAI 的 GPT-4o 多模态模型。支持多种图片格式（jpg/png/gif/webp/bmp/tiff）和视频格式（mp4/mov/avi/mkv/webm），以及通过 URL 直接分析在线媒体。

## 关键代码解读

### 1. MIME 类型推断

```python
def guess_mime_media_type_from_extension(file_path: str) -> tuple[str, str]:
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    if ext in [".jpg", ".jpeg"]:
        return "image/jpeg", "image"
    elif ext == ".mp4":
        return "video/mp4", "video"
    # ...
    return "image/jpeg", "image"  # 默认
```

返回值是元组 `(MIME类型, 媒体类别)`，媒体类别用于后续区分文件大小限制。

### 2. 文件大小验证

```python
MAX_IMAGE_SIZE = 20 * 1024 * 1024   # 20MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024   # 50MB

def _validate_file_size(file_path, media_category):
    file_size = os.path.getsize(file_path)
    max_size = MAX_VIDEO_SIZE if media_category == "video" else MAX_IMAGE_SIZE
    if file_size > max_size:
        return False, f"[ERROR]: File size exceeds maximum..."
    if file_size == 0:
        return False, "[ERROR]: File is empty"
    return True, ""
```

在发送到 API 之前检查文件大小，避免上传过大的文件导致 API 错误或长时间等待。

### 3. 视觉问答工具

```python
@mcp.tool()
async def visual_question_answering(media_path_or_url: str, question: str) -> str:
    content = [{"type": "text", "text": question}]

    if os.path.exists(media_path_or_url):
        # 本地文件：读取 -> base64 编码 -> 嵌入请求
        with open(media_path_or_url, "rb") as media_file:
            media_data = base64.b64encode(media_file.read()).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{media_data}"}
        })
    else:
        # URL：直接传递给 API
        content.append({"type": "image_url", "image_url": {"url": media_path_or_url}})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": content}],
        max_tokens=1024,
    )
```

处理逻辑：
- **本地文件**：读取文件 -> base64 编码 -> 构造 data URI -> 嵌入多模态消息
- **URL**：直接将 URL 传递给 OpenAI API，由 API 端自行下载
- **沙箱路径检测**：如果路径包含 `home/user`（E2B 沙箱路径），返回错误提示

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `guess_mime_media_type_from_extension` | 函数 | 根据文件扩展名推断 MIME 类型和媒体类别 |
| `_validate_file_size` | 函数 | 验证文件大小是否在限制范围内 |
| `visual_question_answering` | MCP 工具 | 对图片/视频进行视觉问答 |

## 与其他模块的关系

- **被 ToolManager 管理**：作为 stdio MCP 服务器被调用
- **依赖 OpenAI API**：使用 GPT-4o 模型，需要 `OPENAI_API_KEY`
- **与 Python 沙箱配合**：沙箱中生成的图片需先下载到本地，才能被此工具分析
- **对比 `vision_mcp_server_os.py`**：本文件使用 OpenAI API，`_os` 版本使用自部署视觉模型

## 总结

`vision_mcp_server.py` 通过 GPT-4o 多模态模型为 Agent 提供了视觉理解能力。它支持 11 种图片/视频格式，能处理本地文件和在线 URL，并包含文件大小验证和沙箱路径检测等防护措施。

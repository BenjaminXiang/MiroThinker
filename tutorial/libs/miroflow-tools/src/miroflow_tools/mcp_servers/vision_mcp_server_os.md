# `vision_mcp_server_os.py` -- 视觉问答 MCP 服务器（开源/自部署版）

## 文件概述

这是 `vision_mcp_server.py` 的开源替代版本，使用自部署的视觉语言模型（VLM）代替 OpenAI GPT-4o。通过原始 HTTP 请求调用兼容 OpenAI Chat Completions 格式的自定义端点。功能上仅支持图片问答（不支持视频），且没有文件大小验证。

## 关键代码解读

### 1. 环境变量

```python
VISION_API_KEY = os.environ.get("VISION_API_KEY")
VISION_BASE_URL = os.environ.get("VISION_BASE_URL")
VISION_MODEL_NAME = os.environ.get("VISION_MODEL_NAME")
```

三个环境变量指向自部署的视觉模型端点，如 LLaVA、InternVL、Qwen-VL 等。

### 2. 三种输入处理

```python
if os.path.exists(image_path_or_url):
    # 方式1：本地文件 -> base64 编码
    image_data = base64.b64encode(image_file.read()).decode("utf-8")
    messages[0]["content"][0]["image_url"]["url"] = f"data:{mime_type};base64,{image_data}"
elif image_path_or_url.startswith(("http://", "https://")):
    # 方式2：URL -> 下载 -> base64 编码（使用 aiohttp 异步下载）
    async with aiohttp.ClientSession() as session:
        async with session.get(image_path_or_url) as resp:
            image_bytes = await resp.read()
            image_data = base64.b64encode(image_bytes).decode("utf-8")
else:
    # 方式3：直接作为 URL 传递
    messages[0]["content"][0]["image_url"]["url"] = image_path_or_url
```

与 OpenAI 版的关键区别：URL 输入时，开源版使用 `aiohttp` 在客户端下载图片后 base64 编码再发送。这是因为自部署模型通常不支持自动获取外部 URL。

### 3. 原始 HTTP 请求

```python
payload = {"model": VISION_MODEL_NAME, "messages": messages_for_llm}
response = requests.post(VISION_BASE_URL, json=payload, headers=headers)
```

不使用 OpenAI SDK，而是直接发送 HTTP POST 请求。这提供了更大的灵活性，兼容任何实现了 Chat Completions API 的视觉模型服务。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `guess_mime_media_type_from_extension` | 函数 | 根据文件扩展名推断 MIME 类型 |
| `visual_question_answering` | MCP 工具 | 使用自部署 VLM 进行图片问答 |

## 与其他模块的关系

- **与 `vision_mcp_server.py` 互为替代**：通过配置选择使用哪个版本
- **依赖 `aiohttp`**：用于异步下载网络图片
- **兼容 OpenAI Chat Completions 格式**：任何兼容此格式的 VLM API 均可使用

## 总结

`vision_mcp_server_os.py` 是视觉问答的自部署版本。相比 OpenAI 版，它在客户端完成图片下载和 base64 编码（使用 aiohttp 异步 HTTP 库），通过原始 HTTP 请求调用自定义 VLM 端点。功能更精简（仅图片问答），但部署灵活性更高。

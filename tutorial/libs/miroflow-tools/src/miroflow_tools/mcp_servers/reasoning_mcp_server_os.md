# `reasoning_mcp_server_os.py` -- 推理 MCP 服务器（开源/自部署版）

## 文件概述

这是 `reasoning_mcp_server.py` 的开源替代版本，使用自部署的推理模型（如 DeepSeek-R1、Qwen 等支持思考链的模型）代替 Anthropic Claude。通过 HTTP API 直接发送请求，而不使用特定厂商的 SDK。

## 关键代码解读

### 1. 带重试的 HTTP 请求

```python
MAX_RETRIES = 10
BACKOFF_BASE = 1.0
BACKOFF_MAX = 30.0

def post_with_retry(url, json, headers):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=json, headers=headers, timeout=600)
            if resp.status_code == 200:
                return resp
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed on attempt {attempt}: {e}")
        if attempt < MAX_RETRIES:
            sleep_time = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_MAX)
            sleep_time *= 0.8 + 0.4 * random.random()  # 加入随机抖动
            time.sleep(sleep_time)
    return None
```

重试策略设计：
- 最多 10 次重试（比其他工具多很多，因为推理任务耗时长，值得多等）
- 指数退避：1s, 2s, 4s, 8s, 16s, 30s（封顶）
- 随机抖动（jitter）：在退避时间上乘以 0.8~1.2 的随机系数，防止多个客户端同时重试导致的"惊群效应"
- 超时 600 秒（10 分钟）：推理模型可能需要较长时间思考

### 2. 思考链处理

```python
content = json_response["choices"][0]["message"]["content"]
if "</think>" in content:
    content = content.split("</think>", 1)[1].strip()
return content
```

许多开源推理模型（如 DeepSeek-R1）将思考过程包裹在 `<think>...</think>` 标签中。此代码提取 `</think>` 之后的最终答案，丢弃中间推理过程。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `post_with_retry` | 函数 | 带指数退避和随机抖动的 HTTP POST 请求 |
| `reasoning` | MCP 工具 | 使用自部署推理模型解决复杂问题 |

## 与其他模块的关系

- **与 `reasoning_mcp_server.py` 互为替代**：通过配置选择使用哪个版本
- **需要三个环境变量**：`REASONING_API_KEY`、`REASONING_BASE_URL`、`REASONING_MODEL_NAME`
- **兼容 OpenAI Chat Completions 格式**：任何兼容此格式的推理模型 API 均可使用

## 总结

`reasoning_mcp_server_os.py` 是推理工具的自部署版本，通过原始 HTTP 请求调用兼容 OpenAI 格式的推理模型 API。相比标准版，它有更强的重试机制（10 次重试 + 随机抖动），并能自动处理开源推理模型的 `<think>` 标签格式。

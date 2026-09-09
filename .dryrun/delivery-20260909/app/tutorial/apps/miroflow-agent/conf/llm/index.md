# LLM 提供商配置总览 -- `conf/llm/` 全部 4 个配置详解

## 文件概述

`conf/llm/` 目录包含 4 个 YAML 配置文件，定义了 MiroThinker 支持的大语言模型提供商和推理参数。所有配置继承自 `default.yaml`，子配置只需覆盖差异参数。

## 默认配置解读（`default.yaml`）

```yaml
provider: "anthropic"
model_name: "claude-3-7-sonnet-20250219"
async_client: false
temperature: 0.3
top_p: 1.0
min_p: 0.0
top_k: -1
max_tokens: 4096
api_key: ""
base_url: https://api.anthropic.com
repetition_penalty: 1.0
```

### 核心参数表格

| 参数 | 类型 | 说明 | 默认值 |
|---|---|---|---|
| `provider` | 字符串 | LLM 提供商标识（`anthropic` / `openai` / `qwen`） | `"anthropic"` |
| `model_name` | 字符串 | 模型全名 | `"claude-3-7-sonnet-20250219"` |
| `async_client` | 布尔值 | 是否使用异步客户端 | `false` |
| `temperature` | 浮点数 | 生成温度（越高越随机） | `0.3` |
| `top_p` | 浮点数 | 核采样阈值 | `1.0` |
| `min_p` | 浮点数 | 最小概率阈值 | `0.0` |
| `top_k` | 整数 | Top-K 采样（-1=不限制） | `-1` |
| `max_tokens` | 整数 | 单次生成最大 token 数 | `4096` |
| `api_key` | 字符串 | API 密钥（通常通过环境变量覆盖） | `""` |
| `base_url` | 字符串 | API 端点 URL | `"https://api.anthropic.com"` |
| `repetition_penalty` | 浮点数 | 重复惩罚系数（1.0=无惩罚） | `1.0` |

## 全部 4 个提供商对比

| 配置文件 | 提供商 | 模型 | 温度 | max_tokens | 上下文长度 | 特殊参数 |
|---|---|---|---|---|---|---|
| `default.yaml` | anthropic | claude-3-7-sonnet-20250219 | 0.3 | 4096 | -- | 基础配置 |
| `claude-3-7.yaml` | anthropic | claude-3-7-sonnet-20250219 | 0.3 | 4096 | 65536 | 增加 `max_context_length` |
| `gpt-5.yaml` | openai | gpt-5-2025-08-07 | 0.3 | 4096 | 65536 | OpenAI 端点 |
| `qwen-3.yaml` | qwen | qwen-3 | 1.0 | 16384 | 262144 | 高温度、大上下文、自定义端点 |

## 各提供商配置详解

### Claude 3.7（`claude-3-7.yaml`）

```yaml
provider: "anthropic"
model_name: "claude-3-7-sonnet-20250219"
base_url: https://api.anthropic.com
max_context_length: 65536
```

Anthropic 的 Claude 3.7 Sonnet，是项目的**默认模型**。65K 上下文窗口适合大多数研究任务。温度 0.3 保持输出稳定性。

### GPT-5（`gpt-5.yaml`）

```yaml
provider: "openai"
model_name: "gpt-5-2025-08-07"
base_url: https://api.openai.com/v1
max_context_length: 65536
```

OpenAI 的 GPT-5 模型。通过 `provider: "openai"` 切换到 OpenAI SDK 客户端，其余参数继承默认值。

### Qwen-3（`qwen-3.yaml`）

```yaml
provider: "qwen"
model_name: "qwen-3"
base_url: "https://your-api.com/v1"
max_context_length: 262144
max_tokens: 16384
top_p: 0.95
repetition_penalty: 1.05
temperature: 1.0
```

通义千问 Qwen-3 配置差异最大：

- **温度 1.0**：更高的随机性，Qwen 系列模型通常推荐较高温度。
- **max_tokens: 16384**：单次生成上限是默认值的 4 倍。
- **max_context_length: 262144**：256K 超长上下文窗口。
- **repetition_penalty: 1.05**：轻微的重复惩罚，防止输出退化。
- **base_url**：占位符 URL，需要替换为实际的 API 端点（可能是自部署的 vLLM 服务）。

## 与其他模块的关系

- **`src/llm/`**：`ClientFactory` 根据 `provider` 字段创建对应的 LLM 客户端（Anthropic SDK / OpenAI SDK / 自定义 HTTP）。
- **`.env.example`**：API 密钥通过环境变量（`ANTHROPIC_API_KEY`、`OPENAI_API_KEY` 等）传入，不在配置文件中硬编码。
- **`conf/config.yaml`**：通过 `llm: default` 指定默认使用哪个 LLM 配置。

## 总结

4 个 LLM 配置覆盖了三大提供商（Anthropic、OpenAI、Qwen/自定义），通过继承机制最小化重复配置。核心差异在于温度、上下文长度和 token 限制。Qwen-3 配置展示了如何接入自部署模型服务。

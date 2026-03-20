# 配置系统总览 -- `conf/` 目录结构与设计

## 文件概述

`conf/` 目录是 MiroThinker 基于 Hydra 框架的**分层配置系统**。整个目录包含 1 个主配置文件和 3 个子配置组，共计 31 个 YAML 文件。配置系统的设计目标是：通过命令行参数组合不同的 LLM、智能体策略和基准测试，无需修改任何代码即可运行不同实验。

## 目录结构

```
conf/
├── config.yaml                # 主配置文件（配置路由器）
├── agent/                     # 智能体配置组（13 个变体）
│   ├── default.yaml           # 基础默认配置
│   ├── demo.yaml              # 演示用配置
│   ├── single_agent.yaml      # 单智能体模式
│   ├── single_agent_keep5.yaml
│   ├── multi_agent.yaml       # 多智能体模式（含子智能体）
│   ├── multi_agent_os.yaml    # 多智能体开源版
│   ├── mirothinker_v1.0.yaml  # MiroThinker v1.0
│   ├── mirothinker_v1.0_keep5.yaml
│   ├── mirothinker_v1.5.yaml  # MiroThinker v1.5（主力配置）
│   ├── mirothinker_v1.5_keep5_max200.yaml
│   ├── mirothinker_v1.5_keep5_max400.yaml
│   ├── mirothinker_1.7_keep5_max200.yaml  # MiroThinker v1.7
│   └── mirothinker_1.7_keep5_max300.yaml
├── benchmark/                 # 基准测试配置组（17 个）
│   ├── default.yaml           # 基础默认配置
│   ├── browsecomp.yaml        # BrowseComp（英文）
│   ├── browsecomp_zh.yaml     # BrowseComp（中文）
│   ├── gaia-validation.yaml   # GAIA 验证集
│   ├── gaia-validation-text-103.yaml
│   ├── hle.yaml               # HLE 完整集
│   ├── hle-text-2158.yaml     # HLE 纯文本子集
│   ├── hle-text-500.yaml      # HLE 500 题子集
│   ├── frames.yaml            # FRAMES
│   ├── aime2025.yaml          # AIME 2025 数学竞赛
│   ├── deepsearchqa.yaml      # DeepSearchQA
│   ├── futurex.yaml           # FutureX 预测
│   ├── seal-0.yaml            # SEAL-0
│   ├── webwalkerqa.yaml       # WebWalkerQA
│   ├── xbench_deepsearch.yaml # XBench DeepSearch
│   ├── collect_trace.yaml     # 训练数据收集
│   └── debug.yaml             # 调试用配置
└── llm/                       # LLM 提供商配置组（4 个）
    ├── default.yaml           # 默认（Anthropic Claude 3.7）
    ├── claude-3-7.yaml        # Claude 3.7 Sonnet
    ├── gpt-5.yaml             # GPT-5
    └── qwen-3.yaml            # Qwen-3（通义千问）
```

## 三大配置组概要

### 1. Agent 配置组（`agent/`）

控制智能体的**工具集合、子智能体架构、上下文管理策略**。核心参数：

| 参数 | 作用 | 典型值 |
|---|---|---|
| `main_agent.tools` | 主智能体可用工具列表 | `[search_and_scrape_webpage, tool-python, ...]` |
| `main_agent.tool_blacklist` | 工具互斥黑名单（防止冲突组合） | `[["search_and_scrape_webpage", "sogou_search"]]` |
| `main_agent.max_turns` | 最大推理轮数 | 20 ~ 600 |
| `sub_agents` | 子智能体定义（如 browsing agent） | 字典或空 |
| `keep_tool_result` | 保留最近 N 次工具结果（-1=全部） | -1 或 5 |
| `context_compress_limit` | 上下文压缩/格式重试次数（0=禁用） | 0 或 5 |

### 2. Benchmark 配置组（`benchmark/`）

定义**基准测试的数据源和执行参数**。所有基准测试配置继承自 `default.yaml`，仅覆盖名称和数据路径。核心参数：

| 参数 | 作用 | 典型值 |
|---|---|---|
| `name` | 基准测试名称标识符 | `"browsecomp"`, `"hle"` |
| `data.data_dir` | 数据文件目录（相对路径） | `"../../data/browsecomp"` |
| `data.metadata_file` | 元数据文件名 | `"standardized_data.jsonl"` |
| `execution.max_tasks` | 最大任务数（null=不限） | `null` |
| `execution.max_concurrent` | 最大并发数 | 5 |
| `execution.pass_at_k` | Pass@K 评估（K 次尝试中至少一次正确） | 1 |

### 3. LLM 配置组（`llm/`）

定义**大语言模型的提供商和推理参数**。核心参数：

| 参数 | 作用 | 典型值 |
|---|---|---|
| `provider` | 提供商 | `"anthropic"`, `"openai"`, `"qwen"` |
| `model_name` | 模型名称 | `"claude-3-7-sonnet-20250219"` |
| `temperature` | 温度参数 | 0.3 ~ 1.0 |
| `max_tokens` | 最大生成 token 数 | 4096 ~ 16384 |
| `base_url` | API 端点 | `"https://api.anthropic.com"` |
| `max_context_length` | 最大上下文长度 | 65536 ~ 262144 |

## 配置继承机制

所有子配置文件都通过 `defaults` 列表实现继承：

```yaml
# 子配置文件示例
defaults:
  - default    # 继承 default.yaml 的所有值
  - _self_     # 本文件中显式定义的值覆盖父配置
```

这意味着：如果 `mirothinker_v1.5_keep5_max200.yaml` 只写了 `max_turns: 200` 和 `keep_tool_result: 5`，其余参数（如 `tools` 列表）全部从 `default.yaml` 继承。

## 与其他模块的关系

- **`main.py`** 和 **`benchmarks/common_benchmark.py`** 通过 `@hydra.main` 装饰器加载此配置系统。
- **`src/config/settings.py`** 定义了工具名称到 MCP 服务器的映射关系（配置中的工具名在此处解析为实际服务器）。
- **`src/utils/prompt_utils.py`** 定义了子智能体的提示词（配置中的子智能体名称在此处解析为实际 prompt）。

## 总结

配置系统采用三层分离设计（LLM / Agent / Benchmark），通过 Hydra 的 `defaults` 继承和命令行覆盖机制，实现了灵活的实验组合。用户只需一行命令即可切换不同模型、不同智能体策略和不同基准测试，无需修改任何代码。

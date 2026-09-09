# `prompt_patch.py` -- 提示词猴子补丁

## 文件概述

本文件通过 **Monkey Patching**（运行时函数替换）技术，在不修改 `miroflow-agent` 核心代码的前提下，定制 Demo 模式的行为。共应用四处补丁，分别修改系统提示词、输入处理、总结提示词和输出格式检查。

## 关键代码解读

### 1. 系统提示词补丁 -- 注入品牌身份

```python
CUSTOM_IDENTITY_PROMPT = """You are MiroThinker, a specialized deep research AI assistant developed by MiroMind.

IMPORTANT IDENTITY REMINDER:
- You are NOT ChatGPT, Claude, or any other AI assistant
"""

def _patch_system_prompt():
    from src.utils import prompt_utils
    original_generate_mcp_system_prompt = prompt_utils.generate_mcp_system_prompt

    def patched_generate_mcp_system_prompt(date, mcp_servers):
        original_prompt = original_generate_mcp_system_prompt(date, mcp_servers)
        return CUSTOM_IDENTITY_PROMPT + original_prompt

    prompt_utils.generate_mcp_system_prompt = patched_generate_mcp_system_prompt
    openai_client.generate_mcp_system_prompt = patched_generate_mcp_system_prompt
    anthropic_client.generate_mcp_system_prompt = patched_generate_mcp_system_prompt
```

**逐步解释**：
- 保存原始的 `generate_mcp_system_prompt` 函数引用。
- 创建新函数，先调用原始函数获取标准系统提示词，然后在前面拼接品牌身份文本。
- 将新函数替换到 **三个模块**中：`prompt_utils` 本身、`openai_client` 和 `anthropic_client`。
- 必须替换多个模块是因为 Python 的 `from X import Y` 会创建新的引用，只替换源模块不够。

### 2. 输入处理补丁 -- 移除 boxed 格式要求

```python
BOXED_FORMAT_SUFFIX = "\nYou should follow the format instruction in the request strictly and wrap the final answer in \\boxed{}."

def _patch_input_handler():
    original_process_input = input_handler.process_input

    def patched_process_input(task_description, task_file_name):
        result1, result2 = original_process_input(task_description, task_file_name)
        result1 = result1.replace(BOXED_FORMAT_SUFFIX, "")
        result2 = result2.replace(BOXED_FORMAT_SUFFIX, "")
        return result1, result2
```

**逐步解释**：
- 核心框架在基准测试中要求答案用 `\boxed{}` 包裹，但 Demo 模式下不需要。
- 补丁在调用原始函数后，从结果中删除这段格式要求后缀。

### 3. 总结提示词补丁 -- 用户友好的输出格式

```python
def _patch_summarize_prompt():
    def patched_generate_agent_summarize_prompt(task_description, agent_type=""):
        if agent_type == "main":
            target_language = _detect_language(task_description)
            return get_demo_summarize_prompt(target_language, task_description)
        elif agent_type == "agent-browsing" or agent_type == "browsing-agent":
            # 子 Agent 保持原始行为
            ...
```

**逐步解释**：
- 主 Agent 的总结提示词被替换为 Demo 版本：要求输出结构化 Markdown（而非 `\boxed{}` 格式）。
- 包含自动语言检测：通过统计中文/日文/韩文字符比例，用与用户问题相同的语言输出。
- 子 Agent（浏览 Agent）保持原始的总结提示词不变。

### 4. 输出格式补丁 -- 禁用格式检查重试

```python
def _patch_output_formatter():
    def patched_format_final_summary_and_log(self, final_answer_text, client=None):
        boxed_result = re.sub(r"<think>.*?</think>", "", final_answer_text, flags=re.DOTALL).strip()
        actual_boxed = self._extract_boxed_content(final_answer_text)
        if actual_boxed:
            boxed_result = actual_boxed
        # 永远不返回 FORMAT_ERROR_MESSAGE，避免触发重试
        return ("\n".join(summary_lines), boxed_result or "Demo mode - no boxed format required", log_string)
```

**逐步解释**：
- 原始 `format_final_summary_and_log` 在答案没有 `\boxed{}` 时会返回错误并触发重试。
- Demo 模式下不需要 boxed 格式，所以补丁直接使用完整答案文本（移除 `<think>` 标签后）作为结果。
- 如果答案中恰好有 `\boxed{}` 内容，仍然提取它（兼容性考虑）。

### 5. 语言检测辅助函数

```python
def _detect_language(text: str) -> str:
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    total_chars = len(text.replace(" ", ""))
    if chinese_chars / total_chars > 0.1:
        return "Chinese (Simplified)"
    ...
```

**逐步解释**：
- 统计文本中中文、日文、韩文字符的比例。
- 超过 10% 阈值即判定为对应语言。
- 用于总结提示词中指定输出语言。

## 核心类/函数表格

| 函数名 | 说明 |
|--------|------|
| `apply_prompt_patch` | 主入口，幂等地应用所有四处补丁 |
| `_patch_system_prompt` | 注入品牌身份到系统提示词 |
| `_patch_input_handler` | 移除 boxed 格式要求 |
| `_patch_summarize_prompt` | 替换为 Demo 友好的总结提示词 |
| `_patch_output_formatter` | 禁用格式检查重试逻辑 |
| `get_demo_summarize_prompt` | 生成 Demo 模式的总结提示词 |
| `_detect_language` | 基于字符统计的语言检测 |
| `get_custom_identity_prompt` | 获取品牌身份提示词字符串 |

## 与其他模块的关系

- 被 `main.py` 在启动时调用 `apply_prompt_patch()`。
- 修改 `miroflow-agent` 的多个模块：`src.utils.prompt_utils`、`src.llm.providers.openai_client`、`src.llm.providers.anthropic_client`、`src.io.input_handler`、`src.core.orchestrator`、`src.core.answer_generator`、`src.io.output_formatter`。

## 总结

本文件是 Demo 模式适配的核心，通过四处 Monkey Patch 将面向基准测试的 Agent 框架改造为面向用户体验的演示系统。关键设计决策包括：在多个模块中替换同一函数引用（应对 Python 导入机制）、幂等设计（多次调用无副作用）、以及对子 Agent 保持原始行为（仅修改主 Agent 的用户交互部分）。

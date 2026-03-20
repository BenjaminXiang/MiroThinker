# `utils.py` -- 文本处理工具

## 文件概述

本文件提供两个文本处理工具函数，用于检测和替换中文标点符号。在 Demo 应用中，当用户输入包含中文标点时，将其替换为英文标点以提高 LLM 的处理一致性。

## 关键代码解读

### 1. 中文字符检测

```python
def contains_chinese(text):
    chinese_pattern = re.compile(
        r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffef]"
    )
    return bool(chinese_pattern.search(text))
```

**逐步解释**：
- 使用正则表达式匹配多个 Unicode 范围：
  - `\u4e00-\u9fff`：CJK 统一汉字（最常用的中文字符）
  - `\u3400-\u4dbf`：CJK 扩展 A
  - `\uf900-\ufaff`：CJK 兼容字符
  - `\u3000-\u303f`：CJK 符号与标点
  - `\uff00-\uffef`：全角 ASCII 和全角标点
- 只要文本中存在任何匹配字符即返回 `True`。

### 2. 中文标点替换

```python
def replace_chinese_punctuation(text):
    punctuation_map = str.maketrans({
        "，": ",", "。": ".", "！": "!", "？": "?",
        "；": ";", "：": ":", """: '"', """: '"',
        "'": "'", "'": "'", "（": "(", "）": ")",
        "【": "[", "】": "]", "《": "<", "》": ">",
        "、": ",", "—": "-",
    })
    text = text.replace("……", "...")
    return text.translate(punctuation_map)
```

**逐步解释**：
- 使用 `str.maketrans` 创建字符映射表，一次性替换所有中文标点为对应英文标点。
- 特殊处理：`……`（中文省略号）是多字符序列，需要先用 `str.replace` 处理。
- 覆盖 17 种常见中文标点符号。

## 核心类/函数表格

| 函数名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `contains_chinese` | `text: str` | `bool` | 检测字符串是否包含中文字符或标点 |
| `replace_chinese_punctuation` | `text: str` | `str` | 将中文标点替换为对应英文标点 |

## 与其他模块的关系

- `replace_chinese_punctuation` 被 `main.py` 导入，用于处理用户输入。
- `contains_chinese` 目前未在 Demo 中直接使用，但可供其他模块判断是否需要标点替换。

## 总结

这是一个小型工具文件，解决中文标点对 LLM 输入一致性的影响。核心实现利用 Python 内置的 `str.translate` 方法实现高效的批量字符替换。

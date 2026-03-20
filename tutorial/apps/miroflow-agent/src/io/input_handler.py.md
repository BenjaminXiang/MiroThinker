# `input_handler.py` — 多格式输入处理与文件内容提取

## 文件概述

`input_handler.py` 是 MiroThinker 的**输入预处理器**，负责将用户提交的任务描述和附带文件统一转换为 LLM 可理解的 Markdown 文本。它支持 20 多种文件格式，包括文档（PDF、DOCX、PPTX、XLSX）、媒体文件（图片、音频、视频）、数据文件（JSON、CSV）、代码文件和压缩包。

在项目中，它是 `Pipeline` 启动任务时最先调用的处理环节——在 LLM 看到任务之前，所有附带文件的内容都已被提取并拼接到任务描述中。

## 关键代码解读

### 文件类型常量

```python
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
AUDIO_EXTENSIONS = {"wav", "mp3", "m4a"}
VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
SKIP_MARKITDOWN_EXTENSIONS = MEDIA_EXTENSIONS | {"pdb"}
```

**解释**：用集合定义支持的文件扩展名，`MEDIA_EXTENSIONS` 是所有媒体类型的并集。`SKIP_MARKITDOWN_EXTENSIONS` 标记哪些格式不应使用 MarkItDown 回退处理（媒体文件需要专门的 API 处理，而不是文本转换）。

### 图片描述生成

```python
def _generate_image_caption(image_path: str) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    with open(image_path, "rb") as image_file:
        image_data = base64.b64encode(image_file.read()).decode("utf-8")

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Please provide a detailed description of this image..."},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}},
            ],
        }],
        max_tokens=2048, temperature=0,
    )
    return response.choices[0].message.content
```

**解释**：

- 将图片读取为 base64 编码，通过 OpenAI GPT-4o 的视觉能力生成详细描述
- 使用 `temperature=0` 确保输出确定性
- 如果 API 密钥缺失或调用失败，返回友好的错误提示而不是抛出异常

类似的函数还有 `_generate_audio_caption()`（音频转写）和 `_generate_video_caption()`（视频描述），以及与任务相关的信息提取版本 `_extract_task_relevant_info_from_image/audio/video()`。

### 核心入口函数 process_input

```python
def process_input(task_description: str, task_file_name: str) -> Tuple[str, str]:
    updated_task_description = task_description
    file_content_section = ""

    if task_file_name:
        file_extension = task_file_name.rsplit(".", maxsplit=1)[-1].lower()

        if file_extension in IMAGE_EXTENSIONS:
            caption = _generate_image_caption(task_file_name)
            relevant_info = _extract_task_relevant_info_from_image(task_file_name, task_description)
            file_content_section += f"## Image Content\nFile: {task_file_name}\n\n> {caption}\n\n"
            # ...
        elif file_extension == "pdf":
            parsing_result = DocumentConverterResult(
                title=None,
                text_content=pdfminer.high_level.extract_text(task_file_name),
            )
            # ...
        # ... 20+ 种文件类型的处理分支 ...

        # MarkItDown 作为通用回退
        if parsing_result is None and file_extension not in SKIP_MARKITDOWN_EXTENSIONS:
            md = MarkItDown(enable_plugins=True)
            parsing_result = md.convert(task_file_name)

    updated_task_description += "\nYou should follow the format instruction..."
    updated_task_description += file_content_section
    return updated_task_description, updated_task_description
```

**解释**：

- 根据文件扩展名分派到不同的处理逻辑
- 每种文件类型生成包含提示语和内容的 Markdown 片段
- 文本内容有 200,000 字符的截断限制，防止超长文件撑爆 LLM 上下文
- 如果没有专用转换器处理成功，`MarkItDown` 作为通用回退方案
- 最终将 `\boxed{}` 格式要求附加到任务描述末尾

### 文档转换器

文件中还包含多个专用转换器：

```python
class DocumentConverterResult:
    """统一的文档转换结果容器"""
    def __init__(self, title=None, text_content=""):
        self.title = title
        self.text_content = text_content

def HtmlConverter(local_path: str):        # HTML → Markdown
def DocxConverter(local_path: str):        # DOCX → HTML → Markdown
def XlsxConverter(local_path: str):        # Excel → Markdown 表格（保留颜色格式）
def PptxConverter(local_path: str):        # PPTX → Markdown（支持图片/表格/文本）
def ZipConverter(local_path: str):         # ZIP → 递归解压并处理每个文件
```

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `process_input(task_description, task_file_name)` | 函数 | 主入口，处理任务描述和附带文件，返回增强后的任务描述 |
| `_generate_image_caption(image_path)` | 函数 | 使用 GPT-4o 视觉能力为图片生成描述 |
| `_generate_audio_caption(audio_path)` | 函数 | 使用 GPT-4o 转写模型对音频进行文字转写 |
| `_generate_video_caption(video_path)` | 函数 | 使用 GPT-4o 视觉能力为视频生成描述 |
| `_extract_task_relevant_info_from_image/audio/video` | 函数 | 从媒体中提取与当前任务直接相关的信息 |
| `DocumentConverterResult` | 类 | 文档转换结果的统一容器，包含 title 和 text_content |
| `_CustomMarkdownify` | 类 | 自定义的 HTML 转 Markdown 转换器，修复链接/图片/标题格式 |
| `HtmlConverter` / `DocxConverter` / `XlsxConverter` / `PptxConverter` / `ZipConverter` | 函数 | 各类型文档的专用转换器 |

## 与其他模块的关系

- **`core/Pipeline`**：在任务开始时调用 `process_input()` 预处理输入
- **`config/settings.py`**：媒体处理函数依赖其中定义的 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`（通过 `os.environ` 间接获取）
- **外部库依赖**：pdfminer（PDF）、mammoth（DOCX）、openpyxl（Excel）、python-pptx（PPT）、BeautifulSoup + markdownify（HTML）、MarkItDown（通用回退）

## 总结

`input_handler.py` 实现了一个完整的多模态输入管道：无论用户提交什么格式的文件，它都能将其转换为 Markdown 文本供 LLM 处理。对于文本类文件直接提取内容，对于媒体文件则借助 GPT-4o 的多模态能力生成文字描述。这种设计使得核心推理模块可以专注于文本推理，而不需要处理各种文件格式的差异。

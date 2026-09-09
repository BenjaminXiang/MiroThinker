# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""统一翻译规范 — 所有 LLM 提取 prompt 共用。

产品受众为中文用户，所有输出字段必须使用中文。
此模块提供：
1. 常见英中术语映射表（供 prompt 内嵌示例）
2. 统一的翻译指引文本（供各 prompt 直接拼接）
"""
from __future__ import annotations

# ── LLM 调用共用参数 ──
# Gemma 4 要求传递 chat_template_kwargs 来控制 thinking 模式
LLM_EXTRA_BODY: dict = {"chat_template_kwargs": {"enable_thinking": False}}

# ── 职称映射 ──
TITLE_MAP: dict[str, str] = {
    "Chair Professor": "讲席教授",
    "Distinguished Professor": "杰出教授",
    "Professor": "教授",
    "Tenured Associate Professor": "长聘副教授",
    "Associate Professor": "副教授",
    "Assistant Professor": "助理教授",
    "Research Professor": "研究教授",
    "Research Associate Professor": "研究副教授",
    "Research Assistant Professor": "研究助理教授",
    "Adjunct Professor": "兼职教授",
    "Visiting Professor": "访问教授",
    "Lecturer": "讲师",
    "Senior Lecturer": "高级讲师",
    "Postdoctoral Fellow": "博士后研究员",
    "PhD Advisor": "博士生导师",
    "Master Advisor": "硕士生导师",
}

# ── 学位映射 ──
DEGREE_MAP: dict[str, str] = {
    "PhD": "博士",
    "Ph.D.": "博士",
    "Doctor of Philosophy": "哲学博士",
    "Master": "硕士",
    "M.S.": "硕士",
    "M.Sc.": "理学硕士",
    "M.Eng.": "工学硕士",
    "MBA": "工商管理硕士",
    "Bachelor": "学士",
    "B.S.": "学士",
    "B.Sc.": "理学学士",
    "B.Eng.": "工学学士",
    "Postdoc": "博士后",
}

# ── 常见院系映射 ──
DEPARTMENT_MAP: dict[str, str] = {
    "Computer Science and Engineering": "计算机科学与工程系",
    "Computer Science": "计算机科学系",
    "Electrical and Electronic Engineering": "电子与电气工程系",
    "Mechanical and Energy Engineering": "机械与能源工程系",
    "Materials Science and Engineering": "材料科学与工程系",
    "Statistics and Data Science": "统计与数据科学系",
    "Mathematics": "数学系",
    "Physics": "物理系",
    "Chemistry": "化学系",
    "Biology": "生物系",
    "Biomedical Engineering": "生物医学工程系",
    "Environmental Science and Engineering": "环境科学与工程学院",
    "School of Medicine": "医学院",
    "School of Business": "商学院",
}

# ── 常见研究方向术语映射（高频词） ──
DIRECTION_MAP: dict[str, str] = {
    "Machine Learning": "机器学习",
    "Deep Learning": "深度学习",
    "Computer Vision": "计算机视觉",
    "Natural Language Processing": "自然语言处理",
    "Artificial Intelligence": "人工智能",
    "Data Mining": "数据挖掘",
    "Database Systems": "数据库系统",
    "Big Data": "大数据",
    "Robotics": "机器人学",
    "Reinforcement Learning": "强化学习",
    "Information Retrieval": "信息检索",
    "Software Engineering": "软件工程",
    "Cybersecurity": "网络安全",
    "Internet of Things": "物联网",
    "Cloud Computing": "云计算",
    "Quantum Computing": "量子计算",
    "Bioinformatics": "生物信息学",
    "Signal Processing": "信号处理",
    "Image Processing": "图像处理",
    "Embedded Systems": "嵌入式系统",
}


def _build_examples_block() -> str:
    """生成 prompt 中使用的映射示例（精选高频词，不全量罗列）。"""
    title_examples = "\n".join(
        f'   - "{en}" → "{zh}"'
        for en, zh in list(TITLE_MAP.items())[:6]
    )
    degree_examples = "\n".join(
        f'   - "{en}" → "{zh}"'
        for en, zh in list(DEGREE_MAP.items())[:4]
    )
    dept_examples = "\n".join(
        f'   - "{en}" → "{zh}"'
        for en, zh in list(DEPARTMENT_MAP.items())[:4]
    )
    direction_examples = "\n".join(
        f'   - "{en}" → "{zh}"'
        for en, zh in list(DIRECTION_MAP.items())[:6]
    )
    return f"""   职称：
{title_examples}
   学位：
{degree_examples}
   院系：
{dept_examples}
   研究方向：
{direction_examples}"""


# ── 统一翻译指引（嵌入到各 LLM prompt 中） ──
TRANSLATION_GUIDELINES = f"""## 翻译规范（必须遵守）
本系统面向中文用户，所有输出字段**必须使用中文**。
如果原文是英文，请按以下规则翻译：

1. **职称**：使用中国高校体系对应称谓
2. **学位**：统一使用中文学位名称
3. **院系**：翻译为中文，优先使用该校官方中文名称
4. **研究方向**：翻译为学术界通用的中文术语
5. **学校名称**：使用官方中文全称（如 "Southern University of Science and Technology" → "南方科技大学"）
6. **获奖/学术职务**：国际奖项保留英文缩写 + 中文说明（如 "ACM SIGMOD Best Paper" → "ACM SIGMOD最佳论文奖"）
7. **人名**：中国人保留中文名；外国人保留原文

常见映射参考：
{_build_examples_block()}

未在映射表中的术语，请根据学术界通用译法自行翻译。"""


def normalize_title(raw: str) -> str:
    """将英文职称标准化为中文。"""
    stripped = raw.strip()
    for en, zh in TITLE_MAP.items():
        if stripped.lower() == en.lower():
            return zh
    return stripped


def normalize_degree(raw: str) -> str:
    """将英文学位标准化为中文。"""
    stripped = raw.strip()
    for en, zh in DEGREE_MAP.items():
        if stripped.lower() == en.lower():
            return zh
    return stripped

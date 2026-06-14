from __future__ import annotations

import re

OPERATOR_META_KEYWORDS = frozenset(
    {
        "摘要仅汇总",
        "人工复核",
        "细粒度检索",
        "该摘要基于",
        "当前画像",
        "可核验事实字段",
        "当前公开资料",
        "持续补全",
        "已同步整理",
        "采集原则",
        "不对缺失经历",
        "后续检索",
        "用于后续检索",
        "系统会持续补充",
        "跨域联动完成前",
        "官网结构化字段",
        "个人资料页正文",
    }
)

_SENTENCE_RE = re.compile(r"[^。！？!?；;]+[。！？!?；;]?")
_WHITESPACE_RE = re.compile(r"\s+")
_FACT_SIGNAL_KEYWORDS = (
    "现任",
    "教授",
    "导师",
    "博士",
    "毕业",
    "博士后",
    "研究员",
    "研究工作",
    "主要从事",
    "致力于",
    "研究方向",
    "聚焦",
    "开发",
    "搭建",
    "发表",
    "授权",
    "入选",
    "承担",
    "项目",
    "荣誉",
    "学术委员会",
    "审稿人",
)
_RESEARCH_SIGNAL_KEYWORDS = (
    "主要从事",
    "致力于",
    "研究方向",
    "聚焦",
    "开发",
    "搭建",
    "方法学",
    "结构解析",
    "分子机制",
    "调控机制",
    "信号调控",
)
_OUTPUT_SIGNAL_KEYWORDS = (
    "发表",
    "授权",
    "入选",
    "承担",
    "项目",
    "荣誉",
    "学术委员会",
    "审稿人",
)
_NOISE_KEYWORDS = (
    "加入我们",
    "招募",
    "招聘",
    "请将简历",
    "联系方式",
    "电子邮箱",
    "邮箱",
    "电话",
    "地址",
    "代表论文",
)


def contains_operator_meta_language(text: str | None) -> bool:
    value = text or ""
    return any(keyword in value for keyword in OPERATOR_META_KEYWORDS)


def extract_profile_fact_sentences(
    text: str | None,
    *,
    max_sentences: int = 3,
    max_sentence_length: int = 140,
) -> list[str]:
    normalized = _WHITESPACE_RE.sub(" ", text or "").strip()
    if not normalized:
        return []

    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for index, match in enumerate(_SENTENCE_RE.finditer(normalized)):
        sentence = _normalize_sentence(match.group(0))
        if not sentence or len(sentence) < 12:
            continue
        if contains_operator_meta_language(sentence):
            continue
        if any(noise in sentence for noise in _NOISE_KEYWORDS):
            continue
        if not any(signal in sentence for signal in _FACT_SIGNAL_KEYWORDS):
            continue
        sentence = _trim_sentence(sentence, max_sentence_length)
        key = sentence.casefold()
        if key in seen:
            continue
        seen.add(key)
        candidates.append((_sentence_rank(sentence), index, sentence))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [sentence for _, _, sentence in candidates[:max_sentences]]


def _normalize_sentence(sentence: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", sentence).strip(" ，、；;")
    if not normalized:
        return ""
    if normalized[-1] not in "。！？!?":
        normalized = f"{normalized}。"
    return normalized


def _trim_sentence(sentence: str, max_length: int) -> str:
    if len(sentence) <= max_length:
        return sentence
    for marker in ("，包括", "，结合", "，并", "，为"):
        marker_at = sentence.find(marker)
        if 20 <= marker_at <= max_length:
            return _normalize_sentence(sentence[:marker_at])
    delimiter_at = max(
        sentence.rfind(marker, 20, max_length)
        for marker in ("，", "；", ";")
    )
    if delimiter_at >= 20:
        return _normalize_sentence(sentence[:delimiter_at])
    trimmed = sentence[:max_length].rstrip("，、；;：: ")
    if trimmed and trimmed[-1] not in "。！？!?":
        trimmed = f"{trimmed}。"
    return trimmed


def _sentence_rank(sentence: str) -> int:
    if any(signal in sentence for signal in _RESEARCH_SIGNAL_KEYWORDS):
        return 0
    if any(signal in sentence for signal in _OUTPUT_SIGNAL_KEYWORDS):
        return 1
    return 2

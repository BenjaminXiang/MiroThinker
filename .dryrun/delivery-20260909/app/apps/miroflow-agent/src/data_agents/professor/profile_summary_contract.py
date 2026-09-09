from __future__ import annotations

import re

PROFILE_SUMMARY_MIN_CHARS = 200
PROFILE_SUMMARY_MAX_CHARS = 300
PROFILE_SUMMARY_MIN_CJK_RATIO = 0.35
PROFILE_SUMMARY_MIN_LATIN_FOR_DOMINANCE = 80
PROFILE_SUMMARY_PROMPT_CONTRACT = (
    "profile_summary must be a 200-300 character Chinese (中文) canonical biography. "
    "Translate English source evidence into natural Chinese instead of writing an "
    "English+Chinese mixed paragraph. Preserve original English source text in "
    "structured facts/evidence, not in professor.profile_summary."
)

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
        "资料缺失",
        "暂无收录",
        "暂无已收录",
        "仅基于基本信息",
        "平台收录",
        "收录状态",
        "论文全文缺失",
        "未收录论文全文",
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
_CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_CHAR_RE = re.compile(r"[A-Za-z]")
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


def profile_summary_contract_violations(text: str | None) -> tuple[str, ...]:
    value = (text or "").strip()
    if not value:
        return ("profile_summary_missing",)

    violations: list[str] = []
    length = len(value)
    if length < PROFILE_SUMMARY_MIN_CHARS:
        violations.append("profile_summary_too_short")
    if length > PROFILE_SUMMARY_MAX_CHARS:
        violations.append("profile_summary_too_long")

    cjk_count = len(_CJK_CHAR_RE.findall(value))
    if cjk_count == 0:
        violations.append("profile_summary_not_chinese")
    else:
        latin_count = len(_LATIN_CHAR_RE.findall(value))
        language_chars = cjk_count + latin_count
        if (
            latin_count >= PROFILE_SUMMARY_MIN_LATIN_FOR_DOMINANCE
            and language_chars
            and cjk_count / language_chars < PROFILE_SUMMARY_MIN_CJK_RATIO
        ):
            violations.append("profile_summary_english_dominant")

    if contains_operator_meta_language(value):
        violations.append("profile_summary_operator_meta_language")
    return tuple(violations)


def profile_summary_contract_issue(text: str | None) -> str | None:
    for violation in profile_summary_contract_violations(text):
        if violation in {
            "profile_summary_missing",
            "profile_summary_not_chinese",
            "profile_summary_too_short",
            "profile_summary_too_long",
            "profile_summary_english_dominant",
        }:
            return violation
    return None


def is_valid_profile_summary(text: str | None) -> bool:
    return not profile_summary_contract_violations(text)


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
        sentence.rfind(marker, 20, max_length) for marker in ("，", "；", ";")
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

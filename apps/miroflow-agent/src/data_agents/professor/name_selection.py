from __future__ import annotations

import re

JUNK_NAME_TITLES = {
    "首页",
    "师资",
    "师资队伍",
    "新闻",
    "南燕新闻",
    "导航",
    "概况",
    "学院概况",
    "学部概况",
    "组织机构",
    "现任领导",
    "新闻中心",
    "科研项目",
    "学术科研",
    "招生就业",
    "常用下载",
}
JUNK_NAME_KEYWORDS = (
    "概况",
    "导航",
    "组织机构",
    "科研",
    "招生",
    "学生",
    "下载",
    "讲座",
    "招聘",
    "学院",
    "学部",
    "文字学",
    "文艺学",
    "哲学",
    "中国史",
    "汉语国际教育",
)
JUNK_NAME_PREFIXES = (
    "新闻",
    "科研",
    "学术",
    "招生",
    "学生",
    "学院",
    "学部",
    "组织",
    "讲座",
    "常用",
    "党建",
    "人才",
    "资料",
)
JUNK_NAME_SUFFIXES = (
    "概况",
    "导航",
    "机构",
    "中心",
    "项目",
    "动态",
    "信息",
    "下载",
    "服务",
    "工作",
    "活动",
    "文字学",
    "文艺学",
    "哲学",
    "中国史",
    "教育系",
)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(
        value.replace("\ufeff", "").replace("\u3000", " ").split()
    ).strip()
    return normalized or None


def normalize_name_key(value: str | None) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return ""
    return re.sub(r"[\s\u3000·•\-_.()（）\[\]【】'\"`]", "", normalized).lower()


def is_obvious_non_person_name(value: str | None) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return False
    if normalized in JUNK_NAME_TITLES:
        return True
    if len(normalized) > 12:
        return False
    if any(keyword in normalized for keyword in JUNK_NAME_KEYWORDS):
        return True
    if normalized.startswith(JUNK_NAME_PREFIXES):
        return True
    if normalized.endswith(JUNK_NAME_SUFFIXES):
        return True
    return False


def is_same_person_name_variant(left: str, right: str) -> bool:
    left_key = normalize_name_key(left)
    right_key = normalize_name_key(right)
    if not left_key or not right_key:
        return False
    return left_key in right_key or right_key in left_key


def choose_richer_name(candidate: str, fallback: str) -> str:
    candidate_key = normalize_name_key(candidate)
    fallback_key = normalize_name_key(fallback)
    if len(candidate_key) >= len(fallback_key):
        return candidate
    return fallback


def select_canonical_name(
    roster_name: str | None,
    extracted_name: str | None,
) -> str | None:
    roster = _normalize_text(roster_name)
    extracted = _normalize_text(extracted_name)

    if extracted is None:
        return roster
    if roster is None:
        return extracted
    if is_obvious_non_person_name(extracted):
        return roster
    if is_same_person_name_variant(roster, extracted):
        return choose_richer_name(extracted, roster)
    return extracted

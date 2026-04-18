from __future__ import annotations

import re

JUNK_NAME_TITLES = {
    "首页",
    "师资",
    "师资队伍",
    "教师队伍",
    "全部教师",
    "教研团队",
    "教研序列",
    "研究序列",
    "教辅序列",
    "行政序列",
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
    "返回主站",
    "最新公告",
    "院长寄语",
    "优质教育",
    "“师说”教授专访",
    "工作履历",
    "专任教师",
    "专职教师",
    "全职教师",
    "兼职教师",
    "机构设置",
    "科学研究",
    "行政教辅",
    "教学平台",
    "行业导师",
    "本科生",
    "研究生",
    "博士生",
    "硕士生",
    "团学风采",
    "党团工作",
    "学生工作",
    "教学工作",
    "本科教学",
    "实验课程",
    "行政人员",
    "行政服务",
    "学术交流",
    "学术活动",
    "人才计划",
    "人才培养",
    "组织架构",
}
EXACT_NON_PERSON_TITLES = {
    "教授",
    "副教授",
    "助理教授",
    "讲席教授",
    "特聘教授",
    "研究员",
    "副研究员",
    "讲师",
    "导师",
    "院士",
}

JUNK_NAME_TITLES_CASEFOLD = {
    "teaching",
    "presentation",
    "presentations",
    "service",
    "biography",
    "publications",
    "research",
    "curriculum vitae",
    "cv",
    "about us",
    "view more",
    "home",
    "contact",
    "central saint martins",
    "english string",
    "job openings admission alumni",
    "highly cited chinese researchers",
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
    "公告",
    "寄语",
    "专访",
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
    "返回",
    "最新",
)
JUNK_NAME_SUFFIXES = (
    "大学",
    "学院",
    "研究院",
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
    "主站",
    "寄语",
    "公告",
)
_PROFILE_BLOB_KEYWORDS = (
    "title",
    "education",
    "background",
    "research",
    "biography",
    "publications",
    "awards",
    "honors",
    "email",
    "office",
    "phone",
    "teaching",
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


_JOURNAL_OR_TOPIC_PATTERN = re.compile(
    r"\b("
    r"journal|review|reviews|advances|express|letters|bulletin|proceedings|"
    r"materials|mater|science|sciences|research|engineering|systems|studies|"
    r"academia|academy|society|institute|committee|association|foundation|"
    r"transactions|international|intelligent|highly cited|postgraduate|"
    r"management|manufacturing|technology|automation|computing|electronics|"
    r"operations|exchange|cooperation|cognition|plasma|physics|chemistry|"
    r"biology|mathematics|transportation|optics|neural|chinese researchers"
    r")\b",
    re.IGNORECASE,
)


def _looks_like_journal_or_topic_name(value: str) -> bool:
    """Detect english strings that are journal / topic / institution labels
    rather than person names. Scraped pages commonly mix these into name
    fields (e.g. ``Energy Mater``, ``Academia Europaea``, ``Intelligent
    Transportation Systems``)."""
    if not value or " " not in value:
        return False
    if not _JOURNAL_OR_TOPIC_PATTERN.search(value):
        return False
    # Real names very rarely contain more than one of these keywords AND a
    # two-word structure lacking person-like cues.
    word_count = len(value.split())
    if word_count >= 2 and not re.search(r"[,.\-']", value):
        return True
    return False


def is_obvious_non_person_name(value: str | None) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return False
    if normalized in JUNK_NAME_TITLES:
        return True
    if normalized in EXACT_NON_PERSON_TITLES:
        return True
    if normalized.casefold() in JUNK_NAME_TITLES_CASEFOLD:
        return True
    if _looks_like_journal_or_topic_name(normalized):
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


def looks_like_profile_blob(value: str | None) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return False
    lowered = normalized.lower()
    keyword_hits = sum(1 for keyword in _PROFILE_BLOB_KEYWORDS if keyword in lowered)
    if len(normalized) >= 80:
        return True
    if keyword_hits >= 2 and len(normalized) >= 40:
        return True
    return normalized.count(" ") >= 12


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
    if looks_like_profile_blob(extracted):
        return roster
    if is_same_person_name_variant(roster, extracted):
        return choose_richer_name(extracted, roster)
    return extracted

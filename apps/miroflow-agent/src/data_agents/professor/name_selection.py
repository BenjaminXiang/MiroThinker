from __future__ import annotations

import re

JUNK_NAME_TITLES = {
    "首页",
    "师资",
    "师资队伍",
    "师资力量",
    "教师简介",
    "综合新闻",
    "新闻动态",
    "最新动态",
    "学术动态",
    "学院动态",
    "招生简章",
    "关于我们",
    "院长致辞",
    "中心简介",
    "学院简介",
    "学院概况",
    "联系我们",
    "机构设置",
    "教师队伍",
    "全部教师",
    "教研团队",
    "活动风采",
    "仪器申请",
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
    "个人简历",
    "个人简介",
    "教育经历",
    "教育背景",
    "工作经历",
    "研究方向",
    "研究领域",
    "研究成果",
    "学术成果",
    "奖励荣誉",
    "荣誉奖项",
    "主要荣誉",
    "学术兼职",
    "代表性论文",
    "代表性著作",
    "主要专利成果",
    "教学",
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
    "中心介绍",
    "交流合作",
    "发展沿革",
    "合作伙伴",
    "校友",
    "校友会",
    "教工",
    "廉洁之窗",
    "未开通",
    "相关教师",
    "友情链接",
    "面包屑",
    "登录",
    "党团工作",
    "党的建设",
    "团建工作",
    "科研实践",
    "科研方向",
    "就业指导",
    "书记｜院长信箱",
    "书记|院长信箱",
}
LEGITIMATE_SHORT_CJK_NAME_EXCEPTIONS = {
    "黄哲学",
}
EXACT_NON_PERSON_TITLES = {
    "教授",
    "副教授",
    "助理教授",
    "讲席教授",
    "特聘教授",
    "杰出教授",
    "工程师",
    "产业导师",
    "研究员",
    "副研究员",
    "讲师",
    "导师",
    "院士",
    "院长",
    "副院长",
    "执行院长",
    "常务副院长",
    "书记",
    "副书记",
    "主任",
    "副主任",
    "系主任",
    "副系主任",
    "所长",
    "副所长",
    "中心主任",
    "外事专员",
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
    "highlighted news",
    "lab introduction",
}
JUNK_NAME_SUFFIXES_CASEFOLD = (
    " lab",
    " laboratory",
    " news",
    " homepage",
    "'s homepage",
)
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
    "风采",
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

# Round 7.18 — Chinese field-label markers that appear when the scraper swallows
# profile metadata into the "name" field. Seen in miroflow_real:
#   "陈怀海 性别： 男" → scraper glued the gender row to the name
#   "倪江群职称：教授" → scraper glued the title row to the name
# A real person's name never contains these substrings.
_FIELD_LABEL_MARKERS = (
    "性别：",
    "性别:",
    "职称：",
    "职称:",
    "职务：",
    "职务:",
    "学位：",
    "学位:",
    "学历：",
    "学历:",
    "邮箱：",
    "邮箱:",
    "电话：",
    "电话:",
    "姓名：",
    "姓名:",
    "E-mail：",
    "e-mail：",
    "Email：",
    "email：",
    "研究方向：",
    "工作单位：",
    "个人简介：",
)

# Round 7.18 — long strings with a · separator usually indicate multi-field
# pollution (e.g. "Prof. Dr. Anita Zehrer·MCI The Entrepreneurial ...").
# Short · names (Uyghur/Tibetan personal names like 吾买尔·阿卜杜拉) must pass.
_LONG_MIDDOT_THRESHOLD = 30
_PAPER_EVIDENCE_TITLE_POLLUTION_MARKERS = (
    "inventor:",
    "inventors:",
    "us patent",
    "u.s. patent",
    "patent no",
    "patent number",
    "cn patent",
    "pct/",
    "modified peptide nucleic acids and their use",
    "授权发明专利",
    "发明专利",
    "专利号",
)
_PAPER_EVIDENCE_TITLE_POLLUTION_RE = re.compile(
    r"\b(?:19|20)\d{2}\b.*\b(?:vol\.?|pp\.?|doi|journal|proceedings)\b"
    r"|[.;]\s*(?:inventors?|authors?)\s*:",
    re.IGNORECASE,
)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(
        value.replace("\x00", "")
        .replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\u3000", " ")
        .split()
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
    bracket_stripped = re.sub(r"[（(][^()（）]*[）)]$", "", normalized).strip()
    if bracket_stripped in EXACT_NON_PERSON_TITLES:
        return True
    casefolded = normalized.casefold()
    if casefolded in JUNK_NAME_TITLES_CASEFOLD:
        return True
    if len(normalized.split()) >= 2 and casefolded.endswith(JUNK_NAME_SUFFIXES_CASEFOLD):
        return True
    if _looks_like_journal_or_topic_name(normalized):
        return True
    if any(marker in normalized for marker in _FIELD_LABEL_MARKERS):
        return True
    if len(normalized) > _LONG_MIDDOT_THRESHOLD and "·" in normalized:
        return True
    if len(normalized) > 12:
        return False
    if normalized in LEGITIMATE_SHORT_CJK_NAME_EXCEPTIONS:
        return False
    if any(keyword in normalized for keyword in JUNK_NAME_KEYWORDS):
        return True
    if normalized.startswith(JUNK_NAME_PREFIXES):
        return True
    if normalized.endswith(JUNK_NAME_SUFFIXES):
        return True
    return False


def looks_like_professor_paper_evidence_title_pollution(value: str | None) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return False
    casefolded = normalized.casefold()
    if any(marker in casefolded for marker in _PAPER_EVIDENCE_TITLE_POLLUTION_MARKERS):
        return True
    if len(normalized) >= 40 and _PAPER_EVIDENCE_TITLE_POLLUTION_RE.search(normalized):
        return True
    return False


def is_unsafe_professor_paper_evidence_identity(
    canonical_name: str | None,
    *,
    affiliation_title: str | None = None,
) -> bool:
    if is_obvious_non_person_name(canonical_name):
        return True
    if looks_like_profile_blob(canonical_name):
        return True
    return looks_like_professor_paper_evidence_title_pollution(affiliation_title)


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
    return roster

"""Shared Chinese follow-up referent detection for the Canonical V2 serving path.

One authority for singular-anchor and displayed-set referent recognition so the
HTTP chat adapter, the serving planner, and the Web query builder cannot drift
into separate, inconsistent marker tables. A follow-up that refers to the active
anchor or the displayed result set MUST bind that referent at planning time, and
referent words MUST NOT leak into retrieval query text.

Deliberately not covered: expansion requests such as "还有哪些" or "其他的呢"
ask for results beyond the displayed set; binding them to the set would narrow
rather than expand, so they remain outside both referent families until a real
expansion operation exists.
"""

from __future__ import annotations

import re

SINGULAR_REFERENT_MARKERS: tuple[str, ...] = (
    "该公司",
    "这家公司",
    "该企业",
    "这家企业",
    "该论文",
    "这篇论文",
    "这论文",
    "该文章",
    "这篇文章",
    "该专利",
    "这项专利",
    "该教授",
    "这位教授",
    "这名教授",
    "该学者",
    "这位学者",
    "这名学者",
    "这位老师",
    "这名老师",
    "这个人",
    "此人",
)

SET_REFERENT_MARKERS: tuple[str, ...] = (
    "上述",
    "以上",
    "这些",
    "已展示",
    "上面",
    "其中",
    "他们",
    "她们",
    "它们",
    "这几家",
    "这几篇",
    "这几位",
    "这几项",
    "这两家",
    "这两篇",
    "这两位",
    "这两项",
)

# Pronoun-led follow-ups ("他有哪些…", "那她的…", "他还是否…"). A pronoun only
# counts at the start or after punctuation/那/这, so compounds like 其他/其它/吉他
# do not masquerade as referents; plural 他们/她们/它们 are set referents instead.
_SINGULAR_PRONOUN_PATTERN = re.compile(
    r"(?:^|[\s，,。.；;？?！!那这])[他她它](?:的|是否)?(?!们)"
)

_LEADING_PRONOUN_PATTERN = re.compile(r"^(?:他|她|它)(?:们)?(?:的)?(?:还|也|就)?")

# Elaboration-led short follow-ups ("具体的论文有哪些", "详细说说"). These only
# make sense over prior context, so they continue the active anchor; a new-topic
# query never looks like this (length cap + no 介绍 scaffolding).
_CONTINUATION_PATTERN = re.compile(r"^(?:具体|详细|展开)")


def has_continuation_intent(query: str) -> bool:
    """Whether the query is an elaboration of prior context."""
    stripped = query.strip()
    return (
        bool(_CONTINUATION_PATTERN.match(stripped))
        and len(stripped) <= 10
        and "介绍" not in stripped
    )


# Explicit noun markers that disclose which domain an anaphoric follow-up
# refers to. Only a preference signal for referent-history binding; a hint
# alone never binds anything.
_REFERENT_DOMAIN_HINT_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("company", ("公司", "企业", "厂商", "供应商")),
    ("paper", ("论文", "paper")),
    ("patent", ("专利",)),
    ("professor", ("教授", "专家", "他", "她")),
)


def referent_domain_hint(query: str) -> str | None:
    """Domain explicitly hinted by noun markers in an anaphoric follow-up."""
    text = query.casefold()
    for domain, markers in _REFERENT_DOMAIN_HINT_MARKERS:
        if any(marker in text for marker in markers):
            return domain
    return None


# The referent's own domain (who/what is being pointed at), as opposed to the
# asked-about object: "他的代表性论文" asks about papers, but the referent 他
# is a person. Type-blind binding would pin a male-person pronoun onto a
# company anchor merely because the anchor is current.
_SINGULAR_REFERENT_SUBJECT_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("company", ("该公司", "这家公司", "该企业", "这家企业")),
    ("paper", ("该论文", "这篇论文", "这论文", "该文章", "这篇文章")),
    ("patent", ("该专利", "这项专利")),
    (
        "professor",
        (
            "该教授",
            "这位教授",
            "这名教授",
            "该学者",
            "这位学者",
            "这名学者",
            "这位老师",
            "这名老师",
            "这个人",
            "此人",
        ),
    ),
)
_SET_REFERENT_SUBJECT_NOUNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("company", ("公司", "企业", "厂商", "供应商")),
    ("paper", ("论文",)),
    ("patent", ("专利",)),
    ("professor", ("教授", "专家")),
)
_SINGULAR_PERSON_PRONOUN_PATTERN = re.compile(
    r"(?:^|[\s，,。.；;？?！!那这])[他她](?:的|是否)?(?!们)"
)


def referent_subject_domain(query: str) -> str | None:
    """Domain of the referent itself, when the query discloses it.

    Returns None when the referent type is undisclosed (bare 它, bare 这些):
    callers must treat that as "no type constraint", never as evidence of a
    mismatch.
    """
    if has_singular_referent(query):
        if _SINGULAR_PERSON_PRONOUN_PATTERN.search(query) is not None:
            return "professor"
        for domain, markers in _SINGULAR_REFERENT_SUBJECT_MARKERS:
            if any(marker in query for marker in markers):
                return domain
        return None
    if has_set_referent(query):
        if "他们" in query or "她们" in query:
            return "professor"
        for domain, markers in _SET_REFERENT_SUBJECT_NOUNS:
            if any(marker in query for marker in markers):
                return domain
        return None
    return None


# A set referent can be resolved inside the query itself ("…厂商，他们…"):
# the antecedent noun phrase precedes the referent, so nothing needs the
# conversation context. Only nouns that actually head enumerable sets count.
_SET_ANTECEDENT_NOUNS: tuple[str, ...] = (
    "厂商",
    "企业",
    "公司",
    "供应商",
    "品牌",
    "厂家",
    "机构",
    "高校",
    "院校",
    "教授",
    "专家",
    "团队",
    "产品",
    "论文",
    "专利",
)
_SET_REFERENT_PREFIXES: tuple[str, ...] = (
    "他们",
    "她们",
    "它们",
    "这些",
    "上述",
    "以上",
    "其中",
)


def has_internal_set_antecedent(query: str) -> bool:
    """Whether the query carries its own set antecedent before the referent."""
    positions = [
        index for marker in _SET_REFERENT_PREFIXES if (index := query.find(marker)) >= 0
    ]
    if not positions:
        return False
    prefix = query[: min(positions)]
    return any(noun in prefix for noun in _SET_ANTECEDENT_NOUNS)


# Exact external identifiers that pin one object without any session context.
IDENTIFIER_PATTERN = re.compile(r"\b(?:CN|WO|US|EP)[A-Z0-9.-]{5,}\b", re.I)

# A title carried inside the query itself: a long Latin-script run (paper
# titles like "pFedGPA: Diffusion-based …") or a 《…》 quoted title. When one is
# present, a following "这篇论文" is cataphoric, not an unbound referent.
LONG_LATIN_TITLE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9:+()&',./\-–— ]{15,}")
QUOTED_TITLE_PATTERN = re.compile(r"《[^》]{2,}》")

COMPANY_NAME_PATTERN = re.compile(
    r"([一-鿿A-Za-z0-9（）()·-]{2,80}(?:有限责任公司|股份有限公司|有限公司|公司))"
)

PROFESSOR_NAME_PATTERN = re.compile(
    r"^(?:请问|请介绍|介绍一下|我想了解|帮我查(?:一下)?)?\s*"
    r"(?P<name>[一-鿿A-Za-z·]{2,40}?)(?:教授|老师)"
    r"(?:的)?(?:研究方向|简介|信息|论文|专利|公司|情况|资料).*$"
)

_INSTITUTION_TERM = r"(?:清华|北大|[一-鿿]{2,20}(?:大学|学院|研究院))"
_INSTITUTION_PERSON_PATTERNS = (
    _INSTITUTION_TERM + r"(?:的)?(?P<name>[一-鿿·]{2,4})(?:教授|老师)?[？?。！!]?\Z",
    _INSTITUTION_TERM + r"(?:的)?(?P<name>[一-鿿·]{2,4}?)(?:教授|老师)?(?:的)?"
    r"(?=(?:评价|简介|信息|情况|研究方向|论文|专利))",
)


def extract_leading_company_name(query: str) -> str | None:
    """Extract an explicit leading Company name from a standalone query."""
    match = re.match(
        r"^(?P<name>[一-鿿A-Za-z0-9（）()·-]{2,40}?)"
        r"(?=这家公司|(?:公司|企业)(?:情况|信息|简介))",
        query.strip(),
    )
    if match is None:
        return None
    name = match.group("name").strip()
    if any(marker in name for marker in ("哪些", "什么", "如何", "上述")):
        return None
    return name


def extract_institution_person_name(query: str) -> str | None:
    """Extract an explicit institution-bound person name from a query."""
    for pattern in _INSTITUTION_PERSON_PATTERNS:
        match = re.search(pattern, query.strip())
        if match is not None:
            return match.group("name")
    return None


_PROFESSOR_NAME_STOPWORDS = frozenset(
    {"这位", "这名", "那位", "那名", "该", "此", "本", "一位", "一名"}
)

# A company-suffix match built from referent/question words ("这些公司",
# "哪些公司", "这家公司") is an anaphora or a quantifier, never a name.
_EXPLICIT_COMPANY_REJECT_MARKERS = (
    "这",
    "那",
    "该",
    "此",
    "哪些",
    "什么",
    "怎么",
    "如何",
    "哪里",
    "几",
    "多少",
    "其他",
    "别的",
    "上述",
    "以上",
    "每",
    "各",
)


def _has_explicit_company_name(query: str) -> bool:
    return any(
        not any(marker in match.group(1) for marker in _EXPLICIT_COMPANY_REJECT_MARKERS)
        for match in COMPANY_NAME_PATTERN.finditer(query)
    )


def has_explicit_named_subject(query: str) -> bool:
    """Whether the query itself names a resolvable subject.

    A referent pronoun may still resolve without any session anchor when the
    same query names its subject explicitly ("介绍清华的丁文伯，他的论文有哪些"),
    so extraction runs clause by clause. Referent determiners ("这位老师")
    are not names.
    """
    if IDENTIFIER_PATTERN.search(query) is not None:
        return True
    if LONG_LATIN_TITLE_PATTERN.search(query) is not None:
        return True
    if QUOTED_TITLE_PATTERN.search(query) is not None:
        return True
    if _has_explicit_company_name(query):
        return True

    def _clause_names_subject(clause: str) -> bool:
        if extract_leading_company_name(clause) is not None:
            return True
        professor_match = PROFESSOR_NAME_PATTERN.match(clause)
        if (
            professor_match is not None
            and professor_match.group("name").strip() not in _PROFESSOR_NAME_STOPWORDS
        ):
            return True
        return extract_institution_person_name(clause) is not None

    return any(
        _clause_names_subject(clause)
        for clause in re.split(r"[，,。；;！!？?\n]+", query)
        if clause.strip()
    )


def has_singular_referent(query: str) -> bool:
    """Whether the query refers to one active anchor entity."""
    return any(marker in query for marker in SINGULAR_REFERENT_MARKERS) or bool(
        _SINGULAR_PRONOUN_PATTERN.search(query)
    )


def has_set_referent(query: str) -> bool:
    """Whether the query refers to the displayed result set."""
    return any(marker in query for marker in SET_REFERENT_MARKERS)


def strip_leading_pronoun(query: str) -> str:
    """Remove one leading referent pronoun so entity context can take its place."""
    stripped = _LEADING_PRONOUN_PATTERN.sub(" ", query, count=1).strip()
    return stripped or query


__all__ = [
    "COMPANY_NAME_PATTERN",
    "IDENTIFIER_PATTERN",
    "PROFESSOR_NAME_PATTERN",
    "SET_REFERENT_MARKERS",
    "SINGULAR_REFERENT_MARKERS",
    "extract_institution_person_name",
    "extract_leading_company_name",
    "has_continuation_intent",
    "has_explicit_named_subject",
    "has_internal_set_antecedent",
    "has_set_referent",
    "has_singular_referent",
    "referent_domain_hint",
    "referent_subject_domain",
    "strip_leading_pronoun",
]

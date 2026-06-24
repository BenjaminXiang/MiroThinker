from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Callable, Literal
from uuid import UUID

from src.data_agents.storage.postgres.professor_profile_section import (
    ProfessorProfileSectionInput,
    upsert_professor_profile_section,
)


ResearchOverviewBuildStatus = Literal[
    "section_ready",
    "missing_source",
    "translation_required",
    "invalid_translation",
]
ResearchOverviewTranslator = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class ResearchOverviewBuildResult:
    professor_id: str
    status: ResearchOverviewBuildStatus
    section: ProfessorProfileSectionInput | None
    reason: str | None = None


_RESEARCH_SECTION_LABELS = (
    "研究领域介绍",
    "研究领域",
    "研究方向",
    "研究兴趣",
    "研究概况",
    "研究简介",
    "Research Overview",
    "Research Interests",
    "Research Direction",
    "Research Directions",
    "Research Area",
    "Research Areas",
    "Research",
)

_SECTION_STOP_LABELS = (
    "教育经历",
    "教育背景",
    "工作经历",
    "个人简介",
    "学术兼职",
    "奖励荣誉",
    "荣誉奖励",
    "研究成果",
    "主要项目",
    "项目",
    "代表论文",
    "发表论文",
    "论文",
    "招生",
    "联系方式",
    "邮箱",
    "Education",
    "Experience",
    "Biography",
    "Publications",
    "Selected Publications",
    "Teaching",
    "Awards",
    "Contact",
    "Email",
)

_CHINESE_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_WHITESPACE_RE = re.compile(r"\s+")
_URL_OR_EMAIL_RE = re.compile(
    r"(https?://|www\.|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})",
    flags=re.IGNORECASE,
)
_RESEARCH_OVERVIEW_SOURCE_NOISE_TERMS = (
    "科研详情",
    "研究课题可参考",
    "学术主页",
    "个人主页",
    "个人网站",
    "谷歌学术",
    "Google Scholar",
    "ResearchGate",
    "ORCID",
    "招生",
    "研究生",
    "发送简历",
    "欢迎报考",
    "联系方式",
    "联系电话",
    "邮箱",
    "代表论著",
    "发表论文",
    "论文清单",
    "主讲课程",
    "教学课程",
)


def build_research_overview_section(
    *,
    professor_id: str,
    profile_raw_text: str | None,
    source_page_id: UUID | str | None = None,
    run_id: UUID | str | None = None,
    translator: ResearchOverviewTranslator | None = None,
) -> ResearchOverviewBuildResult:
    candidate = extract_research_overview_text(profile_raw_text)
    if candidate is None:
        return ResearchOverviewBuildResult(
            professor_id=professor_id,
            status="missing_source",
            section=None,
            reason="research_overview_not_found",
        )

    source_language = _detect_language(candidate)
    if source_language == "zh":
        if _research_overview_source_needs_llm_cleaning(candidate):
            if translator is None:
                return ResearchOverviewBuildResult(
                    professor_id=professor_id,
                    status="translation_required",
                    section=None,
                    reason="chinese_source_requires_cleaner",
                )
            cleaned = _clean_inline_text(translator(candidate))
            validation_errors = validate_chinese_research_overview(cleaned)
            if validation_errors:
                return ResearchOverviewBuildResult(
                    professor_id=professor_id,
                    status="invalid_translation",
                    section=None,
                    reason=";".join(validation_errors),
                )
            return ResearchOverviewBuildResult(
                professor_id=professor_id,
                status="section_ready",
                section=ProfessorProfileSectionInput(
                    professor_id=professor_id,
                    section_type="research_overview",
                    language="zh",
                    content=cleaned,
                    source_page_id=source_page_id,
                    source_language="zh",
                    source_text=candidate,
                    source_text_hash=_hash_text(candidate),
                    source_span=candidate,
                    generation_method="llm_cleaning",
                    run_id=run_id,
                ),
            )

        validation_errors = validate_chinese_research_overview(candidate)
        if validation_errors:
            return ResearchOverviewBuildResult(
                professor_id=professor_id,
                status="invalid_translation",
                section=None,
                reason=";".join(validation_errors),
            )
        return ResearchOverviewBuildResult(
            professor_id=professor_id,
            status="section_ready",
            section=ProfessorProfileSectionInput(
                professor_id=professor_id,
                section_type="research_overview",
                language="zh",
                content=candidate,
                source_page_id=source_page_id,
                source_language="zh",
                source_text=candidate,
                source_text_hash=_hash_text(candidate),
                source_span=candidate,
                generation_method="official_extract",
                run_id=run_id,
            ),
        )

    if translator is None:
        return ResearchOverviewBuildResult(
            professor_id=professor_id,
            status="translation_required",
            section=None,
            reason="english_source_requires_translator",
        )

    translated = _clean_inline_text(translator(candidate))
    validation_errors = validate_chinese_research_overview(translated)
    if validation_errors:
        return ResearchOverviewBuildResult(
            professor_id=professor_id,
            status="invalid_translation",
            section=None,
            reason=";".join(validation_errors),
        )
    return ResearchOverviewBuildResult(
        professor_id=professor_id,
        status="section_ready",
        section=ProfessorProfileSectionInput(
            professor_id=professor_id,
            section_type="research_overview",
            language="zh",
            content=translated,
            source_page_id=source_page_id,
            source_language=source_language,
            source_text=candidate,
            source_text_hash=_hash_text(candidate),
            source_span=candidate,
            generation_method="llm_translation",
            run_id=run_id,
        ),
    )


def extract_research_overview_text(profile_raw_text: str | None) -> str | None:
    if not isinstance(profile_raw_text, str) or not profile_raw_text.strip():
        return None
    raw = _clean_inline_text(profile_raw_text)
    label_matches = sorted(
        {
            match.span(): match
            for label in _RESEARCH_SECTION_LABELS
            for match in re.finditer(re.escape(label), raw, flags=re.IGNORECASE)
        }.values(),
        key=lambda match: match.start(),
    )
    for label_match in label_matches:
        body = raw[label_match.end() :].strip(" :：-")
        if not body:
            continue
        if _starts_with_stop_label(body):
            continue
        stop_positions = [
            match.start()
            for label in _SECTION_STOP_LABELS
            if (
                match := re.search(
                    re.escape(label),
                    body,
                    flags=re.IGNORECASE,
                )
            )
            is not None
            and match.start() > 12
        ]
        if stop_positions:
            body = body[: min(stop_positions)]
        overview = _clean_inline_text(body).strip(" ;；")
        if len(overview) >= 12:
            return overview
    return None


def _starts_with_stop_label(text: str) -> bool:
    prefix = text[:80].lstrip(" :：-")
    return any(
        re.match(re.escape(label), prefix, flags=re.IGNORECASE)
        for label in _SECTION_STOP_LABELS
    )


def persist_research_overview_section(
    conn,
    result: ResearchOverviewBuildResult,
) -> str | UUID | None:
    if result.status != "section_ready" or result.section is None:
        return None
    return upsert_professor_profile_section(conn, result.section).section_id


def validate_chinese_research_overview(text: str | None) -> list[str]:
    cleaned = _clean_inline_text(text or "")
    if not _CHINESE_CHAR_RE.search(cleaned):
        return ["missing_chinese_text"]
    if len(cleaned) < 10:
        return ["too_short"]
    if _research_overview_cleaned_text_has_noise(cleaned):
        return ["source_noise_retained"]
    return []


def _detect_language(text: str) -> Literal["zh", "en"]:
    chinese_chars = len(_CHINESE_CHAR_RE.findall(text))
    return "zh" if chinese_chars >= 4 else "en"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_inline_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(text)).strip()


def _research_overview_source_needs_llm_cleaning(text: str) -> bool:
    cleaned = _clean_inline_text(text)
    if len(cleaned) > 500:
        return True
    if _URL_OR_EMAIL_RE.search(cleaned):
        return True
    return any(term.lower() in cleaned.lower() for term in _RESEARCH_OVERVIEW_SOURCE_NOISE_TERMS)


def _research_overview_cleaned_text_has_noise(text: str) -> bool:
    cleaned = _clean_inline_text(text)
    if _URL_OR_EMAIL_RE.search(cleaned):
        return True
    lower = cleaned.lower()
    noisy_terms = (
        "科研详情",
        "研究课题可参考",
        "学术主页",
        "个人主页",
        "个人网站",
        "谷歌学术",
        "google scholar",
        "researchgate",
        "orcid",
        "招生",
        "发送简历",
        "欢迎报考",
        "联系方式",
        "联系电话",
        "邮箱",
        "代表论著",
        "发表论文",
        "论文清单",
        "主讲课程",
        "教学课程",
    )
    return any(term in lower for term in noisy_terms)

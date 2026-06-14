from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


_EMPTY_MARKERS = {"", "-", "--", "—", "－"}
_NAME_SPLIT_RE = re.compile(r"[，,:：\s]+")


@dataclass(frozen=True, slots=True)
class ParsedTeamMember:
    raw_name: str
    raw_role: str | None
    raw_intro: str | None


@dataclass(frozen=True, slots=True)
class StructuredTeamMember:
    name: str
    role: str | None
    background: str | None
    experience_highlights: tuple[str, ...]
    relevance: str | None
    confidence: float
    evidence_span: str
    raw_text: str


def parse_team_raw(raw: str | None) -> list[ParsedTeamMember]:
    """Parse the xlsx 团队 cell into structured team-member records."""
    normalized = (raw or "").strip()
    if normalized in _EMPTY_MARKERS:
        return []

    members: list[ParsedTeamMember] = []
    for segment in _split_member_segments(normalized):
        member = _parse_segment(segment)
        if member is not None:
            members.append(member)
    return members


def structure_team_raw_with_llm(
    raw: str | None,
    *,
    company_name: str,
    llm_client: Any | None,
    llm_model: str,
    extra_body: dict[str, Any] | None = None,
) -> list[StructuredTeamMember]:
    """Structure XLSX team_raw without dropping the original source text."""
    raw_text = (raw or "").strip()
    parsed = parse_team_raw(raw_text)
    if not raw_text or not parsed:
        return []
    if llm_client is None:
        return _fallback_structured_members(parsed, raw_text)

    prompt = "\n".join(
        [
            "Structure company team text into source-grounded JSON.",
            "Use only the supplied XLSX team_raw text. Do not invent education, employer, title, or founder facts.",
            "Return strict JSON: {\"members\":[{\"name\":...,\"role\":...,\"background\":...,\"experience_highlights\":[...],\"relevance\":...,\"confidence\":0.0,\"evidence_span\":...}]}",
            "",
            f"Company: {company_name}",
            "XLSX team_raw:",
            raw_text[:3500],
        ]
    )
    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You structure source-grounded company team facts and output JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
            extra_body=extra_body or {},
        )
    except Exception:
        return _fallback_structured_members(parsed, raw_text)

    payload = _extract_json_object((response.choices[0].message.content or "").strip())
    members = _coerce_structured_members(payload, raw_text=raw_text)
    return members or _fallback_structured_members(parsed, raw_text)


def _split_member_segments(raw: str) -> list[str]:
    segments: list[str] = []
    current: list[str] = []

    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if current and _looks_like_member_start(stripped):
            segments.append("\n".join(current).strip())
            current = [stripped]
            continue
        current.append(stripped)

    if current:
        segments.append("\n".join(current).strip())
    return segments


def _looks_like_member_start(line: str) -> bool:
    return "，职务：" in line or "，介绍：" in line


def _parse_segment(segment: str) -> ParsedTeamMember | None:
    text = segment.strip()
    if not text:
        return None

    try:
        raw_name: str
        raw_role: str | None = None
        raw_intro: str | None = None

        if "，职务：" in text:
            raw_name, remainder = text.split("，职务：", 1)
            raw_name = _clean_name(raw_name)
            if "，介绍：" in remainder:
                raw_role_value, raw_intro_value = remainder.split("，介绍：", 1)
                raw_role = _clean_optional(raw_role_value)
                raw_intro = _clean_optional(raw_intro_value)
            else:
                raw_role = _clean_optional(remainder)
        elif "，介绍：" in text:
            raw_name, raw_intro_value = text.split("，介绍：", 1)
            raw_name = _clean_name(raw_name)
            raw_intro = _clean_optional(raw_intro_value)
        else:
            return _fallback_member(text)

        if not raw_name:
            return _fallback_member(text)
        return ParsedTeamMember(
            raw_name=raw_name,
            raw_role=raw_role,
            raw_intro=raw_intro,
        )
    except Exception:
        return _fallback_member(text)


def _fallback_member(text: str) -> ParsedTeamMember:
    stripped = text.strip()
    if not stripped:
        return ParsedTeamMember(raw_name="unknown", raw_role=None, raw_intro=None)

    token_source, separator, remainder = stripped.partition("，")
    best_name = _clean_name(token_source) if separator else _best_guess_name(stripped)
    if not best_name:
        best_name = _best_guess_name(stripped) or stripped

    intro = None
    if separator:
        intro = _clean_optional(remainder)
    elif best_name != stripped:
        intro = _clean_optional(stripped[len(best_name) :])

    return ParsedTeamMember(raw_name=best_name, raw_role=None, raw_intro=intro)


def _best_guess_name(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    parts = [part for part in _NAME_SPLIT_RE.split(stripped, maxsplit=1) if part]
    return parts[0].strip() if parts else stripped


def _clean_name(value: str) -> str:
    return value.strip().strip("，,")


def _clean_optional(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _fallback_structured_members(
    members: list[ParsedTeamMember], raw_text: str
) -> list[StructuredTeamMember]:
    structured: list[StructuredTeamMember] = []
    for member in members:
        evidence = member.raw_intro or member.raw_role or member.raw_name
        highlights = (member.raw_intro,) if member.raw_intro else ()
        structured.append(
            StructuredTeamMember(
                name=member.raw_name,
                role=member.raw_role,
                background=member.raw_intro,
                experience_highlights=highlights,
                relevance=member.raw_intro or member.raw_role,
                confidence=0.55,
                evidence_span=evidence,
                raw_text=raw_text,
            )
        )
    return structured


def _extract_json_object(raw_text: str) -> Any:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw_text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _coerce_structured_members(payload: Any, *, raw_text: str) -> list[StructuredTeamMember]:
    if not isinstance(payload, dict) or not isinstance(payload.get("members"), list):
        return []
    members: list[StructuredTeamMember] = []
    for value in payload["members"]:
        if not isinstance(value, dict):
            continue
        name = _clean_optional(str(value.get("name") or ""))
        if not name or name not in raw_text:
            continue
        evidence = _clean_optional(str(value.get("evidence_span") or "")) or name
        if evidence not in raw_text:
            evidence = name
        members.append(
            StructuredTeamMember(
                name=name,
                role=_clean_optional(str(value.get("role") or "")),
                background=_clean_optional(str(value.get("background") or "")),
                experience_highlights=tuple(_string_list(value.get("experience_highlights"))),
                relevance=_clean_optional(str(value.get("relevance") or "")),
                confidence=_coerce_confidence(value.get("confidence")),
                evidence_span=evidence,
                raw_text=raw_text,
            )
        )
    return members


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.65
    return min(max(confidence, 0.0), 1.0)

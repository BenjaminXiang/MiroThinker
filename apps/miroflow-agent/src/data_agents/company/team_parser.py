from __future__ import annotations

from dataclasses import dataclass
import re


_EMPTY_MARKERS = {"", "-", "--", "—", "－"}
_NAME_SPLIT_RE = re.compile(r"[，,:：\s]+")


@dataclass(frozen=True, slots=True)
class ParsedTeamMember:
    raw_name: str
    raw_role: str | None
    raw_intro: str | None


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

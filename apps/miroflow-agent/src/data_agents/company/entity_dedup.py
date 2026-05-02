from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha1
import re

from src.data_agents.normalization import normalize_company_name

_PUNCT_RE = re.compile(r"[\s\-_·•.,，。:：;；()（）\[\]【】{}<>《》\"'“”‘’/\\|]+")


@dataclass(frozen=True, slots=True)
class CompanyAliasMatch:
    left_normalized: str
    right_normalized: str
    jaccard_score: float
    is_match: bool
    reasoning: str


@dataclass(frozen=True, slots=True)
class SignalEventDedupDecision:
    dedup_key: str
    reasoning: str


def normalize_name(name: str | None) -> str:
    """Normalize company aliases for local fuzzy matching."""
    normalized = normalize_company_name(name or "")
    normalized = _PUNCT_RE.sub("", normalized).lower()
    return normalized.strip()


def jaccard_similarity(left: str | None, right: str | None) -> float:
    left_tokens = _tokenize_for_jaccard(normalize_name(left))
    right_tokens = _tokenize_for_jaccard(normalize_name(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def match_company_alias(
    left: str | None,
    right: str | None,
    *,
    threshold: float = 0.72,
) -> CompanyAliasMatch:
    left_normalized = normalize_name(left)
    right_normalized = normalize_name(right)
    score = jaccard_similarity(left_normalized, right_normalized)
    exact_match = bool(left_normalized and left_normalized == right_normalized)
    is_match = exact_match or score >= threshold
    if exact_match:
        reason = "normalized_names_equal"
    elif is_match:
        reason = f"jaccard_score_above_threshold:{score:.3f}>={threshold:.3f}"
    else:
        reason = f"jaccard_score_below_threshold:{score:.3f}<{threshold:.3f}"
    return CompanyAliasMatch(
        left_normalized=left_normalized,
        right_normalized=right_normalized,
        jaccard_score=round(score, 6),
        is_match=is_match,
        reasoning=reason,
    )


def build_signal_event_dedup_key(
    *, company_id: str, event_type: str, event_date: date | datetime | str
) -> str:
    normalized_date = _normalize_event_date(event_date)
    natural_key = f"{company_id.strip()}|{event_type.strip()}|{normalized_date}"
    return sha1(natural_key.encode("utf-8")).hexdigest()[:20]


def explain_signal_event_dedup_key(
    *, company_id: str, event_type: str, event_date: date | datetime | str
) -> SignalEventDedupDecision:
    normalized_date = _normalize_event_date(event_date)
    dedup_key = build_signal_event_dedup_key(
        company_id=company_id,
        event_type=event_type,
        event_date=normalized_date,
    )
    return SignalEventDedupDecision(
        dedup_key=dedup_key,
        reasoning=(
            "dedup_key=sha1(company_id|event_type|event_date)[:20]; "
            f"company_id={company_id.strip()}, event_type={event_type.strip()}, "
            f"event_date={normalized_date}"
        ),
    )


def _tokenize_for_jaccard(value: str) -> set[str]:
    if not value:
        return set()
    if len(value) <= 2:
        return set(value)
    return {value[index : index + 2] for index in range(len(value) - 1)}


def _normalize_event_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        raise ValueError("event_date is required for signal event dedup")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]

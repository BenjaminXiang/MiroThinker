"""M1 Unit 1 — name variant resolver.

Given a professor's canonical name fields (any of: free-form canonical_name,
canonical_name_zh, canonical_name_en), produce all plausible textual forms
the same person's name might take across OpenAlex / arxiv / homepage sources.

Used by paper_identity_gate v2 to render a richer prompt so the LLM can
correctly match same-person papers across CJK/Latin/pinyin renderings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


@dataclass(frozen=True, slots=True)
class NameVariants:
    """All plausible textual forms of a single professor's name.

    Each field may be None / empty when the source data doesn't support it.
    `all_lower` is a deduped tuple of all non-empty variants lowercased, useful
    for set-membership token checks downstream.
    """

    zh: str | None
    en: str | None
    pinyin: str | None
    initials: tuple[str, ...]
    all_lower: tuple[str, ...]


def _contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _is_latin_only(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    return not _contains_cjk(stripped)


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = text.strip()
    return cleaned or None


def _split_latin_tokens(latin: str) -> list[str]:
    return [tok for tok in re.split(r"\s+", latin.strip()) if tok]


def _build_initials(latin: str | None) -> tuple[str, ...]:
    """For 'Jianquan Yao' → ('J. Yao', 'J.Q. Yao'). Surname = last token."""
    if not latin:
        return ()
    tokens = _split_latin_tokens(latin)
    if len(tokens) < 2:
        return ()
    surname = tokens[-1]
    given_tokens = tokens[:-1]

    variants: list[str] = []

    # Single-initial form: "J. Yao"
    if given_tokens:
        first_initial = given_tokens[0][:1].upper()
        if first_initial:
            variants.append(f"{first_initial}. {surname}")

    # Full-initials form: "J.Q. Yao" for multi-token given names
    if len(given_tokens) > 1:
        all_initials = ".".join(tok[:1].upper() for tok in given_tokens if tok)
        if all_initials:
            variants.append(f"{all_initials}. {surname}")

    # Dedupe while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return tuple(unique)


def _cjk_to_pinyin(zh: str) -> str | None:
    """Return a space-joined lowercase pinyin string, or None on failure."""
    if not zh:
        return None
    try:
        from pypinyin import Style, lazy_pinyin

        parts = lazy_pinyin(zh, style=Style.NORMAL)
    except Exception:  # noqa: BLE001 — pypinyin internal errors shouldn't break callers
        return None
    if not parts:
        return None
    joined = " ".join(p for p in parts if p).strip().lower()
    return joined or None


def resolve_name_variants(
    canonical_name: str | None,
    canonical_name_zh: str | None,
    canonical_name_en: str | None,
) -> NameVariants:
    """Build a NameVariants from any combination of input name fields.

    All inputs are optional. Missing fields produce None / empty output
    for that variant category. Never raises on empty/None inputs.
    """
    canonical = _clean(canonical_name)
    zh_field = _clean(canonical_name_zh)
    en_field = _clean(canonical_name_en)

    # Infer zh when canonical_name is CJK and no explicit zh field.
    if zh_field is None and canonical and _contains_cjk(canonical):
        zh_field = canonical

    # Infer en when canonical_name is Latin-only and no explicit en field.
    if en_field is None and canonical and _is_latin_only(canonical):
        en_field = canonical

    pinyin = _cjk_to_pinyin(zh_field) if zh_field else None
    initials = _build_initials(en_field)

    # Build all_lower — deduped lowercased tuple of every non-empty form.
    all_forms: list[str] = []
    if zh_field:
        all_forms.append(zh_field)
    if en_field:
        all_forms.append(en_field)
    if pinyin:
        all_forms.append(pinyin)
    for initial in initials:
        all_forms.append(initial)

    seen: set[str] = set()
    all_lower: list[str] = []
    for form in all_forms:
        lowered = form.lower()
        if lowered not in seen:
            seen.add(lowered)
            all_lower.append(lowered)

    return NameVariants(
        zh=zh_field,
        en=en_field,
        pinyin=pinyin,
        initials=initials,
        all_lower=tuple(all_lower),
    )

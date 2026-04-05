from __future__ import annotations

from collections.abc import Callable, Mapping


def build_normalized_index(
    values: Mapping[str, str],
    *,
    normalizer: Callable[[str], str],
) -> dict[str, str | None]:
    index: dict[str, str | None] = {}
    for key, value in values.items():
        normalized = normalizer(key)
        if not normalized:
            continue
        existing = index.get(normalized)
        if existing is None and normalized in index:
            continue
        if existing is not None and existing != value:
            index[normalized] = None
            continue
        index[normalized] = value
    return index


def link_normalized_values(
    candidates: list[str],
    index: Mapping[str, str | None],
    *,
    normalizer: Callable[[str], str],
) -> list[str]:
    matched: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalizer(candidate)
        target = index.get(normalized)
        if not target or target in seen:
            continue
        seen.add(target)
        matched.append(target)
    return matched

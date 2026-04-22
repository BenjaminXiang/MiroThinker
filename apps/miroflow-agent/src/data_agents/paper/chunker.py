from __future__ import annotations

import re
from dataclasses import dataclass

_MAX_CHUNK_CHARS = 500
_SEGMENT_SPLIT_RE = re.compile(r"\.\s*\n|\n\n")


@dataclass(frozen=True, slots=True)
class PaperChunk:
    chunk_id: str
    paper_id: str
    chunk_type: str
    segment_index: int
    year: int | None
    venue: str | None
    content_text: str


def chunk_paper(
    *,
    paper_id: str,
    title: str,
    year: int | None,
    venue: str | None,
    abstract: str | None = None,
    intro: str | None = None,
) -> list[PaperChunk]:
    normalized_title = title.strip()
    if not normalized_title:
        return []

    chunks = [
        PaperChunk(
            chunk_id=_chunk_id(paper_id, "title", 0),
            paper_id=paper_id,
            chunk_type="title",
            segment_index=0,
            year=year,
            venue=venue,
            content_text=normalized_title,
        )
    ]
    chunks.extend(
        _chunk_optional_text(
            paper_id=paper_id,
            chunk_type="abstract",
            year=year,
            venue=venue,
            text=abstract,
            max_segments=3,
        )
    )
    chunks.extend(
        _chunk_optional_text(
            paper_id=paper_id,
            chunk_type="intro",
            year=year,
            venue=venue,
            text=intro,
            max_segments=4,
        )
    )
    return chunks


def _chunk_optional_text(
    *,
    paper_id: str,
    chunk_type: str,
    year: int | None,
    venue: str | None,
    text: str | None,
    max_segments: int,
) -> list[PaperChunk]:
    if text is None:
        return []

    normalized_text = text.strip()
    if not normalized_text:
        return []

    if len(normalized_text) <= _MAX_CHUNK_CHARS:
        return [
            PaperChunk(
                chunk_id=_chunk_id(paper_id, chunk_type, 0),
                paper_id=paper_id,
                chunk_type=chunk_type,
                segment_index=0,
                year=year,
                venue=venue,
                content_text=normalized_text,
            )
        ]

    raw_segments = _SEGMENT_SPLIT_RE.split(normalized_text)
    segments: list[str] = []
    for raw_segment in raw_segments:
        cleaned_segment = raw_segment.strip()
        if not cleaned_segment:
            continue
        if len(cleaned_segment) <= _MAX_CHUNK_CHARS:
            segments.append(cleaned_segment)
            if len(segments) >= max_segments:
                break
            continue

        start = 0
        while start < len(cleaned_segment) and len(segments) < max_segments:
            segments.append(cleaned_segment[start : start + _MAX_CHUNK_CHARS])
            start += _MAX_CHUNK_CHARS

        if len(segments) >= max_segments:
            break

    return [
        PaperChunk(
            chunk_id=_chunk_id(paper_id, chunk_type, index),
            paper_id=paper_id,
            chunk_type=chunk_type,
            segment_index=index,
            year=year,
            venue=venue,
            content_text=segment,
        )
        for index, segment in enumerate(segments)
    ]


def _chunk_id(paper_id: str, chunk_type: str, segment_index: int) -> str:
    return f"{paper_id}:{chunk_type}:{segment_index}"

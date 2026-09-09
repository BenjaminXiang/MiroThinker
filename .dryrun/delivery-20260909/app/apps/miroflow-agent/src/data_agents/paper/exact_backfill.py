from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, TypeVar

from src.data_agents.contracts import PaperRecord, ReleasedObject

from .models import DiscoveredPaper


T = TypeVar("T")


def load_exact_backfill_papers(paths: Iterable[Path]) -> list[DiscoveredPaper]:
    papers: list[DiscoveredPaper] = []
    for path in paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            papers.append(
                DiscoveredPaper(
                    paper_id=str(payload["paper_id"]),
                    title=str(payload["title"]),
                    year=int(payload["year"]),
                    publication_date=payload.get("publication_date"),
                    venue=payload.get("venue"),
                    doi=payload.get("doi"),
                    arxiv_id=payload.get("arxiv_id"),
                    abstract=payload.get("abstract"),
                    authors=tuple(str(item) for item in payload.get("authors", [])),
                    professor_ids=tuple(
                        str(item) for item in payload.get("professor_ids", [])
                    ),
                    citation_count=payload.get("citation_count"),
                    source_url=str(payload["source_url"]),
                    fields_of_study=tuple(
                        str(item) for item in payload.get("fields_of_study", [])
                    ),
                    tldr=payload.get("tldr"),
                    license=payload.get("license"),
                    funders=tuple(str(item) for item in payload.get("funders", [])),
                    oa_status=payload.get("oa_status"),
                    reference_count=payload.get("reference_count"),
                    enrichment_sources=tuple(
                        str(item) for item in payload.get("enrichment_sources", [])
                    ),
                )
            )
    return papers


def merge_release_outputs_by_id(
    primary_records: list[PaperRecord],
    primary_objects: list[ReleasedObject],
    supplemental_records: list[PaperRecord],
    supplemental_objects: list[ReleasedObject],
) -> tuple[list[PaperRecord], list[ReleasedObject]]:
    return (
        _merge_models_by_id(primary_records, supplemental_records),
        _merge_models_by_id(primary_objects, supplemental_objects),
    )


def _merge_models_by_id(primary: list[T], supplemental: list[T]) -> list[T]:
    merged: dict[str, T] = {}
    for item in [*primary, *supplemental]:
        item_id = getattr(item, "id")
        merged[item_id] = item
    return list(merged.values())

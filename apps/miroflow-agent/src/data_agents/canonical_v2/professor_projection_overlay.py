"""Sidecar overlay that adds professor paper evidence to claims.

The serving pack is hash-checked at boot, so the projection produced offline
(gate 3.2 allowlist) cannot be written into `lookup.sqlite3`. Instead the runtime
can opt into a JSON sidecar and merge two fields into the professor payload the
claim builder already renders:

- ``paper_count`` — the number of papers in the pack's relationship graph;
- ``top_papers``  — up to three representative papers (title, year).

Rules (precision first — see `coherence-calibration.md`):

- only professors present in the overlay are touched;
- an existing ``paper_count`` in the pack is never overwritten;
- records flagged ``duplicate_name`` are ignored, because two people sharing a
  name cannot be told apart by that evidence;
- a missing or malformed file disables the overlay (the runtime keeps today's
  behaviour) instead of failing the request.

The path comes from ``CANONICAL_V2_PROFESSOR_PROJECTION``; unset means off.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

ENV_VAR = "CANONICAL_V2_PROFESSOR_PROJECTION"
TOP_PAPER_LIMIT = 3
_SKIP_FLAGS = frozenset({"duplicate_name"})


class ProfessorProjectionOverlay:
    """Immutable lookup over the allowlist, keyed by professor canonical id."""

    def __init__(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        self._records = {
            key: record
            for key, record in records.items()
            if isinstance(record, Mapping)
            and not (_SKIP_FLAGS & set(record.get("flags") or ()))
        }

    def __len__(self) -> int:
        return len(self._records)

    def apply(self, professor_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return a payload with the overlay fields merged in (never overwritten)."""
        record = self._records.get(professor_id)
        if record is None:
            return dict(payload)
        merged = dict(payload)
        count = record.get("paper_count")
        if isinstance(count, int) and merged.get("paper_count") in (None, ""):
            merged["paper_count"] = count
            merged["_paper_count_local"] = True
        top_papers = record.get("top_papers")
        if isinstance(top_papers, list) and top_papers and not merged.get("top_papers"):
            merged["top_papers"] = top_papers
        return merged

    def top_papers_text(self, teacher_payload: Mapping[str, Any]) -> str | None:
        """Render ``《title》(year)；…`` for the payload's top papers."""
        papers = teacher_payload.get("top_papers")
        if not isinstance(papers, list):
            return None
        rendered = []
        for paper in papers[:TOP_PAPER_LIMIT]:
            if not isinstance(paper, Mapping):
                continue
            title = str(paper.get("title_zh") or paper.get("title") or "").strip()
            if not title:
                continue
            year = paper.get("year")
            rendered.append(f"《{title}》{year}" if year else f"《{title}》")
        return "；".join(rendered) if rendered else None


def load_overlay(
    path: str | os.PathLike[str] | None,
) -> ProfessorProjectionOverlay | None:
    """Load the overlay from ``path``; ``None``/missing/invalid means disabled."""
    if not path:
        return None
    file_path = Path(path)
    try:
        records = json.loads(file_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        print(
            f"[professor-projection] overlay disabled: {error}",
            file=sys.stderr,
        )
        return None
    if not isinstance(records, dict):
        print(
            "[professor-projection] overlay disabled: expected a JSON object",
            file=sys.stderr,
        )
        return None
    return ProfessorProjectionOverlay(records)


_ACTIVE: ProfessorProjectionOverlay | None | bool = False


def active_overlay() -> ProfessorProjectionOverlay | None:
    """Process-wide overlay from the environment, loaded once."""
    global _ACTIVE
    if _ACTIVE is False:
        _ACTIVE = load_overlay(os.environ.get(ENV_VAR))
    return _ACTIVE if isinstance(_ACTIVE, ProfessorProjectionOverlay) else None


def reset_overlay_cache() -> None:
    """Test hook: forget the process-wide overlay."""
    global _ACTIVE
    _ACTIVE = False

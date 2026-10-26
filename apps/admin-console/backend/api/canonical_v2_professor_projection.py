"""Read-only surface for the professor×paper projection metrics.

The weekly refresh (`scripts/refresh_professor_projection.py`) writes
`metrics.json` next to the allowlist. The console only reads that file — it never
triggers a refresh, because the refresh costs minutes of embedding calls and must
run from the scheduled job, not from a page load.

Path comes from `CANONICAL_V2_PROFESSOR_PROJECTION_METRICS`; unset means the
surface is not configured (503), a missing file is 404, malformed JSON is 500.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/canonical-v2/admin/professor-projection")

METRICS_PATH_ENV = "CANONICAL_V2_PROFESSOR_PROJECTION_METRICS"


@router.get("")
def read_projection_metrics() -> dict:
    """Return the latest refresh metrics, or a bounded error."""

    configured = os.environ.get(METRICS_PATH_ENV, "").strip()
    if not configured:
        raise HTTPException(
            status_code=503,
            detail="professor_projection_metrics_not_configured",
        )
    path = Path(configured)
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="professor_projection_metrics_missing",
        )
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=500,
            detail="professor_projection_metrics_unreadable",
        ) from None
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=500,
            detail="professor_projection_metrics_unreadable",
        )
    return payload

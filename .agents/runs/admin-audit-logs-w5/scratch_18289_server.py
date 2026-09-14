"""Scratch-only ASGI launcher for the W5 audit smoke (port 18289, never 18188).

The bare V2 shell does not compose a serving-pack runtime, so the chat endpoint
cannot serve a turn here. Everything else is the real application: this launcher
only installs the real access-log store on the real app state and exposes one
scratch route that calls the real ``_record_access_turn`` choke point with the
real request object, so the ``X-Remote-User`` write path is exercised over real
HTTP.
"""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "admin-console"))

import uvicorn  # noqa: E402
from fastapi import Request  # noqa: E402

from backend.api.canonical_v2_chat import _record_access_turn  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.canonical_v2_access_log import AccessLogStore  # noqa: E402


database = Path(os.environ["CANONICAL_V2_ACCESS_LOG_DB"])
app.state.canonical_v2_access_log_store = AccessLogStore(database)
print(f"scratch access log store = {database}", flush=True)


@app.post("/scratch/record")
def scratch_record(request: Request, payload: dict) -> dict:
    """Write one turn through the real recording choke point."""

    _record_access_turn(
        request,
        session_id=payload["session_id"],
        query=payload["query"],
        chat_response=None,
        status="error",
        error_detail=payload.get("error_detail", "canonical_v2_invalid_option"),
        started_at=datetime.now(UTC),
    )
    return {"recorded": True, "session_id": payload["session_id"]}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("SCRATCH_PORT", "18289")),
        workers=1,
        reload=False,
        access_log=True,
    )

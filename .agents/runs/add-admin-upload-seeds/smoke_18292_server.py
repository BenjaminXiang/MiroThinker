"""W3 scratch launcher: the real V2 shell + the real gate + the real declared tasks on port 18292.

Unlike W2's smoke this one does NOT stub the tasks: the point of the W3 verification is that the
legacy subprocess chain runs inside the V2 shell, so the upload/seed tasks spawn exactly what they
declare (`uv run python scripts/...`) against a throwaway Postgres and scratch storage.

Usage::

    DEV_A=1 DATABASE_URL=… CANONICAL_V2_DATABASE_URL=… \
    uv run python .agents/runs/add-admin-upload-seeds/smoke_18292_server.py
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

WORKTREE = Path(__file__).resolve().parents[3]
ADMIN = WORKTREE / "apps" / "admin-console"
AGENT = WORKTREE / "apps" / "miroflow-agent"
sys.path.insert(0, str(ADMIN))
sys.path.insert(0, str(AGENT))

from backend.api.canonical_v2_jobs import build_job_runtime  # noqa: E402
from backend.api.canonical_v2_uploads import build_upload_runtime  # noqa: E402
from backend.main import _create_canonical_v2_route_shell  # noqa: E402


SCRATCH = Path(os.environ.get("W3_SCRATCH_DIR", "/var/tmp/w3-smoke-18292"))
PORT = int(os.environ.get("W3_SMOKE_PORT", "18292"))


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    settings_path = SCRATCH / "settings.json"
    if not settings_path.exists():
        settings_path.write_text('{"schema_version": 1}', encoding="utf-8")

    # The API's own builders, so the smoke exercises the production wiring (the same gate, the same
    # Postgres preflight and the same batch reader the served routes use).
    gate = build_job_runtime()
    gate._repo_root = WORKTREE  # noqa: SLF001 - the scratch server runs from the worktree
    uploads = build_upload_runtime()
    uploads.gate = gate
    app = _create_canonical_v2_route_shell()
    app.state.canonical_v2_jobs_runtime = gate
    app.state.canonical_v2_uploads_runtime = uploads
    app.state.canonical_v2_seed_gate = gate

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

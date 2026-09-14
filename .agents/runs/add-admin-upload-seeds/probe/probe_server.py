"""W3 technical verification point: can the legacy subprocess chain run inside the V2 shell?

Launched the same way the serving shell is launched (``uv run`` from ``apps/admin-console``),
because that is the environment the question is about: env pass-through, cwd, uv on PATH, timeout.

The probe reuses the W2 spawn helper unchanged (``jobs._spawn_subprocess``) so the answer applies
to the gate that W3 must go through.

Usage (from the worktree root)::

    cd apps/admin-console && uv run python ../../.agents/runs/add-admin-upload-seeds/probe/probe_server.py

Then: ``curl -s http://127.0.0.1:18292/probe`` (port 18292 is the W3 scratch port; 18188 is the
live service and is never touched).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

WORKTREE = Path(__file__).resolve().parents[4]
ADMIN = WORKTREE / "apps" / "admin-console"
AGENT = WORKTREE / "apps" / "miroflow-agent"
sys.path.insert(0, str(ADMIN))
sys.path.insert(0, str(AGENT))

from fastapi import FastAPI  # noqa: E402

from src.data_agents.canonical_v2.jobs import _spawn_subprocess  # noqa: E402

PORT = int(os.environ.get("W3_PROBE_PORT", "18292"))
SENTINEL = "w3-probe-sentinel-9f2c"

CHILD_ECHO = (
    "import json,os,shutil,sys;"
    "print(json.dumps({"
    "'argv0':sys.argv[0],"
    "'exe':sys.executable,"
    "'cwd':os.getcwd(),"
    "'sentinel':os.environ.get('W3_PROBE_SENTINEL'),"
    "'database_url_set':bool(os.environ.get('DATABASE_URL')),"
    "'quota':os.environ.get('MIROTHINKER_MAX_WEB_SEARCHES_PER_RUN'),"
    "'path_has_uv':shutil.which('uv') is not None,"
    "'path':os.environ.get('PATH',''),"
    "'uv_env_keys':sorted(k for k in os.environ if k.startswith('UV_')),"
    "'virtual_env':os.environ.get('VIRTUAL_ENV'),"
    "}))"
)
# A real legacy script import path, exercised without side effects: the enrichment runner's
# argparse help exits before any database work.
LEGACY_SCRIPT = "scripts/run_company_upload_enrichment_batch.py"

app = FastAPI()


def _run_case(name: str, argv: list[str], *, cwd: Path, timeout: int) -> dict[str, object]:
    env = dict(os.environ)
    env["W3_PROBE_SENTINEL"] = SENTINEL
    started = time.monotonic()
    record: dict[str, object] = {
        "case": name,
        "argv": argv,
        "cwd": str(cwd),
        "cwd_exists": cwd.is_dir(),
    }
    try:
        completed = _spawn_subprocess(argv, cwd=str(cwd), env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        record.update({"outcome": "timeout", "elapsed_s": round(time.monotonic() - started, 2)})
        return record
    except Exception as exc:  # noqa: BLE001 - the probe reports every failure shape
        record.update(
            {
                "outcome": "launch_error",
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_s": round(time.monotonic() - started, 2),
            }
        )
        return record
    record.update(
        {
            "outcome": "completed",
            "returncode": completed.returncode,
            "elapsed_s": round(time.monotonic() - started, 2),
            "stdout_tail": (completed.stdout or "")[-1200:],
            "stderr_tail": (completed.stderr or "")[-1200:],
        }
    )
    return record


@app.get("/probe")
def probe() -> dict[str, object]:
    python = sys.executable
    cases = [
        _run_case(
            "A_uv_run_echo",
            ["uv", "run", "python", "-c", CHILD_ECHO],
            cwd=AGENT,
            timeout=120,
        ),
        _run_case(
            "B_sys_executable_echo",
            [python, "-c", CHILD_ECHO],
            cwd=AGENT,
            timeout=120,
        ),
        _run_case(
            "C_uv_run_legacy_script_help",
            ["uv", "run", "python", LEGACY_SCRIPT, "--help"],
            cwd=AGENT,
            timeout=180,
        ),
        _run_case(
            "D_sys_executable_legacy_script_help",
            [python, LEGACY_SCRIPT, "--help"],
            cwd=AGENT,
            timeout=180,
        ),
        _run_case(
            "E_timeout_1s_sleeper",
            ["uv", "run", "python", "-c", "import time; time.sleep(30)"],
            cwd=AGENT,
            timeout=1,
        ),
        _run_case(
            "F_wrong_cwd_is_visible",
            ["uv", "run", "python", "-c", "print('should not reach')"],
            cwd=WORKTREE / "definitely-not-here",
            timeout=30,
        ),
    ]
    return {
        "shell_process": {
            "executable": python,
            "cwd": os.getcwd(),
            "uv_on_path": shutil.which("uv"),
            "path": os.environ.get("PATH", ""),
            "virtual_env": os.environ.get("VIRTUAL_ENV"),
            "uv_env_keys": sorted(k for k in os.environ if k.startswith("UV_")),
            "database_url_set": bool(os.environ.get("DATABASE_URL")),
        },
        "worktree": str(WORKTREE),
        "agent_root": str(AGENT),
        "agent_root_is_dir": AGENT.is_dir(),
        "cases": cases,
    }


def main() -> int:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

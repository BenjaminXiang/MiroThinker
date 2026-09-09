from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


APP_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = APP_ROOT / "scripts" / "canonical_v2_schema_fingerprint.py"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_schema_fingerprint", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_fingerprint_ignores_only_pg_dump_random_restrict_tokens() -> None:
    module = _module()
    first = (
        b"-- PostgreSQL database dump\n"
        b"\\restrict random-token-one\n"
        b"CREATE TABLE landing.example (id text);\n"
        b"\\unrestrict random-token-one\n"
    )
    second = first.replace(b"random-token-one", b"different-random-token")
    changed_schema = second.replace(b"id text", b"id bigint")

    first_result = module.fingerprint_schema_dump(first)
    second_result = module.fingerprint_schema_dump(second)
    changed_result = module.fingerprint_schema_dump(changed_schema)

    assert first_result == second_result
    assert first_result["removed_control_lines"] == 2
    assert first_result["normalized_sha256"] != changed_result["normalized_sha256"]


def test_schema_fingerprint_cli_reports_normalized_hash_without_dump_bytes() -> None:
    payload = b"\\restrict token\nCREATE SCHEMA landing;\n\\unrestrict token\n"

    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=payload,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["removed_control_lines"] == 2
    assert result["normalized_bytes"] == len(b"CREATE SCHEMA landing;\n")
    assert "CREATE SCHEMA" not in completed.stdout.decode()

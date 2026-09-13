#!/usr/bin/env python
"""Report the effective managed configuration and provider key status.

This is the real consumer of the managed settings file introduced by the
`add-admin-config-center` slice: it reads the same file through the same loader
the admin API uses, and shows for every field which source won
(`env > file > default`).

Read-only by construction: it never writes the settings file, never writes an
audit record, and never prints credential material (only presence, origin, and
the last four characters).

Usage::

    uv run python scripts/settings_status.py
    uv run python scripts/settings_status.py --json
    uv run python scripts/settings_status.py --check-keys
    uv run python scripts/settings_status.py --require collection.max_llm_calls_per_run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.canonical_v2.managed_config import (  # noqa: E402
    ManagedSettingsError,
    ManagedSettingsStore,
    default_settings_path,
)

_PROVIDER_ENV = {
    "bocha": ("BOCHA_API_KEY", ".bocha_api_key"),
    "serper": ("SERPER_API_KEY", ".serper_api_key"),
    "deepseek": ("DEEPSEEK_API_KEY", ".deepseek_api_key"),
    "dashscope": ("DASHSCOPE_API_KEY", ".dashscope_api_key"),
    "local_llm": ("LOCAL_LLM_API_KEY", ".sglang_api_key"),
}


def _key_roots() -> tuple[Path, ...]:
    here = Path(__file__).resolve()
    roots = [*here.parents, Path.cwd()]
    seen: list[Path] = []
    for root in roots:
        if root not in seen:
            seen.append(root)
    return tuple(seen)


def _provider_report() -> list[dict[str, object]]:
    import os

    report: list[dict[str, object]] = []
    for name, (env_var, filename) in _PROVIDER_ENV.items():
        material = os.environ.get(env_var, "").strip()
        origin = f"env:{env_var}" if material else None
        if not material:
            for root in _key_roots():
                candidate = root / filename
                if candidate.is_file():
                    try:
                        material = candidate.read_text(encoding="utf-8").strip()
                    except OSError:
                        continue
                    if material:
                        origin = f"file:{filename}"
                        break
        report.append(
            {
                "provider": name,
                "configured": bool(material),
                "suffix4": material[-4:] if material else None,
                "origin": origin,
            }
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--check-keys", action="store_true", help="also report provider key presence"
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        help="exit non-zero when this field path is unset in the effective view",
    )
    args = parser.parse_args(argv)

    store = ManagedSettingsStore(path=default_settings_path())
    try:
        document, fields = store.effective()
    except ManagedSettingsError as exc:
        print(f"managed settings invalid: {exc}", file=sys.stderr)
        return 2

    payload = {
        "path": str(store.path),
        "exists": store.exists(),
        "schema_version": document.schema_version,
        "fields": [field.as_dict() for field in fields],
    }
    if args.check_keys:
        payload["providers"] = _provider_report()

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"managed settings : {store.path} ({'exists' if store.exists() else 'defaults'})")
        print(f"schema_version   : {document.schema_version}")
        print("-" * 72)
        for field in fields:
            marker = {"env": "[env ]", "file": "[file]", "default": "[deflt]"}[field.source]
            value = json.dumps(field.value, ensure_ascii=False)
            env_note = f"  <- {field.env_var}" if field.env_var else ""
            print(f"{marker} {field.path:44} = {value}{env_note}")
        if args.check_keys:
            print("-" * 72)
            for provider in payload["providers"]:
                suffix = provider["suffix4"] or "----"
                state = "configured" if provider["configured"] else "MISSING   "
                print(
                    f"[key ] {provider['provider']:12} {state} "
                    f"suffix={suffix} origin={provider['origin'] or '-'}"
                )

    missing = [
        path
        for path in args.require
        if not any(
            field.path == path and field.value not in (None, "", False)
            for field in fields
        )
    ]
    if missing:
        print(f"required fields unset: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

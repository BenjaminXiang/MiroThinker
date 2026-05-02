# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_profile_summary_reinforcement.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location(
        "run_profile_summary_reinforcement_threshold",
        _SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_min_length_is_150():
    cli = _import_cli()

    args = cli._parse_args([])
    sql, _params = cli._build_select_sql(
        only_missing=True,
        limit=None,
        min_length=args.min_length,
    )

    assert args.min_length == 150
    assert "length(profile_summary) < 150" in sql


def test_min_length_cli_override():
    cli = _import_cli()

    args = cli._parse_args(["--min-length", "50"])
    sql, _params = cli._build_select_sql(
        only_missing=True,
        limit=None,
        min_length=args.min_length,
    )

    assert args.min_length == 50
    assert "length(profile_summary) < 50" in sql

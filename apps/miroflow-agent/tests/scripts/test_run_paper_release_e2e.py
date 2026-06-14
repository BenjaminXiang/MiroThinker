# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_script():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_paper_release_e2e.py"
    spec = importlib.util.spec_from_file_location("run_paper_release_e2e", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_paper_release_e2e"] = module
    spec.loader.exec_module(module)
    return module


def test_run_paper_release_e2e_is_retired_wrapper(monkeypatch, capsys) -> None:
    module = _load_script()
    monkeypatch.setattr(module.sys, "argv", ["script"])

    with pytest.warns(DeprecationWarning, match="retired"):
        code = module.main()

    captured = capsys.readouterr()
    assert code == 2
    assert "homepage ingest" in captured.err
    assert "author-profile database discovery" in captured.err


def test_run_paper_release_e2e_no_longer_accepts_source_modes(monkeypatch) -> None:
    module = _load_script()
    monkeypatch.setattr(module.sys, "argv", ["script", "--source", "hybrid"])

    with pytest.raises(SystemExit):
        module.main()

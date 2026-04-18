# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_script():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_professor_phase_a_query_set.py"
    return _load_module("run_professor_phase_a_query_set", script_path)


def test_phase_a_query_set_builds_queries_from_audit_manifest(tmp_path, monkeypatch) -> None:
    module = _load_script()
    input_path = tmp_path / "phase_a_audit_manifest.json"
    input_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "audit_id": "001_南方科技大学",
                        "institution": "南方科技大学",
                        "machine": {
                            "name": "吴亚北",
                        },
                    },
                    {
                        "audit_id": "002_跳过",
                        "institution": "南方科技大学",
                        "machine": {
                            "name": "",
                        },
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "query_set"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--input-json",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    code = module.main()
    assert code == 0

    payload = json.loads((output_dir / "query_set.json").read_text(encoding="utf-8"))
    assert payload["query_count"] == 1
    assert payload["skipped_count"] == 1
    [query] = payload["queries"]
    assert query == {
        "query_id": "001_南方科技大学",
        "query": "南方科技大学 吴亚北 教授",
        "expected_name": "吴亚北",
        "expected_institution": "南方科技大学",
        "topk": 5,
    }
    assert (output_dir / "query_set.md").exists()


def test_phase_a_query_set_accepts_machine_audit_payload(tmp_path, monkeypatch) -> None:
    module = _load_script()
    input_path = tmp_path / "phase_a_machine_audit.json"
    input_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "audit_id": "003_北京大学深圳研究生院",
                        "institution": "",
                        "machine": {},
                        "machine_audit": {
                            "profile_name": "陈少川",
                            "profile_institution": "北京大学深圳研究生院",
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "query_set"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--input-json",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    code = module.main()
    assert code == 0

    payload = json.loads((output_dir / "query_set.json").read_text(encoding="utf-8"))
    [query] = payload["queries"]
    assert query["query_id"] == "003_北京大学深圳研究生院"
    assert query["query"] == "北京大学深圳研究生院 陈少川 教授"
    assert query["expected_name"] == "陈少川"
    assert query["expected_institution"] == "北京大学深圳研究生院"
    assert query["topk"] == 5

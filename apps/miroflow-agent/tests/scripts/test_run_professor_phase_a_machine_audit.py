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
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_professor_phase_a_machine_audit.py"
    return _load_module("run_professor_phase_a_machine_audit", script_path)


def test_phase_a_machine_audit_fills_identity_and_paper_verification(tmp_path, monkeypatch) -> None:
    module = _load_script()
    rerun_ok = tmp_path / "001_ok"
    rerun_bad = tmp_path / "002_bad"
    rerun_ok.mkdir()
    rerun_bad.mkdir()
    (rerun_ok / "enriched_v3.jsonl").write_text(
        json.dumps(
            {
                "name": "吴亚北",
                "institution": "南方科技大学",
                "homepage": "https://example.com/wuyabei",
                "profile_url": "https://example.com/wuyabei",
                "top_papers": [{"title": "Paper A"}, {"title": "Paper B"}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (rerun_bad / "enriched_v3.jsonl").write_text(
        json.dumps(
            {
                "name": "陈少川",
                "institution": "北京大学深圳研究生院",
                "homepage": "https://example.com/chensc",
                "profile_url": "https://example.com/chensc",
                "top_papers": [{"title": "Wrong Paper 1"}, {"title": "Wrong Paper 2"}, {"title": "Wrong Paper 3"}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "phase_a_audit_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "audit_id": "001_ok",
                        "institution": "南方科技大学",
                        "url": "https://example.com/seed-ok",
                        "output_dir": str(rerun_ok),
                        "machine": {
                            "name": "吴亚北",
                            "resolved_institution": "南方科技大学",
                            "identity_passed": True,
                            "top_papers_len": 2,
                        },
                        "manual": {
                            "identity_correct": None,
                            "paper_matches_judged": 0,
                            "paper_matches_correct": 0,
                            "notes": "",
                        },
                    },
                    {
                        "audit_id": "002_bad",
                        "institution": "北京大学深圳研究生院",
                        "url": "https://example.com/seed-bad",
                        "output_dir": str(rerun_bad),
                        "machine": {
                            "name": "陈少川",
                            "resolved_institution": "北京大学深圳研究生院",
                            "identity_passed": True,
                            "top_papers_len": 3,
                        },
                        "manual": {
                            "identity_correct": None,
                            "paper_matches_judged": 0,
                            "paper_matches_correct": 0,
                            "notes": "",
                        },
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "machine_audit"

    def fake_discover_best_hybrid_result(**kwargs):
        if kwargs["name"] == "吴亚北":
            return module.ProfessorPaperDiscoveryResult(
                professor_id="PROF-1",
                professor_name="Yabei Wu",
                institution="南方科技大学",
                author_id="https://openalex.org/A1",
                h_index=15,
                citation_count=708,
                paper_count=70,
                source="openalex",
                school_matched=True,
                fallback_used=False,
                name_disambiguation_conflict=False,
                papers=[],
            )
        return None

    monkeypatch.setattr(module, "_discover_best_hybrid_result", fake_discover_best_hybrid_result)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--audit-manifest-json",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    code = module.main()
    assert code == 0

    payload = json.loads((output_dir / "phase_a_machine_audit.json").read_text(encoding="utf-8"))
    first, second = payload["items"]
    assert first["manual"]["identity_correct"] is True
    assert first["manual"]["paper_matches_judged"] == 2
    assert first["manual"]["paper_matches_correct"] == 2
    assert first["machine_audit"]["paper_verification"]["accepted"] is True
    assert second["manual"]["identity_correct"] is True
    assert second["manual"]["paper_matches_judged"] == 3
    assert second["manual"]["paper_matches_correct"] == 0
    assert second["machine_audit"]["paper_verification"]["accepted"] is False


def test_phase_a_machine_audit_uses_profile_selector_when_present(
    tmp_path, monkeypatch
) -> None:
    module = _load_script()
    rerun_dir = tmp_path / "001_rerun"
    rerun_dir.mkdir()
    (rerun_dir / "enriched_v3.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "name": "甲老师",
                        "institution": "南方科技大学",
                        "homepage": "https://example.com/a",
                        "profile_url": "https://example.com/a",
                        "top_papers": [{"title": "Paper A"}, {"title": "Paper B"}, {"title": "Paper C"}],
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "name": "乙老师",
                        "institution": "南方科技大学",
                        "homepage": "https://example.com/b",
                        "profile_url": "https://example.com/b",
                        "top_papers": [{"title": "Paper X"}],
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "phase_a_audit_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "audit_id": "001_target_profile",
                        "institution": "南方科技大学",
                        "url": "https://example.com/seed",
                        "output_dir": str(rerun_dir),
                        "profile_selector": {
                            "name": "乙老师",
                            "institution": "南方科技大学",
                            "profile_url": "https://example.com/b",
                        },
                        "machine": {
                            "name": "乙老师",
                            "resolved_institution": "南方科技大学",
                            "identity_passed": True,
                            "top_papers_len": 1,
                        },
                        "manual": {
                            "identity_correct": None,
                            "paper_matches_judged": 0,
                            "paper_matches_correct": 0,
                            "notes": "",
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "machine_audit"

    def fake_discover_best_hybrid_result(**kwargs):
        assert kwargs["name"] == "乙老师"
        return module.ProfessorPaperDiscoveryResult(
            professor_id="PROF-2",
            professor_name="乙老师",
            institution="南方科技大学",
            author_id="https://openalex.org/A2",
            h_index=9,
            citation_count=88,
            paper_count=6,
            source="openalex",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            papers=[],
        )

    monkeypatch.setattr(module, "_discover_best_hybrid_result", fake_discover_best_hybrid_result)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--audit-manifest-json",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    code = module.main()
    assert code == 0

    payload = json.loads((output_dir / "phase_a_machine_audit.json").read_text(encoding="utf-8"))
    [item] = payload["items"]
    assert item["machine_audit"]["profile_name"] == "乙老师"
    assert item["manual"]["paper_matches_judged"] == 1
    assert item["manual"]["paper_matches_correct"] == 1


def test_phase_a_machine_audit_accepts_strong_non_school_matched_openalex_result(
    tmp_path, monkeypatch
) -> None:
    module = _load_script()
    rerun_dir = tmp_path / "001_rerun"
    rerun_dir.mkdir()
    (rerun_dir / "enriched_v3.jsonl").write_text(
        json.dumps(
            {
                "name": "周垚",
                "institution": "南方科技大学",
                "homepage": "https://example.com/zhouyao",
                "profile_url": "https://example.com/zhouyao",
                "top_papers": [
                    {"title": "Paper 1"},
                    {"title": "Paper 2"},
                    {"title": "Paper 3"},
                    {"title": "Paper 4"},
                    {"title": "Paper 5"},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "phase_a_audit_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "audit_id": "001_strong_non_school_match",
                        "institution": "南方科技大学",
                        "url": "https://example.com/seed",
                        "output_dir": str(rerun_dir),
                        "machine": {
                            "name": "周垚",
                            "resolved_institution": "南方科技大学",
                            "identity_passed": True,
                            "top_papers_len": 5,
                        },
                        "manual": {
                            "identity_correct": None,
                            "paper_matches_judged": 0,
                            "paper_matches_correct": 0,
                            "notes": "",
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "machine_audit"

    def fake_discover_best_hybrid_result(**kwargs):
        return module.ProfessorPaperDiscoveryResult(
            professor_id="PROF-3",
            professor_name="Yao Zhou",
            institution="Another Institution",
            author_id="https://openalex.org/A3",
            h_index=57,
            citation_count=14746,
            paper_count=316,
            source="openalex",
            school_matched=False,
            fallback_used=False,
            name_disambiguation_conflict=False,
            papers=[],
        )

    monkeypatch.setattr(module, "_discover_best_hybrid_result", fake_discover_best_hybrid_result)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--audit-manifest-json",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    code = module.main()
    assert code == 0

    payload = json.loads((output_dir / "phase_a_machine_audit.json").read_text(encoding="utf-8"))
    [item] = payload["items"]
    assert item["manual"]["paper_matches_judged"] == 5
    assert item["manual"]["paper_matches_correct"] == 5
    assert item["machine_audit"]["paper_verification"]["accepted"] is True

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


def _load_audit_script():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_professor_phase_a_audit.py"
    return _load_module("run_professor_phase_a_audit", script_path)


def test_phase_a_audit_writes_fixed_and_random_manifest(tmp_path, monkeypatch) -> None:
    module = _load_audit_script()
    seed_path = tmp_path / "seed.md"
    seed_path.write_text(
        "\n".join(
            [
                "清华大学深圳国际研究生院 https://example.com/tsinghua-1",
                "清华大学深圳国际研究生院 https://example.com/tsinghua-2",
                "南方科技大学 https://example.com/sustech-1",
                "深圳大学 https://example.com/szu-1",
                "深圳大学 https://example.com/szu-2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "url_e2e_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "index": 1,
                        "label": "清华大学深圳国际研究生院",
                        "url": "https://example.com/tsinghua-1",
                        "rerun_id": "001_tsinghua_1",
                        "output_dir": "/tmp/001_tsinghua_1",
                        "name": "张三",
                        "resolved_institution": "清华大学深圳国际研究生院",
                        "quality_status": "ready",
                        "gate_passed": True,
                        "identity_passed": True,
                        "paper_backed_passed": True,
                        "required_fields_passed": True,
                        "paper_count": 12,
                        "top_papers_len": 5,
                    },
                    {
                        "index": 2,
                        "label": "清华大学深圳国际研究生院",
                        "url": "https://example.com/tsinghua-2",
                        "rerun_id": "002_tsinghua_2",
                        "output_dir": "/tmp/002_tsinghua_2",
                        "name": "李四",
                        "resolved_institution": "清华大学深圳国际研究生院",
                        "quality_status": "ready",
                        "gate_passed": True,
                        "identity_passed": True,
                        "paper_backed_passed": True,
                        "required_fields_passed": True,
                        "paper_count": 8,
                        "top_papers_len": 4,
                    },
                    {
                        "index": 3,
                        "label": "南方科技大学",
                        "url": "https://example.com/sustech-1",
                        "rerun_id": "003_sustech_1",
                        "output_dir": "/tmp/003_sustech_1",
                        "name": "王五",
                        "resolved_institution": "南方科技大学",
                        "quality_status": "ready",
                        "gate_passed": True,
                        "identity_passed": True,
                        "paper_backed_passed": True,
                        "required_fields_passed": True,
                        "paper_count": 10,
                        "top_papers_len": 5,
                    },
                    {
                        "index": 4,
                        "label": "深圳大学",
                        "url": "https://example.com/szu-1",
                        "rerun_id": "004_szu_1",
                        "output_dir": "/tmp/004_szu_1",
                        "name": "赵六",
                        "resolved_institution": "深圳大学",
                        "quality_status": "ready",
                        "gate_passed": True,
                        "identity_passed": True,
                        "paper_backed_passed": True,
                        "required_fields_passed": True,
                        "paper_count": 6,
                        "top_papers_len": 3,
                    },
                    {
                        "index": 5,
                        "label": "深圳大学",
                        "url": "https://example.com/szu-2",
                        "rerun_id": "005_szu_2",
                        "output_dir": "/tmp/005_szu_2",
                        "name": "钱七",
                        "resolved_institution": "深圳大学",
                        "quality_status": "needs_enrichment",
                        "gate_passed": False,
                        "identity_passed": True,
                        "paper_backed_passed": False,
                        "required_fields_passed": True,
                        "paper_count": 0,
                        "top_papers_len": 0,
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "audit"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--seed-doc",
            str(seed_path),
            "--summary-json",
            str(summary_path),
            "--output-dir",
            str(output_dir),
            "--fixed-per-school",
            "1",
            "--random-sample-size",
            "1",
            "--sample-seed",
            "7",
        ],
    )

    code = module.main()
    assert code == 0

    manifest = json.loads((output_dir / "phase_a_audit_manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_urls"] == 5
    assert manifest["selected_urls"] == 4
    assert manifest["fixed_urls"] == 3
    assert manifest["random_urls"] == 1

    fixed_items = [item for item in manifest["items"] if item["selection_source"] == "fixed"]
    random_items = [item for item in manifest["items"] if item["selection_source"] == "random"]
    assert len(fixed_items) == 3
    assert len(random_items) == 1
    assert {item["institution"] for item in fixed_items} == {
        "清华大学深圳国际研究生院",
        "南方科技大学",
        "深圳大学",
    }
    assert random_items[0]["index"] in {2, 5}

    first_item = manifest["items"][0]
    assert first_item["manual"] == {
        "identity_correct": None,
        "paper_matches_judged": 0,
        "paper_matches_correct": 0,
        "notes": "",
    }
    assert first_item["machine"]["name"]
    assert (output_dir / "phase_a_audit_manifest.md").exists()


def test_phase_a_audit_matches_summary_by_url_when_index_changes(tmp_path, monkeypatch) -> None:
    module = _load_audit_script()
    seed_path = tmp_path / "seed.md"
    seed_path.write_text(
        "南方科技大学 https://example.com/sustech-1\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "url_e2e_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "index": 88,
                        "label": "南方科技大学",
                        "url": "https://example.com/sustech-1",
                        "rerun_id": "088_sustech_1",
                        "output_dir": "/tmp/088_sustech_1",
                        "name": "王五",
                        "resolved_institution": "南方科技大学",
                        "quality_status": "ready",
                        "gate_passed": True,
                        "identity_passed": True,
                        "paper_backed_passed": True,
                        "required_fields_passed": True,
                        "paper_count": 10,
                        "top_papers_len": 5,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "audit"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--seed-doc",
            str(seed_path),
            "--summary-json",
            str(summary_path),
            "--output-dir",
            str(output_dir),
            "--random-sample-size",
            "0",
        ],
    )

    code = module.main()
    assert code == 0

    manifest = json.loads((output_dir / "phase_a_audit_manifest.json").read_text(encoding="utf-8"))
    assert manifest["items"][0]["machine"]["name"] == "王五"
    assert manifest["items"][0]["rerun_id"] == "088_sustech_1"


def test_phase_a_audit_can_limit_candidates_to_summary_results(tmp_path, monkeypatch) -> None:
    module = _load_audit_script()
    seed_path = tmp_path / "seed.md"
    seed_path.write_text(
        "\n".join(
            [
                "南方科技大学 https://example.com/sustech-1",
                "南方科技大学 https://example.com/sustech-2",
                "深圳大学 https://example.com/szu-1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "url_e2e_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "index": 1,
                        "label": "南方科技大学",
                        "url": "https://example.com/sustech-1",
                        "rerun_id": "001_sustech_1",
                        "output_dir": "/tmp/001_sustech_1",
                        "name": "王五",
                        "resolved_institution": "南方科技大学",
                        "quality_status": "ready",
                        "gate_passed": True,
                        "identity_passed": True,
                        "paper_backed_passed": True,
                        "required_fields_passed": True,
                        "paper_count": 10,
                        "top_papers_len": 5,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "audit"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--seed-doc",
            str(seed_path),
            "--summary-json",
            str(summary_path),
            "--output-dir",
            str(output_dir),
            "--random-sample-size",
            "0",
            "--summary-results-only",
        ],
    )

    code = module.main()
    assert code == 0

    manifest = json.loads((output_dir / "phase_a_audit_manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_urls"] == 1
    assert manifest["selected_urls"] == 1
    assert [item["url"] for item in manifest["items"]] == ["https://example.com/sustech-1"]


def test_phase_a_audit_can_build_profile_level_manifest_from_enriched_dir(
    tmp_path, monkeypatch
) -> None:
    module = _load_audit_script()
    seed_path = tmp_path / "seed.md"
    seed_path.write_text(
        "\n".join(
            [
                "南方科技大学 https://example.com/sustech-1",
                "深圳大学 https://example.com/szu-1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    enriched_dir = tmp_path / "e2e"
    sustech_dir = enriched_dir / "001_南方科技大学"
    szu_dir = enriched_dir / "002_深圳大学"
    sustech_dir.mkdir(parents=True)
    szu_dir.mkdir(parents=True)
    (sustech_dir / "enriched_v3.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "name": "吴亚北",
                        "institution": "南方科技大学",
                        "profile_url": "https://example.com/wuyabei",
                        "evidence_urls": ["https://example.com/wuyabei"],
                        "profile_summary": "吴亚北，南方科技大学教师。",
                        "evaluation_summary": "评价摘要。",
                        "top_papers": [{"title": "Paper A"}, {"title": "Paper B"}],
                        "paper_count": 12,
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "name": "王五",
                        "institution": "南方科技大学",
                        "profile_url": "https://example.com/wangwu",
                        "evidence_urls": ["https://example.com/wangwu"],
                        "profile_summary": "王五，南方科技大学教师。",
                        "evaluation_summary": "评价摘要。",
                        "top_papers": [],
                        "paper_count": 0,
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (szu_dir / "enriched_v3.jsonl").write_text(
        json.dumps(
            {
                "name": "靳玉乐",
                "institution": "深圳大学",
                "profile_url": "https://example.com/jinyule",
                "evidence_urls": ["https://example.com/jinyule"],
                "profile_summary": "靳玉乐，深圳大学教师。",
                "evaluation_summary": "评价摘要。",
                "top_papers": [{"title": "Paper C"}],
                "paper_count": 5,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "audit"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--seed-doc",
            str(seed_path),
            "--enriched-dir",
            str(enriched_dir),
            "--output-dir",
            str(output_dir),
            "--profile-level",
            "--fixed-per-school",
            "1",
            "--random-sample-size",
            "1",
            "--sample-seed",
            "7",
        ],
    )

    code = module.main()
    assert code == 0

    manifest = json.loads((output_dir / "phase_a_audit_manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_profiles"] == 3
    assert manifest["selected_profiles"] == 3
    assert manifest["fixed_profiles"] == 2
    assert manifest["random_profiles"] == 1
    assert manifest["selection_unit"] == "profile"
    assert {item["machine"]["name"] for item in manifest["items"]} == {"吴亚北", "王五", "靳玉乐"}
    assert all(item["output_dir"] in {str(sustech_dir), str(szu_dir)} for item in manifest["items"])
    assert all(item["profile_selector"]["name"] for item in manifest["items"])

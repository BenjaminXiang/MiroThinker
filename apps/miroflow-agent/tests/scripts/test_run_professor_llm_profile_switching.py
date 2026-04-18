# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from collections import Counter
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_url_md_script():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_professor_url_md_e2e.py"
    return _load_module("run_professor_url_md_e2e_sampling", script_path)


def _v3_fake_result():
    return SimpleNamespace(
        report=SimpleNamespace(
            seed_count=0,
            discovered_count=0,
            unique_count=0,
            regex_structured_count=0,
            regex_partial_count=0,
            direction_cleaned_count=0,
            homepage_crawled_count=0,
            homepage_fields_filled=0,
            paper_enriched_count=0,
            papers_collected_total=0,
            paper_staging_count=0,
            paper_observation_count=0,
            paper_school_hit_count=0,
            paper_fallback_count=0,
            paper_name_disambiguation_conflict_count=0,
            paper_source_breakdown={},
            agent_triggered_count=0,
            agent_local_success_count=0,
            agent_online_escalation_count=0,
            agent_failed_count=0,
            web_search_count=0,
            identity_verified_count=0,
            company_links_confirmed=0,
            summary_generated_count=0,
            summary_fallback_count=0,
            l1_blocked_count=0,
            released_count=0,
            quality_distribution={},
            vectorized_count=0,
            alerts=[],
        ),
        output_files={},
    )


def _v2_fake_result():
    return SimpleNamespace(
        report=SimpleNamespace(
            seed_count=0,
            discovered_count=0,
            unique_count=0,
            regex_structured_count=0,
            regex_partial_count=0,
            paper_enriched_count=0,
            papers_collected_total=0,
            paper_staging_count=0,
            paper_observation_count=0,
            paper_school_hit_count=0,
            paper_fallback_count=0,
            paper_name_disambiguation_conflict_count=0,
            paper_source_breakdown={},
            agent_triggered_count=0,
            agent_local_success_count=0,
            agent_online_escalation_count=0,
            agent_failed_count=0,
            summary_generated_count=0,
            summary_fallback_count=0,
            l1_blocked_count=0,
            released_count=0,
            quality_distribution={},
            vectorized_count=0,
            alerts=[],
        ),
        output_files={},
    )


def _batch_fake_result():
    return SimpleNamespace(
        report=SimpleNamespace(
            total_loaded=0,
            processed=0,
            direction_cleaned=0,
            homepage_crawled=0,
            paper_enriched=0,
            agent_triggered=0,
            agent_success=0,
            web_searched=0,
            identity_verified=0,
            company_links=0,
            summary_generated=0,
            failed=0,
        ),
    )


@pytest.mark.parametrize(
    "module_file, runner_name, fake_result_factory, argv",
    [
        (
            "run_professor_pipeline_v3_e2e.py",
            "run_professor_pipeline_v3",
            _v3_fake_result,
            [
                "--seed-doc",
                "tmp_seed.md",
                "--output-dir",
                "tmp_out",
            ],
        ),
        (
            "run_professor_enrichment_v2_e2e.py",
            "run_professor_pipeline_v2",
            _v2_fake_result,
            [
                "--seed-doc",
                "tmp_seed.md",
                "--output-dir",
                "tmp_out",
            ],
        ),
        (
            "run_batch_reprocess_v3.py",
            "run_batch_reprocess",
            _batch_fake_result,
            [
                "--store-db",
                "tmp_store.db",
                "--output-dir",
                "tmp_out",
            ],
        ),
        (
            "run_professor_url_md_e2e.py",
            "run_professor_pipeline_v3",
            _v3_fake_result,
            [
                "--seed-doc",
                "tmp_seed.md",
                "--output-dir",
                "tmp_out",
                "--limit-per-url",
                "1",
                "--end-index",
                "1",
            ],
        ),
    ],
)
def test_llm_profile_switching_is_resolved_in_strict_mode(
    module_file: str,
    runner_name: str,
    fake_result_factory,
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / module_file
    module = _load_module(module_file.replace(".py", ""), script_path)

    captured: dict[str, object] = {}
    seed_path = tmp_path / argv[1]
    output_path = tmp_path / argv[3]

    if module_file == "run_batch_reprocess_v3.py":
        output_argv = tmp_path / "tmp_store.db"
        output_argv.write_text("", encoding="utf-8")
        argv[1] = str(output_argv)
        argv[3] = str(output_path)
    else:
        if module_file == "run_professor_url_md_e2e.py":
            seed_path.write_text("A https://example.com\n", encoding="utf-8")
        elif module_file == "run_professor_pipeline_v3_e2e.py":
            seed_path.write_text("A https://example.com\n", encoding="utf-8")
        elif module_file == "run_professor_enrichment_v2_e2e.py":
            seed_path.write_text("A https://example.com\n", encoding="utf-8")
        argv[1] = str(seed_path)
        argv[3] = str(output_path)

    def fake_resolve_professor_llm_settings(
        profile_name: str | None = None,
        *,
        default_profile: str,
        strict: bool,
        include_profile: bool = False,
    ) -> dict[str, str]:
        captured["strict"] = strict
        captured["include_profile"] = include_profile
        return {
            "local_llm_base_url": "http://localhost:1234/v1",
            "local_llm_model": "test-local-model",
            "local_llm_api_key": "",
            "online_llm_base_url": "http://localhost:5678/v1",
            "online_llm_model": "test-online-model",
            "online_llm_api_key": "",
            "llm_profile": "gemma4",
        }

    async def fake_runner(*_args, **_kwargs):
        return fake_result_factory()

    monkeypatch.setattr(module, "resolve_professor_llm_settings", fake_resolve_professor_llm_settings)
    monkeypatch.setattr(module, runner_name, fake_runner)
    monkeypatch.setattr(module.sys, "argv", ["script"] + argv)

    code = module.main()
    assert code == 0
    assert captured["strict"] is True
    assert captured["include_profile"] is True


def test_weighted_school_sampling_tracks_school_distribution():
    module = _load_url_md_script()
    entries = [
        {"index": 1, "label": "A1", "url": "http://example.com/1", "institution": "alpha"},
        {"index": 2, "label": "A2", "url": "http://example.com/2", "institution": "alpha"},
        {"index": 3, "label": "A3", "url": "http://example.com/3", "institution": "alpha"},
        {"index": 4, "label": "A4", "url": "http://example.com/4", "institution": "alpha"},
        {"index": 5, "label": "B1", "url": "http://example.com/5", "institution": "beta"},
        {"index": 6, "label": "B2", "url": "http://example.com/6", "institution": "beta"},
        {"index": 7, "label": "C1", "url": "http://example.com/7", "institution": "gamma"},
    ]
    counts: Counter[str] = Counter()

    for seed in range(1, 1201):
        [item] = module._weighted_school_sample(
            entries,
            sample_size=1,
            random_seed=seed,
            enable_weighting=True,
        )
        counts[item["institution"]] += 1

    total = sum(counts.values())
    assert total == 1200
    assert abs((counts["alpha"] / total) - (4 / 7)) < 0.08
    assert abs((counts["beta"] / total) - (2 / 7)) < 0.08
    assert abs((counts["gamma"] / total) - (1 / 7)) < 0.08


def test_build_config_treats_zero_limit_as_unbounded(tmp_path: Path):
    module = _load_url_md_script()
    config = module._build_config(
        seed_doc=tmp_path / "seed.md",
        output_dir=tmp_path / "out",
        llm_settings={
            "local_llm_base_url": "http://localhost:1234/v1",
            "local_llm_model": "local-model",
            "local_llm_api_key": "",
            "online_llm_base_url": "http://localhost:5678/v1",
            "online_llm_model": "online-model",
            "online_llm_api_key": "",
        },
        timeout=30.0,
        skip_web_search=True,
        skip_vectorize=True,
        limit_per_url=0,
    )

    assert config.limit is None


def test_build_config_defaults_store_db_to_output_dir(tmp_path: Path):
    module = _load_url_md_script()
    output_dir = tmp_path / "out"
    config = module._build_config(
        seed_doc=tmp_path / "seed.md",
        output_dir=output_dir,
        llm_settings={
            "local_llm_base_url": "http://localhost:1234/v1",
            "local_llm_model": "local-model",
            "local_llm_api_key": "",
            "online_llm_base_url": "http://localhost:5678/v1",
            "online_llm_model": "online-model",
            "online_llm_api_key": "",
        },
        timeout=30.0,
        skip_web_search=True,
        skip_vectorize=True,
        limit_per_url=1,
    )

    assert config.store_db_path == str(output_dir / "released_objects.db")


def test_parse_seed_lines_keeps_contiguous_indices_when_blank_lines_exist(tmp_path: Path):
    module = _load_url_md_script()
    seed_doc = tmp_path / "教授 URL.md"
    seed_doc.write_text(
        "\n".join(
            [
                "清华大学深圳国际研究生院 https://www.sigs.tsinghua.edu.cn/7644/list.htm",
                "",
                "南方科技大学 https://www.sustech.edu.cn/zh/letter/",
                "",
                "深圳大学 https://www.szu.edu.cn/szdw/jsjj.htm",
            ]
        ),
        encoding="utf-8",
    )

    entries = module._parse_seed_lines(seed_doc)

    assert [entry["index"] for entry in entries] == [1, 2, 3]


def test_parse_seed_lines_skips_non_url_content(tmp_path: Path):
    module = _load_url_md_script()
    seed_doc = tmp_path / "教授 URL.md"
    seed_doc.write_text(
        "\n".join(
            [
                "# 深圳高校教师",
                "清华大学深圳国际研究生院 https://www.sigs.tsinghua.edu.cn/7644/list.htm",
                "说明文字，不是 seed",
                "南方科技大学 https://www.sustech.edu.cn/zh/letter/",
            ]
        ),
        encoding="utf-8",
    )

    entries = module._parse_seed_lines(seed_doc)

    assert [entry["label"] for entry in entries] == [
        "清华大学深圳国际研究生院",
        "南方科技大学",
    ]


def test_main_uses_single_asyncio_run_for_multiple_sampled_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_url_md_script()
    seed_doc = tmp_path / "教授 URL.md"
    seed_doc.write_text(
        "\n".join(
            [
                "清华大学深圳国际研究生院 https://www.sigs.tsinghua.edu.cn/7644/list.htm",
                "南方科技大学 https://www.sustech.edu.cn/zh/letter/",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"

    def fake_resolve_professor_llm_settings(
        profile_name: str | None = None,
        *,
        default_profile: str,
        strict: bool,
        include_profile: bool = False,
    ) -> dict[str, str]:
        return {
            "local_llm_base_url": "http://localhost:1234/v1",
            "local_llm_model": "local-model",
            "local_llm_api_key": "",
            "online_llm_base_url": "http://localhost:5678/v1",
            "online_llm_model": "online-model",
            "online_llm_api_key": "",
            "llm_profile": "gemma4",
        }

    async def fake_runner(*_args, **_kwargs):
        return _v3_fake_result()

    original_asyncio_run = module.asyncio.run
    run_calls = 0

    def counting_asyncio_run(coro):
        nonlocal run_calls
        run_calls += 1
        return original_asyncio_run(coro)

    monkeypatch.setattr(module, "resolve_professor_llm_settings", fake_resolve_professor_llm_settings)
    monkeypatch.setattr(module, "run_professor_pipeline_v3", fake_runner)
    monkeypatch.setattr(module, "_load_profiles", lambda _path: [])
    monkeypatch.setattr(module.asyncio, "run", counting_asyncio_run)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--seed-doc",
            str(seed_doc),
            "--output-dir",
            str(output_dir),
            "--disable-school-weighting",
            "--limit-per-url",
            "1",
        ],
    )

    code = module.main()

    assert code == 0
    assert run_calls == 1


def test_url_md_e2e_fails_when_degraded_ratio_exceeds_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_url_md_script()
    seed_path = tmp_path / "seed.md"
    seed_path.write_text(
        "\n".join(
            [
                "A1 https://example.com/1",
                "A2 https://example.com/2",
                "A3 https://example.com/3",
                "A4 https://example.com/4",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "out"

    captured: dict[str, object] = {}

    def fake_resolve_professor_llm_settings(
        profile_name: str | None = None,
        *,
        default_profile: str,
        strict: bool,
        include_profile: bool = False,
    ) -> dict[str, str]:
        captured["strict"] = strict
        captured["include_profile"] = include_profile
        return {
            "local_llm_base_url": "http://localhost:1234/v1",
            "local_llm_model": "test-local-model",
            "local_llm_api_key": "",
            "online_llm_base_url": "http://localhost:5678/v1",
            "online_llm_model": "test-online-model",
            "online_llm_api_key": "",
            "llm_profile": "gemma4",
        }

    async def always_fail(*_args, **_kwargs):
        raise RuntimeError("pipeline failed")

    monkeypatch.setattr(module, "resolve_professor_llm_settings", fake_resolve_professor_llm_settings)
    monkeypatch.setattr(module, "run_professor_pipeline_v3", always_fail)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--seed-doc",
            str(seed_path),
            "--output-dir",
            str(output_path),
            "--end-index",
            "4",
            "--degraded-ratio-threshold",
            "0.5",
        ],
    )

    code = module.main()
    assert code == 1
    assert captured["strict"] is True
    assert captured["include_profile"] is True


def test_url_md_e2e_succeeds_when_degraded_ratio_within_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_url_md_script()
    seed_path = tmp_path / "seed.md"
    seed_path.write_text(
        "\n".join(
            [
                "A1 https://example.com/1",
                "A2 https://example.com/2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "out"

    def fake_resolve_professor_llm_settings(
        profile_name: str | None = None,
        *,
        default_profile: str,
        strict: bool,
        include_profile: bool = False,
    ) -> dict[str, str]:
        return {
            "local_llm_base_url": "http://localhost:1234/v1",
            "local_llm_model": "test-local-model",
            "local_llm_api_key": "",
            "online_llm_base_url": "http://localhost:5678/v1",
            "online_llm_model": "test-online-model",
            "online_llm_api_key": "",
            "llm_profile": "gemma4",
        }

    calls = {"i": 0}

    async def first_success_then_fail(*_args, **_kwargs):
        calls["i"] += 1
        if calls["i"] == 1:
            return _v3_fake_result()
        raise RuntimeError("pipeline failed")

    monkeypatch.setattr(module, "resolve_professor_llm_settings", fake_resolve_professor_llm_settings)
    monkeypatch.setattr(module, "run_professor_pipeline_v3", first_success_then_fail)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--seed-doc",
            str(seed_path),
            "--output-dir",
            str(output_path),
            "--sample-size",
            "2",
            "--degraded-ratio-threshold",
            "0.6",
        ],
    )

    code = module.main()
    assert code == 0

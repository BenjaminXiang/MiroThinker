from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from company_data_agent.config import ArtifactLayout, CompanyDataAgentConfig, EnvVarRef


def build_config_payload() -> dict[str, object]:
    return {
        "company_list_path": "data/shenzhen_company_list.xlsx",
        "qimingpian": {
            "api_key": {"env_var": "QIMINGPIAN_API_KEY"},
            "endpoint": "https://api.qimingpian.com",
            "cache_ttl_days": 7,
            "rate_limit_per_minute": 100,
        },
        "crawling": {
            "max_concurrency": 3,
            "delay_min_seconds": 2,
            "delay_max_seconds": 5,
            "timeout_seconds": 30,
        },
        "llm": {
            "api_key": {"env_var": "SUMMARY_LLM_API_KEY"},
            "base_url": "https://llm.internal.example/v1",
            "model_name": "summary-model",
        },
        "embedding": {
            "api_key": {"env_var": "EMBEDDING_API_KEY"},
            "base_url": "https://embedding.internal.example/v1",
            "model_name": "embedding-model",
            "dimensions": 1024,
        },
        "postgres": {
            "dsn": {"env_var": "POSTGRES_DSN"},
            "schema": "public",
            "companies_table": "companies",
        },
        "artifacts": {
            "root_dir": "artifacts/company-data-agent",
        },
    }


def test_config_parses_valid_fixture() -> None:
    config = CompanyDataAgentConfig.model_validate(build_config_payload())

    assert config.company_list_path == Path("data/shenzhen_company_list.xlsx")
    assert config.qimingpian.rate_limit_per_minute == 100
    assert config.crawling.delay_max_seconds == 5
    assert config.embedding.dimensions == 1024


def test_env_var_ref_requires_uppercase_snake_case() -> None:
    with pytest.raises(ValidationError, match="uppercase snake case"):
        EnvVarRef.model_validate({"env_var": "qimingpian_api_key"})


def test_invalid_delay_window_is_rejected() -> None:
    payload = build_config_payload()
    payload["crawling"] = {
        "max_concurrency": 3,
        "delay_min_seconds": 5,
        "delay_max_seconds": 2,
        "timeout_seconds": 30,
    }

    with pytest.raises(ValidationError, match="delay_max_seconds"):
        CompanyDataAgentConfig.model_validate(payload)


def test_missing_required_environment_fails_fast() -> None:
    config = CompanyDataAgentConfig.model_validate(build_config_payload())

    with pytest.raises(ValueError, match="QIMINGPIAN_API_KEY"):
        config.validate_required_environment(
            {
                "SUMMARY_LLM_API_KEY": "llm-key",
                "EMBEDDING_API_KEY": "embed-key",
                "POSTGRES_DSN": "postgresql://user:pass@localhost:5432/db",
            }
        )


def test_artifact_layout_resolves_deterministic_paths() -> None:
    layout = ArtifactLayout.model_validate({"root_dir": "artifacts/company-data-agent"})

    assert layout.normalized_companies_path("full-2026-03") == Path(
        "artifacts/company-data-agent/runs/full-2026-03/normalized/companies.jsonl"
    )
    assert layout.raw_payload_path(
        "91440300MA5FUTURE1",
        "qimingpian",
        "detail.json",
    ) == Path(
        "artifacts/company-data-agent/raw/companies/91440300MA5FUTURE1/qimingpian/detail.json"
    )
    assert layout.qimingpian_cache_path("91440300MA5FUTURE1") == Path(
        "artifacts/company-data-agent/cache/qimingpian/91440300MA5FUTURE1.json"
    )
    assert layout.crawl_cache_path("future-robotics.com", "homepage.html") == Path(
        "artifacts/company-data-agent/cache/crawl/future-robotics.com/homepage.html"
    )
    assert layout.run_report_path("full-2026-03", "import-summary.json") == Path(
        "artifacts/company-data-agent/reports/full-2026-03/import-summary.json"
    )


def test_artifact_layout_rejects_path_traversal_segments() -> None:
    layout = ArtifactLayout.model_validate({"root_dir": "artifacts/company-data-agent"})

    with pytest.raises(ValueError, match="path separators"):
        layout.raw_payload_path("91440300MA5FUTURE1", "qimingpian", "../detail.json")


def test_invalid_url_or_secret_contract_is_rejected() -> None:
    payload = build_config_payload()
    payload["embedding"] = {
        "api_key": {"env_var": "EMBEDDING_API_KEY"},
        "base_url": "not-a-url",
        "model_name": "embedding-model",
        "dimensions": 1024,
    }

    with pytest.raises(ValidationError, match="URL"):
        CompanyDataAgentConfig.model_validate(payload)

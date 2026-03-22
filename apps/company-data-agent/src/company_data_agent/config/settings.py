"""Strongly typed configuration models and artifact path helpers."""

from __future__ import annotations

from pathlib import Path
from re import fullmatch
from typing import Mapping

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


def _validate_credit_code(credit_code: str) -> str:
    normalized = credit_code.strip().upper()
    if len(normalized) != 18 or not normalized.isalnum():
        raise ValueError("credit_code must be an 18-character alphanumeric string")
    return normalized


def _validate_simple_filename(filename: str) -> str:
    if not filename or filename in {".", ".."}:
        raise ValueError("filename must not be empty")
    if Path(filename).name != filename:
        raise ValueError("filename must not contain path separators")
    return filename


def _validate_run_id(run_id: str) -> str:
    normalized = run_id.strip()
    if not normalized:
        raise ValueError("run_id must not be empty")
    if "/" in normalized or "\\" in normalized:
        raise ValueError("run_id must not contain path separators")
    return normalized


class EnvVarRef(BaseModel):
    """Reference to a required environment variable secret."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    env_var: str = Field(min_length=1)

    @field_validator("env_var")
    @classmethod
    def validate_env_var(cls, value: str) -> str:
        normalized = value.strip()
        if not fullmatch(r"[A-Z][A-Z0-9_]*", normalized):
            raise ValueError(
                "env_var must be uppercase snake case, for example QIMINGPIAN_API_KEY"
            )
        return normalized

    def resolve(self, environ: Mapping[str, str]) -> str:
        value = environ.get(self.env_var, "").strip()
        if not value:
            raise ValueError(
                f"required environment variable '{self.env_var}' is not set or empty"
            )
        return value


class QimingpianConfig(BaseModel):
    """Configuration contract for the Qimingpian adapter."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    api_key: EnvVarRef
    endpoint: AnyHttpUrl
    cache_ttl_days: int = Field(gt=0)
    rate_limit_per_minute: int = Field(gt=0)


class CrawlConfig(BaseModel):
    """Configuration contract for website crawling."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    max_concurrency: int = Field(gt=0)
    delay_min_seconds: float = Field(ge=0)
    delay_max_seconds: float = Field(ge=0)
    timeout_seconds: int = Field(gt=0)

    @field_validator("delay_max_seconds")
    @classmethod
    def validate_delay_window(cls, value: float, info) -> float:
        delay_min = info.data.get("delay_min_seconds")
        if delay_min is not None and value < delay_min:
            raise ValueError("delay_max_seconds must be greater than or equal to delay_min_seconds")
        return value


class LLMConfig(BaseModel):
    """Configuration contract for an LLM provider used by the pipeline."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    api_key: EnvVarRef
    base_url: AnyHttpUrl
    model_name: str = Field(min_length=1)


class EmbeddingConfig(BaseModel):
    """Configuration contract for the embedding provider."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    api_key: EnvVarRef
    base_url: AnyHttpUrl
    model_name: str = Field(min_length=1)
    dimensions: int = Field(gt=0)


class PostgresConfig(BaseModel):
    """Configuration contract for PostgreSQL connectivity."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    dsn: EnvVarRef
    pg_schema: str = Field(min_length=1, alias="schema")
    companies_table: str = Field(min_length=1, default="companies")


class ArtifactLayout(BaseModel):
    """Deterministic path resolver for normalized outputs, raw payloads, cache, and reports."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    root_dir: Path

    @field_validator("root_dir")
    @classmethod
    def validate_root_dir(cls, value: Path) -> Path:
        if not str(value).strip():
            raise ValueError("root_dir must not be empty")
        return value

    def normalized_companies_path(self, run_id: str) -> Path:
        return self.root_dir / "runs" / _validate_run_id(run_id) / "normalized" / "companies.jsonl"

    def raw_payload_path(self, credit_code: str, source: str, filename: str) -> Path:
        normalized_source = _validate_simple_filename(source)
        normalized_file = _validate_simple_filename(filename)
        return (
            self.root_dir
            / "raw"
            / "companies"
            / _validate_credit_code(credit_code)
            / normalized_source
            / normalized_file
        )

    def qimingpian_cache_path(self, credit_code: str) -> Path:
        return self.root_dir / "cache" / "qimingpian" / f"{_validate_credit_code(credit_code)}.json"

    def crawl_cache_path(self, hostname: str, filename: str) -> Path:
        normalized_host = _validate_simple_filename(hostname)
        normalized_file = _validate_simple_filename(filename)
        return self.root_dir / "cache" / "crawl" / normalized_host / normalized_file

    def run_report_path(self, run_id: str, report_name: str) -> Path:
        normalized_name = _validate_simple_filename(report_name)
        return self.root_dir / "reports" / _validate_run_id(run_id) / normalized_name


class CompanyDataAgentConfig(BaseModel):
    """Top-level validated configuration for the company data agent."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company_list_path: Path
    qimingpian: QimingpianConfig
    crawling: CrawlConfig
    llm: LLMConfig
    embedding: EmbeddingConfig
    postgres: PostgresConfig
    artifacts: ArtifactLayout

    @field_validator("company_list_path")
    @classmethod
    def validate_company_list_path(cls, value: Path) -> Path:
        if not str(value).strip():
            raise ValueError("company_list_path must not be empty")
        return value

    def validate_required_environment(self, environ: Mapping[str, str]) -> None:
        """Fail fast if any referenced secret is missing."""

        self.qimingpian.api_key.resolve(environ)
        self.llm.api_key.resolve(environ)
        self.embedding.api_key.resolve(environ)
        self.postgres.dsn.resolve(environ)

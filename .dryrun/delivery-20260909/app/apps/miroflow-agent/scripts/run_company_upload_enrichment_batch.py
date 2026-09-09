#!/usr/bin/env python3
"""Run resumable upload-scoped company enrichment batches."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterator
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.data_agents.company.enrichment_batch import (  # noqa: E402
    BASELINE_READINESS_STAGE,
    RepresentativeCompanySample,
    build_miss_reason_buckets,
    close_stale_running_enrichment_batches,
    load_representative_company_sample,
    load_pending_company_ids,
    load_stage_pending_company_ids,
    mark_batch_finished,
    mark_batch_progress,
    mark_batch_started,
    mark_company_stage_complete,
    mark_company_stage_running,
    record_batch_heartbeat,
    record_baseline_readiness_stage,
)
from src.data_agents.company.llm_routing import (  # noqa: E402
    COMPANY_LLM_LITE_TASKS,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402


logger = logging.getLogger(__name__)

_STAGE_LLM_TASKS: dict[str, str] = {
    "xlsx_team_synthesis": "trusted_xlsx_structuring",
    "news_iyiou": "search_hint_generation",
    "news_pitchhub": "search_hint_generation",
    "generic_source_judgment": "source_judgment",
    "signal_extract": "financing_extraction",
    "source_product_extract": "generic_product_admission",
    "multi_source_narrative": "multi_source_profile_synthesis",
}

_STAGE_FAMILY: dict[str, str] = {
    BASELINE_READINESS_STAGE: "baseline",
    "xlsx_team_synthesis": "llm",
    "official_product_capture": "web",
    "news_iyiou": "web",
    "news_pitchhub": "web",
    "generic_source_judgment": "llm",
    "signal_extract": "llm",
    "source_product_extract": "llm",
    "multi_source_narrative": "llm",
    "milvus_refresh": "vector",
    "batch_complete": "checkpoint",
}

_STAGE_RATE_LIMIT_KEY: dict[str, str | None] = {
    "official_product_capture": "official_site",
    "news_iyiou": "serper",
    "news_pitchhub": "serper",
    "generic_source_judgment": "deepseek",
    "signal_extract": "deepseek",
    "source_product_extract": "deepseek",
    "multi_source_narrative": "deepseek",
    "xlsx_team_synthesis": "deepseek",
    "milvus_refresh": "milvus",
}

_JSON_REPAIR_STAGES = {
    "xlsx_team_synthesis",
    "generic_source_judgment",
    "signal_extract",
    "source_product_extract",
    "multi_source_narrative",
}

REPORT_STAGE_NAMES = (
    BASELINE_READINESS_STAGE,
    "xlsx_team_synthesis",
    "official_product_capture",
    "news_iyiou",
    "news_pitchhub",
    "generic_source_judgment",
    "signal_extract",
    "source_product_extract",
    "multi_source_narrative",
    "milvus_refresh",
)


@dataclass(frozen=True, slots=True)
class StageExecutionPolicy:
    stage_name: str
    task_family: str
    default_concurrency: int
    max_concurrency: int
    effective_concurrency: int
    timeout_seconds: float
    retry_budget: int
    retry_backoff_seconds: float
    json_repair_retry: bool
    llm_task_type: str | None
    llm_audit: dict[str, object] | None
    rate_limit_key: str | None

    def to_report_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "stage_name": self.stage_name,
            "task_family": self.task_family,
            "default_concurrency": self.default_concurrency,
            "max_concurrency": self.max_concurrency,
            "effective_concurrency": self.effective_concurrency,
            "timeout_seconds": self.timeout_seconds,
            "retry_budget": self.retry_budget,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "json_repair_retry": self.json_repair_retry,
            "rate_limit_key": self.rate_limit_key,
        }
        if self.llm_task_type:
            payload["llm_task_type"] = self.llm_task_type
        if self.llm_audit:
            payload["llm_audit"] = dict(self.llm_audit)
        return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process queued company_enrichment_batch rows.",
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument(
        "--limit",
        type=int,
        default=_optional_int_env("COMPANY_UPLOAD_ENRICHMENT_LIMIT"),
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=_int_env("COMPANY_UPLOAD_ENRICHMENT_CHUNK_SIZE", 20),
    )
    parser.add_argument("--sleep-seconds", default="0.2")
    parser.add_argument("--source-product-limit", type=int, default=1000)
    parser.add_argument("--official-product-max-pages", type=int, default=4)
    parser.add_argument("--milvus-uri", default=os.environ.get("MILVUS_URI"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-live-web", action="store_true")
    parser.add_argument("--skip-official-site", action="store_true")
    parser.add_argument("--skip-yiou-pitchhub", action="store_true")
    parser.add_argument("--skip-generic-serper", action="store_true")
    parser.add_argument("--skip-persistence", action="store_true")
    parser.add_argument("--skip-milvus", action="store_true")
    parser.add_argument("--include-failed", action="store_true")
    parser.add_argument(
        "--stage-concurrency",
        type=int,
        default=_int_env("COMPANY_UPLOAD_ENRICHMENT_STAGE_CONCURRENCY", 8),
    )
    parser.add_argument(
        "--llm-stage-concurrency",
        type=int,
        default=_optional_int_env("COMPANY_UPLOAD_ENRICHMENT_LLM_STAGE_CONCURRENCY"),
    )
    parser.add_argument(
        "--web-stage-concurrency",
        type=int,
        default=_optional_int_env("COMPANY_UPLOAD_ENRICHMENT_WEB_STAGE_CONCURRENCY"),
    )
    parser.add_argument(
        "--stage-subchunk-size",
        type=int,
        default=_optional_int_env("COMPANY_UPLOAD_ENRICHMENT_STAGE_SUBCHUNK_SIZE"),
    )
    parser.add_argument(
        "--stage-timeout-seconds",
        type=float,
        default=_optional_float_env("COMPANY_UPLOAD_ENRICHMENT_STAGE_TIMEOUT_SECONDS"),
    )
    parser.add_argument(
        "--stage-retry-budget",
        type=int,
        default=_optional_int_env("COMPANY_UPLOAD_ENRICHMENT_STAGE_RETRY_BUDGET"),
    )
    parser.add_argument("--retry-backoff-seconds", type=float, default=0.0)
    parser.add_argument(
        "--child-llm-concurrency",
        type=int,
        default=_int_env("COMPANY_UPLOAD_ENRICHMENT_CHILD_LLM_CONCURRENCY", 8),
    )
    parser.add_argument(
        "--child-web-concurrency",
        type=int,
        default=_int_env("COMPANY_UPLOAD_ENRICHMENT_CHILD_WEB_CONCURRENCY", 8),
    )
    parser.add_argument(
        "--child-llm-timeout-seconds",
        type=float,
        default=None,
        help="Pass a per-request LLM timeout override to LLM-heavy child scripts.",
    )
    parser.add_argument(
        "--child-llm-retry-budget",
        type=int,
        default=None,
        help="Pass an OpenAI SDK max_retries override to LLM-heavy child scripts.",
    )
    parser.add_argument(
        "--provider-llm-max-concurrency",
        type=int,
        default=_optional_int_env("COMPANY_UPLOAD_ENRICHMENT_PROVIDER_LLM_MAX_CONCURRENCY"),
        help=(
            "Override the cross-process DeepSeek provider limiter for this batch. "
            "This controls real LLM API concurrency across stage shards."
        ),
    )
    parser.add_argument(
        "--provider-serper-max-concurrency",
        type=int,
        default=_optional_int_env(
            "COMPANY_UPLOAD_ENRICHMENT_PROVIDER_SERPER_MAX_CONCURRENCY"
        ),
        help=(
            "Override the cross-process Serper provider limiter for this batch. "
            "This controls real web-search API concurrency across stage shards."
        ),
    )
    parser.add_argument("--stale-after-minutes", type=int, default=120)
    parser.add_argument("--representative-sample-size", type=int, default=None)
    parser.add_argument(
        "--company-id-file",
        default=None,
        help="Optional newline or JSON list file that freezes the selected companies.",
    )
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args(argv)


def _optional_int_env(name: str) -> int | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return int(value)


def _int_env(name: str, default: int) -> int:
    value = _optional_int_env(name)
    return default if value is None else value


def _optional_float_env(name: str) -> float | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return float(value)


def _apply_provider_rate_limit_overrides(
    *,
    llm_max_concurrency: int | None = None,
    serper_max_concurrency: int | None = None,
) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if llm_max_concurrency is not None:
        value = max(1, int(llm_max_concurrency))
        os.environ["COMPANY_DEEPSEEK_MAX_CONCURRENCY"] = str(value)
        overrides["deepseek_max_concurrency"] = value
    if serper_max_concurrency is not None:
        value = max(1, int(serper_max_concurrency))
        os.environ["COMPANY_SERPER_MAX_CONCURRENCY"] = str(value)
        overrides["serper_max_concurrency"] = value
    return overrides


def _provider_rate_limit_summary() -> dict[str, int | float]:
    return {
        "deepseek_max_concurrency": int(
            os.environ.get("COMPANY_DEEPSEEK_MAX_CONCURRENCY", "8")
        ),
        "serper_max_concurrency": int(
            os.environ.get("COMPANY_SERPER_MAX_CONCURRENCY", "8")
        ),
        "deepseek_min_interval_seconds": float(
            os.environ.get("COMPANY_DEEPSEEK_MIN_INTERVAL_SECONDS", "0.05")
        ),
        "serper_min_interval_seconds": float(
            os.environ.get("COMPANY_SERPER_MIN_INTERVAL_SECONDS", "0.10")
        ),
    }


def _effective_stage_policy(
    stage_name: str,
    *,
    stage_concurrency: int = 1,
    llm_stage_concurrency: int | None = None,
    web_stage_concurrency: int | None = None,
    stage_timeout_seconds: float | None = None,
    stage_retry_budget: int | None = None,
    retry_backoff_seconds: float | None = None,
) -> StageExecutionPolicy:
    task_family = _STAGE_FAMILY.get(stage_name, "other")
    default_concurrency = _default_concurrency_for_stage(
        stage_name=stage_name,
        task_family=task_family,
        stage_concurrency=stage_concurrency,
        llm_stage_concurrency=llm_stage_concurrency,
        web_stage_concurrency=web_stage_concurrency,
    )
    max_concurrency = _max_concurrency_for_stage(stage_name, task_family)
    effective_concurrency = max(1, min(default_concurrency, max_concurrency))
    timeout_seconds = (
        float(stage_timeout_seconds)
        if stage_timeout_seconds is not None
        else _default_timeout_for_stage(stage_name, task_family)
    )
    retry_budget = (
        max(0, int(stage_retry_budget))
        if stage_retry_budget is not None
        else _default_retry_budget_for_stage(stage_name, task_family)
    )
    llm_task_type = _STAGE_LLM_TASKS.get(stage_name)
    return StageExecutionPolicy(
        stage_name=stage_name,
        task_family=task_family,
        default_concurrency=default_concurrency,
        max_concurrency=max_concurrency,
        effective_concurrency=effective_concurrency,
        timeout_seconds=timeout_seconds,
        retry_budget=retry_budget,
        retry_backoff_seconds=max(0.0, float(retry_backoff_seconds or 0.0)),
        json_repair_retry=stage_name in _JSON_REPAIR_STAGES,
        llm_task_type=llm_task_type,
        llm_audit=_llm_audit_for_task(llm_task_type),
        rate_limit_key=_STAGE_RATE_LIMIT_KEY.get(stage_name),
    )


def _default_concurrency_for_stage(
    *,
    stage_name: str,
    task_family: str,
    stage_concurrency: int,
    llm_stage_concurrency: int | None,
    web_stage_concurrency: int | None,
) -> int:
    if stage_name in {BASELINE_READINESS_STAGE, "milvus_refresh", "batch_complete"}:
        return 1
    if task_family == "llm" and llm_stage_concurrency is not None:
        return int(llm_stage_concurrency)
    if task_family == "web" and web_stage_concurrency is not None:
        return int(web_stage_concurrency)
    return int(stage_concurrency or 1)


def _max_concurrency_for_stage(stage_name: str, task_family: str) -> int:
    if stage_name in {BASELINE_READINESS_STAGE, "milvus_refresh", "batch_complete"}:
        return 1
    rate_limit_key = _STAGE_RATE_LIMIT_KEY.get(stage_name)
    if rate_limit_key:
        env_name = f"COMPANY_{rate_limit_key.upper()}_MAX_CONCURRENCY"
        if env_name in os.environ:
            return int(os.environ[env_name])
        provider_defaults = {
            "deepseek": 8,
            "serper": 8,
            "official_site": 2,
            "milvus": 1,
        }
        if rate_limit_key in provider_defaults:
            return provider_defaults[rate_limit_key]
    if task_family == "llm":
        return int(os.environ.get("COMPANY_LLM_STAGE_MAX_CONCURRENCY", "8"))
    if task_family == "web":
        return int(os.environ.get("COMPANY_WEB_STAGE_MAX_CONCURRENCY", "8"))
    return int(os.environ.get("COMPANY_STAGE_MAX_CONCURRENCY", "8"))


def _default_timeout_for_stage(stage_name: str, task_family: str) -> float:
    env_value = os.environ.get("COMPANY_UPLOAD_ENRICHMENT_TIMEOUT_SECONDS")
    if env_value:
        return float(env_value)
    if stage_name == "milvus_refresh":
        return 600.0
    if task_family in {"llm", "web"}:
        return 900.0
    return 300.0


def _default_retry_budget_for_stage(stage_name: str, task_family: str) -> int:
    if stage_name in {BASELINE_READINESS_STAGE, "milvus_refresh", "batch_complete"}:
        return 0
    if task_family in {"llm", "web"}:
        return 1
    return 0


def _llm_audit_for_task(task_type: str | None) -> dict[str, object] | None:
    if not task_type:
        return None
    model = (
        "deepseek-v4-lite"
        if task_type in COMPANY_LLM_LITE_TASKS
        else "deepseek-v4-pro"
    )
    return {
        "task_type": task_type,
        "llm_profile": model,
        "model": model,
        "cascade_strategy": "direct",
    }


def _stage_policy_summary(
    *,
    stage_names: list[str],
    stage_concurrency: int,
    llm_stage_concurrency: int | None,
    web_stage_concurrency: int | None,
    stage_timeout_seconds: float | None,
    stage_retry_budget: int | None,
    retry_backoff_seconds: float,
) -> dict[str, dict[str, object]]:
    return {
        stage_name: _effective_stage_policy(
            stage_name,
            stage_concurrency=stage_concurrency,
            llm_stage_concurrency=llm_stage_concurrency,
            web_stage_concurrency=web_stage_concurrency,
            stage_timeout_seconds=stage_timeout_seconds,
            stage_retry_budget=stage_retry_budget,
            retry_backoff_seconds=retry_backoff_seconds,
        ).to_report_dict()
        for stage_name in stage_names
    }


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _agent_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _company_id_args(company_ids: list[str]) -> list[str]:
    args: list[str] = []
    for company_id in company_ids:
        args.extend(["--company-id", company_id])
    return args


def _build_stage_commands(
    *,
    batch_id: UUID | str,
    company_ids: list[str],
    skip_milvus: bool,
    sleep_seconds: str,
    source_product_limit: int,
    official_product_max_pages: int,
    milvus_uri: str | None = None,
    dry_run: bool = False,
    skip_live_web: bool = False,
    skip_official_site: bool = False,
    skip_yiou_pitchhub: bool = False,
    skip_generic_serper: bool = False,
    skip_persistence: bool = False,
    child_llm_concurrency: int = 4,
    child_web_concurrency: int = 3,
    child_llm_timeout_seconds: float | None = None,
    child_llm_retry_budget: int | None = None,
) -> list[tuple[str, list[str]]]:
    company_args = _company_id_args(company_ids)
    child_dry_run = dry_run or skip_persistence
    llm_child_args = ["--concurrency", str(max(1, int(child_llm_concurrency or 1)))]
    web_child_args = ["--concurrency", str(max(1, int(child_web_concurrency or 1)))]
    llm_request_args: list[str] = []
    if child_llm_timeout_seconds is not None:
        llm_request_args.extend(
            ["--llm-timeout-seconds", str(child_llm_timeout_seconds)]
        )
    if child_llm_retry_budget is not None:
        llm_request_args.extend(["--llm-retry-budget", str(child_llm_retry_budget)])
    high_trust_source_adapters = [
        "--source-adapter",
        "iyiou",
        "--source-adapter",
        "pitchhub_36kr",
    ]
    synthesis_source_adapters = [
        *high_trust_source_adapters,
        "--source-adapter",
        "generic_web",
    ]
    commands: list[tuple[str, list[str]]] = []
    commands.append((
        "xlsx_team_synthesis",
        [
            sys.executable,
            str(_agent_root() / "scripts" / "run_company_xlsx_team_synthesis.py"),
            "--enrichment-batch-id",
            str(batch_id),
            "--skip-narrative",
            "--checkpoint-stage",
            "xlsx_team_synthesis",
            *llm_child_args,
            *llm_request_args,
            *company_args,
        ],
    ))
    if not skip_live_web and not skip_official_site:
        commands.append((
            "official_product_capture",
            [
                sys.executable,
                str(_agent_root() / "scripts" / "run_company_official_product_capture.py"),
                "--max-pages",
                str(official_product_max_pages),
                "--sleep-seconds",
                sleep_seconds,
                "--enable-js-render",
                "--output",
                "-",
                "--enrichment-batch-id",
                str(batch_id),
                *company_args,
            ],
        ))
    if not skip_live_web and not skip_yiou_pitchhub:
        commands.append((
            "news_iyiou",
            [
                sys.executable,
                str(_agent_root() / "scripts" / "run_company_news_ingest.py"),
                "--connector",
                "iyiou",
                "--priority",
                "all",
                "--since",
                "2000-01-01",
                "--sleep-seconds",
                sleep_seconds,
                "--serper-fetch-article-text",
                "--serper-article-max-chars",
                "4000",
                "--llm-search-hints",
                "--enrichment-batch-id",
                str(batch_id),
                "--checkpoint-stage",
                "news_iyiou",
                *web_child_args,
                *llm_request_args,
                *company_args,
            ],
        ))
        commands.append((
            "news_pitchhub",
            [
                sys.executable,
                str(_agent_root() / "scripts" / "run_company_news_ingest.py"),
                "--connector",
                "pitchhub",
                "--priority",
                "all",
                "--since",
                "2000-01-01",
                "--sleep-seconds",
                sleep_seconds,
                "--serper-article-max-chars",
                "4000",
                "--llm-search-hints",
                "--enrichment-batch-id",
                str(batch_id),
                "--checkpoint-stage",
                "news_pitchhub",
                *web_child_args,
                *llm_request_args,
                *company_args,
            ],
        ))
    if not skip_live_web and not skip_generic_serper:
        commands.append((
            "generic_source_judgment",
            [
                sys.executable,
                str(_agent_root() / "scripts" / "run_company_generic_source_judgment.py"),
                "--since",
                "2000-01-01",
                "--llm-search-hints",
                "--enrichment-batch-id",
                str(batch_id),
                "--checkpoint-stage",
                "generic_source_judgment",
                *llm_child_args,
                *llm_request_args,
                *company_args,
            ],
        ))
    commands.extend([
        (
            "signal_extract",
            [
                sys.executable,
                str(_agent_root() / "scripts" / "run_company_signal_extract.py"),
                "--since",
                "2000-01-01",
                *high_trust_source_adapters,
                "--enrichment-batch-id",
                str(batch_id),
                "--checkpoint-stage",
                "signal_extract",
                *llm_child_args,
                *llm_request_args,
                *company_args,
            ],
        ),
        (
            "source_product_extract",
            [
                sys.executable,
                str(_agent_root() / "scripts" / "run_company_source_product_extract.py"),
                "--limit",
                str(max(source_product_limit, len(company_ids) * 20)),
                *synthesis_source_adapters,
                "--llm-structured-extract",
                "--enrichment-batch-id",
                str(batch_id),
                "--checkpoint-stage",
                "source_product_extract",
                *llm_child_args,
                *llm_request_args,
                *company_args,
            ],
        ),
        (
            "multi_source_narrative",
            [
                sys.executable,
                str(_agent_root() / "scripts" / "run_company_xlsx_team_synthesis.py"),
                "--enrichment-batch-id",
                str(batch_id),
                "--include-source-materials",
                "--skip-team",
                "--checkpoint-stage",
                "multi_source_narrative",
                *llm_child_args,
                *llm_request_args,
                *company_args,
            ],
        ),
    ])
    if child_dry_run:
        commands = [
            (name, _with_dry_run(command))
            for name, command in commands
            if name != "milvus_refresh"
        ]
        skip_milvus = True
    if not skip_milvus:
        milvus_args: list[str] = []
        if milvus_uri:
            milvus_args = ["--milvus-uri", milvus_uri]
        commands.append(
            (
                "milvus_refresh",
                [
                    sys.executable,
                    str(_agent_root() / "scripts" / "run_milvus_backfill.py"),
                    "--domain",
                    "company",
                    "--batch-size",
                    str(max(1, len(company_ids))),
                    *milvus_args,
                    *company_args,
                ],
            )
        )
    return commands


def _with_dry_run(command: list[str]) -> list[str]:
    if "--dry-run" in command:
        return command
    return [*command, "--dry-run"]


def _run_command(
    name: str,
    command: list[str],
    dsn: str,
    *,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["DATABASE_URL"] = dsn
    env.setdefault(
        "MIROTHINKER_COMPANY_SOURCE_CACHE_DIR",
        str(_agent_root().parents[1] / "data" / "company_source_cache"),
    )
    _scrub_milvus_env_for_cli_uri(command, env)
    timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else float(os.environ.get("COMPANY_UPLOAD_ENRICHMENT_TIMEOUT_SECONDS", "900"))
    )
    try:
        completed = subprocess.run(
            command,
            cwd=_agent_root(),
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.output or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        payload = _parse_command_json_output(str(stdout))
        stderr_tail = (
            f"Command timed out after {timeout:g} seconds"
            + (f"\n{stderr}" if stderr else "")
        )
        return {
            "name": name,
            "status": "failed",
            "returncode": None,
            "report": payload,
            "stderr_tail": stderr_tail[-1000:],
        }
    payload = _parse_command_json_output(completed.stdout)
    status = "succeeded" if completed.returncode == 0 else "failed"
    return {
        "name": name,
        "status": status,
        "returncode": completed.returncode,
        "report": payload,
        "stderr_tail": completed.stderr[-1000:] if completed.returncode else "",
    }


def _scrub_milvus_env_for_cli_uri(command: list[str], env: dict[str, str]) -> None:
    if "--milvus-uri" not in command:
        return
    try:
        uri = command[command.index("--milvus-uri") + 1]
    except IndexError:
        return
    if _is_local_milvus_uri(uri):
        env.pop("MILVUS_URI", None)


def _is_local_milvus_uri(uri: str) -> bool:
    value = str(uri or "").strip().lower()
    if not value or value == ":memory:":
        return False
    return not (value.startswith("http://") or value.startswith("https://"))


def _parse_command_json_output(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        return payload
    for line in reversed(stdout.strip().splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _chunks(values: list[str], size: int) -> list[list[str]]:
    size = max(1, size)
    return [values[index : index + size] for index in range(0, len(values), size)]


def _stage_subchunks(
    company_ids: list[str],
    *,
    stage_name: str,
    stage_concurrency: int,
    stage_subchunk_size: int | None,
) -> list[list[str]]:
    if not company_ids:
        return []
    if stage_name == "milvus_refresh" or stage_concurrency <= 1:
        return [company_ids]
    if stage_subchunk_size is not None and stage_subchunk_size > 0:
        size = stage_subchunk_size
    else:
        concurrency = max(1, int(stage_concurrency))
        size = max(1, (len(company_ids) + concurrency - 1) // concurrency)
    return _chunks(company_ids, size)


def _commit_if_supported(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def _record_batch_heartbeat(conn: Any, **kwargs: Any) -> None:
    try:
        record_batch_heartbeat(conn, **kwargs)
    except Exception as exc:  # noqa: BLE001 - telemetry must not stop enrichment.
        logger.warning("Company enrichment heartbeat update skipped: %s", exc)


def _skipped_stage_reasons(
    *,
    skip_milvus: bool,
    skip_live_web: bool,
    skip_official_site: bool,
    skip_yiou_pitchhub: bool,
    skip_generic_serper: bool,
    skip_persistence: bool,
) -> dict[str, str]:
    reasons: dict[str, str] = {}
    if skip_live_web:
        reasons.update(
            {
                "official_product_capture": "skip_live_web",
                "news_iyiou": "skip_live_web",
                "news_pitchhub": "skip_live_web",
                "generic_source_judgment": "skip_live_web",
            }
        )
    if skip_official_site:
        reasons["official_product_capture"] = "skip_official_site"
    if skip_yiou_pitchhub:
        reasons["news_iyiou"] = "skip_yiou_pitchhub"
        reasons["news_pitchhub"] = "skip_yiou_pitchhub"
    if skip_generic_serper:
        reasons["generic_source_judgment"] = "skip_generic_serper"
    if skip_persistence:
        reasons["persistence"] = "dry_run_or_skip_persistence"
    if skip_milvus:
        reasons["milvus_refresh"] = "skip_milvus"
    return reasons


def _enabled_stage_names(skipped_stages: dict[str, str]) -> list[str]:
    return [stage for stage in REPORT_STAGE_NAMES if stage not in skipped_stages]


def _residual_risks(
    *,
    dry_run: bool,
    skipped_stages: dict[str, str],
    rag_smoke_status: str,
) -> list[str]:
    risks: list[str] = []
    if dry_run:
        risks.append("dry_run_no_persistence")
    for stage, reason in sorted(skipped_stages.items()):
        risks.append(f"{stage}:{reason}")
    if rag_smoke_status != "passed":
        risks.append(f"rag_smoke:{rag_smoke_status}")
    risks.append("requires_5180_manual_inspection")
    return risks


def _pending_company_sample(
    company_ids: list[str],
    *,
    strategy: str = "batch_pending_order",
) -> RepresentativeCompanySample:
    return RepresentativeCompanySample(
        company_ids=list(company_ids),
        candidates_total=len(company_ids),
        selected_count=len(company_ids),
        selection_criteria={
            "strategy": strategy,
            "stable_sort": "company_id",
        },
        bucket_summary=[],
    )


def _load_company_id_file(path: str | os.PathLike[str]) -> list[str]:
    raw = Path(path).read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if raw.startswith("["):
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("--company-id-file JSON payload must be a list")
        ids = [str(item).strip() for item in payload if str(item).strip()]
    else:
        ids = [
            line.strip()
            for line in raw.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    seen: set[str] = set()
    result: list[str] = []
    for company_id in ids:
        if company_id in seen:
            continue
        seen.add(company_id)
        result.append(company_id)
    return result


def _load_company_sample(
    conn: Any,
    *,
    batch_id: UUID | str,
    limit: int | None,
    include_failed: bool,
    representative_sample_size: int | None,
    explicit_company_ids: list[str] | None = None,
) -> RepresentativeCompanySample:
    if explicit_company_ids is not None:
        company_ids = list(explicit_company_ids)
        if limit is not None:
            company_ids = company_ids[: int(limit)]
        return _pending_company_sample(
            company_ids,
            strategy="explicit_company_id_file",
        )
    if representative_sample_size is not None:
        requested = int(representative_sample_size)
        if limit is not None:
            requested = min(requested, int(limit))
        return load_representative_company_sample(
            conn,
            batch_id=batch_id,
            sample_size=requested,
            include_failed=include_failed,
        )
    company_ids = load_pending_company_ids(
        conn,
        batch_id=batch_id,
        limit=limit,
        include_failed=include_failed,
    )
    return _pending_company_sample(company_ids)


def _validation_scope(
    *,
    representative_sample_size: int | None,
    company_count: int,
    explicit_company_ids: bool = False,
) -> dict[str, Any]:
    if explicit_company_ids:
        return {
            "scope": "explicit_company_ids",
            "companies_selected": company_count,
            "full_population_attempted": False,
        }
    if representative_sample_size is None:
        return {
            "scope": "batch_pending",
            "companies_selected": company_count,
            "full_population_attempted": False,
        }
    return {
        "scope": "representative_sample",
        "sample_size_requested": int(representative_sample_size),
        "companies_selected": company_count,
        "full_population_attempted": False,
    }


def _expected_writes(
    *,
    company_count: int,
    dry_run: bool,
    plan_only: bool,
    skip_persistence: bool,
    skip_milvus: bool,
) -> dict[str, Any]:
    no_domain_writes = bool(dry_run or plan_only or skip_persistence)
    domain_rows = {
        "company_news_item": 0 if no_domain_writes else None,
        "company_signal_event": 0 if no_domain_writes else None,
        "company_product": 0 if no_domain_writes else None,
        "company_application_scenario": 0 if no_domain_writes else None,
        "company_vector_upsert": (
            0 if no_domain_writes or skip_milvus else company_count
        ),
    }
    return {
        "mode": (
            "plan_only_no_writes"
            if plan_only
            else "dry_run_no_domain_writes"
            if no_domain_writes
            else "live_bounded_to_selected_companies"
        ),
        "domain_rows": domain_rows,
        "batch_state_rows": 0 if plan_only else company_count,
        "bounded_to_selected_company_ids": True,
    }


def _blocked_prerequisites(
    *,
    company_count: int,
    representative_sample_size: int | None,
    skip_live_web: bool,
    skip_yiou_pitchhub: bool,
    skip_generic_serper: bool,
) -> list[str]:
    blockers: list[str] = []
    if company_count <= 0:
        blockers.append("no_companies_selected")
    if representative_sample_size is not None and company_count < int(
        representative_sample_size
    ):
        blockers.append("sample_underfilled")
    if (
        not skip_live_web
        and (not skip_yiou_pitchhub or not skip_generic_serper)
        and not os.environ.get("SERPER_API_KEY")
    ):
        blockers.append("missing_serper_api_key")
    return blockers


def _build_plan_report(
    *,
    batch_id: UUID | str,
    sample: RepresentativeCompanySample,
    sample_size_requested: int | None,
    dry_run: bool,
    skip_milvus: bool,
    skip_live_web: bool,
    skip_official_site: bool,
    skip_yiou_pitchhub: bool,
    skip_generic_serper: bool,
    skip_persistence: bool,
    stage_concurrency: int,
    llm_stage_concurrency: int | None,
    web_stage_concurrency: int | None,
    stage_timeout_seconds: float | None,
    stage_retry_budget: int | None,
    retry_backoff_seconds: float,
    child_llm_concurrency: int = 4,
    child_web_concurrency: int = 3,
    child_llm_timeout_seconds: float | None = None,
    child_llm_retry_budget: int | None = None,
    explicit_company_ids: bool = False,
) -> dict[str, Any]:
    skipped_stages = _skipped_stage_reasons(
        skip_milvus=skip_milvus,
        skip_live_web=skip_live_web,
        skip_official_site=skip_official_site,
        skip_yiou_pitchhub=skip_yiou_pitchhub,
        skip_generic_serper=skip_generic_serper,
        skip_persistence=skip_persistence,
    )
    rag_smoke_status = "not_run"
    company_count = len(sample.company_ids)
    return {
        "batch_id": str(batch_id),
        "status": "planned",
        "plan_only": True,
        "dry_run": dry_run,
        "selected_company_ids": list(sample.company_ids),
        "companies_selected": company_count,
        "selection": sample.to_report_dict(
            sample_size_requested=sample_size_requested,
        ),
        "validation_scope": _validation_scope(
            representative_sample_size=sample_size_requested,
            company_count=company_count,
            explicit_company_ids=explicit_company_ids,
        ),
        "expected_writes": _expected_writes(
            company_count=company_count,
            dry_run=True,
            plan_only=True,
            skip_persistence=True,
            skip_milvus=skip_milvus,
        ),
        "blocked_prerequisites": _blocked_prerequisites(
            company_count=company_count,
            representative_sample_size=sample_size_requested,
            skip_live_web=skip_live_web,
            skip_yiou_pitchhub=skip_yiou_pitchhub,
            skip_generic_serper=skip_generic_serper,
        ),
        "rag_smoke": {
            "status": rag_smoke_status,
            "reason": "rag_smoke_is_post_batch_validation_gate",
        },
        "run_config": {
            "dry_run": dry_run,
            "plan_only": True,
            "enabled_stages": _enabled_stage_names(skipped_stages),
            "skipped_stages": skipped_stages,
            "stage_policies": _stage_policy_summary(
                stage_names=list(REPORT_STAGE_NAMES),
                stage_concurrency=stage_concurrency,
                llm_stage_concurrency=llm_stage_concurrency,
                web_stage_concurrency=web_stage_concurrency,
                stage_timeout_seconds=stage_timeout_seconds,
                stage_retry_budget=stage_retry_budget,
                retry_backoff_seconds=retry_backoff_seconds,
            ),
            "child_concurrency": {
                "llm": max(1, int(child_llm_concurrency or 1)),
                "web": max(1, int(child_web_concurrency or 1)),
            },
            "child_llm_policy": {
                "timeout_seconds": child_llm_timeout_seconds,
                "retry_budget": child_llm_retry_budget,
            },
            "provider_rate_limits": _provider_rate_limit_summary(),
        },
        "residual_risks": _residual_risks(
            dry_run=True,
            skipped_stages=skipped_stages,
            rag_smoke_status=rag_smoke_status,
        ),
        "summary": _empty_batch_summary(),
        "stage_reports": [],
    }


def _empty_batch_summary() -> dict[str, Any]:
    return {
        "companies_processed": 0,
        "companies_skipped_by_checkpoint": 0,
        "stage_skipped_by_checkpoint": {},
        "stage_succeeded_count": 0,
        "stage_failed_count": 0,
        "stage_reports_count": 0,
        "query_count": 0,
        "fetch_count": 0,
        "accepted_source_count": 0,
        "rejected_source_count": 0,
        "llm_failure_count": 0,
        "official_failure_reasons": {},
        "product_count": 0,
        "scenario_count": 0,
        "products_with_target_customers": 0,
        "funding_event_count": 0,
        "narrative_count": 0,
        "vector_refresh_count": 0,
        "rejected_candidate_count": 0,
        "rejected_candidate_reasons": {},
        "miss_reason_counts": {},
        "source_adapter_counts": {},
    }


def _record_checkpoint_skip(
    report: dict[str, Any],
    *,
    stage_name: str,
    requested_count: int,
    pending_count: int,
) -> None:
    skipped = max(0, int(requested_count) - int(pending_count))
    if skipped <= 0:
        return
    summary = report.setdefault("summary", _empty_batch_summary())
    summary["companies_skipped_by_checkpoint"] = (
        int(summary.get("companies_skipped_by_checkpoint") or 0) + skipped
    )
    skipped_by_stage = summary.setdefault("stage_skipped_by_checkpoint", {})
    skipped_by_stage[stage_name] = int(skipped_by_stage.get(stage_name) or 0) + skipped


def _accumulate_stage_report(
    report: dict[str, Any],
    stage_report: dict[str, Any],
) -> None:
    summary = report.setdefault("summary", _empty_batch_summary())
    summary["stage_reports_count"] = int(summary.get("stage_reports_count") or 0) + 1
    if stage_report.get("status") == "succeeded":
        summary["stage_succeeded_count"] = int(summary.get("stage_succeeded_count") or 0) + 1
    elif stage_report.get("status") == "failed":
        summary["stage_failed_count"] = int(summary.get("stage_failed_count") or 0) + 1
    payload = stage_report.get("report") or {}
    if not isinstance(payload, dict):
        payload = {}
    summary["query_count"] += int(
        payload.get("queries_run")
        or payload.get("search_audit_rows")
        or payload.get("query_count")
        or 0
    )
    summary["fetch_count"] += int(
        payload.get("fetch_count")
        or payload.get("news_fetched")
        or payload.get("official_pages_captured")
        or 0
    )
    summary["accepted_source_count"] += int(
        payload.get("accepted_sources")
        or payload.get("news_fetched")
        or payload.get("accepted_source_count")
        or 0
    )
    summary["rejected_source_count"] += int(
        payload.get("rejected_sources")
        or payload.get("rejected_source_count")
        or 0
    )
    summary["llm_failure_count"] += int(
        payload.get("llm_fallback_failed")
        or payload.get("llm_search_hints_failed")
        or payload.get("news_with_errors")
        or 0
    )
    summary["product_count"] += int(
        payload.get("products_inserted") or payload.get("products_written") or 0
    )
    summary["scenario_count"] += int(
        payload.get("scenarios_inserted") or payload.get("scenarios_written") or 0
    )
    summary["products_with_target_customers"] += int(
        payload.get("products_with_target_customers") or 0
    )
    summary["funding_event_count"] += int(payload.get("events_inserted") or 0)
    summary["narrative_count"] += int(payload.get("narratives_written") or 0)
    if stage_report.get("name") == "milvus_refresh" and stage_report.get("status") == "succeeded":
        summary["vector_refresh_count"] += int(stage_report.get("company_count") or 0)
    source_adapter_counts = payload.get("source_adapter_counts") or {}
    if isinstance(source_adapter_counts, dict):
        summary_counts = summary.setdefault("source_adapter_counts", {})
        for adapter, counts in source_adapter_counts.items():
            if not isinstance(counts, dict):
                continue
            adapter_bucket = summary_counts.setdefault(str(adapter), {})
            for key, value in counts.items():
                adapter_bucket[str(key)] = int(adapter_bucket.get(str(key)) or 0) + int(
                    value or 0
                )
    for reason, count in (payload.get("official_failure_reasons") or {}).items():
        reasons = summary.setdefault("official_failure_reasons", {})
        reasons[str(reason)] = int(reasons.get(str(reason)) or 0) + int(count or 0)
    rejected_reasons = payload.get("rejected_candidate_reasons") or {}
    if isinstance(rejected_reasons, dict):
        total_rejected = 0
        summary_reasons = summary.setdefault("rejected_candidate_reasons", {})
        for reason, count in rejected_reasons.items():
            count_int = int(count or 0)
            total_rejected += count_int
            summary_reasons[str(reason)] = (
                int(summary_reasons.get(str(reason)) or 0) + count_int
            )
        summary["rejected_candidate_count"] = (
            int(summary.get("rejected_candidate_count") or 0) + total_rejected
        )


def _finalize_batch_summary(report: dict[str, Any]) -> None:
    summary = report.setdefault("summary", _empty_batch_summary())
    summary["companies_processed"] = int(report.get("companies_processed") or 0)


def _batch_quality_report(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.setdefault("summary", _empty_batch_summary())
    companies_selected = int(report.get("companies_selected") or 0)
    companies_processed = int(report.get("companies_processed") or 0)
    return {
        "headline": f"{companies_processed}/{companies_selected} companies processed",
        "status": str(report.get("status") or "unknown"),
        "companies_selected": companies_selected,
        "companies_processed": companies_processed,
        "query_count": int(summary.get("query_count") or 0),
        "accepted_source_count": int(summary.get("accepted_source_count") or 0),
        "rejected_source_count": int(summary.get("rejected_source_count") or 0),
        "product_count": int(summary.get("product_count") or 0),
        "scenario_count": int(summary.get("scenario_count") or 0),
        "funding_event_count": int(summary.get("funding_event_count") or 0),
        "vector_refresh_count": int(summary.get("vector_refresh_count") or 0),
        "failed_stage_count": int(summary.get("stage_failed_count") or 0),
        "top_miss_reason_buckets": _batch_miss_reason_buckets(report),
        "sample_company_ids": list(report.get("selected_company_ids") or [])[:5],
    }


def _batch_miss_reason_buckets(report: dict[str, Any]) -> dict[str, int]:
    summary = report.setdefault("summary", _empty_batch_summary())
    return build_miss_reason_buckets(
        miss_reasons=summary.get("miss_reason_counts") or {},
        official_failure_reasons=summary.get("official_failure_reasons") or {},
        rejected_candidate_reasons=summary.get("rejected_candidate_reasons") or {},
    )


def _record_miss_reasons(
    report: dict[str, Any],
    miss_reason_by_company: dict[str, str | None],
) -> None:
    if not miss_reason_by_company:
        return
    summary = report.setdefault("summary", _empty_batch_summary())
    counts = summary.setdefault("miss_reason_counts", {})
    for reason in miss_reason_by_company.values():
        if not reason:
            continue
        key = str(reason)
        counts[key] = int(counts.get(key) or 0) + 1


def process_batch(
    *,
    dsn: str,
    batch_id: UUID | str,
    limit: int | None = None,
    chunk_size: int = 20,
    skip_milvus: bool = False,
    include_failed: bool = False,
    sleep_seconds: str = "0.2",
    source_product_limit: int = 1000,
    official_product_max_pages: int = 4,
    milvus_uri: str | None = None,
    dry_run: bool = False,
    skip_live_web: bool = False,
    skip_official_site: bool = False,
    skip_yiou_pitchhub: bool = False,
    skip_generic_serper: bool = False,
    skip_persistence: bool = False,
    stale_after_minutes: int = 120,
    stage_concurrency: int = 1,
    llm_stage_concurrency: int | None = None,
    web_stage_concurrency: int | None = None,
    stage_subchunk_size: int | None = None,
    stage_timeout_seconds: float | None = None,
    stage_retry_budget: int | None = None,
    retry_backoff_seconds: float = 0.0,
    child_llm_concurrency: int = 4,
    child_web_concurrency: int = 3,
    child_llm_timeout_seconds: float | None = None,
    child_llm_retry_budget: int | None = None,
    representative_sample_size: int | None = None,
    explicit_company_ids: list[str] | None = None,
    plan_only: bool = False,
) -> dict[str, Any]:
    conn = _open_database_connection(dsn)
    try:
        sample = _load_company_sample(
            conn,
            batch_id=batch_id,
            limit=limit,
            include_failed=include_failed,
            representative_sample_size=representative_sample_size,
            explicit_company_ids=explicit_company_ids,
        )
        if plan_only:
            return _build_plan_report(
                batch_id=batch_id,
                sample=sample,
                sample_size_requested=representative_sample_size,
                dry_run=True,
                skip_milvus=skip_milvus,
                skip_live_web=skip_live_web,
                skip_official_site=skip_official_site,
                skip_yiou_pitchhub=skip_yiou_pitchhub,
                skip_generic_serper=skip_generic_serper,
                skip_persistence=True,
                stage_concurrency=stage_concurrency,
                llm_stage_concurrency=llm_stage_concurrency,
                web_stage_concurrency=web_stage_concurrency,
                stage_timeout_seconds=stage_timeout_seconds,
                stage_retry_budget=stage_retry_budget,
                retry_backoff_seconds=retry_backoff_seconds,
                child_llm_concurrency=child_llm_concurrency,
                child_web_concurrency=child_web_concurrency,
                child_llm_timeout_seconds=child_llm_timeout_seconds,
                child_llm_retry_budget=child_llm_retry_budget,
                explicit_company_ids=explicit_company_ids is not None,
            )
        stale_closed = close_stale_running_enrichment_batches(
            conn,
            stale_after_minutes=stale_after_minutes,
        )
        company_ids = list(sample.company_ids)
        mark_batch_started(conn, batch_id=batch_id)
        _record_batch_heartbeat(
            conn,
            batch_id=batch_id,
            current_stage="started",
            quality_report={
                "headline": f"0/{len(company_ids)} companies processed",
                "companies_selected": len(company_ids),
                "companies_processed": 0,
            },
            miss_reason_buckets={},
        )
        _commit_if_supported(conn)
        skipped_stages = _skipped_stage_reasons(
            skip_milvus=skip_milvus,
            skip_live_web=skip_live_web,
            skip_official_site=skip_official_site,
            skip_yiou_pitchhub=skip_yiou_pitchhub,
            skip_generic_serper=skip_generic_serper,
            skip_persistence=skip_persistence,
        )
        report: dict[str, Any] = {
            "batch_id": str(batch_id),
            "selected_company_ids": list(company_ids),
            "companies_selected": len(company_ids),
            "selection": sample.to_report_dict(
                sample_size_requested=representative_sample_size,
            ),
            "validation_scope": _validation_scope(
                representative_sample_size=representative_sample_size,
                company_count=len(company_ids),
                explicit_company_ids=explicit_company_ids is not None,
            ),
            "expected_writes": _expected_writes(
                company_count=len(company_ids),
                dry_run=dry_run,
                plan_only=False,
                skip_persistence=skip_persistence,
                skip_milvus=skip_milvus,
            ),
            "blocked_prerequisites": _blocked_prerequisites(
                company_count=len(company_ids),
                representative_sample_size=representative_sample_size,
                skip_live_web=skip_live_web,
                skip_yiou_pitchhub=skip_yiou_pitchhub,
                skip_generic_serper=skip_generic_serper,
            ),
            "companies_processed": 0,
            "status": "succeeded",
            "dry_run": dry_run,
            "stale_runs_closed": stale_closed,
            "rag_smoke": {
                "status": "not_run",
                "reason": "rag_smoke_is_post_batch_validation_gate",
            },
            "run_config": {
                "dry_run": dry_run,
                "enabled_stages": _enabled_stage_names(skipped_stages),
                "skipped_stages": skipped_stages,
                "stage_policies": _stage_policy_summary(
                    stage_names=list(REPORT_STAGE_NAMES),
                    stage_concurrency=stage_concurrency,
                    llm_stage_concurrency=llm_stage_concurrency,
                    web_stage_concurrency=web_stage_concurrency,
                    stage_timeout_seconds=stage_timeout_seconds,
                    stage_retry_budget=stage_retry_budget,
                    retry_backoff_seconds=retry_backoff_seconds,
                ),
                "child_concurrency": {
                    "llm": max(1, int(child_llm_concurrency or 1)),
                    "web": max(1, int(child_web_concurrency or 1)),
                },
                "child_llm_policy": {
                    "timeout_seconds": child_llm_timeout_seconds,
                    "retry_budget": child_llm_retry_budget,
                },
                "provider_rate_limits": _provider_rate_limit_summary(),
            },
            "residual_risks": _residual_risks(
                dry_run=dry_run,
                skipped_stages=skipped_stages,
                rag_smoke_status="not_run",
            ),
            "summary": _empty_batch_summary(),
            "stage_reports": [],
        }
        for chunk in _chunks(company_ids, chunk_size):
            baseline_stage_ids = load_stage_pending_company_ids(
                conn=conn,
                batch_id=batch_id,
                stage=BASELINE_READINESS_STAGE,
                company_ids=chunk,
            )
            _record_checkpoint_skip(
                report,
                stage_name=BASELINE_READINESS_STAGE,
                requested_count=len(chunk),
                pending_count=len(baseline_stage_ids),
            )
            baseline_report = _run_baseline_readiness_for_chunk(
                conn=conn,
                batch_id=batch_id,
                company_ids=baseline_stage_ids,
            )
            if baseline_report:
                report["stage_reports"].append(baseline_report)
                _accumulate_stage_report(report, baseline_report)
                blocked = int(
                    (baseline_report.get("report") or {}).get("baseline_blocked")
                    or 0
                )
                if blocked:
                    _record_miss_reasons(
                        report,
                        {
                            f"baseline_blocked_{index}": "baseline_not_ready"
                            for index in range(blocked)
                        },
                    )
                _commit_if_supported(conn)
            for stage_name, command_template in _build_stage_commands(
                batch_id=batch_id,
                company_ids=chunk,
                skip_milvus=skip_milvus,
                sleep_seconds=sleep_seconds,
                source_product_limit=source_product_limit,
                official_product_max_pages=official_product_max_pages,
                milvus_uri=milvus_uri,
                dry_run=dry_run,
                skip_live_web=skip_live_web,
                skip_official_site=skip_official_site,
                skip_yiou_pitchhub=skip_yiou_pitchhub,
                skip_generic_serper=skip_generic_serper,
                skip_persistence=skip_persistence,
                child_llm_concurrency=child_llm_concurrency,
                child_web_concurrency=child_web_concurrency,
                child_llm_timeout_seconds=child_llm_timeout_seconds,
                child_llm_retry_budget=child_llm_retry_budget,
            ):
                stage_company_ids = load_stage_pending_company_ids(
                    conn,
                    batch_id=batch_id,
                    stage=stage_name,
                    company_ids=chunk,
                )
                if not stage_company_ids:
                    _record_checkpoint_skip(
                        report,
                        stage_name=stage_name,
                        requested_count=len(chunk),
                        pending_count=0,
                    )
                    continue
                _record_checkpoint_skip(
                    report,
                    stage_name=stage_name,
                    requested_count=len(chunk),
                    pending_count=len(stage_company_ids),
                )
                for company_id in stage_company_ids:
                    mark_company_stage_running(
                        conn,
                        batch_id=batch_id,
                        company_id=company_id,
                        stage=stage_name,
                    )
                _commit_if_supported(conn)
                stage_policy = _effective_stage_policy(
                    stage_name,
                    stage_concurrency=stage_concurrency,
                    llm_stage_concurrency=llm_stage_concurrency,
                    web_stage_concurrency=web_stage_concurrency,
                    stage_timeout_seconds=stage_timeout_seconds,
                    stage_retry_budget=stage_retry_budget,
                    retry_backoff_seconds=retry_backoff_seconds,
                )
                stage_shards = _stage_subchunks(
                    stage_company_ids,
                    stage_name=stage_name,
                    stage_concurrency=stage_policy.effective_concurrency,
                    stage_subchunk_size=stage_subchunk_size,
                )
                for (
                    shard_company_ids,
                    stage_started_at,
                    stage_report,
                ) in _run_stage_shards(
                    stage_name=stage_name,
                    command_template=command_template,
                    company_id_shards=stage_shards,
                    dsn=dsn,
                    stage_concurrency=stage_policy.effective_concurrency,
                    policy=stage_policy,
                ):
                    report["stage_reports"].append(stage_report)
                    _accumulate_stage_report(report, stage_report)
                    counters_by_company = _stage_counters_by_company(
                        conn=conn,
                        batch_id=batch_id,
                        stage_name=stage_name,
                        company_ids=shard_company_ids,
                        stage_report=stage_report,
                        stage_started_at=stage_started_at,
                    )
                    miss_reason_by_company = _miss_reason_by_company(
                        stage_name=stage_name,
                        stage_report=stage_report,
                        counters_by_company=counters_by_company,
                        company_ids=shard_company_ids,
                    )
                    _record_miss_reasons(report, miss_reason_by_company)
                    stage_status = (
                        "partial"
                        if stage_report["status"] == "succeeded"
                        else "failed"
                    )
                    if (
                        stage_name == "milvus_refresh"
                        and stage_report["status"] == "succeeded"
                    ):
                        stage_status = "succeeded"
                    company_ids_to_mark = _company_ids_to_mark_for_stage_report(
                        conn=conn,
                        batch_id=batch_id,
                        stage_name=stage_name,
                        company_ids=shard_company_ids,
                        stage_report=stage_report,
                    )
                    for company_id in company_ids_to_mark:
                        counters = dict(counters_by_company.get(company_id) or {})
                        if (
                            stage_name == "milvus_refresh"
                            and stage_report["status"] == "succeeded"
                        ):
                            counters["milvus_refreshed"] = 1
                        mark_company_stage_complete(
                            conn,
                            batch_id=batch_id,
                            company_id=company_id,
                            stage=stage_name,
                            counters=counters,
                            details=_stage_details(
                                stage_name=stage_name,
                                stage_report=stage_report,
                            ),
                            miss_reason=miss_reason_by_company.get(company_id),
                            status=stage_status,
                            last_error=stage_report.get("stderr_tail") or None,
                        )
                    _commit_if_supported(conn)
                    _record_batch_heartbeat(
                        conn,
                        batch_id=batch_id,
                        current_stage=stage_name,
                        last_completed_company_id=(
                            company_ids_to_mark[-1] if company_ids_to_mark else None
                        ),
                        quality_report=_batch_quality_report(report),
                        miss_reason_buckets=_batch_miss_reason_buckets(report),
                    )
                    _commit_if_supported(conn)
                    if stage_report["status"] != "succeeded":
                        report["status"] = "partial"
            report["companies_processed"] += len(chunk)
            report["summary"]["companies_processed"] = report["companies_processed"]
            mark_batch_progress(
                conn,
                batch_id=batch_id,
                companies_processed=int(report["companies_processed"]),
                current_stage="chunk_complete",
            )
            _record_batch_heartbeat(
                conn,
                batch_id=batch_id,
                current_stage="chunk_complete",
                last_completed_company_id=chunk[-1] if chunk else None,
                quality_report=_batch_quality_report(report),
                miss_reason_buckets=_batch_miss_reason_buckets(report),
            )
            _commit_if_supported(conn)
        if skip_milvus:
            for company_id in company_ids:
                mark_company_stage_complete(
                    conn,
                    batch_id=batch_id,
                    company_id=company_id,
                    stage="batch_complete",
                    counters={},
                    status="succeeded",
                )
            _commit_if_supported(conn)
        _finalize_batch_summary(report)
        mark_batch_finished(
            conn,
            batch_id=batch_id,
            status=str(report["status"]),
        )
        _record_batch_heartbeat(
            conn,
            batch_id=batch_id,
            current_stage=str(report["status"]),
            last_completed_company_id=company_ids[-1] if company_ids else None,
            quality_report=_batch_quality_report(report),
            miss_reason_buckets=_batch_miss_reason_buckets(report),
        )
        _commit_if_supported(conn)
        return report
    finally:
        conn.close()


def _run_baseline_readiness_for_chunk(
    *,
    conn: Any,
    batch_id: UUID | str,
    company_ids: list[str],
) -> dict[str, Any] | None:
    stage_company_ids = load_stage_pending_company_ids(
        conn,
        batch_id=batch_id,
        stage=BASELINE_READINESS_STAGE,
        company_ids=company_ids,
    )
    if not stage_company_ids:
        return None
    for company_id in stage_company_ids:
        mark_company_stage_running(
            conn,
            batch_id=batch_id,
            company_id=company_id,
            stage=BASELINE_READINESS_STAGE,
        )
    summary = record_baseline_readiness_stage(
        conn,
        batch_id=batch_id,
        company_ids=stage_company_ids,
    )
    return {
        "name": BASELINE_READINESS_STAGE,
        "status": "succeeded",
        "report": summary,
    }


def _run_stage_shards(
    *,
    stage_name: str,
    command_template: list[str],
    company_id_shards: list[list[str]],
    dsn: str,
    stage_concurrency: int,
    policy: StageExecutionPolicy,
) -> Iterator[tuple[list[str], datetime, dict[str, Any]]]:
    if not company_id_shards:
        return
    if len(company_id_shards) == 1 or stage_concurrency <= 1:
        yield _run_stage_shard(
            stage_name=stage_name,
            command_template=command_template,
            company_ids=company_id_shards[0],
            dsn=dsn,
            shard_index=0,
            shard_count=len(company_id_shards),
            policy=policy,
        )
        return

    max_workers = min(max(1, int(stage_concurrency)), len(company_id_shards))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _run_stage_shard,
                stage_name=stage_name,
                command_template=command_template,
                company_ids=company_ids,
                dsn=dsn,
                shard_index=index,
                shard_count=len(company_id_shards),
                policy=policy,
            )
            for index, company_ids in enumerate(company_id_shards)
        ]
        for future in as_completed(futures):
            yield future.result()


def _company_ids_to_mark_for_stage_report(
    *,
    conn: Any,
    batch_id: UUID | str,
    stage_name: str,
    company_ids: list[str],
    stage_report: dict[str, Any],
) -> list[str]:
    if stage_report.get("status") == "succeeded":
        return list(company_ids)
    return load_stage_pending_company_ids(
        conn,
        batch_id=batch_id,
        stage=stage_name,
        company_ids=company_ids,
    )


def _run_stage_shard(
    *,
    stage_name: str,
    command_template: list[str],
    company_ids: list[str],
    dsn: str,
    shard_index: int,
    shard_count: int,
    policy: StageExecutionPolicy | None = None,
) -> tuple[list[str], datetime, dict[str, Any]]:
    policy = policy or _effective_stage_policy(stage_name)
    command = _replace_company_args(command_template, company_ids)
    started_at = datetime.now(timezone.utc)
    stage_report, attempt_reports = _run_command_with_retries(
        stage_name=stage_name,
        command=command,
        dsn=dsn,
        policy=policy,
    )
    stage_report["shard_index"] = shard_index
    stage_report["shard_count"] = shard_count
    stage_report["company_count"] = len(company_ids)
    stage_report["attempts"] = len(attempt_reports)
    stage_report["attempt_reports"] = attempt_reports
    stage_report["execution_policy"] = policy.to_report_dict()
    if stage_report.get("status") != "succeeded":
        stage_report["final_failure_reason"] = _failed_stage_miss_reason(stage_report)
    return company_ids, started_at, stage_report


def _run_command_with_retries(
    *,
    stage_name: str,
    command: list[str],
    dsn: str,
    policy: StageExecutionPolicy,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempt_reports: list[dict[str, Any]] = []
    max_attempts = max(1, int(policy.retry_budget) + 1)
    last_report: dict[str, Any] | None = None
    for attempt_index in range(max_attempts):
        stage_report = _run_command_for_policy(
            stage_name=stage_name,
            command=command,
            dsn=dsn,
            policy=policy,
        )
        last_report = stage_report
        failure_reason = None
        if stage_report.get("status") != "succeeded":
            failure_reason = _failed_stage_miss_reason(stage_report)
        attempt_reports.append(
            {
                "attempt": attempt_index + 1,
                "status": stage_report.get("status"),
                "returncode": stage_report.get("returncode"),
                "failure_reason": failure_reason,
                "stderr_tail": stage_report.get("stderr_tail") or "",
            }
        )
        if stage_report.get("status") == "succeeded":
            break
        if attempt_index >= max_attempts - 1:
            break
        if not _is_retryable_stage_failure(stage_report):
            break
        if policy.retry_backoff_seconds > 0:
            time.sleep(policy.retry_backoff_seconds)
    return last_report or {"name": stage_name, "status": "failed"}, attempt_reports


def _run_command_for_policy(
    *,
    stage_name: str,
    command: list[str],
    dsn: str,
    policy: StageExecutionPolicy,
) -> dict[str, Any]:
    parameters = inspect.signature(_run_command).parameters
    if "timeout_seconds" in parameters:
        return _run_command(
            stage_name,
            command,
            dsn,
            timeout_seconds=policy.timeout_seconds,
        )
    return _run_command(stage_name, command, dsn)


def _is_retryable_stage_failure(stage_report: dict[str, Any]) -> bool:
    if stage_report.get("status") == "succeeded":
        return False
    reason = _failed_stage_miss_reason(stage_report)
    if reason in {"llm_structured_output_failed", "persist_failed"}:
        return False
    text = _stage_failure_text(stage_report)
    return any(
        marker in text
        for marker in (
            "timeout",
            "temporary",
            "transient",
            "rate limit",
            "429",
            "502",
            "503",
            "504",
            "connection",
            "network",
        )
    )


def _replace_company_args(command: list[str], company_ids: list[str]) -> list[str]:
    result: list[str] = []
    skip_next = False
    for token in command:
        if skip_next:
            skip_next = False
            continue
        if token == "--company-id":
            skip_next = True
            continue
        result.append(token)
    result.extend(_company_id_args(company_ids))
    return result


def _stage_counters_by_company(
    *,
    conn: Any,
    batch_id: UUID | str,
    stage_name: str,
    company_ids: list[str],
    stage_report: dict[str, Any],
    stage_started_at: datetime,
) -> dict[str, dict[str, int]]:
    if stage_report.get("status") != "succeeded":
        return {}
    if not company_ids:
        return {}
    if stage_name in {
        "xlsx_team_synthesis",
        "multi_source_narrative",
        "generic_source_judgment",
    }:
        return _company_report_counters(
            stage_name=stage_name,
            stage_report=stage_report,
            company_ids=company_ids,
        )
    if stage_name.startswith("news_"):
        return _news_stage_counters_by_company(
            conn=conn,
            batch_id=batch_id,
            source_adapter=_source_adapter_for_news_stage(stage_name),
            company_ids=company_ids,
            stage_started_at=stage_started_at,
        )
    if stage_name == "signal_extract":
        return _count_rows_by_company(
            conn,
            """
            SELECT e.company_id, count(*)::int AS event_count
              FROM company_signal_event e
              JOIN company_news_item n ON n.news_id = e.primary_news_id
             WHERE e.company_id = ANY(%(company_ids)s::text[])
               AND e.created_at >= %(stage_started_at)s
               AND n.source_adapter = ANY(%(source_adapters)s::text[])
             GROUP BY e.company_id
            """,
            {
                "company_ids": company_ids,
                "stage_started_at": stage_started_at,
                "source_adapters": ["iyiou", "pitchhub_36kr"],
            },
        )
    if stage_name == "source_product_extract":
        counters = _count_rows_by_company(
            conn,
            """
            SELECT company_id, count(*)::int AS product_count
              FROM company_product
             WHERE company_id = ANY(%(company_ids)s::text[])
               AND created_at >= %(stage_started_at)s
               AND (
                   official_product_url LIKE 'https://pitchhub.36kr.com%%'
                   OR official_product_url LIKE 'https://data.iyiou.com%%'
               )
             GROUP BY company_id
            """,
            {"company_ids": company_ids, "stage_started_at": stage_started_at},
        )
        _merge_company_counters(
            counters,
            _count_rows_by_company(
                conn,
                """
                SELECT company_id, count(*)::int AS scenario_count
                  FROM company_application_scenario
                 WHERE company_id = ANY(%(company_ids)s::text[])
                   AND created_at >= %(stage_started_at)s
                   AND (
                       source_url LIKE 'https://pitchhub.36kr.com%%'
                       OR source_url LIKE 'https://data.iyiou.com%%'
                   )
                 GROUP BY company_id
                """,
                {"company_ids": company_ids, "stage_started_at": stage_started_at},
            ),
        )
        return counters
    if stage_name == "official_product_capture":
        return _count_rows_by_company(
            conn,
            """
            SELECT company_id, count(*)::int AS official_product_count
              FROM company_product
             WHERE company_id = ANY(%(company_ids)s::text[])
               AND created_at >= %(stage_started_at)s
               AND official_product_url IS NOT NULL
               AND official_product_url NOT LIKE 'https://pitchhub.36kr.com%%'
               AND official_product_url NOT LIKE 'https://data.iyiou.com%%'
             GROUP BY company_id
            """,
            {"company_ids": company_ids, "stage_started_at": stage_started_at},
        )
    if len(company_ids) == 1:
        return {company_ids[0]: _stage_counters(stage_name, stage_report)}
    return {}


def _news_stage_counters_by_company(
    *,
    conn: Any,
    batch_id: UUID | str,
    source_adapter: str,
    company_ids: list[str],
    stage_started_at: datetime,
) -> dict[str, dict[str, int]]:
    return _count_rows_by_company(
        conn,
        """
        SELECT company_id,
               count(*)::int AS query_count,
               COALESCE(sum(result_count), 0)::int AS source_result_count,
               COALESCE(sum(accepted_count), 0)::int AS accepted_source_count,
               COALESCE(sum(
                   rejected_offsite
                   + rejected_irrelevant_path
                   + rejected_name_mismatch
               ), 0)::int AS rejected_source_count
          FROM company_enrichment_search_audit
         WHERE batch_id = %(batch_id)s
           AND company_id = ANY(%(company_ids)s::text[])
           AND source_adapter = %(source_adapter)s
           AND searched_at >= %(stage_started_at)s
         GROUP BY company_id
        """,
        {
            "batch_id": batch_id,
            "company_ids": company_ids,
            "source_adapter": source_adapter,
            "stage_started_at": stage_started_at,
        },
    )


def _source_adapter_for_news_stage(stage_name: str) -> str:
    if stage_name == "news_iyiou":
        return "iyiou"
    if stage_name == "news_pitchhub":
        return "pitchhub_36kr"
    return stage_name.removeprefix("news_")


def _count_rows_by_company(
    conn: Any,
    sql: str,
    params: dict[str, Any],
) -> dict[str, dict[str, int]]:
    rows = conn.execute(sql, params).fetchall()
    counters: dict[str, dict[str, int]] = {}
    for row in rows:
        company_id = str(_row_get(row, "company_id", 0))
        counters[company_id] = {
            str(key): int(value or 0)
            for key, value in _row_items(row).items()
            if key != "company_id"
        }
    return counters


def _merge_company_counters(
    target: dict[str, dict[str, int]],
    source: dict[str, dict[str, int]],
) -> None:
    for company_id, counters in source.items():
        bucket = target.setdefault(company_id, {})
        for key, value in counters.items():
            bucket[key] = bucket.get(key, 0) + int(value or 0)


def _company_report_counters(
    *,
    stage_name: str,
    stage_report: dict[str, Any],
    company_ids: list[str],
) -> dict[str, dict[str, int]]:
    payload = stage_report.get("report") or {}
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("company_reports") or []
    if not isinstance(rows, list):
        rows = []
    counters: dict[str, dict[str, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        company_id = str(row.get("company_id") or "")
        if company_id not in company_ids:
            continue
        if stage_name in {"xlsx_team_synthesis", "multi_source_narrative"}:
            counters[company_id] = {
                "narratives_written": int(row.get("narratives_written") or 0),
                "narratives_rejected": int(row.get("narratives_rejected") or 0),
                "team_members_extracted": int(row.get("team_members_extracted") or 0),
                "team_members_written": int(row.get("team_members_written") or 0),
                "product_count": int(row.get("products_written") or 0),
                "scenario_count": int(row.get("scenarios_written") or 0),
                "product_synthesis_failures": (
                    1 if row.get("product_synthesis_error") else 0
                ),
            }
        elif stage_name == "generic_source_judgment":
            counters[company_id] = {
                "query_count": int(row.get("queries_run") or 0),
                "source_result_count": int(row.get("results_seen") or 0),
                "accepted_source_count": int(row.get("accepted_sources") or 0),
                "rejected_source_count": int(row.get("rejected_sources") or 0),
                "generic_fetch_count": int(row.get("fetch_count") or 0),
                "generic_source_judgment_count": int(row.get("source_judgments") or 0),
            }
    if counters:
        return counters
    if len(company_ids) == 1:
        return {company_ids[0]: _stage_counters(stage_name, stage_report)}
    return {}


def _row_get(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[index]


def _row_items(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    raise TypeError("Expected dict row for company enrichment counters")


def _miss_reason_by_company(
    *,
    stage_name: str,
    stage_report: dict[str, Any],
    counters_by_company: dict[str, dict[str, int]],
    company_ids: list[str],
) -> dict[str, str | None]:
    if stage_report.get("status") != "succeeded":
        reason = _failed_stage_miss_reason(stage_report)
        return {company_id: reason for company_id in company_ids}
    if not stage_name.startswith("news_"):
        return {
            company_id: _non_search_stage_miss_reason(
                stage_name=stage_name,
                counters=counters_by_company.get(company_id) or {},
            )
            for company_id in company_ids
        }
    reasons: dict[str, str | None] = {}
    for company_id in company_ids:
        counters = counters_by_company.get(company_id) or {}
        if int(counters.get("accepted_source_count", 0)) > 0:
            reasons[company_id] = None
        elif int(counters.get("source_result_count", 0)) == 0:
            reasons[company_id] = "no_results"
        elif int(counters.get("rejected_source_count", 0)) > 0:
            reasons[company_id] = "all_results_rejected"
        else:
            reasons[company_id] = None
    return reasons


def _failed_stage_miss_reason(stage_report: dict[str, Any]) -> str:
    text = _stage_failure_text(stage_report)
    if any(
        marker in text
        for marker in (
            "json parse",
            "jsondecode",
            "parse failed",
            "schema",
            "structured output",
            "structured-output",
            "invalid response",
        )
    ):
        return "llm_structured_output_failed"
    if "persist" in text or "insert" in text or "database" in text:
        return "persist_failed"
    return "fetch_failed"


def _stage_failure_text(stage_report: dict[str, Any]) -> str:
    report = stage_report.get("report") if isinstance(stage_report, dict) else None
    return " ".join(
        str(value or "")
        for value in (
            stage_report.get("stderr_tail"),
            stage_report.get("error"),
            report.get("error") if isinstance(report, dict) else None,
        )
    ).casefold()


def _non_search_stage_miss_reason(
    *,
    stage_name: str,
    counters: dict[str, int],
) -> str | None:
    if stage_name in {"xlsx_team_synthesis", "multi_source_narrative"}:
        facts = int(counters.get("narratives_written", 0)) + int(
            counters.get("team_members_written", 0)
        ) + int(counters.get("product_count", 0)) + int(
            counters.get("scenario_count", 0)
        )
        return None if facts > 0 else "synthesis_no_facts"
    if stage_name == "generic_source_judgment":
        if int(counters.get("accepted_source_count", 0)) > 0:
            return None
        if int(counters.get("source_result_count", 0)) == 0:
            return "no_results"
        return "llm_rejected"
    if stage_name == "signal_extract":
        return None if int(counters.get("event_count", 0)) > 0 else "llm_rejected"
    if stage_name == "source_product_extract":
        facts = int(counters.get("product_count", 0)) + int(
            counters.get("scenario_count", 0)
        )
        return None if facts > 0 else "synthesis_no_facts"
    if stage_name == "official_product_capture":
        return (
            None
            if int(counters.get("official_product_count", 0)) > 0
            else "synthesis_no_facts"
        )
    return None


def _stage_counters(stage_name: str, stage_report: dict[str, Any]) -> dict[str, int]:
    payload = stage_report.get("report") or {}
    if not isinstance(payload, dict):
        payload = {}
    if stage_name.startswith("news_"):
        news_fetched = int(payload.get("news_fetched") or 0)
        return {
            "query_count": int(payload.get("search_audit_rows") or 0),
            "source_result_count": news_fetched,
            "accepted_source_count": news_fetched,
        }
    if stage_name in {"xlsx_team_synthesis", "multi_source_narrative"}:
        return {
            "narratives_written": int(payload.get("narratives_written") or 0),
            "narratives_rejected": int(payload.get("narratives_rejected") or 0),
            "team_members_extracted": int(payload.get("team_members_extracted") or 0),
            "team_members_written": int(payload.get("team_members_written") or 0),
            "product_count": int(payload.get("products_written") or 0),
            "scenario_count": int(payload.get("scenarios_written") or 0),
            "product_synthesis_failures": int(
                payload.get("product_synthesis_failures") or 0
            ),
        }
    if stage_name == "generic_source_judgment":
        return {
            "query_count": int(payload.get("queries_run") or 0),
            "source_result_count": int(payload.get("results_seen") or 0),
            "accepted_source_count": int(payload.get("accepted_sources") or 0),
            "rejected_source_count": int(payload.get("rejected_sources") or 0),
            "generic_fetch_count": int(payload.get("fetch_count") or 0),
            "generic_source_judgment_count": int(payload.get("source_judgments") or 0),
        }
    if stage_name == "signal_extract":
        return {"event_count": int(payload.get("events_inserted") or 0)}
    if stage_name == "source_product_extract":
        return {
            "product_count": int(payload.get("products_inserted") or 0),
            "scenario_count": int(payload.get("scenarios_inserted") or 0),
        }
    if stage_name == "official_product_capture":
        return {"official_product_count": int(payload.get("products_inserted") or 0)}
    return {}


def _rejected_candidate_samples(payload: dict[str, Any], *, limit: int = 20) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    raw_items = payload.get("rejected_candidates") or []
    if not isinstance(raw_items, list):
        return samples
    allowed_keys = (
        "company_id",
        "source_adapter",
        "source_url",
        "gate",
        "reason",
        "rejected_count",
    )
    for item in raw_items[: max(0, limit)]:
        if not isinstance(item, dict):
            continue
        samples.append({key: item.get(key) for key in allowed_keys if key in item})
    return samples


def _stage_details(
    *,
    stage_name: str,
    stage_report: dict[str, Any],
) -> dict[str, Any]:
    payload = stage_report.get("report") or {}
    if not isinstance(payload, dict):
        payload = {}
    details: dict[str, Any] = {
        "persistence_outcome": {
            "dry_run": bool(payload.get("dry_run", False)),
            "status": stage_report.get("status"),
            "returncode": stage_report.get("returncode"),
        }
    }
    policy = stage_report.get("execution_policy")
    if isinstance(policy, dict):
        details["execution_policy"] = _sanitize_stage_policy_payload(policy)
        llm_audit = policy.get("llm_audit")
        if isinstance(llm_audit, dict):
            structured_output_failures = int(
                payload.get("llm_fallback_failed")
                or payload.get("llm_parse_failures")
                or (
                    1
                    if stage_report.get("final_failure_reason")
                    == "llm_structured_output_failed"
                    else 0
                )
            )
            details["llm_task_outcome"] = {
                "task_type": llm_audit.get("task_type"),
                "llm_profile": llm_audit.get("llm_profile"),
                "model": llm_audit.get("model"),
                "attempts": int(stage_report.get("attempts") or 1),
                "json_repair_retry": bool(policy.get("json_repair_retry")),
                "failure_reason": stage_report.get("final_failure_reason"),
                "structured_output_failures": structured_output_failures,
            }
    if stage_name == "source_product_extract":
        rejected_candidate_reasons = payload.get("rejected_candidate_reasons") or {}
        if not isinstance(rejected_candidate_reasons, dict):
            rejected_candidate_reasons = {}
        candidate_gate_rejected = int(payload.get("source_candidate_gate_rejected") or 0)
        rejected_samples = _rejected_candidate_samples(payload)
        rejected_facts: dict[str, Any] = {
            "llm_rejected_or_empty": int(payload.get("llm_fallback_failed") or 0),
        }
        if candidate_gate_rejected or rejected_candidate_reasons or rejected_samples:
            rejected_facts.update(
                {
                    "candidate_gate_rejected": candidate_gate_rejected,
                    "rejected_candidate_reasons": {
                        str(reason): int(count or 0)
                        for reason, count in rejected_candidate_reasons.items()
                    },
                    "rejected_candidate_samples": rejected_samples,
                }
            )
        details.update(
            {
                "synthesis_inputs": {
                    "source_adapters": list(payload.get("source_adapters") or []),
                    "news_processed": int(payload.get("news_processed") or 0),
                },
                "produced_facts": {
                    "products": int(payload.get("products_inserted") or 0),
                    "scenarios": int(payload.get("scenarios_inserted") or 0),
                },
                "rejected_facts": rejected_facts,
            }
        )
    elif stage_name in {"xlsx_team_synthesis", "multi_source_narrative"}:
        source_tier = (
            "multi_source"
            if stage_name == "multi_source_narrative"
            else "xlsx_baseline"
        )
        details.update(
            {
                "synthesis_inputs": {
                    "source_tier": source_tier,
                    "companies_processed": int(payload.get("companies_processed") or 0),
                },
                "produced_facts": {
                    "narratives": int(payload.get("narratives_written") or 0),
                    "team_members": int(payload.get("team_members_written") or 0),
                    "products": int(payload.get("products_written") or 0),
                    "scenarios": int(payload.get("scenarios_written") or 0),
                },
                "rejected_facts": {
                    "narratives_rejected": int(payload.get("narratives_rejected") or 0),
                    "companies_with_errors": int(payload.get("companies_with_errors") or 0),
                    "product_synthesis_errors": int(
                        payload.get("product_synthesis_failures") or 0
                    ),
                },
            }
        )
    elif stage_name == "generic_source_judgment":
        details.update(
            {
                "source_discovery": {
                    "query_count": int(payload.get("queries_run") or 0),
                    "result_count": int(payload.get("results_seen") or 0),
                    "snippet_judgments": int(payload.get("snippet_judgments") or 0),
                    "fetch_attempts": int(payload.get("fetch_count") or 0),
                    "source_judgments": int(payload.get("source_judgments") or 0),
                    "accepted_source_material": int(payload.get("accepted_sources") or 0),
                    "rejected_source_material": int(payload.get("rejected_sources") or 0),
                    "needs_review_source_material": int(
                        payload.get("needs_review_sources") or 0
                    ),
                    "search_audit_rows": int(payload.get("search_audit_rows") or 0),
                }
            }
        )
    elif stage_name == "signal_extract":
        details.update(
            {
                "synthesis_inputs": {
                    "source_adapters": list(payload.get("source_adapters") or []),
                    "news_processed": int(payload.get("news_processed") or 0),
                },
                "produced_facts": {
                    "events": int(payload.get("events_inserted") or 0),
                },
                "rejected_facts": {
                    "news_with_errors": int(payload.get("news_with_errors") or 0),
                },
            }
        )
    elif stage_name == "official_product_capture":
        details.update(
            {
                "synthesis_inputs": {
                    "official_pages_captured": int(
                        payload.get("official_pages_captured") or 0
                    ),
                    "source_materials": len(payload.get("source_materials") or []),
                },
                "produced_facts": {
                    "official_products": int(payload.get("products_inserted") or 0),
                },
                "rejected_facts": {
                    "companies_with_errors": int(
                        payload.get("companies_with_errors") or 0
                    ),
                },
            }
        )
    elif stage_name.startswith("news_"):
        details.update(
            {
                "source_discovery": {
                    "news_fetched": int(payload.get("news_fetched") or 0),
                    "search_audit_rows": int(payload.get("search_audit_rows") or 0),
                }
            }
        )
    return details


def _sanitize_stage_policy_payload(policy: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "stage_name",
        "task_family",
        "default_concurrency",
        "max_concurrency",
        "effective_concurrency",
        "timeout_seconds",
        "retry_budget",
        "retry_backoff_seconds",
        "json_repair_retry",
        "rate_limit_key",
        "llm_task_type",
        "llm_audit",
    }
    sanitized = {key: value for key, value in policy.items() if key in allowed}
    llm_audit = sanitized.get("llm_audit")
    if isinstance(llm_audit, dict):
        sanitized["llm_audit"] = {
            key: llm_audit.get(key)
            for key in ("task_type", "llm_profile", "model", "cascade_strategy")
            if key in llm_audit
        }
    return sanitized


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _apply_provider_rate_limit_overrides(
        llm_max_concurrency=args.provider_llm_max_concurrency,
        serper_max_concurrency=args.provider_serper_max_concurrency,
    )
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1
    explicit_company_ids = (
        _load_company_id_file(args.company_id_file) if args.company_id_file else None
    )
    report = process_batch(
        dsn=dsn,
        batch_id=UUID(args.batch_id),
        limit=args.limit,
        chunk_size=args.chunk_size,
        skip_milvus=args.skip_milvus,
        include_failed=args.include_failed,
        sleep_seconds=str(args.sleep_seconds),
        source_product_limit=args.source_product_limit,
        official_product_max_pages=args.official_product_max_pages,
        milvus_uri=args.milvus_uri,
        dry_run=args.dry_run,
        skip_live_web=args.skip_live_web,
        skip_official_site=args.skip_official_site,
        skip_yiou_pitchhub=args.skip_yiou_pitchhub,
        skip_generic_serper=args.skip_generic_serper,
        skip_persistence=args.skip_persistence,
        stale_after_minutes=args.stale_after_minutes,
        stage_concurrency=args.stage_concurrency,
        llm_stage_concurrency=args.llm_stage_concurrency,
        web_stage_concurrency=args.web_stage_concurrency,
        stage_subchunk_size=args.stage_subchunk_size,
        stage_timeout_seconds=args.stage_timeout_seconds,
        stage_retry_budget=args.stage_retry_budget,
        retry_backoff_seconds=args.retry_backoff_seconds,
        child_llm_concurrency=args.child_llm_concurrency,
        child_web_concurrency=args.child_web_concurrency,
        child_llm_timeout_seconds=args.child_llm_timeout_seconds,
        child_llm_retry_budget=args.child_llm_retry_budget,
        representative_sample_size=args.representative_sample_size,
        explicit_company_ids=explicit_company_ids,
        plan_only=args.plan_only,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get("status") in {"planned", "succeeded", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

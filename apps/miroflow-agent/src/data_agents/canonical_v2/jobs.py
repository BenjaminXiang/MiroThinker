"""Declarative task-run surface for the Canonical V2 admin zone.

One deep module owns everything the manual trigger and (from W6) the scheduled entry point must
share:

* :data:`JOB_TASKS` — the closed white list. A task maps to a **fixed argv tuple**, a working
  directory, a timeout, a declared cadence, a switch source, a quota class and a PostgreSQL
  requirement. The only parameters a caller may supply are values from an explicitly declared
  closed set; no caller text is ever concatenated into a command line and no shell is used.
* :class:`JobRunStore` — serving-side SQLite run history (one file, same pattern as
  ``access-logs.sqlite3``) plus the per-task breaker/last-run state.
* :class:`JobRuntime` — the single gate: PostgreSQL availability, breaker, managed-config switch,
  quota cap, then a cross-process ``flock`` re-entrancy lock before any process is spawned. The
  manual and the scheduled trigger run through this same function, so a manual trigger cannot
  bypass a limit.

Run history deliberately does **not** live in the build-time ``pipeline_run`` table: that table only
exists on the build host, while this surface runs on the serving host (see the W2 current-state
evidence). A future slice may mirror rows into ``pipeline_run`` when a build database is reachable.

Credential hygiene: the child's environment is never persisted, and stored excerpts pass through
:func:`redact_secrets` (``key=value`` pairs whose key names a credential, and ``Bearer <token>``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time as clock_time, timedelta, tzinfo
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from typing import Any, Literal

from src.data_agents.canonical_v2.managed_config import (
    ManagedSettings,
    ManagedSettingsError,
    ManagedSettingsStore,
    PUBLIC_DOMAINS,
    default_repo_root,
)


logger = logging.getLogger(__name__)

SCHEMA_VERSION = "canonical-v2-jobs-v1"
JOBS_DB_ENV = "CANONICAL_V2_JOBS_DB"
ACCESS_LOG_DB_ENV = "CANONICAL_V2_ACCESS_LOG_DB"
JOBS_DB_FILENAME = "jobs.sqlite3"

MANUAL_TRIGGER = "manual"
SCHEDULE_TRIGGER = "schedule"

QUOTA_WEB_SEARCH_ENV = "MIROTHINKER_MAX_WEB_SEARCHES_PER_RUN"
QUOTA_LLM_ENV = "MIROTHINKER_MAX_LLM_CALLS_PER_RUN"
JOB_TASK_ID_ENV = "MIROTHINKER_JOB_TASK_ID"
JOB_RUN_ID_ENV = "MIROTHINKER_JOB_RUN_ID"

RUN_STATUSES: tuple[str, ...] = (
    "running",
    "succeeded",
    "failed",
    "skipped",
    "breaker_reset",
)

SKIP_SWITCH_OFF = "switch_off"
SKIP_QUOTA_EXHAUSTED = "quota_exhausted"
SKIP_OUTSIDE_WINDOW = "outside_window"

_EXCERPT_LIMIT = 4000
_OPERATOR_LIMIT = 200
_MAX_HISTORY_LIMIT = 200

_SECRET_PATTERN = re.compile(
    r"(?i)((?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token|secret|password|passwd|"
    r"credential)['\"]?(?:\s*[:=]\s*)['\"]?)([^\s\"'&,;}]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{8,})")
# A parameter placeholder is a whole token: ``{domain}`` yes, ``print('{}')`` no.
_PLACEHOLDER_PATTERN = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_]*)\}$")


# --------------------------------------------------------------------------------------- errors


class JobsError(Exception):
    """Base class for every refusal this module raises; ``code`` is HTTP-stable."""

    code = "jobs_error"


class JobTaskUnknownError(JobsError):
    code = "job_unknown_task"


class JobParameterError(JobsError):
    code = "job_invalid_params"


class JobAlreadyRunningError(JobsError):
    code = "job_already_running"

    def __init__(self, message: str, *, active_run_id: str | None = None) -> None:
        super().__init__(message)
        self.active_run_id = active_run_id


class JobBreakerOpenError(JobsError):
    code = "job_breaker_open"


class JobPostgresUnavailableError(JobsError):
    code = "job_postgres_unavailable"


class JobsStorageUnavailableError(JobsError):
    code = "jobs_storage_unavailable"


class JobsConfigurationError(JobsError):
    code = "job_config_unavailable"


# ------------------------------------------------------------------------------- secret hygiene


def redact_secrets(text: str) -> str:
    """Replace credential-shaped values for storage and display."""

    if not text:
        return text
    redacted = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}[redacted]", text)
    return _BEARER_PATTERN.sub(lambda match: f"{match.group(1)}[redacted]", redacted)


def _bounded(text: str | bytes | None, *, limit: int = _EXCERPT_LIMIT) -> str | None:
    if text is None:
        return None
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return redact_secrets(text[-limit:])


# ------------------------------------------------------------------------------------ white list


@dataclass(frozen=True, slots=True)
class JobTask:
    """One declared task: a fixed command plus the gate metadata that constrains it."""

    task_id: str
    label: str
    description: str
    domain: str | None
    argv_template: tuple[str, ...]
    cwd_relative: str
    timeout_seconds: int
    schedule_cron: str | None = None
    schedule_display: str = "手动触发"
    params: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    collection_gated: bool = False
    quota: Literal["web_search", "llm"] | None = None
    requires_postgres: bool = False
    window_bound: bool = False

    @property
    def script_relative(self) -> str | None:
        for token in self.argv_template:
            if token.endswith((".py", ".sh")):
                return token
        return None

    @property
    def command_display(self) -> str:
        return " ".join(self.argv_template)

    def argv_for(self, values: Mapping[str, str] | None = None) -> tuple[str, ...]:
        """Render the fixed template with values from the declared closed sets only."""

        provided = dict(values or {})
        unknown = sorted(set(provided) - set(self.params))
        if unknown:
            raise JobParameterError(
                f"{self.task_id} does not accept parameter(s): {', '.join(unknown)}"
            )
        resolved: dict[str, str] = {}
        for name, allowed in self.params.items():
            if name not in provided:
                raise JobParameterError(f"{self.task_id} requires parameter '{name}'")
            value = provided[name]
            if not isinstance(value, str) or value not in allowed:
                raise JobParameterError(
                    f"{self.task_id}.{name} must be one of: {', '.join(allowed)}"
                )
            resolved[name] = value
        argv: list[str] = []
        for token in self.argv_template:
            match = _PLACEHOLDER_PATTERN.match(token)
            if match is None:
                argv.append(token)
                continue
            name = match.group(1)
            if name not in resolved:
                raise JobParameterError(
                    f"{self.task_id} declares an unknown placeholder {token!r}"
                )
            argv.append(resolved[name])
        return tuple(argv)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "label": self.label,
            "description": self.description,
            "domain": self.domain,
            "command_display": self.command_display,
            "cwd_relative": self.cwd_relative,
            "timeout_seconds": self.timeout_seconds,
            "schedule_cron": self.schedule_cron,
            "schedule_display": self.schedule_display,
            "params": {name: list(allowed) for name, allowed in self.params.items()},
            "collection_gated": self.collection_gated,
            "quota": self.quota,
            "requires_postgres": self.requires_postgres,
            "window_bound": self.window_bound,
        }


def _collection_task(task_id: str, label: str, domain: str, cadence: str, display: str,
                     script: str, quota: str, args: tuple[str, ...] = ()) -> JobTask:
    return JobTask(
        task_id=task_id,
        label=label,
        description=f"{label}（{script}）",
        domain=domain,
        argv_template=("uv", "run", "python", script, *args),
        cwd_relative="apps/miroflow-agent",
        timeout_seconds=3600,
        schedule_cron=cadence,
        schedule_display=display,
        collection_gated=True,
        quota=quota,  # type: ignore[arg-type]
        requires_postgres=False,
        window_bound=True,
    )


JOB_TASKS: tuple[JobTask, ...] = (
    _collection_task(
        "company-news-ingest",
        "企业新闻采集",
        "company",
        "0 2 * * 1",
        "每周一 02:00",
        "scripts/run_company_news_ingest.py",
        "web_search",
    ),
    _collection_task(
        "company-official-product-capture",
        "企业官网产品重抓",
        "company",
        "30 3 * * 1",
        "每周一 03:30",
        "scripts/run_company_official_product_capture.py",
        "web_search",
    ),
    _collection_task(
        "paper-search-backfill",
        "论文标题检索回填",
        "paper",
        "0 2 * * 3",
        "每周三 02:00",
        "scripts/run_paper_search_backfill.py",
        "web_search",
    ),
    _collection_task(
        "paper-summary-zh-backfill",
        "论文摘要中文回填",
        "paper",
        "30 3 * * 3",
        "每周三 03:30",
        "scripts/run_paper_summary_zh_backfill.py",
        "llm",
    ),
    _collection_task(
        "paper-doi-verify",
        "论文 DOI 校验",
        "paper",
        "30 3 * * 3",
        "每周三 03:30",
        "scripts/run_paper_doi_verify.py",
        "llm",
    ),
    _collection_task(
        "professor-homepage-rescrape",
        "教授主页重爬（写入域库）",
        "professor",
        "0 2 1 * *",
        "每月 1 日 02:00",
        "scripts/run_profile_bio_rescrape.py",
        "llm",
        args=("--apply", "--confirm-real-db"),
    ),
    JobTask(
        task_id="professor-homepage-paper-ingest",
        label="教授主页论文增量",
        description="主页论文/专利增量 ingest（断点续跑）",
        domain="professor",
        argv_template=(
            "uv",
            "run",
            "python",
            "scripts/run_homepage_paper_ingest.py",
            "--resume",
        ),
        cwd_relative="apps/miroflow-agent",
        timeout_seconds=3600,
        schedule_cron="0 3 1 * *",
        schedule_display="每月 1 日 03:00",
        collection_gated=True,
        quota="web_search",
        window_bound=True,
    ),
    JobTask(
        task_id="ops-milvus-backfill",
        label="Milvus 回填",
        description="按域回填域 Milvus（需构建期 PostgreSQL）",
        domain=None,
        argv_template=(
            "uv",
            "run",
            "python",
            "scripts/run_milvus_backfill.py",
            "--domain",
            "{domain}",
        ),
        cwd_relative="apps/miroflow-agent",
        timeout_seconds=5400,
        params={"domain": tuple(PUBLIC_DOMAINS)},
        quota="llm",
        requires_postgres=True,
    ),
    JobTask(
        task_id="ops-milvus-backfill-dry-run",
        label="Milvus 回填（干跑）",
        description="按域回填干跑，不写 Milvus（需构建期 PostgreSQL）",
        domain=None,
        argv_template=(
            "uv",
            "run",
            "python",
            "scripts/run_milvus_backfill.py",
            "--domain",
            "{domain}",
            "--dry-run",
        ),
        cwd_relative="apps/miroflow-agent",
        timeout_seconds=5400,
        params={"domain": tuple(PUBLIC_DOMAINS)},
        quota="llm",
        requires_postgres=True,
    ),
    JobTask(
        task_id="ops-retrieval-validation",
        label="检索验证",
        description="对当前服务入口跑一遍 host e2e 检索验证（需构建期 PostgreSQL）",
        domain=None,
        argv_template=("bash", "apps/admin-console/scripts/host_e2e_agentic_rag.sh"),
        cwd_relative=".",
        timeout_seconds=5400,
        quota="llm",
        requires_postgres=True,
    ),
)


JOB_TASKS_BY_ID: Mapping[str, JobTask] = {task.task_id: task for task in JOB_TASKS}


def get_job_task(task_id: str) -> JobTask:
    task = JOB_TASKS_BY_ID.get(task_id)
    if task is None:
        raise JobTaskUnknownError(f"unknown task id: {task_id}")
    return task


# -------------------------------------------------------------------------- declared cadence


def _parse_cron_field(field_value: str, *, minimum: int, maximum: int) -> tuple[frozenset[int], bool]:
    """Return (values, restricted) for one cron field."""

    values: set[int] = set()
    restricted = field_value != "*"
    for part in field_value.split(","):
        if not part:
            raise ValueError(f"empty cron field element in {field_value!r}")
        step = 1
        body = part
        if "/" in part:
            body, _, step_text = part.partition("/")
            if not step_text.isdigit() or int(step_text) <= 0:
                raise ValueError(f"invalid cron step in {part!r}")
            step = int(step_text)
        if body == "*":
            start, end = minimum, maximum
        elif "-" in body:
            start_text, _, end_text = body.partition("-")
            if not start_text.isdigit() or not end_text.isdigit():
                raise ValueError(f"invalid cron range in {part!r}")
            start, end = int(start_text), int(end_text)
        else:
            if not body.isdigit():
                raise ValueError(f"invalid cron value in {part!r}")
            start = end = int(body)
        if start < minimum or end > maximum or start > end:
            raise ValueError(f"cron value out of range in {part!r}")
        values.update(range(start, end + 1, step))
    if not values:
        raise ValueError(f"empty cron field {field_value!r}")
    return frozenset(values), restricted


def cron_next_fire(
    expression: str,
    *,
    now: datetime,
    tz: tzinfo | None = None,
) -> datetime:
    """Next fire time of a 5-field cron expression, computed from the declaration.

    Day-of-month and day-of-week follow Vixie semantics: when both are restricted, either may match.
    Day-of-week accepts ``0``/``7`` as Sunday. The cron table that will actually run these tasks is
    installed by the W6 slice; this function exists so the page can show the declared cadence as a
    concrete next run time.
    """

    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("a cron expression must have exactly five fields")
    minutes, _ = _parse_cron_field(fields[0], minimum=0, maximum=59)
    hours, _ = _parse_cron_field(fields[1], minimum=0, maximum=23)
    days, days_restricted = _parse_cron_field(fields[2], minimum=1, maximum=31)
    months, _ = _parse_cron_field(fields[3], minimum=1, maximum=12)
    weekdays, weekdays_restricted = _parse_cron_field(fields[4], minimum=0, maximum=7)
    sunday_zero = frozenset(0 if value == 7 else value for value in weekdays)

    zone = tz or now.tzinfo or datetime.now().astimezone().tzinfo
    local_now = now.astimezone(zone)
    candidate_day: date = local_now.date()
    for _ in range(366 * 5):
        weekday = (candidate_day.weekday() + 1) % 7
        if candidate_day.month in months:
            if days_restricted and weekdays_restricted:
                day_matches = candidate_day.day in days or weekday in sunday_zero
            elif days_restricted:
                day_matches = candidate_day.day in days
            elif weekdays_restricted:
                day_matches = weekday in sunday_zero
            else:
                day_matches = True
            if day_matches:
                for hour in sorted(hours):
                    for minute in sorted(minutes):
                        moment = datetime.combine(
                            candidate_day, clock_time(hour, minute)
                        ).replace(tzinfo=zone)
                        if moment > local_now:
                            return moment
        candidate_day += timedelta(days=1)
    raise ValueError(f"cron expression never fires: {expression!r}")


# --------------------------------------------------------------------------------------- store


def _prepare_database_file(database_path: Path) -> Path:
    """Open-target hardening identical in spirit to the access-log store."""

    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        os.close(descriptor)
    except FileExistsError:
        pass
    metadata = os.lstat(path)
    if path.is_symlink() or not path.is_file():
        raise OSError("jobs database path must be a regular file")
    if metadata.st_nlink != 1:
        raise OSError("jobs database path must not be hard-linked")
    os.chmod(path, 0o600, follow_symlinks=False)
    return path


_DDL = """
CREATE TABLE IF NOT EXISTS workspace_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_run (
    run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    trigger_source TEXT NOT NULL,
    operator TEXT NOT NULL,
    status TEXT NOT NULL,
    skip_reason TEXT,
    command_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_ms INTEGER,
    exit_code INTEGER,
    items_processed INTEGER,
    items_failed INTEGER,
    summary_json TEXT,
    stdout_excerpt TEXT,
    stderr_excerpt TEXT,
    window_bound INTEGER NOT NULL DEFAULT 0,
    inside_window INTEGER
);
CREATE INDEX IF NOT EXISTS job_run_task_started
    ON job_run (task_id, started_at DESC);
CREATE INDEX IF NOT EXISTS job_run_status_started
    ON job_run (status, started_at DESC);
CREATE TABLE IF NOT EXISTS job_task_state (
    task_id TEXT PRIMARY KEY,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    breaker_open INTEGER NOT NULL DEFAULT 0,
    breaker_opened_at TEXT,
    last_run_id TEXT,
    last_status TEXT,
    last_failure_at TEXT,
    last_success_at TEXT
);
"""


@dataclass(frozen=True, slots=True)
class JobRun:
    run_id: str
    task_id: str
    trigger_source: str
    operator: str
    status: str
    skip_reason: str | None
    command: tuple[str, ...]
    started_at: str
    finished_at: str | None
    duration_ms: int | None
    exit_code: int | None
    items_processed: int | None
    items_failed: int | None
    summary: dict[str, Any] | None
    stdout_excerpt: str | None
    stderr_excerpt: str | None
    window_bound: bool
    inside_window: bool | None

    def as_dict(self, *, include_samples: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "trigger_source": self.trigger_source,
            "operator": self.operator,
            "status": self.status,
            "skip_reason": self.skip_reason,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "exit_code": self.exit_code,
            "items_processed": self.items_processed,
            "items_failed": self.items_failed,
            "summary": self.summary,
            "window_bound": self.window_bound,
            "inside_window": self.inside_window,
        }
        if include_samples:
            payload["command"] = list(self.command)
            payload["stdout_excerpt"] = self.stdout_excerpt
            payload["stderr_excerpt"] = self.stderr_excerpt
        return payload


@dataclass(frozen=True, slots=True)
class JobTaskState:
    task_id: str
    consecutive_failures: int = 0
    breaker_open: bool = False
    breaker_opened_at: str | None = None
    last_run_id: str | None = None
    last_status: str | None = None
    last_failure_at: str | None = None
    last_success_at: str | None = None


@dataclass(frozen=True, slots=True)
class JobTaskSummary:
    task_id: str
    last_run: JobRun | None
    state: JobTaskState

    @property
    def failure_flag(self) -> bool:
        if self.state.breaker_open:
            return True
        return self.last_run is not None and self.last_run.status == "failed"


class JobRunStore:
    """Owns one SQLite database of task runs and per-task breaker state."""

    def __init__(
        self,
        database_path: Path | str,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._database_path = _prepare_database_file(Path(database_path))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            self._database_path,
            check_same_thread=False,
            timeout=30.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = NORMAL")
        self._connection.execute("PRAGMA busy_timeout = 30000")
        with self._lock, self._connection:
            self._connection.executescript(_DDL)
            self._connection.execute(
                "INSERT OR IGNORE INTO workspace_meta (key, value) VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,),
            )

    @property
    def database_path(self) -> Path:
        return self._database_path

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _now(self) -> str:
        return self._clock().isoformat()

    # -- writes -----------------------------------------------------------------------------

    def start_run(
        self,
        *,
        task_id: str,
        trigger_source: str,
        operator: str,
        command: Sequence[str] = (),
        window_bound: bool = False,
        inside_window: bool | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO job_run (
                    run_id, task_id, trigger_source, operator, status, command_json,
                    started_at, window_bound, inside_window
                ) VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task_id,
                    trigger_source,
                    operator,
                    json.dumps(list(command)),
                    self._now(),
                    1 if window_bound else 0,
                    None if inside_window is None else (1 if inside_window else 0),
                ),
            )
            self._touch_state(task_id, run_id=run_id, status="running")
        return run_id

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        duration_ms: int,
        exit_code: int | None = None,
        items_processed: int | None = None,
        items_failed: int | None = None,
        summary: Mapping[str, Any] | None = None,
        stdout: str | bytes | None = None,
        stderr: str | bytes | None = None,
    ) -> None:
        row = self._run_row(run_id)
        if row is None:
            raise JobsError(f"run {run_id} does not exist")
        payload = None
        if summary is not None:
            payload = json.loads(redact_secrets(json.dumps(summary, ensure_ascii=False, default=str)))
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE job_run
                   SET status = ?, finished_at = ?, duration_ms = ?, exit_code = ?,
                       items_processed = ?, items_failed = ?, summary_json = ?,
                       stdout_excerpt = ?, stderr_excerpt = ?
                 WHERE run_id = ?
                """,
                (
                    status,
                    self._now(),
                    int(duration_ms),
                    exit_code,
                    items_processed,
                    items_failed,
                    None if payload is None else json.dumps(payload, ensure_ascii=False),
                    _bounded(stdout),
                    _bounded(stderr),
                    run_id,
                ),
            )
            self._record_outcome(row["task_id"], run_id=run_id, status=status)

    def record_skip(
        self,
        *,
        task_id: str,
        trigger_source: str,
        operator: str,
        reason: str,
        command: Sequence[str] = (),
        window_bound: bool = False,
        inside_window: bool | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        now = self._now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO job_run (
                    run_id, task_id, trigger_source, operator, status, skip_reason, command_json,
                    started_at, finished_at, duration_ms, window_bound, inside_window
                ) VALUES (?, ?, ?, ?, 'skipped', ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    run_id,
                    task_id,
                    trigger_source,
                    operator,
                    reason,
                    json.dumps(list(command)),
                    now,
                    now,
                    1 if window_bound else 0,
                    None if inside_window is None else (1 if inside_window else 0),
                ),
            )
            self._touch_state(task_id, run_id=run_id, status="skipped")
        return run_id

    def record_breaker_reset(self, *, task_id: str, operator: str) -> str:
        run_id = str(uuid.uuid4())
        now = self._now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO job_run (
                    run_id, task_id, trigger_source, operator, status, command_json,
                    started_at, finished_at, duration_ms
                ) VALUES (?, ?, 'operator_reset', ?, 'breaker_reset', '[]', ?, ?, 0)
                """,
                (run_id, task_id, operator, now, now),
            )
            self._connection.execute(
                """
                UPDATE job_task_state
                   SET consecutive_failures = 0, breaker_open = 0, breaker_opened_at = NULL,
                       last_run_id = ?, last_status = 'breaker_reset'
                 WHERE task_id = ?
                """,
                (run_id, task_id),
            )
            self._ensure_state(task_id)
        return run_id

    def _ensure_state(self, task_id: str) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO job_task_state (task_id) VALUES (?)", (task_id,)
        )

    def _touch_state(self, task_id: str, *, run_id: str, status: str) -> None:
        self._ensure_state(task_id)
        self._connection.execute(
            """
            UPDATE job_task_state
               SET last_run_id = ?, last_status = ?
             WHERE task_id = ?
            """,
            (run_id, status, task_id),
        )

    def _record_outcome(self, task_id: str, *, run_id: str, status: str) -> None:
        self._ensure_state(task_id)
        now = self._now()
        if status == "succeeded":
            self._connection.execute(
                """
                UPDATE job_task_state
                   SET consecutive_failures = 0, breaker_open = 0, breaker_opened_at = NULL,
                       last_run_id = ?, last_status = 'succeeded', last_success_at = ?
                 WHERE task_id = ?
                """,
                (run_id, now, task_id),
            )
            return
        if status != "failed":
            self._touch_state(task_id, run_id=run_id, status=status)
            return
        current = self._connection.execute(
            "SELECT consecutive_failures, breaker_open FROM job_task_state WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        failures = int(current["consecutive_failures"] or 0) + 1 if current else 1
        breaker_open = 1 if failures >= 2 else 0
        opened_at = now if breaker_open else None
        self._connection.execute(
            """
            UPDATE job_task_state
               SET consecutive_failures = ?, breaker_open = ?, breaker_opened_at = ?,
                   last_run_id = ?, last_status = 'failed', last_failure_at = ?
             WHERE task_id = ?
            """,
            (failures, breaker_open, opened_at, run_id, now, task_id),
        )

    # -- reads ------------------------------------------------------------------------------

    def _run_row(self, run_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self._connection.execute(
                "SELECT * FROM job_run WHERE run_id = ?", (run_id,)
            ).fetchone()

    def run(self, run_id: str) -> JobRun | None:
        row = self._run_row(run_id)
        return None if row is None else _run_from_row(row)

    def history(
        self,
        *,
        task_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[JobRun, ...]:
        clauses: list[str] = []
        params: list[Any] = []
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(task_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([int(limit), int(offset)])
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT * FROM job_run
                {where}
                ORDER BY started_at DESC, rowid DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return tuple(_run_from_row(row) for row in rows)

    def total(self, *, task_id: str | None = None, status: str | None = None) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(task_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            row = self._connection.execute(
                f"SELECT COUNT(*) AS total FROM job_run {where}", params
            ).fetchone()
        return int(row["total"])

    def task_state(self, task_id: str) -> JobTaskState:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM job_task_state WHERE task_id = ?", (task_id,)
            ).fetchone()
        return _state_from_row(task_id, row)

    def summaries(self, task_ids: Iterable[str]) -> dict[str, JobTaskSummary]:
        summaries: dict[str, JobTaskSummary] = {}
        for task_id in task_ids:
            latest_run = None
            for candidate in self.history(task_id=task_id, limit=5):
                # A breaker reset is an operator action, not a run: the "last run" shown to the
                # operator is the most recent real run, so a failed run keeps its red dot.
                if candidate.status != "breaker_reset":
                    latest_run = candidate
                    break
            summaries[task_id] = JobTaskSummary(
                task_id=task_id,
                last_run=latest_run,
                state=self.task_state(task_id),
            )
        return summaries


def _run_from_row(row: sqlite3.Row) -> JobRun:
    return JobRun(
        run_id=row["run_id"],
        task_id=row["task_id"],
        trigger_source=row["trigger_source"],
        operator=row["operator"],
        status=row["status"],
        skip_reason=row["skip_reason"],
        command=tuple(json.loads(row["command_json"] or "[]")),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        duration_ms=row["duration_ms"],
        exit_code=row["exit_code"],
        items_processed=row["items_processed"],
        items_failed=row["items_failed"],
        summary=json.loads(row["summary_json"]) if row["summary_json"] else None,
        stdout_excerpt=row["stdout_excerpt"],
        stderr_excerpt=row["stderr_excerpt"],
        window_bound=bool(row["window_bound"]),
        inside_window=None if row["inside_window"] is None else bool(row["inside_window"]),
    )


def _state_from_row(task_id: str, row: sqlite3.Row | None) -> JobTaskState:
    if row is None:
        return JobTaskState(task_id=task_id)
    return JobTaskState(
        task_id=task_id,
        consecutive_failures=int(row["consecutive_failures"] or 0),
        breaker_open=bool(row["breaker_open"]),
        breaker_opened_at=row["breaker_opened_at"],
        last_run_id=row["last_run_id"],
        last_status=row["last_status"],
        last_failure_at=row["last_failure_at"],
        last_success_at=row["last_success_at"],
    )


# ---------------------------------------------------------------------------------------- lock


class JobLock:
    """One ``flock``-based re-entrancy lock file, held for the whole run."""

    def __init__(self, path: Path, descriptor: int) -> None:
        self._path = path
        self._descriptor = descriptor

    @property
    def path(self) -> Path:
        return self._path

    @classmethod
    def try_acquire(cls, path: Path | str) -> "JobLock | None":
        lock_path = Path(path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(descriptor)
            return None
        return cls(lock_path, descriptor)

    def release(self) -> None:
        if self._descriptor < 0:
            return
        descriptor, self._descriptor = self._descriptor, -1
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def __enter__(self) -> "JobLock":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


# ------------------------------------------------------------------------------- postgres probe


class PostgresProbe:
    """Cached, fail-soft availability probe for the build-time PostgreSQL."""

    ENV_ORDER = ("CANONICAL_V2_DATABASE_URL", "DATABASE_URL", "DATABASE_URL_TEST")

    def __init__(
        self,
        environ: Mapping[str, str] | None = None,
        *,
        connect: Callable[..., Any] | None = None,
        ttl_seconds: float = 30.0,
        timeout_seconds: float = 2.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._environ = dict(os.environ if environ is None else environ)
        self._connect = connect or _connect_postgres
        self._ttl = float(ttl_seconds)
        self._timeout = float(timeout_seconds)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._cached: bool | None = None
        self._monotonic: float = 0.0
        self._source: str | None = None
        self._checked_at: str | None = None

    def _dsn(self) -> tuple[str | None, str | None]:
        for name in self.ENV_ORDER:
            value = self._environ.get(name, "").strip()
            if value:
                return name, value
        return None, None

    def available(self) -> bool:
        with self._lock:
            now_monotonic = time.monotonic()
            if self._cached is not None and (now_monotonic - self._monotonic) < self._ttl:
                return self._cached
            source, dsn = self._dsn()
            self._source = source
            self._checked_at = self._clock().isoformat()
            self._monotonic = now_monotonic
            if dsn is None:
                self._cached = False
                return False
            try:
                connection = self._connect(dsn, connect_timeout=self._timeout)
            except Exception as exc:  # noqa: BLE001 - a probe failure is a result, not an error
                logger.debug("PostgreSQL probe failed: %s", type(exc).__name__)
                self._cached = False
                return False
            try:
                close = getattr(connection, "close", None)
                if callable(close):
                    close()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass
            self._cached = True
            return True

    def describe(self) -> dict[str, Any]:
        available = self.available()
        return {
            "available": available,
            "source": self._source,
            "checked_at": self._checked_at,
        }


def _connect_postgres(dsn: str, *, connect_timeout: float) -> Any:
    import psycopg

    return psycopg.connect(dsn, connect_timeout=connect_timeout)


# -------------------------------------------------------------------------------------- runtime


@dataclass(frozen=True, slots=True)
class TriggerOutcome:
    task_id: str
    run_id: str
    status: str
    skip_reason: str | None
    started_at: str
    command: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "status": self.status,
            "skip_reason": self.skip_reason,
            "started_at": self.started_at,
            "command": list(self.command),
        }


def _spawn_subprocess(
    argv: Sequence[str], *, cwd: str, env: Mapping[str, str], timeout: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        env=dict(env),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def parse_job_summary(stdout: str | None) -> dict[str, Any] | None:
    """Read the child's declared reporting line: ``{"job_summary": {...}}``."""

    if not stdout:
        return None
    for line in reversed(stdout.splitlines()):
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            payload = json.loads(text)
        except ValueError:
            continue
        if isinstance(payload, Mapping) and isinstance(payload.get("job_summary"), Mapping):
            return dict(payload["job_summary"])
    return None


def _inside_window(collection: Any, moment: datetime) -> bool:
    hour = moment.astimezone(UTC).hour
    return collection.window_start_hour_utc <= hour < collection.window_end_hour_utc


class JobRuntime:
    """The single gate plus execution for every trigger source."""

    def __init__(
        self,
        *,
        store: JobRunStore,
        settings_store: ManagedSettingsStore,
        tasks: Sequence[JobTask] | None = None,
        lock_dir: Path | str | None = None,
        environ: Mapping[str, str] | None = None,
        repo_root: Path | str | None = None,
        clock: Callable[[], datetime] | None = None,
        spawn: Callable[..., Any] | None = None,
        postgres_probe: PostgresProbe | None = None,
    ) -> None:
        self.store = store
        self._settings = settings_store
        declared = tuple(JOB_TASKS if tasks is None else tasks)
        self._tasks = declared
        self._tasks_by_id: dict[str, JobTask] = {}
        for task in declared:
            if task.task_id in self._tasks_by_id:
                raise JobsConfigurationError(f"duplicate task id: {task.task_id}")
            self._tasks_by_id[task.task_id] = task
        self._environ = dict(os.environ if environ is None else environ)
        self._repo_root = Path(repo_root) if repo_root is not None else default_repo_root()
        self._lock_dir = (
            Path(lock_dir)
            if lock_dir is not None
            else store.database_path.parent / "locks"
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._spawn = spawn or _spawn_subprocess
        self._probe = postgres_probe or PostgresProbe(self._environ)
        self._threads: list[threading.Thread] = []
        self._threads_lock = threading.Lock()

    # -- introspection ----------------------------------------------------------------------

    def _effective_settings(self) -> ManagedSettings:
        try:
            document, _ = self._settings.effective()
        except ManagedSettingsError as exc:
            raise JobsConfigurationError(str(exc)) from exc
        return document

    def _settings_snapshot(self) -> tuple[ManagedSettings | None, str | None]:
        try:
            return self._effective_settings(), None
        except JobsConfigurationError as exc:
            return None, str(exc)

    def task_views(self) -> list[dict[str, Any]]:
        document, config_error = self._settings_snapshot()
        summaries = self.store.summaries(task.task_id for task in self._tasks)
        postgres = self._probe.describe()
        now = self._clock()
        views: list[dict[str, Any]] = []
        for task in self._tasks:
            summary = summaries[task.task_id]
            last_run = summary.last_run
            enabled: bool | None = None
            quota_limit: int | None = None
            if document is not None:
                enabled = bool(document.collection.enabled.get(task.domain or "", True))
                quota_limit = self._quota_limits(task, document).get(task.quota or "", None)
            if task.requires_postgres and not postgres["available"]:
                available, reason = False, "postgres_unavailable"
            elif config_error is not None:
                available, reason = True, None
            else:
                available, reason = True, None
            views.append(
                {
                    **task.as_dict(),
                    "next_run_at": (
                        cron_next_fire(task.schedule_cron, now=now).isoformat()
                        if task.schedule_cron
                        else None
                    ),
                    "switch_enabled": enabled,
                    "quota_limit": quota_limit,
                    "available": available,
                    "unavailable_reason": reason,
                    "last_run": None if last_run is None else last_run.as_dict(),
                    "failure_flag": summary.failure_flag,
                    "consecutive_failures": summary.state.consecutive_failures,
                    "breaker_open": summary.state.breaker_open,
                    "last_success_at": summary.state.last_success_at,
                    "last_failure_at": summary.state.last_failure_at,
                }
            )
        return views

    def _quota_limits(self, task: JobTask, document: ManagedSettings) -> dict[str, int]:
        return {
            "web_search": int(document.collection.max_web_searches_per_run),
            "llm": int(document.collection.max_llm_calls_per_run),
        } if task.quota is not None else {}

    def storage_status(self) -> dict[str, Any]:
        return {"available": True, "path": str(self.store.database_path)}

    def config_status(self) -> dict[str, Any]:
        _, error = self._settings_snapshot()
        return {"available": error is None, "reason": error}

    def postgres_status(self) -> dict[str, Any]:
        return self._probe.describe()

    def task_state(self, task_id: str) -> JobTaskState:
        get_job_task_or_declared(self._tasks_by_id, task_id)
        return self.store.task_state(task_id)

    def history(
        self,
        task_id: str,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[JobRun, ...]:
        get_job_task_or_declared(self._tasks_by_id, task_id)
        return self.store.history(task_id=task_id, status=status, limit=limit, offset=offset)

    def history_total(self, task_id: str, *, status: str | None = None) -> int:
        return self.store.total(task_id=task_id, status=status)

    def run_detail(self, run_id: str) -> dict[str, Any] | None:
        row = self.store.run(run_id)
        return None if row is None else row.as_dict(include_samples=True)

    def reset_breaker(self, task_id: str, *, operator: str) -> dict[str, Any]:
        task = get_job_task_or_declared(self._tasks_by_id, task_id)
        run_id = self.store.record_breaker_reset(task_id=task.task_id, operator=operator)
        state = self.store.task_state(task.task_id)
        return {
            "task_id": task.task_id,
            "breaker_open": state.breaker_open,
            "consecutive_failures": state.consecutive_failures,
            "reset_run_id": run_id,
        }

    # -- the gate ---------------------------------------------------------------------------

    def _resolve(self, task_id: str) -> JobTask:
        return get_job_task_or_declared(self._tasks_by_id, task_id)

    def trigger(
        self,
        task_id: str,
        *,
        params: Mapping[str, str] | None = None,
        operator: str = "anonymous",
        trigger_source: str = MANUAL_TRIGGER,
    ) -> TriggerOutcome:
        task = self._resolve(task_id)
        argv = task.argv_for(params)
        operator_text = (operator or "anonymous").strip()[:_OPERATOR_LIMIT] or "anonymous"

        if task.requires_postgres and not self._probe.available():
            raise JobPostgresUnavailableError(
                f"{task.task_id} requires the build-time PostgreSQL, which is unavailable here"
            )
        state = self.store.task_state(task.task_id)
        if state.breaker_open:
            raise JobBreakerOpenError(
                f"{task.task_id} is fused open after {state.consecutive_failures} consecutive failures"
            )
        document = self._effective_settings()
        now = self._clock()
        inside_window = _inside_window(document.collection, now)

        if task.collection_gated and not document.collection.enabled.get(task.domain or "", True):
            return self._skip(
                task,
                argv,
                operator_text,
                trigger_source,
                reason=SKIP_SWITCH_OFF,
                inside_window=inside_window,
            )
        quota_limits = self._quota_limits(task, document)
        if task.quota is not None and quota_limits.get(task.quota, 0) == 0:
            return self._skip(
                task,
                argv,
                operator_text,
                trigger_source,
                reason=SKIP_QUOTA_EXHAUSTED,
                inside_window=inside_window,
            )
        if trigger_source == SCHEDULE_TRIGGER and task.window_bound and not inside_window:
            return self._skip(
                task,
                argv,
                operator_text,
                trigger_source,
                reason=SKIP_OUTSIDE_WINDOW,
                inside_window=inside_window,
            )

        lock = JobLock.try_acquire(self._lock_dir / f"{task.task_id}.lock")
        if lock is None:
            active = state.last_run_id if state.last_status == "running" else None
            raise JobAlreadyRunningError(
                f"{task.task_id} is already running", active_run_id=active
            )
        try:
            run_id = self.store.start_run(
                task_id=task.task_id,
                trigger_source=trigger_source,
                operator=operator_text,
                command=argv,
                window_bound=task.window_bound,
                inside_window=inside_window,
            )
        except Exception:
            lock.release()
            raise
        started_at = self.store.run(run_id)
        thread = threading.Thread(
            target=self._execute,
            args=(task, argv, run_id, lock, quota_limits),
            name=f"job-{task.task_id}",
            daemon=True,
        )
        with self._threads_lock:
            self._threads = [candidate for candidate in self._threads if candidate.is_alive()]
            self._threads.append(thread)
        try:
            thread.start()
        except Exception as exc:  # pragma: no cover - thread start failure is environmental
            lock.release()
            self.store.finish_run(
                run_id,
                status="failed",
                duration_ms=0,
                exit_code=None,
                summary={"quota": quota_limits},
                stderr=f"{type(exc).__name__}: {exc}",
            )
            raise JobsError(f"{task.task_id} could not start: {type(exc).__name__}") from exc
        return TriggerOutcome(
            task_id=task.task_id,
            run_id=run_id,
            status="running",
            skip_reason=None,
            started_at=(started_at.started_at if started_at else now.isoformat()),
            command=argv,
        )

    def _skip(
        self,
        task: JobTask,
        argv: Sequence[str],
        operator: str,
        trigger_source: str,
        *,
        reason: str,
        inside_window: bool,
    ) -> TriggerOutcome:
        run_id = self.store.record_skip(
            task_id=task.task_id,
            trigger_source=trigger_source,
            operator=operator,
            reason=reason,
            command=argv,
            window_bound=task.window_bound,
            inside_window=inside_window,
        )
        row = self.store.run(run_id)
        return TriggerOutcome(
            task_id=task.task_id,
            run_id=run_id,
            status="skipped",
            skip_reason=reason,
            started_at=row.started_at if row else "",
            command=tuple(argv),
        )

    def _execute(
        self,
        task: JobTask,
        argv: Sequence[str],
        run_id: str,
        lock: JobLock,
        quota_limits: Mapping[str, int],
    ) -> None:
        started = time.monotonic()
        env = dict(self._environ)
        env[QUOTA_WEB_SEARCH_ENV] = str(quota_limits.get("web_search", 0))
        env[QUOTA_LLM_ENV] = str(quota_limits.get("llm", 0))
        env[JOB_TASK_ID_ENV] = task.task_id
        env[JOB_RUN_ID_ENV] = run_id
        cwd = str(self._repo_root / task.cwd_relative)
        status, exit_code = "succeeded", 0
        stdout: str | bytes | None = ""
        stderr: str | bytes | None = ""
        try:
            completed = self._spawn(
                argv, cwd=cwd, env=env, timeout=task.timeout_seconds
            )
            stdout = getattr(completed, "stdout", "") or ""
            stderr = getattr(completed, "stderr", "") or ""
            exit_code = int(getattr(completed, "returncode", 0) or 0)
            status = "succeeded" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = f"{exc.stderr or ''}\njob timed out after {task.timeout_seconds}s\n"
            exit_code, status = 124, "failed"
        except Exception as exc:  # noqa: BLE001 - a launch failure is a failed run
            stdout, stderr = "", f"{type(exc).__name__}: {exc}"
            exit_code, status = None, "failed"
        duration_ms = int((time.monotonic() - started) * 1000)
        summary: dict[str, Any] = {"quota": dict(quota_limits)}
        parsed = parse_job_summary(stdout if isinstance(stdout, str) else None)
        if parsed is not None:
            summary["job_summary"] = parsed
        try:
            self.store.finish_run(
                run_id,
                status=status,
                duration_ms=duration_ms,
                exit_code=exit_code,
                items_processed=_optional_int(parsed, "items_processed"),
                items_failed=_optional_int(parsed, "items_failed"),
                summary=summary,
                stdout=stdout,
                stderr=stderr,
            )
        except Exception:  # noqa: BLE001 - never lose the lock on a bookkeeping failure
            logger.exception("failed to close job run %s", run_id)
        finally:
            lock.release()

    def wait_for_idle(self, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        with self._threads_lock:
            threads = list(self._threads)
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))

    def close(self) -> None:
        self.wait_for_idle(timeout=5.0)
        self.store.close()


def get_job_task_or_declared(tasks_by_id: Mapping[str, JobTask], task_id: str) -> JobTask:
    task = tasks_by_id.get(task_id)
    if task is None:
        raise JobTaskUnknownError(f"unknown task id: {task_id}")
    return task


def _optional_int(payload: Mapping[str, Any] | None, key: str) -> int | None:
    if not payload:
        return None
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


# ------------------------------------------------------------------------------- store location


def jobs_database_path(environ: Mapping[str, str] | None = None) -> Path:
    """Resolve the jobs database the same way the other serving stores resolve theirs."""

    values = os.environ if environ is None else environ
    explicit = values.get(JOBS_DB_ENV, "").strip()
    if explicit:
        return Path(explicit)
    sibling = values.get(ACCESS_LOG_DB_ENV, "").strip()
    if sibling:
        return Path(sibling).parent / JOBS_DB_FILENAME
    raise JobsStorageUnavailableError(
        f"neither {JOBS_DB_ENV} nor {ACCESS_LOG_DB_ENV} is set"
    )


__all__ = [
    "ACCESS_LOG_DB_ENV",
    "JOB_TASKS",
    "JOB_TASKS_BY_ID",
    "JOB_RUN_ID_ENV",
    "JOB_TASK_ID_ENV",
    "JOBS_DB_ENV",
    "JobAlreadyRunningError",
    "JobBreakerOpenError",
    "JobLock",
    "JobParameterError",
    "JobPostgresUnavailableError",
    "JobRun",
    "JobRunStore",
    "JobRuntime",
    "JobTask",
    "JobTaskState",
    "JobTaskSummary",
    "JobTaskUnknownError",
    "JobsConfigurationError",
    "JobsError",
    "JobsStorageUnavailableError",
    "MANUAL_TRIGGER",
    "PostgresProbe",
    "QUOTA_LLM_ENV",
    "QUOTA_WEB_SEARCH_ENV",
    "RUN_STATUSES",
    "SCHEDULE_TRIGGER",
    "SCHEMA_VERSION",
    "SKIP_OUTSIDE_WINDOW",
    "SKIP_QUOTA_EXHAUSTED",
    "SKIP_SWITCH_OFF",
    "TriggerOutcome",
    "cron_next_fire",
    "get_job_task",
    "jobs_database_path",
    "parse_job_summary",
    "redact_secrets",
]

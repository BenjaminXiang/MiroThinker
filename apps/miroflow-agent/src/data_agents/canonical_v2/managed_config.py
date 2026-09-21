"""Managed, non-sensitive operator configuration for the serving line.

One file (`config/managed/settings.json` by default) carries the values an
operator may change from the admin page. The file is a whitelist schema: any key
outside it is rejected, and credential material is structurally excluded. A
missing file, a missing key, or an unreadable file resolves to documented
defaults — never to an error.

Precedence is ``env > file > default`` for every field that already has an
environment variable, so this file can never become a second source of truth for
a behavior the environment pins. Every read reports which source won — and since
the startup bootstrap projects the file's own values into the environment, a
variable this process adopted from the file is reported as the file (see
:data:`APPLIED_ENV_VAR`), so a saved field stays editable across restarts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


DEFAULT_SETTINGS_DIRNAME = "config/managed"
DEFAULT_SETTINGS_FILENAME = "settings.json"
DEFAULT_AUDIT_FILENAME = "audit.jsonl"
SETTINGS_PATH_ENV = "CANONICAL_V2_MANAGED_SETTINGS"
SCHEMA_VERSION = 1

# The startup bootstrap (`managed_runtime.apply_managed_runtime_config`) records
# here — names only, never values — which variables it projected from the managed
# files. Reading it is what separates "this process adopted the file's value" from
# "someone pinned this variable externally": the former is still the operator's
# own setting and must stay editable on the page, the latter stays read-only.
APPLIED_ENV_VAR = "CANONICAL_V2_MANAGED_ENV_APPLIED"


def applied_env_names(environ: Mapping[str, str] | None = None) -> frozenset[str]:
    """Names of the environment variables this process adopted from managed files."""

    values = os.environ if environ is None else environ
    raw = values.get(APPLIED_ENV_VAR, "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


PUBLIC_DOMAINS: tuple[str, ...] = ("company", "paper", "patent", "professor")

# Field path -> (environment variable, renderer). Only fields listed here can be
# shadowed by the environment; anything else is file/default owned.
_FIELD_ENV_VARS: dict[str, str] = {
    "collection.max_web_searches_per_run": "WEB_LANE_DAILY_QUOTA",
    "collection.window_start_hour_utc": "CANONICAL_V2_COLLECTION_WINDOW_START_HOUR_UTC",
    "collection.window_end_hour_utc": "CANONICAL_V2_COLLECTION_WINDOW_END_HOUR_UTC",
    "extraction_endpoints.llm_base_url": "LOCAL_LLM_BASE_URL",
    "extraction_endpoints.llm_model": "LOCAL_LLM_MODEL",
    "extraction_endpoints.embedding_base_url": "CANONICAL_V2_EMBEDDING_BASE_URL",
    "extraction_endpoints.embedding_model": "CANONICAL_V2_EMBEDDING_MODEL",
    "extraction_endpoints.rerank_base_url": "CANONICAL_V2_RERANK_BASE_URL",
    "extraction_endpoints.rerank_model": "CANONICAL_V2_RERANK_MODEL",
    "paths.serving_pack_dir": "CANONICAL_V2_SERVING_PACK",
    "paths.access_log_retention_days": "CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS",
    "serving.chat_llm_profile": "CHAT_LLM_PROFILE",
    "serving.web_topical_floor": "CANONICAL_V2_WEB_TOPICAL_FLOOR",
    "serving.rerank_timeout_seconds": "CANONICAL_V2_RERANK_TIMEOUT_SECONDS",
    "serving.rerank_max_documents": "CANONICAL_V2_RERANK_MAX_DOCUMENTS",
    "serving.mount_receipt_path": "CANONICAL_V2_SERVING_RECEIPT_PATH",
    "serving.turn_debug_dir": "CANONICAL_V2_TURN_DEBUG_DIR",
    "serving.full_verify": "CANONICAL_V2_SERVING_FULL_VERIFY",
}

# Public alias: the startup bootstrap projects exactly these fields into the
# environment, so the mapping is part of this module's contract.
FIELD_ENV_VARS: dict[str, str] = _FIELD_ENV_VARS

# Displayed on the page but never writable from it. Each entry states why: either
# the value is pinned by the service unit (a page toggle would let one click change
# boot cost or scatter forensic artefacts), or it belongs to the frozen release
# bundle (a real change would require rebuilding the serving index).
PAGE_READONLY_FIELDS: dict[str, str] = {
    "serving.mount_receipt_path": (
        "取证路径：由服务单元钉死；页面改动会让挂载收据散落各处（只读展示）"
    ),
    "serving.turn_debug_dir": (
        "调试目录：开启会把原始轮次转储落盘，必须由部署显式决定（只读展示）"
    ),
    "serving.full_verify": (
        "启动全量校验：开启会把启动从秒级拉到分钟级，必须由服务单元决定（只读展示）"
    ),
    "extraction_endpoints.embedding_model": (
        "服务线向量模型身份由发布包冻结：模型名与维度来自发布包 embedding bundle"
        "（含校验和，不符即拒绝加载），改它需要重建全部向量。地址另有受管字段"
        "（extraction_endpoints.embedding_base_url，已可在页面设置）（只读展示）"
    ),
}

# Credential-shaped names are rejected even if a future schema mistake would
# otherwise let them through: never persist, never echo, never audit a secret.
_SECRET_NAME_FRAGMENTS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
    "database_url",
    "dsn",
    "webhook",
)


class ManagedSettingsError(ValueError):
    """The managed settings request or file is not acceptable."""


class ManagedSettingsUnsupportedError(ManagedSettingsError):
    """A field outside the whitelist (or credential-shaped) was requested."""


class CollectionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    enabled: dict[str, bool] = Field(
        default_factory=lambda: {d: True for d in PUBLIC_DOMAINS}
    )
    max_web_searches_per_run: int = Field(default=200, ge=0, le=10_000)
    max_llm_calls_per_run: int = Field(default=500, ge=0, le=100_000)
    window_start_hour_utc: int = Field(default=17, ge=0, le=23)
    window_end_hour_utc: int = Field(default=22, ge=0, le=23)

    @field_validator("enabled")
    @classmethod
    def _exact_domains(cls, value: dict[str, bool]) -> dict[str, bool]:
        unknown = sorted(set(value) - set(PUBLIC_DOMAINS))
        if unknown:
            raise ValueError(
                "collection.enabled only accepts the four public domains: "
                + ", ".join(unknown)
            )
        return {domain: bool(value.get(domain, True)) for domain in PUBLIC_DOMAINS}

    @model_validator(mode="after")
    def _ordered_window(self) -> CollectionSettings:
        if self.window_end_hour_utc <= self.window_start_hour_utc:
            raise ValueError(
                "collection.window_end_hour_utc must be greater than "
                "collection.window_start_hour_utc (no overnight wrap)"
            )
        return self


class ExtractionEndpoints(BaseModel):
    """Collection-time endpoints. Credentials are env/key-file owned, never here.

    ``embedding_base_url`` is the operator's embedding address: the managed
    value is the runtime's **effective** address (it wins over the address
    recorded in the embedding bundle), so it is editable on the page.
    ``embedding_model`` stays listed in :data:`PAGE_READONLY_FIELDS`: the model
    identity is frozen by the release bundle (the index was built with it), and
    no runtime code reads the variable it projects. The collection/build scripts
    have their own (unmanaged) ``EMBEDDING_BASE_URL`` override.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    llm_base_url: str | None = None
    llm_model: str | None = Field(default=None, max_length=200)
    embedding_base_url: str | None = None
    embedding_model: str | None = Field(default=None, max_length=200)
    rerank_base_url: str | None = None
    rerank_model: str | None = Field(default=None, max_length=200)

    @field_validator("*")
    @classmethod
    def _bounded_url_or_name(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if info.field_name.endswith("_base_url"):
            parsed = urlsplit(text)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"{info.field_name} must be an absolute http(s) URL")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError(f"{info.field_name} must not embed credentials")
            return text.rstrip("/")
        if len(text) > 200:
            raise ValueError(f"{info.field_name} must be at most 200 characters")
        return text


class PathSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    serving_pack_dir: str | None = None
    access_log_retention_days: int = Field(default=90, ge=1, le=3650)

    @field_validator("serving_pack_dir")
    @classmethod
    def _absolute_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if not text.startswith("/"):
            raise ValueError("paths.serving_pack_dir must be an absolute path")
        return text


class ServingSettings(BaseModel):
    """Serving-line switches added after W1 (R16: they belong on the page).

    Page-suitability judgement (design §6): the three tunables below are
    operator-facing (recall floor / latency budget / cost ceiling).
    ``chat_llm_profile`` is the profile the answer/rewrite paths resolve through
    ``CHAT_LLM_PROFILE``. The receipt path, turn-debug directory and full-verify
    flag are declared here so the page can *display* the effective value and its
    source, but they are listed in :data:`PAGE_READONLY_FIELDS` and cannot be
    written from the web surface.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    chat_llm_profile: str | None = Field(default=None, max_length=200)
    web_topical_floor: bool | None = None
    rerank_timeout_seconds: float | None = Field(default=None, gt=0, le=120)
    rerank_max_documents: int | None = Field(default=None, gt=0, le=2048)
    mount_receipt_path: str | None = None
    turn_debug_dir: str | None = None
    full_verify: bool | None = None

    @field_validator("mount_receipt_path", "turn_debug_dir")
    @classmethod
    def _absolute_path_or_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if not text.startswith("/"):
            raise ValueError("serving artifact paths must be absolute")
        return text


class ManagedSettings(BaseModel):
    """The complete, validated managed configuration document."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1, le=SCHEMA_VERSION)
    collection: CollectionSettings = Field(default_factory=CollectionSettings)
    extraction_endpoints: ExtractionEndpoints = Field(
        default_factory=ExtractionEndpoints
    )
    paths: PathSettings = Field(default_factory=PathSettings)
    serving: ServingSettings = Field(default_factory=ServingSettings)


def assert_non_secret_payload(value: object, *, where: str = "settings") -> None:
    """Refuse any credential-shaped key anywhere in a settings payload."""

    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            if key == "schema_version":
                continue
            folded = key.casefold()
            if any(fragment in folded for fragment in _SECRET_NAME_FRAGMENTS):
                raise ManagedSettingsUnsupportedError(
                    f"{where}.{key} looks like credential material and is not "
                    "allowed in the managed settings file"
                )
            assert_non_secret_payload(child, where=f"{where}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_non_secret_payload(child, where=f"{where}[{index}]")


def flatten_settings(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten a settings payload into dotted paths (public helper)."""

    return _flatten(payload)


def _flatten(payload: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


def _dig(payload: Mapping[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _coerce(raw: str, template: Any) -> Any:
    """Coerce an environment string into the type of the field it shadows."""

    text = raw.strip()
    if isinstance(template, bool):
        return text.casefold() in {"1", "true", "yes", "on"}
    if isinstance(template, int) and not isinstance(template, bool):
        return int(text)
    if isinstance(template, float):
        return float(text)
    return text


# Presentation of one managed setting: the only place that knows how a field is
# labelled, bounded and grouped. The page renders from this catalogue (through
# ``EffectiveField.as_dict()``) and holds no field list of its own.
_DOMAIN_LABELS: dict[str, str] = {
    "company": "企业",
    "paper": "论文",
    "patent": "专利",
    "professor": "教授",
}


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One catalogue row. ``default`` is derived from the schema, never typed.

    ``connection`` names the connection card a row belongs to and ``test_arg``
    the ``connections/test`` request argument it supplies — together they are why
    the page can render and probe endpoint fields without knowing any field name.
    """

    path: str
    label: str
    kind: Literal["bool", "int", "float", "text", "url"]
    group: str
    order: int
    consumer: str
    min: float | None = None
    max: float | None = None
    step: float | None = None
    connection: str | None = None
    test_arg: Literal["base_url", "model"] | None = None

    @property
    def default(self) -> Any:
        return _DEFAULT_VALUES[self.path]


FIELD_CATALOG: dict[str, FieldSpec] = {
    "schema_version": FieldSpec(
        path="schema_version",
        label="受管配置 schema 版本",
        kind="int",
        group="meta",
        order=0,
        consumer="服务启动：受管配置 schema 版本",
        min=1,
        max=SCHEMA_VERSION,
        step=1,
    ),
    **{
        f"collection.enabled.{domain}": FieldSpec(
            path=f"collection.enabled.{domain}",
            label=f"{_DOMAIN_LABELS[domain]}采集开关",
            kind="bool",
            group="collection",
            order=10 + index,
            consumer="采集与构建调度：域开关",
        )
        for index, domain in enumerate(PUBLIC_DOMAINS)
    },
    "collection.max_web_searches_per_run": FieldSpec(
        path="collection.max_web_searches_per_run",
        label="每轮 web search 配额上限",
        kind="int",
        group="collection",
        order=20,
        consumer="采集与构建调度：每轮 web 检索配额",
        min=0,
        max=10_000,
        step=1,
    ),
    "collection.max_llm_calls_per_run": FieldSpec(
        path="collection.max_llm_calls_per_run",
        label="每轮 LLM 调用上限",
        kind="int",
        group="collection",
        order=21,
        consumer="采集与构建调度：每轮 LLM 调用上限",
        min=0,
        max=100_000,
        step=1,
    ),
    "collection.window_start_hour_utc": FieldSpec(
        path="collection.window_start_hour_utc",
        label="执行窗口起始（UTC 小时）",
        kind="int",
        group="collection",
        order=22,
        consumer="采集与构建调度：执行窗口起始",
        min=0,
        max=23,
        step=1,
    ),
    "collection.window_end_hour_utc": FieldSpec(
        path="collection.window_end_hour_utc",
        label="执行窗口结束（UTC 小时）",
        kind="int",
        group="collection",
        order=23,
        consumer="采集与构建调度：执行窗口结束",
        min=0,
        max=23,
        step=1,
    ),
    "extraction_endpoints.llm_base_url": FieldSpec(
        path="extraction_endpoints.llm_base_url",
        label="采集 LLM Base URL",
        kind="url",
        group="endpoints",
        order=10,
        consumer="采集与构建：LLM 端点",
        connection="llm",
        test_arg="base_url",
    ),
    "extraction_endpoints.llm_model": FieldSpec(
        path="extraction_endpoints.llm_model",
        label="采集 LLM 模型名",
        kind="text",
        group="endpoints",
        order=11,
        consumer="采集与构建：LLM 模型",
        connection="llm",
        test_arg="model",
    ),
    "extraction_endpoints.embedding_base_url": FieldSpec(
        path="extraction_endpoints.embedding_base_url",
        label="Embedding Base URL",
        kind="url",
        group="endpoints",
        order=20,
        consumer="服务线向量读取 + 采集与构建：Embedding 端点（运行期生效地址）",
        connection="embedding",
        test_arg="base_url",
    ),
    "extraction_endpoints.embedding_model": FieldSpec(
        path="extraction_endpoints.embedding_model",
        label="Embedding 模型名",
        kind="text",
        group="endpoints",
        order=21,
        consumer="采集与构建：Embedding 模型",
        connection="embedding",
        test_arg="model",
    ),
    "extraction_endpoints.rerank_base_url": FieldSpec(
        path="extraction_endpoints.rerank_base_url",
        label="Rerank Base URL",
        kind="url",
        group="endpoints",
        order=30,
        consumer="检索与回答：rerank 客户端端点（未配置则 rerank 不启用）",
        connection="rerank",
        test_arg="base_url",
    ),
    "extraction_endpoints.rerank_model": FieldSpec(
        path="extraction_endpoints.rerank_model",
        label="Rerank 模型名",
        kind="text",
        group="endpoints",
        order=31,
        consumer="检索与回答：rerank 客户端模型",
        connection="rerank",
        test_arg="model",
    ),
    "paths.serving_pack_dir": FieldSpec(
        path="paths.serving_pack_dir",
        label="serving pack 目录",
        kind="text",
        group="paths",
        order=10,
        consumer="服务启动：serving pack 目录",
    ),
    "paths.access_log_retention_days": FieldSpec(
        path="paths.access_log_retention_days",
        label="访问日志保留天数",
        kind="int",
        group="paths",
        order=20,
        consumer="访问日志清理与保留",
        min=1,
        max=3650,
        step=1,
    ),
    "serving.chat_llm_profile": FieldSpec(
        path="serving.chat_llm_profile",
        label="对话模型档位",
        kind="text",
        group="serving",
        order=12,
        consumer="知识服务/对话模型档位",
    ),
    "serving.web_topical_floor": FieldSpec(
        path="serving.web_topical_floor",
        label="Web 轨主题相关性下限（kill switch）",
        kind="bool",
        group="serving",
        order=10,
        consumer="检索与回答：Web 轨相关度下限",
    ),
    "serving.rerank_timeout_seconds": FieldSpec(
        path="serving.rerank_timeout_seconds",
        label="Rerank 超时（秒）",
        kind="float",
        group="serving",
        order=20,
        consumer="检索与回答：rerank 超时预算",
        min=0.1,
        max=120,
        step=0.1,
    ),
    "serving.rerank_max_documents": FieldSpec(
        path="serving.rerank_max_documents",
        label="Rerank 单次最大文档数",
        kind="int",
        group="serving",
        order=21,
        consumer="检索与回答：rerank 单次文档上限",
        min=1,
        max=2048,
        step=1,
    ),
    "serving.mount_receipt_path": FieldSpec(
        path="serving.mount_receipt_path",
        label="挂载收据路径",
        kind="text",
        group="serving",
        order=30,
        consumer="服务启动：挂载收据路径（只读展示）",
    ),
    "serving.turn_debug_dir": FieldSpec(
        path="serving.turn_debug_dir",
        label="轮次调试目录",
        kind="text",
        group="serving",
        order=31,
        consumer="服务启动：轮次转储目录（只读展示）",
    ),
    "serving.full_verify": FieldSpec(
        path="serving.full_verify",
        label="启动全量校验",
        kind="bool",
        group="serving",
        order=32,
        consumer="服务启动：全量校验（只读展示）",
    ),
}

_DEFAULT_VALUES: dict[str, Any] = _flatten(ManagedSettings().model_dump(mode="json"))


@dataclass(frozen=True, slots=True)
class EffectiveField:
    path: str
    value: Any
    source: Literal["env", "file", "default"]
    env_var: str | None
    editable: bool
    readonly_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        spec = FIELD_CATALOG[self.path]
        return {
            "path": self.path,
            "value": self.value,
            "source": self.source,
            "env_var": self.env_var,
            "editable": self.editable,
            "readonly_reason": self.readonly_reason,
            "label": spec.label,
            "kind": spec.kind,
            "group": spec.group,
            "order": spec.order,
            "consumer": spec.consumer,
            "min": spec.min,
            "max": spec.max,
            "step": spec.step,
            "connection": spec.connection,
            "test_arg": spec.test_arg,
            "default": spec.default,
        }


class ManagedSettingsStore:
    """Read, validate, atomically write, and audit the managed settings file."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        repo_root: Path | str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._environ = dict(os.environ if environ is None else environ)
        self._repo_root = (
            Path(repo_root) if repo_root is not None else default_repo_root()
        )
        self._path = (
            Path(path) if path is not None else default_settings_path(self._environ)
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def path(self) -> Path:
        return self._path

    @property
    def audit_path(self) -> Path:
        return self._path.with_name(DEFAULT_AUDIT_FILENAME)

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    # -- reads ---------------------------------------------------------------

    def exists(self) -> bool:
        return self._path.is_file()

    def raw(self) -> dict[str, Any]:
        """Return the validated on-disk document, or defaults when unusable."""

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ManagedSettings().model_dump(mode="json")
        if not isinstance(payload, Mapping):
            return ManagedSettings().model_dump(mode="json")
        try:
            assert_non_secret_payload(payload)
            return ManagedSettings.model_validate(payload).model_dump(mode="json")
        except (ManagedSettingsError, ValidationError):
            return ManagedSettings().model_dump(mode="json")

    def effective(self) -> tuple[ManagedSettings, tuple[EffectiveField, ...]]:
        """Resolve ``env > file > default`` and report the winning source.

        A variable the startup bootstrap projected from this file resolves the same
        way (the environment still holds the winning value) but is reported as
        ``file``: the value's origin is the managed document, so the page must keep
        offering the field. Only a variable the projection did not set is an
        external pin and stays read-only.
        """

        document = ManagedSettings.model_validate(self.raw())
        file_values = _flatten(document.model_dump(mode="json"))
        resolved: dict[str, Any] = dict(file_values)
        sources: dict[str, Literal["env", "file", "default"]] = {}
        projected = applied_env_names(self._environ)
        defaults = _flatten(ManagedSettings().model_dump(mode="json"))
        for path, value in file_values.items():
            sources[path] = "default" if value == defaults.get(path) else "file"
        for path, env_var in _FIELD_ENV_VARS.items():
            raw = self._environ.get(env_var)
            if raw is None or not raw.strip():
                continue
            try:
                resolved[path] = _coerce(raw, file_values.get(path))
            except (TypeError, ValueError):
                raise ManagedSettingsError(
                    f"environment variable {env_var} does not match the type of {path}"
                ) from None
            sources[path] = "file" if env_var in projected else "env"
        try:
            effective_document = ManagedSettings.model_validate(_unflatten(resolved))
        except ValidationError as exc:
            raise ManagedSettingsError(
                "effective configuration is invalid once environment overrides "
                "are applied"
            ) from exc
        effective_values = _flatten(effective_document.model_dump(mode="json"))
        fields = tuple(
            EffectiveField(
                path=path,
                value=effective_values.get(path),
                source=sources.get(path, "default"),
                env_var=_FIELD_ENV_VARS.get(path),
                editable=(
                    sources.get(path, "default") != "env"
                    and path not in PAGE_READONLY_FIELDS
                ),
                readonly_reason=(
                    PAGE_READONLY_FIELDS.get(path)
                    if sources.get(path, "default") != "env"
                    else None
                ),
            )
            for path in sorted(file_values)
        )
        return effective_document, fields

    def field_map(self) -> dict[str, dict[str, Any]]:
        _, fields = self.effective()
        return {field.path: field.as_dict() for field in fields}

    # -- writes --------------------------------------------------------------

    def patch(
        self,
        updates: Mapping[str, Any],
        *,
        operator: str | None = None,
    ) -> dict[str, Any]:
        """Validate, atomically persist, and audit one whitelist-only patch.

        Only the operator-written keys live in the file: the patch is merged onto
        the overrides already on disk, an explicit ``None`` removes an override
        (the three-state "回到默认" gesture), and a patch that moves nothing is a
        no-write/no-audit no-op. The audit record still carries the resolved
        before/after documents, so a reader sees the whole picture rather than a
        diff against invisible defaults.
        """

        if not isinstance(updates, Mapping) or not updates:
            raise ManagedSettingsError("patch body must be a non-empty object")
        assert_non_secret_payload(updates, where="patch")
        allowed = set(_flatten(ManagedSettings().model_dump(mode="json")))
        submitted = _flatten(updates)
        unknown = sorted(set(submitted) - allowed)
        if unknown:
            raise ManagedSettingsUnsupportedError(
                "field is not in the managed settings whitelist: " + ", ".join(unknown)
            )
        readonly = sorted(path for path in submitted if path in PAGE_READONLY_FIELDS)
        if readonly:
            reasons = "; ".join(
                f"{path}: {PAGE_READONLY_FIELDS[path]}" for path in readonly
            )
            raise ManagedSettingsUnsupportedError(
                "field is display-only on the admin page: " + reasons
            )
        _validate_chat_llm_profile_choice(submitted)
        stored_before = self._stored_overrides()
        stored_after = _apply_overrides(stored_before, updates)
        document = self._validated_document(stored_after)
        before_flat = _flatten(stored_before)
        after_flat = _flatten(stored_after)
        changed = sorted(
            path
            for path in set(before_flat) | set(after_flat)
            if before_flat.get(path) != after_flat.get(path)
        )
        if not changed:
            return {
                "settings": document.model_dump(mode="json"),
                "changed": [],
                "audit_written": False,
            }
        before_document = self._validated_document(stored_before)
        self._atomic_write(stored_after)
        self._append_audit(
            {
                "action": "patch",
                "operator": (operator or "anonymous").strip() or "anonymous",
                "before": before_document.model_dump(mode="json"),
                "after": document.model_dump(mode="json"),
                "changed": changed,
            }
        )
        return {
            "settings": document.model_dump(mode="json"),
            "changed": changed,
            "audit_written": True,
        }

    def _stored_overrides(self) -> dict[str, Any]:
        """The operator-written keys on disk; ``{}`` when absent or unusable.

        A file that no longer validates (hand-edited, or carrying credential-shaped
        keys) is treated as unusable exactly like today's ``raw()`` fallback: the
        patch then starts from defaults instead of persisting broken content.
        """

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(payload, Mapping):
            return {}
        candidate = {str(key): value for key, value in payload.items()}
        try:
            assert_non_secret_payload(candidate)
            self._validated_document(candidate)
        except ManagedSettingsError:
            return {}
        return candidate

    def _validated_document(self, overrides: Mapping[str, Any]) -> ManagedSettings:
        merged = _deep_merge(ManagedSettings().model_dump(mode="json"), overrides)
        try:
            return ManagedSettings.model_validate(merged)
        except ValidationError as exc:
            raise ManagedSettingsError(
                "managed settings validation failed: "
                + "; ".join(
                    f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                    for error in exc.errors()
                )
            ) from exc

    def _atomic_write(self, document: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        )
        descriptor, temp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix=".settings-", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self._path)
        except BaseException:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def _append_audit(self, record: Mapping[str, Any]) -> None:
        entry = {"at": self._clock().isoformat(), **record}
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True, allow_nan=False)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.audit_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            os.write(descriptor, (line + "\n").encode("utf-8"))
            os.fsync(descriptor)
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def audit_records(self) -> tuple[dict[str, Any], ...]:
        try:
            raw = self.audit_path.read_text(encoding="utf-8")
        except OSError:
            return ()
        records: list[dict[str, Any]] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, Mapping):
                records.append(dict(value))
        return tuple(records)


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = {key: value for key, value in base.items()}
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _apply_overrides(
    base: Mapping[str, Any], overlay: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge one patch onto the stored overrides; an explicit ``None`` removes.

    A branch that empties out is dropped too, so clearing the last override of a
    group leaves no empty shell behind in the file. An empty mapping in the patch
    is not a deletion: it carries no instruction.
    """

    merged: dict[str, Any] = {key: value for key, value in base.items()}
    for key, value in overlay.items():
        if isinstance(value, Mapping):
            if not value:
                continue
            existing = merged.get(key)
            child = _apply_overrides(
                existing if isinstance(existing, Mapping) else {}, value
            )
            if child:
                merged[key] = child
            else:
                merged.pop(key, None)
        elif value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def _validate_chat_llm_profile_choice(flat_updates: Mapping[str, Any]) -> None:
    """Refuse a saved profile name the serving line would silently replace.

    ``serving.chat_llm_profile`` is free text in the schema on purpose: the schema
    also validates the effective document (environment overrides included) and
    hand-edited files, and there an unknown name is tolerated — the serving line
    falls back to its default profile and keeps answering. A *save* is a different
    act: it is the operator's decision, and quietly landing on the fallback is
    exactly the lie this file exists to remove. So the name is resolved strictly
    here, on the write path, and the refusal lists the choices.
    """

    value = flat_updates.get("serving.chat_llm_profile")
    if not isinstance(value, str) or not value.strip():
        return
    from ..professor.llm_profiles import (
        list_professor_llm_profile_names,
        resolve_professor_llm_profile_name,
    )

    text = value.strip()
    try:
        resolve_professor_llm_profile_name(profile_name=text, strict=True)
    except ValueError:
        raise ManagedSettingsError(
            f"serving.chat_llm_profile is not a known LLM profile: {text!r}; "
            "available profiles: " + ", ".join(list_professor_llm_profile_names())
        ) from None


def _unflatten(flat: Mapping[str, Any]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for path, value in flat.items():
        parts = path.split(".")
        cursor = document
        for part in parts[:-1]:
            node = cursor.get(part)
            if not isinstance(node, dict):
                node = {}
                cursor[part] = node
            cursor = node
        cursor[parts[-1]] = value
    return document


def default_repo_root() -> Path:
    """Return the checkout root that contains this app (worktree aware)."""

    here = Path(__file__).resolve()
    # apps/miroflow-agent/src/data_agents/canonical_v2/managed_config.py
    return here.parents[5]


def default_settings_path(environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    override = values.get(SETTINGS_PATH_ENV, "").strip()
    if override:
        return Path(override)
    return default_repo_root() / DEFAULT_SETTINGS_DIRNAME / DEFAULT_SETTINGS_FILENAME


def store_from_environment(
    *, environ: Mapping[str, str] | None = None, path: Path | str | None = None
) -> ManagedSettingsStore:
    return ManagedSettingsStore(path=path, environ=environ)


__all__ = [
    "APPLIED_ENV_VAR",
    "CollectionSettings",
    "DEFAULT_AUDIT_FILENAME",
    "DEFAULT_SETTINGS_DIRNAME",
    "DEFAULT_SETTINGS_FILENAME",
    "EffectiveField",
    "ExtractionEndpoints",
    "FIELD_CATALOG",
    "FIELD_ENV_VARS",
    "FieldSpec",
    "ManagedSettings",
    "ManagedSettingsError",
    "ManagedSettingsStore",
    "ManagedSettingsUnsupportedError",
    "PAGE_READONLY_FIELDS",
    "PUBLIC_DOMAINS",
    "PathSettings",
    "SCHEMA_VERSION",
    "ServingSettings",
    "SETTINGS_PATH_ENV",
    "applied_env_names",
    "assert_non_secret_payload",
    "default_repo_root",
    "default_settings_path",
    "flatten_settings",
    "store_from_environment",
]

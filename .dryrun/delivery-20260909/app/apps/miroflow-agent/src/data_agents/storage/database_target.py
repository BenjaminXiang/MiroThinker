"""Fail-closed target resolution for destructive database operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class _AlembicConfig(Protocol):
    def get_main_option(self, name: str, default: str | None = None) -> str | None: ...


class _WritableAlembicConfig(Protocol):
    def set_main_option(self, name: str, value: str) -> None: ...


class DatabaseTargetSafetyError(RuntimeError):
    """Raised before a destructive operation can use an unproven target."""


_ALLOWED_TARGET_KINDS = frozenset({"disposable", "isolated-candidate"})
_FORBIDDEN_DATABASES = frozenset(
    {
        "miroflow_real",
        "miroflow_recovery_candidate",
        "miroflow_recovery_candidate_verify",
        "postgres",
        "template0",
        "template1",
    }
)
_FORBIDDEN_PORTS = frozenset({15432})


def set_alembic_database_url(
    config: _WritableAlembicConfig,
    raw_url: str,
) -> None:
    """Set a raw URL while escaping ConfigParser interpolation exactly once."""
    config.set_main_option("sqlalchemy.url", raw_url.replace("%", "%%"))


@dataclass(frozen=True)
class DestructiveDatabaseTarget:
    """Explicit target plus the independently asserted database identity."""

    url: str
    expected_database: str
    target_kind: str

    @property
    def database_marker(self) -> str:
        return (
            "miroflow:destructive-target:v1:"
            f"{self.target_kind}:{self.expected_database}"
        )

    def verify_connected_database(self, connection: object) -> None:
        """Verify server identity after connect and before migration statements."""
        result = connection.exec_driver_sql("SELECT current_database()")  # type: ignore[attr-defined]
        actual_database = result.scalar_one()
        marker_result = connection.exec_driver_sql(  # type: ignore[attr-defined]
            "SELECT shobj_description(oid, 'pg_database') FROM pg_database "
            "WHERE datname = current_database()"
        )
        self.verify_database_identity(
            actual_database=actual_database,
            database_marker=marker_result.scalar_one(),
        )

    def verify_database_identity(
        self,
        *,
        actual_database: str | None,
        database_marker: str | None,
    ) -> None:
        """Verify identity values obtained through any database driver."""
        if actual_database != self.expected_database:
            raise DatabaseTargetSafetyError(
                "Connected database identity does not match the explicit expected "
                "database; refusing to run migrations."
            )
        if database_marker != self.database_marker:
            raise DatabaseTargetSafetyError(
                "Database-side destructive target marker does not match the explicit "
                "target identity; refusing to run migrations."
            )


def _option(config: _AlembicConfig, name: str) -> str | None:
    value = config.get_main_option(name)
    return value.strip() if value and value.strip() else None


def _select_explicit_value(
    *,
    config_value: str | None,
    environment_value: str | None,
    label: str,
    normalize: object | None = None,
) -> str | None:
    if config_value and environment_value:
        left = normalize(config_value) if callable(normalize) else config_value
        right = (
            normalize(environment_value) if callable(normalize) else environment_value
        )
        if left != right:
            raise DatabaseTargetSafetyError(
                f"Ambiguous explicit {label}: Alembic config and dedicated "
                "environment values conflict."
            )
    return config_value or environment_value


def _parsed_url(raw_url: str):
    try:
        return make_url(raw_url)
    except (ArgumentError, TypeError, ValueError) as exc:
        raise DatabaseTargetSafetyError(
            "The explicit Alembic database URL is invalid."
        ) from exc


def _normalized_url(raw_url: str) -> str:
    parsed = _parsed_url(raw_url)
    if parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


def resolve_destructive_database_target(
    config: _AlembicConfig,
    environment: Mapping[str, str],
) -> DestructiveDatabaseTarget:
    """Resolve one explicit, identity-checked Alembic target.

    Generic ``DATABASE_URL`` and ``DATABASE_URL_TEST`` values are intentionally
    ignored. Destructive callers must use Alembic config options or the dedicated
    ``ALEMBIC_*`` variables so inherited runtime configuration cannot become a
    migration target.
    """
    raw_url = _select_explicit_value(
        config_value=_option(config, "sqlalchemy.url"),
        environment_value=environment.get("ALEMBIC_DATABASE_URL"),
        label="database URL",
        normalize=_normalized_url,
    )
    expected_database = _select_explicit_value(
        config_value=_option(config, "miroflow.expected_database"),
        environment_value=environment.get("ALEMBIC_EXPECTED_DATABASE"),
        label="expected database identity",
    )
    target_kind = _select_explicit_value(
        config_value=_option(config, "miroflow.target_kind"),
        environment_value=environment.get("ALEMBIC_TARGET_KIND"),
        label="target kind",
        normalize=str.casefold,
    )

    if not raw_url or not expected_database or not target_kind:
        raise DatabaseTargetSafetyError(
            "An explicit destructive database target is required: provide the URL, "
            "expected database name, and target kind through Alembic config or "
            "dedicated ALEMBIC_* variables. Generic DATABASE_URL values are not "
            "accepted."
        )

    parsed = _parsed_url(raw_url)
    if parsed.get_backend_name() != "postgresql":
        raise DatabaseTargetSafetyError(
            "Only an explicit PostgreSQL target is supported for Alembic migrations."
        )
    actual_database = parsed.database
    if not actual_database or actual_database != expected_database:
        raise DatabaseTargetSafetyError(
            "The database URL identity does not match the explicit expected database."
        )

    normalized_kind = target_kind.casefold()
    if normalized_kind not in _ALLOWED_TARGET_KINDS:
        raise DatabaseTargetSafetyError(
            "The explicit target kind is non-disposable; expected 'disposable' or "
            "'isolated-candidate'."
        )

    database_key = actual_database.casefold()
    if database_key in _FORBIDDEN_DATABASES:
        raise DatabaseTargetSafetyError(
            "The explicit database identity is forbidden for destructive operations."
        )
    if parsed.port in _FORBIDDEN_PORTS:
        raise DatabaseTargetSafetyError(
            "The explicit database endpoint is forbidden for destructive operations."
        )

    return DestructiveDatabaseTarget(
        url=_normalized_url(raw_url),
        expected_database=expected_database,
        target_kind=normalized_kind,
    )

#!/opt/mirothinker/.venv/bin/python
"""幂等的采集库迁移器（容器交付件）。

做三件事，顺序固定，全部可重复执行：

1. **有界等待 PG**（默认 120 s，`--wait` 可调）：连不上就退出非零并打人话提示 ——
   容器入口把它当**降级**处理（服务照常启动，采集面 503），所以这里绝不允许无限阻塞。
2. **写库身份标记**（幂等）：`COMMENT ON DATABASE <db> IS
   'miroflow:destructive-target:v1:<kind>:<db>'`。迁移合同是 fail-closed 的：
   `alembic/env.py` → `resolve_destructive_database_target()` 只接受
   `ALEMBIC_DATABASE_URL` + `ALEMBIC_EXPECTED_DATABASE` + `ALEMBIC_TARGET_KIND`
   三个显式值，并且连接后要用 `shobj_description()` 读回标记比对
   (`src/data_agents/storage/database_target.py:59-80`)。**没有标记就没有迁移。**
3. **`alembic upgrade head`**（幂等，alembic 自己的版本表保证）。

DSN 解析优先级（与 README「PG」一节一致）：

- `DATABASE_URL` 显式给出则直接用（escape hatch）；
- 否则由 `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_HOST` /
  `POSTGRES_PORT` 组装（容器里这些来自 compose 的 `env_file: secrets/postgres.env`），
  口令按 URL 规则转义，因此口令里出现 `@ : / ? #` 也不会破坏 DSN。

**任何输出都不包含口令**（出错时只打印掩码后的 DSN）。

CLI：
    mirothinker-migrate                  # 等待 + 标记 + 迁移（入口默认调用）
    mirothinker-migrate --wait 300       # 加长等待上限
    mirothinker-migrate --status         # 只报告当前版本与表数（不迁移）
    mirothinker-migrate --print-dsn      # 只把组装好的 DSN 打到 stdout（入口用它取回）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.parse import quote

APP_DIR = "/opt/mirothinker/apps/miroflow-agent"
DEFAULT_DATABASE = "miroflow_collection_v1"
# 迁移合同只允许 disposable / isolated-candidate（database_target.py:25）。
TARGET_KIND = "disposable"

EXIT_OK = 0
EXIT_UNCONFIGURED = 3
EXIT_WAIT_TIMEOUT = 4
EXIT_MIGRATION_FAILED = 5


def _mask(dsn: str) -> str:
    """Return the DSN with the password replaced, safe for logs."""

    if "@" not in dsn:
        return dsn
    head, _, tail = dsn.partition("@")
    scheme, sep, credentials = head.partition("://")
    if not sep or ":" not in credentials:
        return dsn
    user, _, _password = credentials.partition(":")
    return f"{scheme}://{user}:***@{tail}"


def resolve_dsn() -> tuple[str, str]:
    """Return ``(dsn, source)``; empty DSN means "not configured"."""

    explicit = (os.environ.get("DATABASE_URL") or "").strip()
    if explicit:
        return explicit, "DATABASE_URL"
    user = (os.environ.get("POSTGRES_USER") or "").strip()
    password = os.environ.get("POSTGRES_PASSWORD") or ""
    if not user or not password:
        return "", "unset"
    database = (os.environ.get("POSTGRES_DB") or "").strip() or DEFAULT_DATABASE
    host = (os.environ.get("POSTGRES_HOST") or "").strip() or "db"
    port = (os.environ.get("POSTGRES_PORT") or "").strip() or "5432"
    dsn = (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(database, safe='')}"
    )
    return dsn, "POSTGRES_*"


def database_name(dsn: str) -> str:
    from sqlalchemy.engine import make_url

    return make_url(dsn).database or DEFAULT_DATABASE


def _connect(dsn: str):
    import psycopg

    return psycopg.connect(dsn, connect_timeout=5, autocommit=True)


def wait_for_pg(dsn: str, seconds: float) -> tuple[bool, float, str]:
    """Bounded wait; returns ``(ok, waited_seconds, last_error)``."""

    started = time.monotonic()
    deadline = started + max(0.0, seconds)
    last_error = ""
    while True:
        try:
            with _connect(dsn):
                return True, time.monotonic() - started, ""
        except Exception as exc:  # noqa: BLE001 - any connection problem means "not up yet"
            last_error = f"{type(exc).__name__}: {exc}"
        if time.monotonic() >= deadline:
            return False, time.monotonic() - started, last_error
        time.sleep(3.0)


def ensure_database_marker(dsn: str, database: str) -> str:
    """Idempotently stamp + read back the fail-closed identity marker.

    ``COMMENT ON DATABASE … IS …`` 是**工具语句**，PostgreSQL 不接受占位符参数
    （实测 `syntax error at or near "$1"`），所以标记必须由客户端安全地拼成字面量
    ——用 psycopg 的 ``sql.SQL/Identifier/Literal`` 组合，不手写引号。
    """

    from psycopg import sql

    marker = f"miroflow:destructive-target:v1:{TARGET_KIND}:{database}"
    statement = sql.SQL("COMMENT ON DATABASE {} IS {}").format(
        sql.Identifier(database), sql.Literal(marker)
    )
    with _connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(statement)
        cursor.execute(
            "SELECT shobj_description(oid, 'pg_database') FROM pg_database "
            "WHERE datname = current_database()"
        )
        row = cursor.fetchone()
    actual = row[0] if row else None
    if actual != marker:
        raise RuntimeError(f"database identity marker did not stick: {actual!r}")
    return marker


def _alembic_env(dsn: str, database: str) -> dict[str, str]:
    environ = dict(os.environ)
    environ["ALEMBIC_DATABASE_URL"] = dsn
    environ["ALEMBIC_EXPECTED_DATABASE"] = database
    environ["ALEMBIC_TARGET_KIND"] = TARGET_KIND
    return environ


def _alembic_config():
    sys.path.insert(0, APP_DIR)
    from alembic.config import Config

    os.chdir(APP_DIR)
    return Config("alembic.ini")


def current_revision(dsn: str, database: str) -> str:
    """Read the applied revision straight from ``alembic_version``.

    （`alembic.command.current()` 只往 stdout 打印、不返回值，用它取版本会永远拿到空串
    —— 实测踩过；直接查表既准确又不依赖 alembic 的输出行为。）
    """

    try:
        with _connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            row = cursor.fetchone()
    except Exception:  # noqa: BLE001 - 表不存在 = 还没迁移过
        return ""
    return row[0] if row else ""


def upgrade(dsn: str, database: str) -> str:
    from alembic import command

    os.environ.update(_alembic_env(dsn, database))
    config = _alembic_config()
    command.upgrade(config, "head")
    with _connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM alembic_version")
        row = cursor.fetchone()
    return row[0] if row else ""


def table_count(dsn: str) -> int:
    with _connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        row = cursor.fetchone()
    return int(row[0]) if row else 0


def revision_head() -> str:
    from alembic.script import ScriptDirectory

    config = _alembic_config()
    return ScriptDirectory.from_config(config).get_current_head() or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="idempotent collection-database migration")
    parser.add_argument("--wait", type=float, default=120.0, help="PG wait budget in seconds")
    parser.add_argument("--status", action="store_true", help="report only; never migrate")
    parser.add_argument("--print-dsn", action="store_true", help="print the resolved DSN and exit")
    args = parser.parse_args(argv)

    dsn, source = resolve_dsn()
    origin = (os.environ.get("MIROTHINKER_DSN_ORIGIN") or "").strip()
    if origin:
        source = origin
    if args.print_dsn:
        if not dsn:
            return EXIT_UNCONFIGURED
        print(dsn)
        return EXIT_OK
    if not dsn:
        print(
            "collection database is unconfigured: set DATABASE_URL, or POSTGRES_USER + "
            "POSTGRES_PASSWORD (+ POSTGRES_DB/POSTGRES_HOST/POSTGRES_PORT). "
            "Collection surfaces stay 503 and the navigation stays hidden.",
            file=sys.stderr,
        )
        return EXIT_UNCONFIGURED

    database = database_name(dsn)
    print(f"target: {_mask(dsn)} (source={source}, database={database})", flush=True)

    ok, waited, last_error = wait_for_pg(dsn, args.wait)
    if not ok:
        print(
            f"postgres did not answer within {args.wait:.0f}s "
            f"({last_error or 'no error detail'}) — check the `db` service and "
            f"secrets/postgres.env; the service will still boot without the collection line.",
            file=sys.stderr,
        )
        return EXIT_WAIT_TIMEOUT
    print(f"postgres reachable in {waited:.2f}s", flush=True)

    status_only = args.status
    try:
        marker = ensure_database_marker(dsn, database)
    except Exception as exc:  # noqa: BLE001
        print(f"could not stamp the database identity marker: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return EXIT_MIGRATION_FAILED
    print(f"identity marker ok ({marker})", flush=True)

    if status_only:
        revision = current_revision(dsn, database)
        print(json.dumps(
            {"status": "ok", "revision": revision, "head": revision_head(),
             "tables": table_count(dsn), "waited_seconds": round(waited, 3)},
            ensure_ascii=False, sort_keys=True,
        ))
        return EXIT_OK

    before = current_revision(dsn, database)
    try:
        revision = upgrade(dsn, database)
    except Exception as exc:  # noqa: BLE001
        print(f"alembic upgrade head failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_MIGRATION_FAILED
    print(json.dumps(
        {"status": "ok", "revision_before": before, "revision": revision,
         "head": revision_head(), "tables": table_count(dsn),
         "waited_seconds": round(waited, 3)},
        ensure_ascii=False, sort_keys=True,
    ))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

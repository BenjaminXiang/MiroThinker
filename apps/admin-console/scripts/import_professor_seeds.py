#!/usr/bin/env python3
"""Import the historical professor roster seeds into the console registry.

`apps/miroflow-agent/scripts/e2e_seeds/*.md` is the historical roster corpus; the console owns
the `professor_seed` registry. This script is the one bridge between them: it parses every `*.md`
with the professor pipeline's own `parse_roster_seed_markdown()` (no second parser), de-duplicates
by roster URL, skips URLs the registry already holds, and reports what each remaining URL resolves
to. Dry-run is the default because the target is a live database; `--apply` writes.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Callable, Literal, Protocol, Sequence
from urllib.parse import urlparse

import psycopg

from backend.storage.seeds import SeedCreate, create_seed, get_seed_by_url
from src.data_agents.professor.adapter_resolution import resolve_seed_adapter_name
from src.data_agents.professor.models import ProfessorRosterSeed
from src.data_agents.professor.parser import parse_roster_seed_markdown

ADMIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ADMIN_ROOT.parents[1]
DEFAULT_SEEDS_DIR = REPO_ROOT / "apps" / "miroflow-agent" / "scripts" / "e2e_seeds"

RunStatus = Literal["created", "would_create", "skipped_existing", "skipped_unresolved"]


class SeedImportError(RuntimeError):
    """A corpus entry cannot be turned into a registry row."""


@dataclass(frozen=True)
class ImportRow:
    """One distinct roster URL and what this run does with it."""

    payload: SeedCreate
    adapter_name: str | None
    status: RunStatus


@dataclass(frozen=True)
class ImportReport:
    parsed_seed_count: int
    duplicate_seed_count: int
    rows: tuple[ImportRow, ...]
    apply: bool


class SeedRegistry(Protocol):
    """The two registry operations the importer needs (see `backend.storage.seeds`)."""

    def get_by_url(self, seed_url: str) -> object | None: ...

    def create(self, payload: SeedCreate) -> object: ...


class PostgresSeedRegistry:
    """`backend.storage.seeds` bound to one psycopg connection."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def get_by_url(self, seed_url: str) -> object | None:
        return get_seed_by_url(self._conn, seed_url)

    def create(self, payload: SeedCreate) -> object:
        return create_seed(self._conn, payload)


def load_roster_seeds(seeds_dir: Path) -> tuple[list[ProfessorRosterSeed], int]:
    """Parse every ``*.md`` under ``seeds_dir``, de-duplicated by roster URL.

    Returns the distinct seeds in file order plus the number of folded duplicates.
    """
    seeds: list[ProfessorRosterSeed] = []
    seen_urls: set[str] = set()
    duplicates = 0
    for path in sorted(seeds_dir.glob("*.md")):
        for seed in parse_roster_seed_markdown(path.read_text(encoding="utf-8")):
            if seed.roster_url in seen_urls:
                duplicates += 1
                continue
            seen_urls.add(seed.roster_url)
            seeds.append(seed)
    return seeds, duplicates


def _seed_payload(seed: ProfessorRosterSeed) -> SeedCreate:
    institution = (seed.institution or "").strip()
    if not institution:
        raise SeedImportError(f"roster entry without an institution: {seed.roster_url}")
    return SeedCreate(
        school=institution, department=seed.department, seed_url=seed.roster_url
    )


def run_import(
    *,
    seeds_dir: Path,
    registry: SeedRegistry | None,
    apply: bool,
    include_unresolved: bool,
    adapter_resolver: Callable[
        [ProfessorRosterSeed], str | None
    ] = resolve_seed_adapter_name,
) -> ImportReport:
    """Plan the import and, with ``apply``, create the missing rows through ``registry``."""
    seeds, duplicates = load_roster_seeds(seeds_dir)
    rows: list[ImportRow] = []
    for seed in seeds:
        payload = _seed_payload(seed)
        adapter_name = adapter_resolver(seed)
        registered = (
            registry is not None
            and registry.get_by_url(str(payload.seed_url)) is not None
        )
        if registered:
            status: RunStatus = "skipped_existing"
        elif adapter_name is None and not include_unresolved:
            status = "skipped_unresolved"
        elif apply and registry is not None:
            registry.create(payload)
            status = "created"
        else:
            status = "would_create"
        rows.append(
            ImportRow(payload=payload, adapter_name=adapter_name, status=status)
        )
    return ImportReport(
        parsed_seed_count=len(seeds) + duplicates,
        duplicate_seed_count=duplicates,
        rows=tuple(rows),
        apply=apply,
    )


def render_report(
    report: ImportReport, *, seeds_dir: Path, registry_configured: bool
) -> str:
    counts = Counter(row.status for row in report.rows)
    registry_state = (
        "database (existing rows checked)"
        if registry_configured
        else "not configured (existing rows not checked)"
    )
    lines = [
        f"seeds dir: {seeds_dir}",
        f"mode: {'apply' if report.apply else 'dry-run'} | registry: {registry_state}",
        "",
        f"{'status':<18} {'adapter':<26} school / department  seed_url",
        "-" * 88,
    ]
    for row in report.rows:
        lines.append(
            f"{row.status:<18} {row.adapter_name or '-':<26} "
            f"{row.payload.school} / {row.payload.department or '-'}  {row.payload.seed_url}"
        )
    unresolved = [row for row in report.rows if row.adapter_name is None]
    lines += [
        "",
        (
            f"parsed entries: {report.parsed_seed_count} "
            f"({report.duplicate_seed_count} duplicate URL(s) folded)"
        ),
        f"distinct urls: {len(report.rows)}",
        (
            f"created: {counts['created']} | would_create: {counts['would_create']} | "
            f"skipped_existing: {counts['skipped_existing']} | "
            f"skipped_unresolved: {counts['skipped_unresolved']}"
        ),
    ]
    if unresolved:
        lines.append("unresolved urls (no registered adapter):")
        lines.extend(f"  - {row.payload.seed_url}" for row in unresolved)
        if counts["skipped_unresolved"]:
            lines.append(
                "pass --include-unresolved to register them anyway; the crawl will then mark "
                "the seed adapter_missing"
            )
    if not report.apply:
        lines.append(
            "dry-run: nothing written (pass --apply to create the missing rows)"
        )
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--seeds-dir",
        default=str(DEFAULT_SEEDS_DIR),
        help="directory of roster markdown files (default: the historical corpus)",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("DATABASE_URL"),
        help="Postgres DSN of the console database (default: $DATABASE_URL)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the missing rows (default: dry-run)",
    )
    parser.add_argument(
        "--include-unresolved",
        action="store_true",
        help="register URLs no adapter serves instead of only reporting them",
    )
    return parser.parse_args(argv)


def _psycopg_dsn(dsn: str) -> str:
    """Environment files sometimes carry the SQLAlchemy spelling of the same DSN."""
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def _redact_dsn(text: str, dsn: str | None) -> str:
    """Never let a driver message echo the credential-bearing DSN."""
    if not dsn:
        return text
    redacted = text.replace(dsn, "***")
    password = urlparse(dsn).password
    if password:
        redacted = redacted.replace(password, "***")
    return redacted


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    seeds_dir = Path(args.seeds_dir).resolve()
    if not seeds_dir.is_dir():
        print(f"seeds directory not found: {seeds_dir}", file=sys.stderr)
        return 2
    dsn = (args.dsn or "").strip() or None
    if args.apply and dsn is None:
        print(
            "--apply needs a database: set DATABASE_URL or pass --dsn", file=sys.stderr
        )
        return 2

    conn: Any = None
    try:
        registry: SeedRegistry | None = None
        if dsn is not None:
            conn = psycopg.connect(_psycopg_dsn(dsn))
            registry = PostgresSeedRegistry(conn)
        report = run_import(
            seeds_dir=seeds_dir,
            registry=registry,
            apply=args.apply,
            include_unresolved=args.include_unresolved,
        )
    except SeedImportError as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 2
    except psycopg.Error as exc:
        print(f"database error: {_redact_dsn(str(exc), dsn)}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()

    print(
        render_report(report, seeds_dir=seeds_dir, registry_configured=dsn is not None)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.paper.exact_backfill import load_exact_backfill_papers
from src.data_agents.paper.release import build_paper_release
from src.data_agents.professor.cross_domain import CompanyLink
from src.data_agents.professor.cross_domain_linker import find_company_by_name, write_bidirectional_link
from src.data_agents.professor.link_backfill import apply_professor_company_role_backfill
from src.data_agents.contracts import ReleasedObject
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

TARGET_DOMAINS = {"professor", "paper", "professor_paper_link"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_target_db() -> Path:
    return _repo_root() / 'logs' / 'data_agents' / 'released_objects.db'


def _default_professor_company_backfill_paths() -> list[Path]:
    return [_repo_root() / 'docs' / 'source_backfills' / 'professor_company_roles.jsonl']


def _default_paper_exact_backfill_paths() -> list[Path]:
    return [_repo_root() / 'docs' / 'source_backfills' / 'paper_exact_identifier_backfills.jsonl']


def _sqlite_sidecar_paths(path: Path) -> tuple[Path, Path]:
    return (path.with_name(path.name + '-wal'), path.with_name(path.name + '-shm'))


def _checkpoint_and_cleanup_sqlite_sidecars(path: Path) -> None:
    if not path.exists():
        return
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    _cleanup_sqlite_sidecars(path)


def _cleanup_sqlite_sidecars(path: Path) -> None:
    for sidecar in _sqlite_sidecar_paths(path):
        if sidecar.exists():
            sidecar.unlink()


def _list_domain_objects(path: Path, domain: str) -> list[ReleasedObject]:
    if not path.exists():
        return []
    return SqliteReleasedObjectStore(path).list_domain_objects(domain)


def _load_preserved_base_objects(base_db_path: Path) -> list[ReleasedObject]:
    if not base_db_path.exists():
        return []
    store = SqliteReleasedObjectStore(base_db_path)
    preserved: list[ReleasedObject] = []
    for domain in store.count_by_domain():
        if domain in TARGET_DOMAINS:
            continue
        preserved.extend(store.list_domain_objects(domain))
    return preserved


def _load_batch_domain_objects(batch_db_paths: Iterable[Path]) -> dict[str, list[ReleasedObject]]:
    objects_by_domain = {domain: [] for domain in TARGET_DOMAINS}
    for path in batch_db_paths:
        if not path.exists():
            raise FileNotFoundError(f'batch db not found: {path}')
        store = SqliteReleasedObjectStore(path)
        for domain in TARGET_DOMAINS:
            objects_by_domain[domain].extend(store.list_domain_objects(domain))
    return objects_by_domain


def _apply_professor_company_backfills(
    professor_objects: list[ReleasedObject],
    *,
    backfill_paths: Iterable[Path],
    now: datetime,
) -> list[ReleasedObject]:
    return apply_professor_company_role_backfill(
        professor_objects,
        paths=backfill_paths,
        now=now,
    )


def _build_supplemental_paper_objects(
    *,
    backfill_paths: Iterable[Path],
    existing_paper_ids: set[str],
    now: datetime,
) -> list[ReleasedObject]:
    discovered = load_exact_backfill_papers(backfill_paths)
    if not discovered:
        return []
    release = build_paper_release(papers=discovered, now=now)
    return [obj for obj in release.released_objects if obj.id not in existing_paper_ids]


def _write_bidirectional_company_links(store: SqliteReleasedObjectStore) -> None:
    for professor in store.list_domain_objects('professor'):
        for role in professor.core_facts.get('company_roles', []):
            if not isinstance(role, dict):
                continue
            company_name = str(role.get('company_name') or '').strip()
            if not company_name:
                continue
            company_obj = find_company_by_name(store, company_name)
            link = CompanyLink(
                company_id=company_obj.id if company_obj is not None else None,
                company_name=company_name,
                role=str(role.get('role') or '').strip(),
                evidence_url=str(role.get('evidence_url') or ''),
                source=str(role.get('source') or 'serving_backfill'),
            )
            write_bidirectional_link(store, professor.id, link)


def rebuild_shared_store_from_batch_dbs(
    *,
    target_path: Path,
    base_db_path: Path,
    batch_db_paths: list[Path],
    professor_company_backfill_paths: list[Path],
    paper_exact_backfill_paths: list[Path],
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    preserved_objects = _load_preserved_base_objects(base_db_path)
    batch_objects = _load_batch_domain_objects(batch_db_paths)
    batch_objects['professor'] = _apply_professor_company_backfills(
        batch_objects['professor'],
        backfill_paths=professor_company_backfill_paths,
        now=now,
    )
    existing_paper_ids = {obj.id for obj in batch_objects['paper']}
    batch_objects['paper'].extend(
        _build_supplemental_paper_objects(
            backfill_paths=paper_exact_backfill_paths,
            existing_paper_ids=existing_paper_ids,
            now=now,
        )
    )

    temp_path = target_path.with_suffix(target_path.suffix + '.tmp')
    if temp_path.exists():
        temp_path.unlink()
    _cleanup_sqlite_sidecars(temp_path)
    try:
        temp_store = SqliteReleasedObjectStore(temp_path)
        if preserved_objects:
            temp_store.upsert_released_objects(preserved_objects)
        for domain in ('professor', 'paper', 'professor_paper_link'):
            objects = batch_objects.get(domain) or []
            if not objects:
                continue
            temp_store.upsert_released_objects(objects)
        _write_bidirectional_company_links(temp_store)
        _checkpoint_and_cleanup_sqlite_sidecars(temp_path)
        temp_path.replace(target_path)
        _cleanup_sqlite_sidecars(target_path)
        return SqliteReleasedObjectStore(target_path).count_by_domain()
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        _cleanup_sqlite_sidecars(temp_path)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description='Rebuild shared released_objects.db from clean professor batch SQLite outputs.')
    parser.add_argument('--target-db', type=Path, default=_default_target_db())
    parser.add_argument('--base-db', type=Path, default=None, help='Base shared DB whose non-professor domains are preserved. Defaults to --target-db.')
    parser.add_argument('--input-db', type=Path, action='append', required=True, help='Batch-level released_objects.db from clean professor full-harvest runs. Repeatable.')
    parser.add_argument('--professor-company-backfill', type=Path, action='append', default=None)
    parser.add_argument('--paper-exact-backfill', type=Path, action='append', default=None)
    args = parser.parse_args()

    counts = rebuild_shared_store_from_batch_dbs(
        target_path=args.target_db,
        base_db_path=args.base_db or args.target_db,
        batch_db_paths=args.input_db,
        professor_company_backfill_paths=(args.professor_company_backfill if args.professor_company_backfill is not None else _default_professor_company_backfill_paths()),
        paper_exact_backfill_paths=(args.paper_exact_backfill if args.paper_exact_backfill is not None else _default_paper_exact_backfill_paths()),
    )
    print(args.target_db)
    print(counts)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

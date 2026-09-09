"""Consolidate all 4 domain data into a unified SQLite released_objects.db.

Sources:
  - Professor: logs/data_agents/professor/search_service/released_objects.sqlite3
  - Company:   logs/debug/company_release_e2e_*/released_objects.jsonl (latest)
  - Paper:     logs/debug/paper_release_e2e_*/released_objects.jsonl (latest)
  - Patent:    logs/debug/patent_release_e2e_*/released_objects.jsonl (latest)

Target:
  logs/data_agents/released_objects.db
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Ensure src is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "apps" / "miroflow-agent"))

from src.data_agents.company.knowledge_backfill import apply_company_knowledge_backfill
from src.data_agents.contracts import ReleasedObject
from src.data_agents.professor.link_backfill import apply_professor_company_role_backfill
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


def _find_latest_jsonl(base_dir: Path, prefix: str) -> Path | None:
    pattern = f"{prefix}*/released_objects.jsonl"
    matches = sorted(base_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _default_professor_company_backfill_paths(repo_root: Path) -> list[Path]:
    return [repo_root / "docs" / "source_backfills" / "professor_company_roles.jsonl"]


def _default_company_knowledge_backfill_paths(repo_root: Path) -> list[Path]:
    return [repo_root / "docs" / "source_backfills" / "company_knowledge_fields.jsonl"]


def _load_jsonl(path: Path) -> list[ReleasedObject]:
    objects: list[ReleasedObject] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            objects.append(ReleasedObject.model_validate_json(line))
    return objects


def _sqlite_sidecar_paths(path: Path) -> tuple[Path, Path]:
    return (path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm"))


def _checkpoint_and_cleanup_sqlite_sidecars(path: Path) -> None:
    if not path.exists():
        return
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for sidecar in _sqlite_sidecar_paths(path):
        if sidecar.exists():
            sidecar.unlink()


def _cleanup_sqlite_sidecars(path: Path) -> None:
    for sidecar in _sqlite_sidecar_paths(path):
        if sidecar.exists():
            sidecar.unlink()


def load_source_objects(logs_dir: Path) -> tuple[dict[str, list[ReleasedObject]], dict[str, str]]:
    source_info: dict[str, str] = {}
    objects_by_domain: dict[str, list[ReleasedObject]] = {}

    prof_db = logs_dir / "data_agents" / "professor" / "search_service" / "released_objects.sqlite3"
    if prof_db.exists():
        prof_store = SqliteReleasedObjectStore(prof_db)
        prof_objects = prof_store.list_domain_objects("professor")
        prof_objects = apply_professor_company_role_backfill(
            prof_objects,
            paths=_default_professor_company_backfill_paths(_REPO_ROOT),
        )
        objects_by_domain["professor"] = prof_objects
        source_info["professor"] = str(prof_db)

    debug_dir = logs_dir / "debug"
    company_jsonl = _find_latest_jsonl(debug_dir, "company_release_e2e_")
    if company_jsonl:
        company_objects = _load_jsonl(company_jsonl)
        company_objects = apply_company_knowledge_backfill(
            company_objects,
            paths=_default_company_knowledge_backfill_paths(_REPO_ROOT),
        )
        objects_by_domain["company"] = company_objects
        source_info["company"] = str(company_jsonl)

    paper_jsonl = _find_latest_jsonl(debug_dir, "paper_release_e2e_")
    if paper_jsonl:
        objects_by_domain["paper"] = _load_jsonl(paper_jsonl)
        source_info["paper"] = str(paper_jsonl)

    patent_jsonl = _find_latest_jsonl(debug_dir, "patent_release_e2e_")
    if patent_jsonl:
        objects_by_domain["patent"] = _load_jsonl(patent_jsonl)
        source_info["patent"] = str(patent_jsonl)

    return objects_by_domain, source_info


def consolidate_from_logs(logs_dir: Path, target_path: Path) -> tuple[dict[str, int], dict[str, str]]:
    objects_by_domain, source_info = load_source_objects(logs_dir)
    temp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    if temp_path.exists():
        temp_path.unlink()
    _cleanup_sqlite_sidecars(temp_path)
    try:
        temp_store = SqliteReleasedObjectStore(temp_path)
        for domain in ("professor", "company", "paper", "patent"):
            objects = objects_by_domain.get(domain)
            if not objects:
                continue
            temp_store.upsert_released_objects(objects)
        _checkpoint_and_cleanup_sqlite_sidecars(temp_path)
        temp_path.replace(target_path)
        _cleanup_sqlite_sidecars(target_path)
        return SqliteReleasedObjectStore(target_path).count_by_domain(), source_info
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        _cleanup_sqlite_sidecars(temp_path)
        raise


def main() -> None:
    logs_dir = _REPO_ROOT / "logs"
    target_path = logs_dir / "data_agents" / "released_objects.db"

    print(f"Target DB: {target_path}")
    counts, source_info = consolidate_from_logs(logs_dir, target_path)

    if "professor" in counts:
        print(f"  Professor: {counts['professor']} records")
    else:
        print(f"  Professor: SKIPPED (not found: {logs_dir / 'data_agents' / 'professor' / 'search_service' / 'released_objects.sqlite3'})")

    if "company" in counts and "company" in source_info:
        print(f"  Company:   {counts['company']} records (from {Path(source_info['company']).name})")
    else:
        print("  Company:   SKIPPED (no jsonl found)")

    if "paper" in counts and "paper" in source_info:
        print(f"  Paper:     {counts['paper']} records (from {Path(source_info['paper']).name})")
    else:
        print("  Paper:     SKIPPED (no jsonl found)")

    if "patent" in counts and "patent" in source_info:
        print(f"  Patent:    {counts['patent']} records (from {Path(source_info['patent']).name})")
    else:
        print("  Patent:    SKIPPED (no jsonl found)")

    total = sum(counts.values())
    print(f"\nConsolidated DB: {total} total records")
    for domain, count in sorted(counts.items()):
        print(f"  {domain}: {count}")


if __name__ == "__main__":
    main()

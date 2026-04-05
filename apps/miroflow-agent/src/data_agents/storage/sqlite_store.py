from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from src.data_agents.contracts import ReleasedObject

_SORTABLE_COLUMNS = ("id", "display_name")


class SqliteReleasedObjectStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def upsert_released_objects(self, objects: list[ReleasedObject]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO released_objects (
                  id,
                  object_type,
                  display_name,
                  payload_json
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  object_type = excluded.object_type,
                  display_name = excluded.display_name,
                  payload_json = excluded.payload_json
                """,
                [
                    (
                        item.id,
                        item.object_type,
                        item.display_name,
                        item.model_dump_json(),
                    )
                    for item in objects
                ],
            )

    def get_object(self, domain: str, object_id: str) -> ReleasedObject | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM released_objects
                WHERE id = ? AND object_type = ?
                """,
                (object_id, domain),
            ).fetchone()
        if row is None:
            return None
        return ReleasedObject.model_validate_json(row[0])

    def search_domain(
        self,
        domain: str,
        query: str,
        filters: dict[str, Any] | None = None,
        mode: str = "exact",
        limit: int = 10,
    ) -> list[ReleasedObject]:
        del mode

        query_text = _normalize_text(query)
        loaded_objects = self._load_domain_objects(domain)
        matched: list[tuple[float, ReleasedObject]] = []
        for item in loaded_objects:
            if not _matches_filters(item, filters):
                continue
            score = _score_exact_match(item, query_text)
            if score <= 0:
                continue
            matched.append((score, item))
        matched.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [item for _, item in matched[:limit]]

    def get_related_objects(
        self,
        *,
        source_domain: str,
        source_id: str,
        target_domain: str,
        relation_type: str,
        limit: int = 20,
    ) -> list[ReleasedObject]:
        target_objects = self._load_domain_objects(target_domain)
        related: list[ReleasedObject] = []
        for item in target_objects:
            if _is_related(
                item,
                source_domain=source_domain,
                source_id=source_id,
                relation_type=relation_type,
            ):
                related.append(item)
        return related[:limit]

    def list_domain_objects(self, domain: str) -> list[ReleasedObject]:
        return self._load_domain_objects(domain)

    def list_domain_paginated(
        self,
        domain: str,
        *,
        query: str = "",
        offset: int = 0,
        limit: int = 20,
        sort_by: str = "display_name",
        sort_order: Literal["asc", "desc"] = "asc",
    ) -> tuple[list[ReleasedObject], int]:
        if sort_by not in _SORTABLE_COLUMNS:
            raise ValueError(
                f"sort_by must be one of {_SORTABLE_COLUMNS}, got {sort_by!r}"
            )
        order = "ASC" if sort_order == "asc" else "DESC"
        with sqlite3.connect(self.db_path) as conn:
            if query:
                escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                where = "WHERE object_type = ? AND display_name LIKE ? ESCAPE '\\'"
                params: tuple[Any, ...] = (domain, f"%{escaped}%")
            else:
                where = "WHERE object_type = ?"
                params = (domain,)

            total = conn.execute(
                f"SELECT COUNT(*) FROM released_objects {where}", params
            ).fetchone()[0]

            rows = conn.execute(
                f"SELECT payload_json FROM released_objects {where} "
                f"ORDER BY {sort_by} {order} LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()

        items = [ReleasedObject.model_validate_json(row[0]) for row in rows]
        return items, total

    def count_by_domain(self) -> dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT object_type, COUNT(*) FROM released_objects GROUP BY object_type"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def quality_breakdown(self, domain: str) -> dict[str, int]:
        objects = self._load_domain_objects(domain)
        counts = Counter(obj.quality_status for obj in objects)
        return dict(counts)

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS released_objects (
                  id TEXT PRIMARY KEY,
                  object_type TEXT NOT NULL,
                  display_name TEXT NOT NULL,
                  payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_released_objects_object_type
                ON released_objects(object_type)
                """
            )

    def _load_domain_objects(self, domain: str) -> list[ReleasedObject]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM released_objects
                WHERE object_type = ?
                ORDER BY id ASC
                """,
                (domain,),
            ).fetchall()
        return [ReleasedObject.model_validate_json(row[0]) for row in rows]


def _matches_filters(
    item: ReleasedObject,
    filters: dict[str, Any] | None,
) -> bool:
    if not filters:
        return True
    for key, expected in filters.items():
        actual = item.core_facts.get(key)
        if isinstance(actual, list):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True


def _score_exact_match(item: ReleasedObject, query_text: str) -> float:
    haystack = _normalize_text(
        " ".join(
            [
                item.display_name,
                json.dumps(item.core_facts, ensure_ascii=False),
                json.dumps(item.summary_fields, ensure_ascii=False),
            ]
        )
    )
    if not query_text:
        return 1.0
    if item.display_name and item.display_name in query_text:
        return 20.0
    if query_text in haystack:
        return 10.0
    overlap = sum(1 for char in set(query_text) if char in haystack)
    return float(overlap)


def _is_related(
    item: ReleasedObject,
    *,
    source_domain: str,
    source_id: str,
    relation_type: str,
) -> bool:
    if relation_type == "professor_papers":
        return (
            source_domain == "professor"
            and item.object_type == "paper"
            and source_id in (item.core_facts.get("professor_ids") or [])
        )
    if relation_type == "company_patents":
        return (
            source_domain == "company"
            and item.object_type == "patent"
            and source_id in (item.core_facts.get("company_ids") or [])
        )
    if relation_type == "professor_patents":
        return (
            source_domain == "professor"
            and item.object_type == "patent"
            and source_id in (item.core_facts.get("professor_ids") or [])
        )
    return False


def _normalize_text(value: str) -> str:
    return "".join(value.lower().split())

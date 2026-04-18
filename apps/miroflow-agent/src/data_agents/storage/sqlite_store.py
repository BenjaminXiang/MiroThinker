from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from src.data_agents.contracts import ReleasedObject, normalize_quality_status

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
        linked_ids = self._get_related_target_ids(
            source_domain=source_domain,
            source_id=source_id,
            target_domain=target_domain,
            relation_type=relation_type,
        )
        if linked_ids:
            target_by_id = {item.id: item for item in target_objects}
            related = [target_by_id[item_id] for item_id in linked_ids if item_id in target_by_id]
            return related[:limit]

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
        counts = Counter(normalize_quality_status(obj.quality_status) for obj in objects)
        return dict(counts)

    def update_object(self, obj: ReleasedObject) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE released_objects
                SET object_type = ?, display_name = ?, payload_json = ?
                WHERE id = ?
                """,
                (obj.object_type, obj.display_name, obj.model_dump_json(), obj.id),
            )
        return cursor.rowcount > 0

    def delete_objects(self, ids: list[str]) -> int:
        if not ids:
            return 0
        with sqlite3.connect(self.db_path) as conn:
            placeholders = ",".join("?" for _ in ids)
            cursor = conn.execute(
                f"DELETE FROM released_objects WHERE id IN ({placeholders})",
                ids,
            )
        return cursor.rowcount

    def delete_domain_objects(self, domain: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM released_objects WHERE object_type = ?",
                (domain,),
            )
        return cursor.rowcount

    def get_domain_last_updated(self, domain: str) -> datetime | None:
        objects = self._load_domain_objects(domain)
        if not objects:
            return None
        return max(obj.last_updated for obj in objects)

    def list_domain_filtered(
        self,
        domain: str,
        *,
        query: str = "",
        filters: dict[str, Any] | None = None,
        offset: int = 0,
        limit: int = 20,
        sort_by: str = "display_name",
        sort_order: Literal["asc", "desc"] = "asc",
    ) -> tuple[list[ReleasedObject], int]:
        if not filters and not query:
            return self.list_domain_paginated(
                domain,
                offset=offset,
                limit=limit,
                sort_by=sort_by,
                sort_order=sort_order,
            )

        if not filters:
            return self.list_domain_paginated(
                domain,
                query=query,
                offset=offset,
                limit=limit,
                sort_by=sort_by,
                sort_order=sort_order,
            )

        all_objects = self._load_domain_objects(domain)

        matched: list[ReleasedObject] = []
        query_text = _normalize_text(query) if query else ""
        for item in all_objects:
            if not _matches_filters(item, filters):
                continue
            if query_text:
                score = _score_exact_match(item, query_text)
                if score <= 0:
                    continue
            matched.append(item)

        reverse = sort_order == "desc"
        if sort_by == "id":
            matched.sort(key=lambda o: o.id, reverse=reverse)
        else:
            matched.sort(key=lambda o: o.display_name, reverse=reverse)

        total = len(matched)
        page = matched[offset : offset + limit]
        return page, total

    def export_domain_objects(
        self,
        domain: str,
        *,
        query: str = "",
        filters: dict[str, Any] | None = None,
    ) -> list[ReleasedObject]:
        if not query and not filters:
            return self._load_domain_objects(domain)

        all_objects = self._load_domain_objects(domain)
        query_text = _normalize_text(query) if query else ""
        result: list[ReleasedObject] = []
        for item in all_objects:
            if not _matches_filters(item, filters):
                continue
            if query_text:
                score = _score_exact_match(item, query_text)
                if score <= 0:
                    continue
            result.append(item)
        return result

    def get_filter_options(self, domain: str, field: str) -> list[str]:
        _TOP_LEVEL = {"quality_status", "display_name", "id", "object_type"}
        objects = self._load_domain_objects(domain)
        values: set[str] = set()
        for obj in objects:
            if field in _TOP_LEVEL:
                val = getattr(obj, field, None)
            else:
                val = obj.core_facts.get(field)
            if isinstance(val, str) and val:
                values.add(val)
            elif isinstance(val, (int, float)):
                values.add(str(val))
            elif isinstance(val, list):
                for v in val:
                    if isinstance(v, str) and v:
                        values.add(v)
                    elif isinstance(v, (int, float)):
                        values.add(str(v))
        return sorted(values)

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

    def _get_related_target_ids(
        self,
        *,
        source_domain: str,
        source_id: str,
        target_domain: str,
        relation_type: str,
    ) -> list[str]:
        relation_objects = self._load_domain_objects("professor_paper_link")
        if relation_type == "professor_papers" and source_domain == "professor" and target_domain == "paper":
            return [
                str(item.core_facts.get("paper_id"))
                for item in relation_objects
                if item.core_facts.get("professor_id") == source_id
                and item.core_facts.get("link_status") == "verified"
                and item.core_facts.get("paper_id")
            ]
        if relation_type == "paper_professors" and source_domain == "paper" and target_domain == "professor":
            return [
                str(item.core_facts.get("professor_id"))
                for item in relation_objects
                if item.core_facts.get("paper_id") == source_id
                and item.core_facts.get("link_status") == "verified"
                and item.core_facts.get("professor_id")
            ]
        return []


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
    # Top-level fields that can be filtered directly
    _TOP_LEVEL = {"quality_status", "display_name", "id", "object_type"}
    for key, expected in filters.items():
        if key in _TOP_LEVEL:
            actual = getattr(item, key, None)
        else:
            actual = item.core_facts.get(key)
        if isinstance(actual, list):
            if expected not in actual and str(expected) not in [str(a) for a in actual]:
                return False
        elif actual != expected and str(actual) != str(expected):
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
    normalized_display_name = _normalize_text(item.display_name)
    if not query_text:
        return 1.0
    if normalized_display_name and normalized_display_name in query_text:
        return 30.0
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

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data_agents.contracts import Evidence, ReleasedObject
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


TIMESTAMP = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _evidence() -> Evidence:
    return Evidence(
        source_type="official_site",
        source_url="https://www.sustech.edu.cn",
        fetched_at=TIMESTAMP,
        snippet="Test evidence.",
    )


def _released_object(
    id: str,
    object_type: str = "professor",
    display_name: str = "Test",
    quality_status: str = "ready",
) -> ReleasedObject:
    return ReleasedObject(
        id=id,
        object_type=object_type,
        display_name=display_name,
        core_facts={"name": display_name},
        summary_fields={"profile_summary": "A test record."},
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
        quality_status=quality_status,
    )


@pytest.fixture()
def store(tmp_path) -> SqliteReleasedObjectStore:
    return SqliteReleasedObjectStore(tmp_path / "test.db")


@pytest.fixture()
def populated_store(store: SqliteReleasedObjectStore) -> SqliteReleasedObjectStore:
    """Store pre-loaded with 5 professors and 2 companies."""
    professors = [
        _released_object("PROF-1", "professor", "靳玉乐", "ready"),
        _released_object("PROF-2", "professor", "李明", "ready"),
        _released_object("PROF-3", "professor", "王芳", "needs_review"),
        _released_object("PROF-4", "professor", "张伟", "low_confidence"),
        _released_object("PROF-5", "professor", "陈静", "ready"),
    ]
    companies = [
        _released_object("COMP-1", "company", "深圳科创有限公司", "ready"),
        _released_object("COMP-2", "company", "南方智能科技", "needs_review"),
    ]
    store.upsert_released_objects(professors + companies)
    return store


# ---------- list_domain_paginated ----------


class TestListDomainPaginated:
    def test_returns_first_page_sorted_by_display_name_asc(
        self, populated_store: SqliteReleasedObjectStore
    ):
        items, total = populated_store.list_domain_paginated("professor")
        assert total == 5
        assert len(items) <= 20
        names = [item.display_name for item in items]
        assert names == sorted(names)

    def test_filters_by_display_name_query(
        self, populated_store: SqliteReleasedObjectStore
    ):
        items, total = populated_store.list_domain_paginated(
            "professor", query="靳"
        )
        assert total == 1
        assert items[0].display_name == "靳玉乐"

    def test_pagination_offset_and_limit(
        self, populated_store: SqliteReleasedObjectStore
    ):
        items_page1, total1 = populated_store.list_domain_paginated(
            "professor", offset=0, limit=2
        )
        items_page2, total2 = populated_store.list_domain_paginated(
            "professor", offset=2, limit=2
        )
        assert total1 == 5
        assert total2 == 5
        assert len(items_page1) == 2
        assert len(items_page2) == 2
        ids_page1 = {item.id for item in items_page1}
        ids_page2 = {item.id for item in items_page2}
        assert ids_page1.isdisjoint(ids_page2)

    def test_empty_db_returns_empty(self, store: SqliteReleasedObjectStore):
        items, total = store.list_domain_paginated("professor")
        assert items == []
        assert total == 0

    def test_sort_by_id_desc(self, populated_store: SqliteReleasedObjectStore):
        items, _ = populated_store.list_domain_paginated(
            "professor", sort_by="id", sort_order="desc"
        )
        ids = [item.id for item in items]
        assert ids == sorted(ids, reverse=True)

    def test_invalid_sort_by_raises_value_error(
        self, populated_store: SqliteReleasedObjectStore
    ):
        with pytest.raises(ValueError):
            populated_store.list_domain_paginated(
                "professor", sort_by="payload_json"
            )

    def test_like_metacharacters_are_escaped(
        self, populated_store: SqliteReleasedObjectStore
    ):
        items, total = populated_store.list_domain_paginated(
            "professor", query="%"
        )
        assert total == 0
        assert items == []

        items2, total2 = populated_store.list_domain_paginated(
            "professor", query="_"
        )
        assert total2 == 0
        assert items2 == []


# ---------- count_by_domain ----------


class TestCountByDomain:
    def test_counts_multiple_domains(
        self, populated_store: SqliteReleasedObjectStore
    ):
        counts = populated_store.count_by_domain()
        assert counts == {"professor": 5, "company": 2}

    def test_empty_db_returns_empty_dict(
        self, store: SqliteReleasedObjectStore
    ):
        counts = store.count_by_domain()
        assert counts == {}


# ---------- quality_breakdown ----------


class TestQualityBreakdown:
    def test_mixed_statuses(self, populated_store: SqliteReleasedObjectStore):
        breakdown = populated_store.quality_breakdown("professor")
        assert breakdown == {"ready": 3, "needs_review": 1, "low_confidence": 1}

    def test_nonexistent_domain_returns_empty(
        self, populated_store: SqliteReleasedObjectStore
    ):
        breakdown = populated_store.quality_breakdown("nonexistent")
        assert breakdown == {}

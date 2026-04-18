from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data_agents.contracts import Evidence, ReleasedObject
from src.data_agents.storage.sqlite_store import (
    SqliteReleasedObjectStore,
    _normalize_text,
    _score_exact_match,
)


TIMESTAMP = datetime(2026, 4, 1, tzinfo=timezone.utc)
TIMESTAMP_LATER = datetime(2026, 4, 5, tzinfo=timezone.utc)


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
    last_updated: datetime | None = None,
    **extra_facts: object,
) -> ReleasedObject:
    core_facts: dict[str, object] = {"name": display_name}
    core_facts.update(extra_facts)
    return ReleasedObject(
        id=id,
        object_type=object_type,
        display_name=display_name,
        core_facts=core_facts,
        summary_fields={"profile_summary": "A test record."},
        evidence=[_evidence()],
        last_updated=last_updated or TIMESTAMP,
        quality_status=quality_status,
    )


@pytest.fixture()
def store(tmp_path) -> SqliteReleasedObjectStore:
    return SqliteReleasedObjectStore(tmp_path / "test.db")


@pytest.fixture()
def populated_store(store: SqliteReleasedObjectStore) -> SqliteReleasedObjectStore:
    """Store pre-loaded with 5 professors and 2 companies."""
    professors = [
        _released_object("PROF-1", "professor", "靳玉乐", "ready", institution="南方科技大学"),
        _released_object("PROF-2", "professor", "李明", "ready", institution="南方科技大学", last_updated=TIMESTAMP_LATER),
        _released_object("PROF-3", "professor", "王芳", "needs_review", institution="深圳大学"),
        _released_object("PROF-4", "professor", "张伟", "low_confidence", institution="深圳大学"),
        _released_object("PROF-5", "professor", "陈静", "ready", institution="哈尔滨工业大学（深圳）"),
    ]
    companies = [
        _released_object("COMP-1", "company", "深圳科创有限公司", "ready", industry="人工智能"),
        _released_object("COMP-2", "company", "南方智能科技", "needs_review", industry="半导体"),
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


# ---------- update_object ----------


class TestUpdateObject:
    def test_updates_display_name(self, populated_store: SqliteReleasedObjectStore):
        obj = populated_store.get_object("professor", "PROF-1")
        assert obj is not None
        updated = obj.model_copy(update={"display_name": "靳玉乐教授"})
        assert populated_store.update_object(updated) is True
        reloaded = populated_store.get_object("professor", "PROF-1")
        assert reloaded is not None
        assert reloaded.display_name == "靳玉乐教授"

    def test_updates_quality_status(self, populated_store: SqliteReleasedObjectStore):
        obj = populated_store.get_object("professor", "PROF-1")
        assert obj is not None
        updated = obj.model_copy(update={"quality_status": "needs_review"})
        assert populated_store.update_object(updated) is True
        reloaded = populated_store.get_object("professor", "PROF-1")
        assert reloaded is not None
        assert reloaded.quality_status == "needs_review"

    def test_nonexistent_id_returns_false(self, populated_store: SqliteReleasedObjectStore):
        obj = _released_object("NONEXISTENT", "professor", "Ghost")
        assert populated_store.update_object(obj) is False


# ---------- delete_objects ----------


class TestDeleteObjects:
    def test_deletes_multiple(self, populated_store: SqliteReleasedObjectStore):
        deleted = populated_store.delete_objects(["PROF-1", "PROF-2"])
        assert deleted == 2
        assert populated_store.get_object("professor", "PROF-1") is None
        assert populated_store.get_object("professor", "PROF-2") is None

    def test_nonexistent_ids_returns_zero(self, populated_store: SqliteReleasedObjectStore):
        deleted = populated_store.delete_objects(["NONEXISTENT"])
        assert deleted == 0

    def test_empty_list_returns_zero(self, populated_store: SqliteReleasedObjectStore):
        deleted = populated_store.delete_objects([])
        assert deleted == 0


class TestDeleteDomainObjects:
    def test_deletes_only_requested_domain(
        self, populated_store: SqliteReleasedObjectStore
    ):
        deleted = populated_store.delete_domain_objects("professor")

        assert deleted == 5
        assert populated_store.list_domain_objects("professor") == []
        assert len(populated_store.list_domain_objects("company")) == 2


# ---------- get_domain_last_updated ----------


class TestGetDomainLastUpdated:
    def test_returns_max_timestamp(self, populated_store: SqliteReleasedObjectStore):
        last = populated_store.get_domain_last_updated("professor")
        assert last == TIMESTAMP_LATER

    def test_empty_domain_returns_none(self, populated_store: SqliteReleasedObjectStore):
        last = populated_store.get_domain_last_updated("patent")
        assert last is None


# ---------- list_domain_filtered ----------


class TestListDomainFiltered:
    def test_filters_by_institution(self, populated_store: SqliteReleasedObjectStore):
        items, total = populated_store.list_domain_filtered(
            "professor", filters={"institution": "南方科技大学"}
        )
        assert total == 2
        assert all(
            item.core_facts.get("institution") == "南方科技大学" for item in items
        )

    def test_query_plus_filters(self, populated_store: SqliteReleasedObjectStore):
        items, total = populated_store.list_domain_filtered(
            "professor", query="靳", filters={"institution": "南方科技大学"}
        )
        assert total == 1
        assert items[0].display_name == "靳玉乐"

    def test_no_match_returns_empty(self, populated_store: SqliteReleasedObjectStore):
        items, total = populated_store.list_domain_filtered(
            "professor", filters={"institution": "不存在的大学"}
        )
        assert total == 0
        assert items == []

    def test_pagination_with_filters(self, populated_store: SqliteReleasedObjectStore):
        items, total = populated_store.list_domain_filtered(
            "professor", filters={"institution": "深圳大学"}, offset=0, limit=1
        )
        assert total == 2
        assert len(items) == 1

    def test_delegates_to_paginated_when_no_filters(
        self, populated_store: SqliteReleasedObjectStore
    ):
        items, total = populated_store.list_domain_filtered("professor")
        assert total == 5
        assert len(items) == 5


# ---------- export_domain_objects ----------


class TestExportDomainObjects:
    def test_exports_all(self, populated_store: SqliteReleasedObjectStore):
        objects = populated_store.export_domain_objects("professor")
        assert len(objects) == 5

    def test_exports_filtered(self, populated_store: SqliteReleasedObjectStore):
        objects = populated_store.export_domain_objects(
            "professor", filters={"institution": "深圳大学"}
        )
        assert len(objects) == 2

    def test_exports_with_query(self, populated_store: SqliteReleasedObjectStore):
        objects = populated_store.export_domain_objects("professor", query="靳")
        assert len(objects) == 1


# ---------- get_filter_options ----------


class TestGetFilterOptions:
    def test_returns_unique_values(self, populated_store: SqliteReleasedObjectStore):
        options = populated_store.get_filter_options("professor", "institution")
        assert "南方科技大学" in options
        assert "深圳大学" in options
        assert "哈尔滨工业大学（深圳）" in options
        assert len(options) == 3

    def test_empty_field_returns_empty(self, populated_store: SqliteReleasedObjectStore):
        options = populated_store.get_filter_options("professor", "nonexistent_field")
        assert options == []


class TestSearchDomain:
    def test_exact_match_score_recognizes_normalized_english_display_name(
        self,
    ):
        target = _released_object(
            "PROF-TARGET",
            "professor",
            "BRESAR, Miha",
            "ready",
            institution="香港中文大学（深圳）",
            department="数据科学学院",
        )

        score = _score_exact_match(
            target,
            _normalize_text("香港中文大学（深圳） BRESAR, Miha 教授"),
        )

        assert score >= 30.0

    def test_english_name_query_prefers_exact_professor_match_over_same_school_noise(
        self, store: SqliteReleasedObjectStore
    ):
        store.upsert_released_objects(
            [
                _released_object(
                    "PROF-TARGET",
                    "professor",
                    "BRESAR, Miha",
                    "ready",
                    institution="香港中文大学（深圳）",
                    department="数据科学学院",
                ),
                _released_object(
                    "PROF-NOISE-1",
                    "professor",
                    "荆炳义",
                    "ready",
                    institution="香港中文大学（深圳）",
                    department="理工学院",
                ),
                _released_object(
                    "PROF-NOISE-2",
                    "professor",
                    "常瑞华",
                    "ready",
                    institution="香港中文大学（深圳）",
                    department="理工学院",
                ),
                _released_object(
                    "PROF-NOISE-3",
                    "professor",
                    "张增辉",
                    "ready",
                    institution="香港中文大学（深圳）",
                    department="理工学院",
                ),
            ]
        )

        results = store.search_domain(
            "professor",
            "香港中文大学（深圳） BRESAR, Miha 教授",
            limit=5,
        )

        assert [item.display_name for item in results][:1] == ["BRESAR, Miha"]


def test_get_related_objects_uses_verified_professor_paper_link_objects(store: SqliteReleasedObjectStore):
    professor = _released_object("PROF-1", "professor", "Ada Lovelace")
    paper = _released_object(
        "PAPER-1",
        "paper",
        "On the Analytical Engine",
        title="On the Analytical Engine",
        professor_ids=[],
    )
    link = ReleasedObject(
        id="PPLINK-1",
        object_type="professor_paper_link",
        display_name="Ada Lovelace -> On the Analytical Engine",
        core_facts={
            "professor_id": "PROF-1",
            "paper_id": "PAPER-1",
            "link_status": "verified",
            "professor_name": "Ada Lovelace",
            "paper_title": "On the Analytical Engine",
            "evidence_source": "official_linked_google_scholar",
            "evidence_url": "https://scholar.google.com/citations?user=ada",
            "verified_by": "pipeline_v3",
        },
        summary_fields={"match_reason": "Official scholar profile contains the paper."},
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
        quality_status="ready",
    )
    store.upsert_released_objects([professor, paper, link])

    related = store.get_related_objects(
        source_domain="professor",
        source_id="PROF-1",
        target_domain="paper",
        relation_type="professor_papers",
    )

    assert [item.id for item in related] == ["PAPER-1"]


def test_get_related_objects_does_not_fallback_to_legacy_professor_ids(store: SqliteReleasedObjectStore):
    professor = _released_object("PROF-1", "professor", "Ada Lovelace")
    paper = _released_object(
        "PAPER-1",
        "paper",
        "On the Analytical Engine",
        title="On the Analytical Engine",
        professor_ids=["PROF-1"],
    )
    store.upsert_released_objects([professor, paper])

    related = store.get_related_objects(
        source_domain="professor",
        source_id="PROF-1",
        target_domain="paper",
        relation_type="professor_papers",
    )

    assert related == []

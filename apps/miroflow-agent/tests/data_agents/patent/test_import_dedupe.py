"""Patent import dedupe: same patent on several rows collapses to one record."""

from __future__ import annotations

from datetime import date

from src.data_agents.patent.import_xlsx import _dedupe_records
from src.data_agents.patent.models import PatentImportRecord


def _record(*, number: str | None, title: str) -> PatentImportRecord:
    return PatentImportRecord(
        source_row=2,
        sequence_number="1",
        title=title,
        title_en=None,
        abstract="摘要",
        abstract_en=None,
        applicants=("深圳市某科技有限公司",),
        patent_number=number,
        publication_date=date(2025, 1, 1),
        filing_date=None,
        patent_type="发明",
        technology_effect_sentence=None,
        technology_effect_phrases=(),
        expected_expiry_date=None,
    )


def test_same_patent_number_collapses() -> None:
    records = [
        _record(number="CN123U", title="一种装置"),
        _record(number="cn123u", title="一种装置（重复行）"),
        _record(number="CN456U", title="另一种装置"),
    ]

    unique, skipped = _dedupe_records(records)

    assert [record.patent_number for record in unique] == ["CN123U", "CN456U"]
    assert skipped["duplicate_patent_number"] == 1


def test_rows_without_number_are_kept() -> None:
    # Titles repeat across genuinely different patents, so a missing number is
    # not a duplicate signal.
    records = [
        _record(number=None, title="一种无菌围帘"),
        _record(number=None, title=" 一种无菌围帘 "),
    ]

    unique, skipped = _dedupe_records(records)

    assert len(unique) == 2
    assert not skipped


def test_distinct_patents_are_all_kept() -> None:
    records = [_record(number=f"CN{i}U", title=f"专利{i}") for i in range(5)]

    unique, skipped = _dedupe_records(records)

    assert len(unique) == 5
    assert not skipped

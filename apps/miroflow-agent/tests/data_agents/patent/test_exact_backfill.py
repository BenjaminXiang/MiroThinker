from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook

from src.data_agents.patent.exact_backfill import build_patent_release_from_sources


TIMESTAMP = datetime(2026, 4, 16, tzinfo=timezone.utc)


def _write_patent_workbook(path: Path, *, title: str, patent_number: str, applicant: str):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Sheet1'
    ws.append(['序号', '标题 (中文)', '申请人', '公开（公告）号', '公开（公告）日', '专利类型', '摘要 (中文)'])
    ws.append(['1', title, applicant, patent_number, '2024-04-12', '发明', '摘要'])
    wb.save(path)


def test_build_patent_release_from_sources_merges_multiple_workbooks(tmp_path: Path):
    primary = tmp_path / 'primary.xlsx'
    supplement = tmp_path / 'supplement.xlsx'
    _write_patent_workbook(
        primary,
        title='现有专利',
        patent_number='CN000000001A',
        applicant='Existing Applicant Ltd',
    )
    _write_patent_workbook(
        supplement,
        title='一种机器人的落地控制方法、机器人及终端设备',
        patent_number='CN117873146A',
        applicant='Shenzhen Ubtech Technology Co ltd',
    )

    release = build_patent_release_from_sources(
        workbook_paths=[primary, supplement],
        company_name_to_id={},
        now=TIMESTAMP,
    )

    assert release.report.input_record_count == 2
    assert len(release.patent_records) == 2
    assert any(record.patent_number == 'CN117873146A' for record in release.patent_records)
    backfilled = next(record for record in release.patent_records if record.patent_number == 'CN117873146A')
    assert backfilled.title == '一种机器人的落地控制方法、机器人及终端设备'
    assert backfilled.applicants == ['Shenzhen Ubtech Technology Co ltd']
    assert any(
        evidence.source_file == str(supplement)
        for evidence in backfilled.evidence
    )

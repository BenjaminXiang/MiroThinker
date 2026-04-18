from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from backend.deps import get_store
from src.data_agents.company.import_xlsx import import_company_xlsx
from src.data_agents.company.release import build_company_release
from src.data_agents.patent.import_xlsx import import_patent_xlsx
from src.data_agents.patent.release import build_patent_release
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

router = APIRouter(prefix="/api/upload")


class UploadResponse(BaseModel):
    imported: int
    skipped: int
    total_in_store: int


@router.post("/company", response_model=UploadResponse)
def upload_company(
    file: UploadFile,
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> UploadResponse:
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are accepted")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = Path(tmp.name)

    try:
        import_result = import_company_xlsx(tmp_path)
        release_result = build_company_release(
            records=import_result.records,
            source_file=tmp_path,
        )
        store.upsert_released_objects(release_result.released_objects)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to parse Excel file")
    finally:
        tmp_path.unlink(missing_ok=True)

    counts = store.count_by_domain()
    return UploadResponse(
        imported=release_result.report.released_record_count,
        skipped=import_result.report.rows_read - len(import_result.records),
        total_in_store=counts.get("company", 0),
    )


@router.post("/patent", response_model=UploadResponse)
def upload_patent(
    file: UploadFile,
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> UploadResponse:
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are accepted")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = Path(tmp.name)

    try:
        import_result = import_patent_xlsx(tmp_path)

        # Build company name→id index from existing company records for linkage
        company_objects = store.list_domain_objects("company")
        company_name_to_id = {
            obj.core_facts.get("normalized_name", obj.display_name): obj.id
            for obj in company_objects
        }

        release_result = build_patent_release(
            records=import_result.records,
            source_file=tmp_path,
            company_name_to_id=company_name_to_id,
        )
        store.upsert_released_objects(release_result.released_objects)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to parse Excel file")
    finally:
        tmp_path.unlink(missing_ok=True)

    counts = store.count_by_domain()
    return UploadResponse(
        imported=release_result.report.released_record_count,
        skipped=import_result.report.rows_read - len(import_result.records),
        total_in_store=counts.get("patent", 0),
    )

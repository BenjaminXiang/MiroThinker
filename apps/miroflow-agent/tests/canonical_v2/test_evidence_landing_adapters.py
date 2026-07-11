from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib import import_module
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from typing import Any

from openpyxl import Workbook
import pytest

from src.data_agents.canonical_v2.contracts import SourceRecord as SharedSourceRecord


NOW = datetime(2026, 7, 11, 18, 40, tzinfo=timezone.utc)


def _module() -> Any:
    return import_module("src.data_agents.canonical_v2.evidence_landing")


def _request(
    module: Any,
    *,
    batch: str,
    source_kind: str,
    parser_name: str,
    content: bytes,
    options: dict[str, Any] | None = None,
) -> Any:
    return module.IngestEvidenceRequest(
        run_id=f"run-{batch}",
        source_batch_id=batch,
        source_kind=source_kind,
        source_locator=f"synthetic/{batch}",
        content=content,
        observed_at=NOW,
        expected_content_sha256=hashlib.sha256(content).hexdigest(),
        parser=module.ParserReference(
            parser_name=parser_name,
            parser_version="v1",
            schema_version="source-record-v1",
            options=options or {},
        ),
    )


def _xlsx_bytes(*, headers: tuple[str, str] = ("id", "name")) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "records"
    sheet.append(list(headers))
    sheet.append(["1", "Alpha"])
    sheet.append(["2", "Beta"])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _sqlite_bytes(path: Path) -> bytes:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE records (id TEXT, name TEXT)")
        connection.executemany(
            "INSERT INTO records (id, name) VALUES (?, ?)",
            (("1", "Alpha"), ("2", "Beta")),
        )
        connection.commit()
    finally:
        connection.close()
    return path.read_bytes()


def test_wal_fpi_salvage_envelope_retains_readable_fields_and_errors() -> None:
    module = _module()
    assert module.SourceRecord is SharedSourceRecord
    landing = module.create_ephemeral_evidence_landing()
    content = (
        json.dumps(
            {
                "record_locator": "salvage.paper:42",
                "readable_fields": {
                    "paper_id": "paper-42",
                    "title": "Recovered title",
                },
                "field_errors": [
                    {
                        "error_code": "missing_toast",
                        "error_kind": "missing_external_content",
                        "message": "External abstract bytes were not recovered.",
                        "field_path": "abstract",
                        "recoverable": False,
                    }
                ],
            },
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    receipt = landing.ingest(
        _request(
            module,
            batch="wal-fpi-1",
            source_kind="wal_fpi_salvage_records",
            parser_name="wal_fpi_salvage",
            content=content,
        )
    )
    records = tuple(landing.stream(receipt.source_batch_id))

    assert len(records) == 1
    record = records[0]
    assert record.record_locator == "salvage.paper:42"
    assert record.parse_status.value == "partial"
    assert record.payload == {"paper_id": "paper-42", "title": "Recovered title"}
    assert [(error.error_kind.value, error.field_path) for error in record.errors] == [
        ("missing_external_content", "abstract")
    ]


def test_historical_json_csv_xlsx_and_sqlite_bytes_share_one_record_contract(
    tmp_path: Path,
) -> None:
    module = _module()
    assert module.SourceRecord is SharedSourceRecord
    landing = module.create_ephemeral_evidence_landing()
    inputs = (
        (
            "json-1",
            "historical_json",
            "historical_json",
            b'[{"id":"1","name":"Alpha"},{"id":"2","name":"Beta"}]',
            {},
        ),
        (
            "csv-1",
            "historical_csv",
            "historical_csv",
            b"id,name\n1,Alpha\n2,Beta\n",
            {},
        ),
        (
            "xlsx-1",
            "historical_xlsx",
            "historical_xlsx",
            _xlsx_bytes(),
            {"sheet": "records"},
        ),
        (
            "sqlite-1",
            "historical_sqlite",
            "historical_sqlite",
            _sqlite_bytes(tmp_path / "records.sqlite"),
            {"table": "records"},
        ),
    )

    for batch, source_kind, parser_name, content, options in inputs:
        landing.ingest(
            _request(
                module,
                batch=batch,
                source_kind=source_kind,
                parser_name=parser_name,
                content=content,
                options=options,
            )
        )
        assert [record.payload for record in landing.stream(batch)] == [
            {"id": "1", "name": "Alpha"},
            {"id": "2", "name": "Beta"},
        ]
        assert all(
            record.parse_status.value == "parsed" for record in landing.stream(batch)
        )


def test_duplicate_structured_headers_are_quarantined_instead_of_overwritten() -> None:
    module = _module()
    landing = module.create_ephemeral_evidence_landing()
    inputs = (
        (
            "csv-duplicate-header",
            "historical_csv",
            "historical_csv",
            b"id,id\n1,2\n",
            {},
        ),
        (
            "xlsx-duplicate-header",
            "historical_xlsx",
            "historical_xlsx",
            _xlsx_bytes(headers=("id", "id")),
            {"sheet": "records"},
        ),
    )

    for batch, source_kind, parser_name, content, options in inputs:
        receipt = landing.ingest(
            _request(
                module,
                batch=batch,
                source_kind=source_kind,
                parser_name=parser_name,
                content=content,
                options=options,
            )
        )
        records = tuple(landing.stream(receipt.source_batch_id))

        assert len(records) == 1
        assert records[0].parse_status.value == "quarantined"
        assert records[0].payload == {}
        assert records[0].errors[0].error_kind.value == "schema_mismatch"


def test_csv_rows_with_unheaded_values_keep_readable_fields_and_a_typed_error() -> None:
    module = _module()
    landing = module.create_ephemeral_evidence_landing()
    receipt = landing.ingest(
        _request(
            module,
            batch="csv-extra-value",
            source_kind="historical_csv",
            parser_name="historical_csv",
            content=b"id\n1,unheaded\n",
        )
    )
    record = tuple(landing.stream(receipt.source_batch_id))[0]

    assert record.parse_status.value == "partial"
    assert record.payload == {"id": "1"}
    assert [(error.error_kind.value, error.field_path) for error in record.errors] == [
        ("schema_mismatch", "$extra_columns")
    ]


def test_json_source_families_quarantine_duplicate_object_keys() -> None:
    module = _module()
    landing = module.create_ephemeral_evidence_landing()
    inputs = (
        (
            "duplicate-jsonl",
            "historical_jsonl",
            "historical_jsonl",
            b'{"id":"one","id":"two"}\n',
        ),
        (
            "duplicate-json",
            "historical_json",
            "historical_json",
            b'{"id":"one","id":"two"}',
        ),
        (
            "duplicate-salvage",
            "wal_fpi_salvage_records",
            "wal_fpi_salvage",
            b'{"record_locator":"one","record_locator":"two",'
            b'"readable_fields":{},"field_errors":[]}\n',
        ),
        (
            "duplicate-milvus",
            "milvus_verified_copy_records",
            "milvus_copy_records",
            b'{"collection":"one","collection":"two","primary_key":"1"}\n',
        ),
        (
            "duplicate-collected",
            "newly_collected_response",
            "collected_response",
            b'{"source_url":"https://one.test","source_url":"https://two.test",'
            b'"retrieved_at":"2026-07-11T18:40:00Z","status_code":200,'
            b'"content_type":"application/json","body":{}}',
        ),
    )

    for batch, source_kind, parser_name, content in inputs:
        receipt = landing.ingest(
            _request(
                module,
                batch=batch,
                source_kind=source_kind,
                parser_name=parser_name,
                content=content,
            )
        )
        record = tuple(landing.stream(receipt.source_batch_id))[0]
        assert record.parse_status.value == "corrupt"
        assert record.payload == {}
        assert record.errors[0].error_kind.value == "corrupt_content"


def test_json_source_families_quarantine_nonstandard_numeric_constants() -> None:
    module = _module()
    landing = module.create_ephemeral_evidence_landing()
    receipt = landing.ingest(
        _request(
            module,
            batch="jsonl-nonstandard-number",
            source_kind="historical_jsonl",
            parser_name="historical_jsonl",
            content=b'{"source_id":"paper-nan","score":NaN}\n',
        )
    )
    record = tuple(landing.stream(receipt.source_batch_id))[0]

    assert record.parse_status.value == "corrupt"
    assert record.payload == {}
    assert record.errors[0].error_kind.value == "corrupt_content"


def test_milvus_adapter_accepts_verified_copy_records_and_rejects_original_source() -> (
    None
):
    module = _module()
    assert module.SourceRecord is SharedSourceRecord
    landing = module.create_ephemeral_evidence_landing()
    content = (
        b'{"collection":"paper_embeddings","primary_key":"paper-1",'
        b'"payload":{"title":"Vector source"},'
        b'"projection":{"embedding_model":"recorded-v1"}}\n'
    )
    receipt = landing.ingest(
        _request(
            module,
            batch="milvus-copy-1",
            source_kind="milvus_verified_copy_records",
            parser_name="milvus_copy_records",
            content=content,
        )
    )
    records = tuple(landing.stream(receipt.source_batch_id))

    assert len(records) == 1
    assert records[0].payload["collection"] == "paper_embeddings"
    assert records[0].payload["primary_key"] == "paper-1"
    assert receipt.active_release_id is None

    with pytest.raises(module.UnverifiedSourceError, match="verified copy"):
        landing.ingest(
            _request(
                module,
                batch="milvus-original-forbidden",
                source_kind="milvus_lite_original",
                parser_name="milvus_copy_records",
                content=content,
            )
        )
    assert tuple(landing.stream("milvus-original-forbidden")) == ()

    invalid_content = b'{"collection":"","primary_key":true,"payload":{}}\n'
    invalid = landing.ingest(
        _request(
            module,
            batch="milvus-copy-invalid-identity",
            source_kind="milvus_verified_copy_records",
            parser_name="milvus_copy_records",
            content=invalid_content,
        )
    )
    invalid_record = tuple(landing.stream(invalid.source_batch_id))[0]
    assert invalid_record.parse_status.value == "quarantined"
    assert invalid_record.errors[0].error_kind.value == "schema_mismatch"


def test_collected_response_adapter_preserves_current_source_provenance_only() -> None:
    module = _module()
    assert module.SourceRecord is SharedSourceRecord
    landing = module.create_ephemeral_evidence_landing()
    envelope = {
        "source_url": "https://example.test/papers/paper-1",
        "retrieved_at": "2026-07-11T18:40:00Z",
        "status_code": 200,
        "content_type": "application/json",
        "body": {"title": "Current title", "status": "published"},
    }
    content = json.dumps(envelope, separators=(",", ":")).encode()
    receipt = landing.ingest(
        _request(
            module,
            batch="collected-response-1",
            source_kind="newly_collected_response",
            parser_name="collected_response",
            content=content,
        )
    )
    records = tuple(landing.stream(receipt.source_batch_id))

    assert len(records) == 1
    assert records[0].payload == envelope
    assert records[0].record_locator == envelope["source_url"]
    assert receipt.active_release_id is None
    assert not hasattr(records[0], "canonical_identity_id")


def test_collected_response_with_invalid_provenance_is_typed_partial_evidence() -> None:
    module = _module()
    landing = module.create_ephemeral_evidence_landing()
    envelope = {
        "source_url": 42,
        "retrieved_at": "not-a-time",
        "status_code": "ok",
        "content_type": [],
        "body": {"title": "Readable body"},
    }
    content = json.dumps(envelope, separators=(",", ":")).encode()
    receipt = landing.ingest(
        _request(
            module,
            batch="collected-invalid-provenance",
            source_kind="newly_collected_response",
            parser_name="collected_response",
            content=content,
        )
    )
    record = tuple(landing.stream(receipt.source_batch_id))[0]

    assert record.parse_status.value == "partial"
    assert record.payload == envelope
    assert {error.field_path for error in record.errors} == {
        "source_url",
        "retrieved_at",
        "status_code",
        "content_type",
    }

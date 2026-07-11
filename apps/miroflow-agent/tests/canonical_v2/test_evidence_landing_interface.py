from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib import import_module
from typing import Any

from src.data_agents.canonical_v2.contracts import SourceRecord as SharedSourceRecord


def test_evidence_landing_ingest_and_stream_preserve_byte_identity_and_lineage() -> (
    None
):
    module: Any = import_module("src.data_agents.canonical_v2.evidence_landing")
    assert module.SourceRecord is SharedSourceRecord
    content = b'{"source_id":"paper-1","title":"Evidence first"}\n'
    digest = hashlib.sha256(content).hexdigest()
    observed_at = datetime(2026, 7, 11, tzinfo=timezone.utc)
    request = module.IngestEvidenceRequest(
        run_id="landing-run-1",
        source_batch_id="batch-1",
        source_kind="historical_jsonl",
        source_locator="fixtures/papers.jsonl",
        content=content,
        observed_at=observed_at,
    )

    class RecordingLanding(module.EvidenceLanding):
        def ingest(self, value: Any) -> Any:
            assert value is request
            return module.LandingReceipt(
                run_id=value.run_id,
                source_batch_id=value.source_batch_id,
                artifact_id=f"sha256:{digest}",
                content_sha256=digest,
                bytes_written=len(value.content),
                status="accepted",
                active_release_id=None,
            )

        def stream(self, source_batch_id: str) -> tuple[Any, ...]:
            assert source_batch_id == request.source_batch_id
            return (
                module.SourceRecord(
                    record_id="record-paper-1",
                    artifact_id=f"sha256:{digest}",
                    source_batch_id=source_batch_id,
                    record_locator="line:1",
                    parser_name="jsonl",
                    parser_version="parser-v1",
                    schema_version="paper-v1",
                    parse_run_id="parse-run-1",
                    parse_status="parsed",
                    payload={"source_id": "paper-1", "title": "Evidence first"},
                    errors=(),
                    parsed_at=observed_at,
                ),
            )

    landing = RecordingLanding()
    receipt = landing.ingest(request)
    records = tuple(landing.stream(request.source_batch_id))

    assert isinstance(receipt, module.LandingReceipt)
    assert receipt.content_sha256 == digest
    assert receipt.bytes_written == len(content)
    assert receipt.status == "accepted"
    assert receipt.run_id == request.run_id
    assert receipt.source_batch_id == request.source_batch_id
    assert receipt.active_release_id is None
    assert len(records) == 1
    assert isinstance(records[0], module.SourceRecord)
    assert records[0].artifact_id == receipt.artifact_id
    assert records[0].record_locator == "line:1"
    assert records[0].parse_status == "parsed"
    assert records[0].errors == ()

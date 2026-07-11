from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from importlib import import_module
from typing import Any

import pytest

from src.data_agents.canonical_v2.contracts import SourceRecord as SharedSourceRecord


NOW = datetime(2026, 7, 11, 18, 30, tzinfo=timezone.utc)


def _module() -> Any:
    return import_module("src.data_agents.canonical_v2.evidence_landing")


def _parser(module: Any, version: str = "v1") -> Any:
    return module.ParserReference(
        parser_name="historical_jsonl",
        parser_version=version,
        schema_version="historical-record-v1",
    )


def _request(
    module: Any,
    *,
    run_id: str,
    source_batch_id: str,
    source_kind: str,
    source_locator: str,
    content: bytes,
    parser_version: str = "v1",
    expected_content_sha256: str | None = None,
    parent_artifact_id: str | None = None,
    parent_content_sha256: str | None = None,
    observed_at: datetime = NOW,
) -> Any:
    return module.IngestEvidenceRequest(
        run_id=run_id,
        source_batch_id=source_batch_id,
        source_kind=source_kind,
        source_locator=source_locator,
        content=content,
        observed_at=observed_at,
        expected_content_sha256=expected_content_sha256,
        parser=_parser(module, parser_version),
        parent_artifact_id=parent_artifact_id,
        parent_content_sha256=parent_content_sha256,
    )


def test_ingest_binds_exact_bytes_and_copy_lineage_before_streaming() -> None:
    module = _module()
    assert module.SourceRecord is SharedSourceRecord
    landing = module.create_ephemeral_evidence_landing()
    content = b'{"source_id":"paper-1","title":"Evidence first"}\n'
    digest = hashlib.sha256(content).hexdigest()

    source = landing.ingest(
        _request(
            module,
            run_id="landing-source-1",
            source_batch_id="batch-source-1",
            source_kind="forensic_source",
            source_locator="source/papers.jsonl",
            content=content,
            expected_content_sha256=digest,
        )
    )
    copied = landing.ingest(
        _request(
            module,
            run_id="landing-copy-1",
            source_batch_id="batch-copy-1",
            source_kind="verified_copy",
            source_locator="backup/papers.jsonl",
            content=content,
            expected_content_sha256=digest,
            parent_artifact_id=source.artifact_id,
            parent_content_sha256=source.content_sha256,
        )
    )

    assert source.content_sha256 == copied.content_sha256 == digest
    assert source.bytes_written == copied.bytes_written == len(content)
    assert source.artifact_id != copied.artifact_id
    assert source.parent_artifact_id is None
    assert copied.parent_artifact_id == source.artifact_id
    assert copied.parent_content_sha256 == source.content_sha256
    assert all(
        record.artifact_id == copied.artifact_id
        for record in landing.stream(copied.source_batch_id)
    )

    tampered = content.replace(b"Evidence first", b"Changed bytes")
    with pytest.raises(module.EvidenceIntegrityError, match="content hash"):
        landing.ingest(
            _request(
                module,
                run_id="landing-tampered-1",
                source_batch_id="batch-tampered-1",
                source_kind="verified_copy",
                source_locator="backup/tampered.jsonl",
                content=tampered,
                expected_content_sha256=digest,
                parent_artifact_id=source.artifact_id,
                parent_content_sha256=source.content_sha256,
            )
        )
    assert tuple(landing.stream("batch-tampered-1")) == ()


def test_one_run_id_cannot_hide_conflicting_parent_lineage() -> None:
    module = _module()
    landing = module.create_ephemeral_evidence_landing()
    child_content = b'{"source_id":"paper-child"}\n'
    parents = []
    for suffix in ("one", "two"):
        parent_content = f'{{"source_id":"parent-{suffix}"}}\n'.encode()
        parents.append(
            landing.ingest(
                _request(
                    module,
                    run_id=f"parent-run-{suffix}",
                    source_batch_id=f"parent-batch-{suffix}",
                    source_kind="forensic_source",
                    source_locator=f"source/parent-{suffix}.jsonl",
                    content=parent_content,
                    expected_content_sha256=hashlib.sha256(parent_content).hexdigest(),
                )
            )
        )
    first_child = landing.ingest(
        _request(
            module,
            run_id="child-copy-run",
            source_batch_id="child-copy-batch",
            source_kind="verified_copy",
            source_locator="backup/child.jsonl",
            content=child_content,
            parent_artifact_id=parents[0].artifact_id,
            parent_content_sha256=parents[0].content_sha256,
        )
    )

    with pytest.raises(module.EvidenceIntegrityError, match="run_id"):
        landing.ingest(
            _request(
                module,
                run_id="child-copy-run",
                source_batch_id="child-copy-batch",
                source_kind="verified_copy",
                source_locator="backup/child.jsonl",
                content=child_content,
                parent_artifact_id=parents[1].artifact_id,
                parent_content_sha256=parents[1].content_sha256,
            )
        )
    assert tuple(landing.stream("child-copy-batch")) == tuple(
        landing.stream(first_child.source_batch_id)
    )
    assert first_child.parent_artifact_id == parents[0].artifact_id


def test_one_run_id_is_idempotent_but_cannot_hide_conflicting_observation_time() -> (
    None
):
    module = _module()
    landing = module.create_ephemeral_evidence_landing()
    content = b'{"source_id":"paper-observed"}\n'
    request = _request(
        module,
        run_id="observed-run",
        source_batch_id="observed-batch",
        source_kind="historical_jsonl",
        source_locator="history/observed.jsonl",
        content=content,
    )

    first = landing.ingest(request)
    assert landing.ingest(request) == first
    assert len(landing.stream("observed-batch")) == 1
    with pytest.raises(module.EvidenceIntegrityError, match="run_id"):
        landing.ingest(
            _request(
                module,
                run_id="observed-run",
                source_batch_id="observed-batch",
                source_kind="historical_jsonl",
                source_locator="history/observed.jsonl",
                content=content,
                observed_at=NOW + timedelta(seconds=1),
            )
        )


def test_stream_returns_detached_snapshots_of_committed_evidence() -> None:
    module = _module()
    landing = module.create_ephemeral_evidence_landing()
    content = b'{"source_id":"paper-snapshot","title":"Original"}\n'
    landing.ingest(
        _request(
            module,
            run_id="snapshot-run",
            source_batch_id="snapshot-batch",
            source_kind="historical_jsonl",
            source_locator="history/snapshot.jsonl",
            content=content,
        )
    )

    returned = landing.stream("snapshot-batch")[0]
    returned.payload["title"] = "Caller mutation"

    assert landing.stream("snapshot-batch")[0].payload["title"] == "Original"


def test_replay_with_a_new_parser_version_retains_both_record_sets() -> None:
    module = _module()
    assert module.SourceRecord is SharedSourceRecord
    landing = module.create_ephemeral_evidence_landing()
    content = b'{"source_id":"paper-1","title":"Replayable"}\n'
    digest = hashlib.sha256(content).hexdigest()

    first = landing.ingest(
        _request(
            module,
            run_id="landing-parser-v1",
            source_batch_id="batch-replay-1",
            source_kind="historical_jsonl",
            source_locator="history/papers.jsonl",
            content=content,
            parser_version="v1",
            expected_content_sha256=digest,
        )
    )
    first_records = tuple(landing.stream(first.source_batch_id))
    second = landing.ingest(
        _request(
            module,
            run_id="landing-parser-v2",
            source_batch_id="batch-replay-1",
            source_kind="historical_jsonl",
            source_locator="history/papers.jsonl",
            content=content,
            parser_version="v2",
            expected_content_sha256=digest,
        )
    )
    all_records = tuple(landing.stream(second.source_batch_id))

    assert first.artifact_id == second.artifact_id
    assert len(first_records) == 1
    assert len(all_records) == 2
    assert first_records[0] in all_records
    by_version = {record.parser_version: record for record in all_records}
    assert set(by_version) == {"v1", "v2"}
    assert by_version["v1"].record_id != by_version["v2"].record_id
    assert by_version["v1"].parse_run_id != by_version["v2"].parse_run_id
    assert by_version["v1"].payload == by_version["v2"].payload


def test_partial_and_corrupt_records_keep_readable_fields_and_typed_errors() -> None:
    module = _module()
    assert module.SourceRecord is SharedSourceRecord
    landing = module.create_ephemeral_evidence_landing()
    content = (
        b'{"source_id":"paper-1","title":"Readable title",'
        b'"abstract":{"$unreadable_external":"toast:42"}}\n'
        b"{not-valid-json\n"
    )
    receipt = landing.ingest(
        _request(
            module,
            run_id="landing-partial-corrupt-1",
            source_batch_id="batch-partial-corrupt-1",
            source_kind="historical_jsonl",
            source_locator="history/recovered-papers.jsonl",
            content=content,
        )
    )
    records = tuple(landing.stream(receipt.source_batch_id))
    by_locator = {record.record_locator: record for record in records}

    assert set(by_locator) == {"line:1", "line:2"}
    partial = by_locator["line:1"]
    assert partial.parse_status.value == "partial"
    assert partial.payload == {"source_id": "paper-1", "title": "Readable title"}
    assert len(partial.errors) == 1
    assert partial.errors[0].error_kind.value == "missing_external_content"
    assert partial.errors[0].field_path == "abstract"

    corrupt = by_locator["line:2"]
    assert corrupt.parse_status.value == "corrupt"
    assert corrupt.payload == {}
    assert len(corrupt.errors) == 1
    assert corrupt.errors[0].error_kind.value == "corrupt_content"
    assert corrupt.errors[0].field_path is None


def test_unreadable_identity_fields_create_no_placeholder_fact_or_canonical_effect() -> (
    None
):
    module = _module()
    assert module.SourceRecord is SharedSourceRecord
    landing = module.create_ephemeral_evidence_landing()
    content = (
        b'{"title":"Readable only",'
        b'"source_id":{"$unreadable_external":"toast:77"},'
        b'"professor_id":{"$unreadable_external":"toast:78"}}\n'
    )
    receipt = landing.ingest(
        _request(
            module,
            run_id="landing-no-placeholder-1",
            source_batch_id="batch-no-placeholder-1",
            source_kind="historical_jsonl",
            source_locator="history/partial-identity.jsonl",
            content=content,
        )
    )
    records = tuple(landing.stream(receipt.source_batch_id))

    assert receipt.active_release_id is None
    assert len(records) == 1
    record = records[0]
    assert record.parse_status.value == "partial"
    assert record.payload == {"title": "Readable only"}
    assert {error.field_path for error in record.errors} == {
        "source_id",
        "professor_id",
    }
    assert not hasattr(record, "canonical_identity_id")
    assert not hasattr(record, "parent_entity_id")
    assert all(
        value.casefold() not in {"unknown", "n/a", "none", "placeholder"}
        for value in record.payload.values()
        if isinstance(value, str)
    )

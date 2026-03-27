"""Skeleton import stage that deduplicates master-list rows and emits import reports."""

from __future__ import annotations

from collections import OrderedDict
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from company_data_agent.config import ArtifactLayout
from company_data_agent.identity import CompanyIdentity, normalize_credit_code
from company_data_agent.ingest import (
    MasterListParseError,
    MasterListParseResult,
    ParsedMasterListRow,
)
from company_data_agent.models.company_record import CompanySource, PartialCompanyRecord


class SkeletonImportActionType(StrEnum):
    """Final disposition for a distinct company identity in the import batch."""

    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"


class SkeletonImportAction(BaseModel):
    """Per-company summary emitted by the skeleton import stage."""

    model_config = ConfigDict(extra="forbid")

    action: SkeletonImportActionType
    company_id: str
    credit_code: str
    row_numbers: list[int]
    source_path: str


class SkeletonImportReport(BaseModel):
    """Deterministic import report for one parsed master-list input."""

    model_config = ConfigDict(extra="forbid")

    source_path: str
    processed_rows: int
    distinct_companies: int
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    actions: list[SkeletonImportAction]
    failures: list[MasterListParseError]


class SkeletonImportResult(BaseModel):
    """Skeleton records plus the deterministic import report."""

    model_config = ConfigDict(extra="forbid")

    records: list[PartialCompanyRecord]
    report: SkeletonImportReport


class _AggregatedImportState(BaseModel):
    """Internal aggregate state for one normalized credit code."""

    model_config = ConfigDict(extra="forbid")

    baseline: PartialCompanyRecord | None
    current: PartialCompanyRecord
    row_numbers: list[int]
    source_path: str


class SkeletonImporter:
    """Merge parsed master-list rows into base company records and a deterministic report."""

    def import_rows(
        self,
        parse_result: MasterListParseResult,
        artifact_layout: ArtifactLayout,
        existing_records: Iterable[PartialCompanyRecord] | None = None,
    ) -> SkeletonImportResult:
        existing_by_credit = OrderedDict()
        for record in sorted(existing_records or [], key=lambda item: item.credit_code):
            existing_by_credit[normalize_credit_code(record.credit_code)] = record

        failures: list[MasterListParseError] = list(parse_result.errors)
        aggregated: OrderedDict[str, _AggregatedImportState] = OrderedDict()

        for row in parse_result.rows:
            try:
                identity = CompanyIdentity.from_raw_credit_code(row.credit_code)
                candidate = self._candidate_record(row, identity, artifact_layout)
            except ValueError as exc:
                failures.append(
                    MasterListParseError(
                        row_number=row.row_number,
                        source_path=row.source_path,
                        message=str(exc),
                        raw_columns=row.raw_columns,
                    )
                )
                continue

            if identity.credit_code not in aggregated:
                baseline = existing_by_credit.get(identity.credit_code)
                merged = self._merge_records(baseline, candidate)
                aggregated[identity.credit_code] = _AggregatedImportState(
                    baseline=baseline,
                    current=merged,
                    row_numbers=[row.row_number],
                    source_path=row.source_path,
                )
                continue

            state = aggregated[identity.credit_code]
            state.current = self._merge_records(state.current, candidate)
            state.row_numbers.append(row.row_number)

        actions: list[SkeletonImportAction] = []
        records: list[PartialCompanyRecord] = []
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for credit_code in sorted(aggregated):
            state = aggregated[credit_code]
            records.append(state.current)
            action_type = self._classify_action(state.baseline, state.current)
            if action_type is SkeletonImportActionType.CREATED:
                created_count += 1
            elif action_type is SkeletonImportActionType.UPDATED:
                updated_count += 1
            else:
                skipped_count += 1

            actions.append(
                SkeletonImportAction(
                    action=action_type,
                    company_id=state.current.id or "",
                    credit_code=credit_code,
                    row_numbers=state.row_numbers,
                    source_path=state.source_path,
                )
            )

        return SkeletonImportResult(
            records=records,
            report=SkeletonImportReport(
                source_path=parse_result.source_path,
                processed_rows=len(parse_result.rows),
                distinct_companies=len(actions),
                created_count=created_count,
                updated_count=updated_count,
                skipped_count=skipped_count,
                failed_count=len(failures),
                actions=actions,
                failures=failures,
            ),
        )

    def _candidate_record(
        self,
        row: ParsedMasterListRow,
        identity: CompanyIdentity,
        artifact_layout: ArtifactLayout,
    ) -> PartialCompanyRecord:
        filename = f"{Path(row.source_path).stem}-row-{row.row_number:06d}.json"
        return PartialCompanyRecord.model_validate(
            {
                "id": identity.company_id,
                "name": row.name,
                "credit_code": identity.credit_code,
                "registered_address": row.registered_address,
                "industry": row.industry,
                "sources": [CompanySource.MASTER_LIST],
                "raw_data_path": str(
                    artifact_layout.raw_payload_path(
                        identity.credit_code,
                        CompanySource.MASTER_LIST.value,
                        filename,
                    )
                ),
            }
        )

    def _merge_records(
        self,
        baseline: PartialCompanyRecord | None,
        candidate: PartialCompanyRecord,
    ) -> PartialCompanyRecord:
        if baseline is None:
            return candidate

        data = baseline.model_dump(mode="python")

        data["id"] = candidate.id
        data["credit_code"] = candidate.credit_code

        changed = False
        for field in ("name", "registered_address", "industry"):
            incoming = getattr(candidate, field)
            if incoming and incoming != data.get(field):
                data[field] = incoming
                changed = True

        merged_sources = [CompanySource.MASTER_LIST, *baseline.sources]
        if list(dict.fromkeys(merged_sources)) != baseline.sources:
            changed = True
        data["sources"] = merged_sources

        if changed or not baseline.raw_data_path:
            data["raw_data_path"] = candidate.raw_data_path

        return PartialCompanyRecord.model_validate(data)

    def _classify_action(
        self,
        baseline: PartialCompanyRecord | None,
        current: PartialCompanyRecord,
    ) -> SkeletonImportActionType:
        if baseline is None:
            return SkeletonImportActionType.CREATED
        if baseline.model_dump(mode="python") == current.model_dump(mode="python"):
            return SkeletonImportActionType.SKIPPED
        return SkeletonImportActionType.UPDATED

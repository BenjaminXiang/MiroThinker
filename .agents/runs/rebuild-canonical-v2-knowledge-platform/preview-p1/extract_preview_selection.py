from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sqlite3
import stat
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlsplit


_EXPECTED_MANIFEST: dict[str, Any] = {
    "schema_version": "preview-selection-manifest-v1",
    "selection_id": "canonical-v2-real-data-preview-p1-v1",
    "accepted_checkpoint": {
        "source_inventory_sha256": (
            "83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09"
        ),
        "backup_manifest_sha256": (
            "a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8"
        ),
        "restore_verification_sha256": (
            "98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231"
        ),
        "acceptance_record_sha256": (
            "3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b"
        ),
    },
    "source": {
        "source_id": (
            "inventory:ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0"
        ),
        "relative_path": "workspace/logs/data_agents/released_objects.db",
        "bytes": 20_267_008,
        "sha256": ("7637d808559685f1bcf0316cd22cfeac4e50bd0850c53652ec95b3dbb5e43bce"),
    },
    "rows": [
        {
            "id": "COMP-3B95F48EB687",
            "object_type": "company",
            "display_name": "深圳森合创新科技有限公司",
            "payload_json_sha256": (
                "9d946d96fdfd216b80425931acb5b572af82c1930df72f7986abd2c559f052de"
            ),
        },
        {
            "id": "PAT-009605B1E383",
            "object_type": "patent",
            "display_name": "底刀调节结构及割草机器人",
            "payload_json_sha256": (
                "90a9ed2538147778a70f2e112e9c40a0103114063308eee4e49c0f7707e9610c"
            ),
        },
        {
            "id": "PROF-8000C9F994C3",
            "object_type": "professor",
            "display_name": "丁文伯",
            "payload_json_sha256": (
                "8164448be7dcb5c82ccb5a19ea801f38be5aaa2d24bf421eb719824c3164ae4e"
            ),
        },
        {
            "id": "PAPER-1258119BC264",
            "object_type": "paper",
            "display_name": (
                "Keystroke dynamics enabled authentication and identification using "
                "triboelectric nanogenerator array"
            ),
            "payload_json_sha256": (
                "26abe842affe9cf940eb2af637ff53620287def9dc4978fae56bfb285934e7d0"
            ),
        },
        {
            "id": "PROF-PAPER-LINK-00A7B60465F2",
            "object_type": "professor_paper_link",
            "display_name": (
                "丁文伯 -> Keystroke dynamics enabled authentication and identification "
                "using triboelectric nanogenerator array"
            ),
            "payload_json_sha256": (
                "9b05dda6e0cc0911b588849c30e67398347aea3e7e35455d63e76cc3774b5225"
            ),
        },
    ],
    "expected_public_domain_counts": {
        "company": 1,
        "paper": 1,
        "patent": 1,
        "professor": 1,
    },
    "expected_relationships": [
        {
            "kind": "company_patent",
            "source_id": "COMP-3B95F48EB687",
            "target_id": "PAT-009605B1E383",
        },
        {
            "kind": "professor_authored_paper",
            "source_id": "PROF-8000C9F994C3",
            "target_id": "PAPER-1258119BC264",
            "link_row_id": "PROF-PAPER-LINK-00A7B60465F2",
        },
    ],
    "expected_row_count": 5,
    "selected_row_set_sha256": (
        "0a806a93c66159b1a824b52131041aa6ff7877dc3d808d1d2c56ffc5efd76f06"
    ),
    "public_field_policy_version": "preview-public-fields-v1",
}

_PUBLIC_CORE_FIELDS = {
    "company": frozenset(
        {"industry", "key_personnel", "name", "normalized_name", "website"}
    ),
    "patent": frozenset(
        {
            "abstract",
            "applicants",
            "company_ids",
            "filing_date",
            "grant_date",
            "inventors",
            "ipc_codes",
            "patent_number",
            "patent_type",
            "professor_ids",
            "publication_date",
            "technology_effect",
            "title",
            "title_en",
        }
    ),
    "professor": frozenset(
        {
            "academic_positions",
            "awards",
            "citation_count",
            "company_roles",
            "department",
            "education_structured",
            "h_index",
            "homepage",
            "institution",
            "name",
            "paper_count",
            "patent_ids",
            "projects",
            "research_directions",
            "title",
            "top_papers",
            "work_experience",
        }
    ),
    "paper": frozenset(
        {
            "abstract",
            "arxiv_id",
            "authors",
            "citation_count",
            "doi",
            "enrichment_sources",
            "fields_of_study",
            "funders",
            "keywords",
            "license",
            "oa_status",
            "professor_ids",
            "publication_date",
            "reference_count",
            "title",
            "title_zh",
            "tldr",
            "venue",
            "year",
        }
    ),
    "professor_paper_link": frozenset(
        {
            "evidence_source",
            "evidence_url",
            "link_status",
            "paper_id",
            "paper_title",
            "professor_id",
            "professor_name",
        }
    ),
}
_PRIVATE_CORE_FIELDS = {
    "company": frozenset(),
    "patent": frozenset(),
    "professor": frozenset({"email", "office"}),
    "paper": frozenset({"pdf_path"}),
    "professor_paper_link": frozenset({"verified_by"}),
}
_PUBLIC_SUMMARY_FIELDS = {
    "company": frozenset(
        {"evaluation_summary", "profile_summary", "technology_route_summary"}
    ),
    "patent": frozenset({"summary_text"}),
    "professor": frozenset({"evaluation_summary", "profile_summary"}),
    "paper": frozenset({"summary_text", "summary_zh"}),
    "professor_paper_link": frozenset({"match_reason"}),
}
_PAYLOAD_FIELDS = frozenset(
    {
        "core_facts",
        "display_name",
        "evidence",
        "id",
        "last_updated",
        "object_type",
        "quality_status",
        "summary_fields",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {"confidence", "fetched_at", "snippet", "source_file", "source_type", "source_url"}
)
_PUBLIC_EVIDENCE_FIELDS = (
    "confidence",
    "fetched_at",
    "snippet",
    "source_type",
    "source_url",
)
_QUALITY_STATUSES = frozenset(
    {
        "ready",
        "needs_review",
        "low_confidence",
        "needs_enrichment",
        "partial",
        "rejected",
    }
)
_EVIDENCE_SOURCE_TYPES = frozenset(
    {"official_site", "xlsx_import", "public_web", "academic_platform", "manual_review"}
)
_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
_DATETIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"manifest contains duplicate key: {key}")
        result[key] = value
    return result


def load_selection_manifest(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load the one frozen P1 selection manifest, rejecting any contract drift."""
    manifest_path = Path(path)
    try:
        raw = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest cannot be loaded: {manifest_path}") from exc

    if not isinstance(manifest, dict):
        raise ValueError("manifest root must be an object")
    if _canonical_json(manifest) != _canonical_json(_EXPECTED_MANIFEST):
        raise ValueError("manifest does not match the frozen Accepted selection")

    rows = manifest["rows"]
    if len(rows) != manifest["expected_row_count"]:
        raise ValueError("manifest row count is inconsistent")
    row_set_sha256 = _canonical_sha256(sorted(rows, key=lambda row: row["id"]))
    if row_set_sha256 != manifest["selected_row_set_sha256"]:
        raise ValueError("manifest row-set hash is inconsistent")
    return copy.deepcopy(manifest)


def _source_stat_signature(source_stat: os.stat_result) -> tuple[int, ...]:
    return (
        source_stat.st_dev,
        source_stat.st_ino,
        source_stat.st_mode,
        source_stat.st_uid,
        source_stat.st_gid,
        source_stat.st_size,
        source_stat.st_mtime_ns,
        source_stat.st_ctime_ns,
    )


def _hash_open_file(file_descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    while chunk := os.read(file_descriptor, 1024 * 1024):
        digest.update(chunk)
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


def _reject_sidecars(source_path: Path) -> None:
    present = [
        str(Path(f"{source_path}{suffix}"))
        for suffix in _SIDECAR_SUFFIXES
        if os.path.lexists(Path(f"{source_path}{suffix}"))
    ]
    if present:
        raise ValueError(f"source sidecar files are forbidden: {present}")


def _open_verified_source(
    source_path: Path, source: dict[str, Any]
) -> tuple[int, tuple[int, ...]]:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    close_on_exec = getattr(os, "O_CLOEXEC", None)
    if no_follow is None or close_on_exec is None:
        raise ValueError("source platform lacks O_NOFOLLOW or O_CLOEXEC")

    try:
        file_descriptor = os.open(source_path, os.O_RDONLY | close_on_exec | no_follow)
    except OSError as exc:
        raise ValueError(
            f"source cannot be opened without following links: {source_path}"
        ) from exc

    try:
        source_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(source_stat.st_mode):
            raise ValueError("source must be a regular file")
        path_stat = os.stat(source_path, follow_symlinks=False)
        if (path_stat.st_dev, path_stat.st_ino) != (
            source_stat.st_dev,
            source_stat.st_ino,
        ):
            raise ValueError("source path does not identify the opened file")
        if source_stat.st_size != source["bytes"]:
            raise ValueError("source size does not match the Accepted gate")
        if _hash_open_file(file_descriptor) != source["sha256"]:
            raise ValueError("source sha256 does not match the Accepted gate")
        return file_descriptor, _source_stat_signature(source_stat)
    except BaseException:
        os.close(file_descriptor)
        raise


def _validate_datetime(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _DATETIME_PATTERN.fullmatch(value) is None:
        raise ValueError(f"row {field_name} is not a canonical UTC datetime")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"row {field_name} is not a valid datetime") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"row {field_name} must be UTC")
    return value


def _validate_http_url(
    value: object, field_name: str, *, optional: bool = False
) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str):
        raise ValueError(f"row {field_name} must be an HTTP(S) URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"row {field_name} must be an HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"row {field_name} must not contain credentials")


def _validate_public_values(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.endswith(("_path", "_sha256")):
                raise ValueError(f"public payload contains forbidden field: {key}")
            _validate_public_values(child)
    elif isinstance(value, list):
        for child in value:
            _validate_public_values(child)
    elif isinstance(value, str):
        if value.startswith(("/", "file://", "\\\\")) or ":\\" in value:
            raise ValueError("public payload contains a local path")


def _sanitize_evidence(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("row evidence must be a non-empty list")
    sanitized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != _EVIDENCE_FIELDS:
            raise ValueError("row evidence does not match the fixed field contract")
        if item["source_type"] not in _EVIDENCE_SOURCE_TYPES:
            raise ValueError("row evidence has an unsupported source type")
        _validate_http_url(item["source_url"], "evidence.source_url", optional=True)
        _validate_datetime(item["fetched_at"], "evidence.fetched_at")
        confidence = item["confidence"]
        if confidence is not None and (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0.0 <= confidence <= 1.0
        ):
            raise ValueError("row evidence confidence must be within [0, 1]")
        if item["snippet"] is not None and not isinstance(item["snippet"], str):
            raise ValueError("row evidence snippet must be a string or null")
        sanitized.append(
            {field: copy.deepcopy(item[field]) for field in _PUBLIC_EVIDENCE_FIELDS}
        )
    return sanitized


def _sanitize_payload(
    descriptor: dict[str, Any],
    database_row: tuple[object, ...],
    source_id: str,
) -> dict[str, Any]:
    if len(database_row) != 4 or not all(
        isinstance(value, str) for value in database_row
    ):
        raise ValueError(
            f"selected row has an invalid database shape: {descriptor['id']}"
        )
    row_id, object_type, display_name, payload_json = database_row
    raw_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    if (
        row_id != descriptor["id"]
        or object_type != descriptor["object_type"]
        or display_name != descriptor["display_name"]
        or raw_sha256 != descriptor["payload_json_sha256"]
    ):
        raise ValueError(f"selected row changed: {descriptor['id']}")

    try:
        payload = json.loads(payload_json, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"selected row payload is invalid JSON: {row_id}") from exc
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD_FIELDS:
        raise ValueError(f"selected row payload shape changed: {row_id}")
    if (
        payload["id"] != row_id
        or payload["object_type"] != object_type
        or payload["display_name"] != display_name
    ):
        raise ValueError(f"selected row embedded identity changed: {row_id}")
    if payload["quality_status"] not in _QUALITY_STATUSES:
        raise ValueError(f"selected row quality status is invalid: {row_id}")
    _validate_datetime(payload["last_updated"], "last_updated")

    core_facts = payload["core_facts"]
    summary_fields = payload["summary_fields"]
    if not isinstance(core_facts, dict) or set(core_facts) != (
        _PUBLIC_CORE_FIELDS[object_type] | _PRIVATE_CORE_FIELDS[object_type]
    ):
        raise ValueError(f"selected row core facts changed: {row_id}")
    if (
        not isinstance(summary_fields, dict)
        or set(summary_fields) != _PUBLIC_SUMMARY_FIELDS[object_type]
    ):
        raise ValueError(f"selected row summary fields changed: {row_id}")

    sanitized_core = {
        field: copy.deepcopy(core_facts[field])
        for field in sorted(_PUBLIC_CORE_FIELDS[object_type])
    }
    sanitized_summary = {
        field: copy.deepcopy(summary_fields[field])
        for field in sorted(_PUBLIC_SUMMARY_FIELDS[object_type])
    }
    sanitized_evidence = _sanitize_evidence(payload["evidence"])
    _validate_public_values(sanitized_core)
    _validate_public_values(sanitized_summary)
    _validate_public_values(sanitized_evidence)

    if object_type == "company":
        if sanitized_core["name"] != display_name:
            raise ValueError("company embedded name does not match its display name")
        _validate_http_url(sanitized_core["website"], "company.website")
    elif object_type == "patent":
        if sanitized_core["title"] != display_name:
            raise ValueError("patent embedded title does not match its display name")
    elif object_type == "professor":
        if sanitized_core["name"] != display_name:
            raise ValueError("professor embedded name does not match its display name")
        _validate_http_url(sanitized_core["homepage"], "professor.homepage")
    elif object_type == "paper":
        if sanitized_core["title"] != display_name:
            raise ValueError("paper embedded title does not match its display name")
    elif object_type == "professor_paper_link":
        expected_display = (
            f"{sanitized_core['professor_name']} -> {sanitized_core['paper_title']}"
        )
        if expected_display != display_name:
            raise ValueError("professor-paper link embedded identity changed")
        _validate_http_url(sanitized_core["evidence_url"], "link.evidence_url")

    artifact_material = {
        "payload_json_sha256": raw_sha256,
        "source_id": source_id,
    }
    return {
        "id": row_id,
        "object_type": object_type,
        "display_name": display_name,
        "core_facts": sanitized_core,
        "summary_fields": sanitized_summary,
        "evidence": sanitized_evidence,
        "last_updated": payload["last_updated"],
        "quality_status": payload["quality_status"],
        "payload_json_sha256": raw_sha256,
        "source_artifact_id": (
            "preview-source-artifact:sha256:" + _canonical_sha256(artifact_material)
        ),
    }


def _validate_selection(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    descriptors = [
        {
            "id": row["id"],
            "object_type": row["object_type"],
            "display_name": row["display_name"],
            "payload_json_sha256": row["payload_json_sha256"],
        }
        for row in rows
    ]
    if len(rows) != manifest["expected_row_count"]:
        raise ValueError("extracted row count does not match the manifest")
    if (
        _canonical_sha256(sorted(descriptors, key=lambda row: row["id"]))
        != manifest["selected_row_set_sha256"]
    ):
        raise ValueError("extracted row-set hash does not match the manifest")

    counts = Counter(
        row["object_type"]
        for row in rows
        if row["object_type"] in manifest["expected_public_domain_counts"]
    )
    if dict(sorted(counts.items())) != manifest["expected_public_domain_counts"]:
        raise ValueError("extracted public-domain counts do not match the manifest")

    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("extracted selection contains duplicate row IDs")
    for relationship in manifest["expected_relationships"]:
        source = by_id.get(relationship["source_id"])
        target = by_id.get(relationship["target_id"])
        if source is None or target is None:
            raise ValueError(
                "relationship endpoint is absent from the extracted selection"
            )
        if relationship["kind"] == "company_patent":
            if source["object_type"] != "company" or target["object_type"] != "patent":
                raise ValueError("company-patent endpoint kinds changed")
            if target["core_facts"]["company_ids"] != [source["id"]]:
                raise ValueError("company-patent endpoints changed")
        elif relationship["kind"] == "professor_authored_paper":
            link = by_id.get(relationship["link_row_id"])
            if (
                source["object_type"] != "professor"
                or target["object_type"] != "paper"
                or link is None
                or link["object_type"] != "professor_paper_link"
                or target["core_facts"]["professor_ids"] != [source["id"]]
                or link["core_facts"]["professor_id"] != source["id"]
                or link["core_facts"]["professor_name"] != source["display_name"]
                or link["core_facts"]["paper_id"] != target["id"]
                or link["core_facts"]["paper_title"] != target["display_name"]
            ):
                raise ValueError("professor-paper endpoints changed")
        else:  # pragma: no cover - the manifest equality gate prevents this branch
            raise ValueError("manifest contains an unsupported relationship kind")


def _verify_source_unchanged(
    file_descriptor: int,
    source_path: Path,
    source: dict[str, Any],
    before_signature: tuple[int, ...],
) -> None:
    after_stat = os.fstat(file_descriptor)
    path_stat = os.stat(source_path, follow_symlinks=False)
    if _source_stat_signature(after_stat) != before_signature:
        raise ValueError("source changed while the preview selection was extracted")
    if (path_stat.st_dev, path_stat.st_ino) != (after_stat.st_dev, after_stat.st_ino):
        raise ValueError("source changed while the preview selection was extracted")
    if _hash_open_file(file_descriptor) != source["sha256"]:
        raise ValueError("source changed while the preview selection was extracted")
    _reject_sidecars(source_path)


def extract_preview_selection(
    evidence_root: str | os.PathLike[str],
    manifest_path: str | os.PathLike[str],
) -> tuple[dict[str, Any], ...]:
    """Extract the frozen five-row preview selection without mutating source evidence."""
    manifest = load_selection_manifest(manifest_path)
    relative_path = PurePosixPath(manifest["source"]["relative_path"])
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("manifest source path must be a safe relative path")
    source_path = Path(evidence_root).joinpath(*relative_path.parts)
    _reject_sidecars(source_path)
    file_descriptor, before_signature = _open_verified_source(
        source_path, manifest["source"]
    )

    try:
        sqlite_path = quote(f"/proc/self/fd/{file_descriptor}", safe="/")
        sqlite_uri = f"file:{sqlite_path}?mode=ro&immutable=1"
        extracted: list[dict[str, Any]] = []
        with sqlite3.connect(sqlite_uri, uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            if connection.execute("PRAGMA query_only").fetchone() != (1,):
                raise ValueError("SQLite query_only could not be enabled")
            for descriptor in manifest["rows"]:
                matches = connection.execute(
                    "SELECT id, object_type, display_name, payload_json "
                    "FROM released_objects WHERE id = ?",
                    (descriptor["id"],),
                ).fetchall()
                if len(matches) != 1:
                    raise ValueError(
                        f"selected row is missing or duplicated: {descriptor['id']}"
                    )
                extracted.append(
                    _sanitize_payload(
                        descriptor,
                        matches[0],
                        manifest["source"]["source_id"],
                    )
                )

        _validate_selection(extracted, manifest)
        _verify_source_unchanged(
            file_descriptor,
            source_path,
            manifest["source"],
            before_signature,
        )
        return tuple(extracted)
    finally:
        os.close(file_descriptor)

"""Read-only DB/Milvus snapshot and two-level paper/chunk parity preflight.

This command never calls collection-creation, insert, upsert, delete, embedding,
or canonical-data write APIs.  It emits only hashes, counts, canonical IDs, and
environment metadata under the Slice A run directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
RUN_ROOT = REPO / ".agents" / "runs" / "close-retrieval-generation-contract"
PAPER_COLLECTION = "paper_chunks"
QUERY_VISIBLE_TABLES = (
    "company",
    "company_snapshot",
    "company_team_member",
    "paper",
    "paper_full_text",
    "paper_merge_alias",
    "professor",
    "professor_affiliation",
    "professor_company_role",
    "professor_paper_link",
)
RELEVANT_CODE_PATHS = (
    Path(__file__).resolve(),
    Path(__file__).with_name("paper_retrieval_gate.py").resolve(),
    (REPO / "apps/miroflow-agent/src/data_agents/paper/chunker.py").resolve(),
    (REPO / "apps/miroflow-agent/src/data_agents/quality/gating_contract.py").resolve(),
    (REPO / "apps/admin-console/backend/deps.py").resolve(),
)

RETRIEVAL_ACTIVE_V1_SQL = """
company: identity_status = 'resolved'
professor: identity_status = 'resolved' AND lifecycle_state = 'active'
paper: identity_status IN ('confirmed', 'unverified')
       AND coalesce(quality_status, 'needs_enrichment') <> 'rejected'
professor_paper_link: link_status = 'verified'
professor_company_role: link_status = 'verified'
secondary company_team_member:
  latest company_snapshot by (snapshot_created_at DESC, snapshot_id DESC)
  AND resolution_status = 'matched' AND resolved_professor_id IS NOT NULL
""".strip()

# The accepted make-partial-papers-retrievable rule is intentionally stricter
# than the current backfill query: partial admission is based only on collected
# paper_full_text abstract/intro richness, not summary/title convenience fields.
INDEX_ELIGIBLE_V1_WHERE = """
p.identity_status IN ('confirmed', 'unverified')
AND (
  p.quality_status = 'ready'
  OR (
    p.quality_status = 'partial'
    AND (
      nullif(btrim(coalesce(pft.abstract, '')), '') IS NOT NULL
      OR nullif(btrim(coalesce(pft.intro, '')), '') IS NOT NULL
    )
  )
)
""".strip()


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    return str(value)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def hash_canonical_rows(
    rows: Iterable[Mapping[str, Any]], *, identity_fields: Sequence[str]
) -> str:
    encoded: list[tuple[bytes, bytes]] = []
    for row in rows:
        identity = canonical_json_bytes([row.get(field) for field in identity_fields])
        encoded.append((identity, canonical_json_bytes(dict(row))))
    digest = hashlib.sha256()
    for identity, row_bytes in sorted(encoded):
        digest.update(struct.pack(">I", len(identity)))
        digest.update(identity)
        digest.update(struct.pack(">I", len(row_bytes)))
        digest.update(row_bytes)
    return digest.hexdigest()


def hash_float_vector(vector: Sequence[float]) -> str:
    digest = hashlib.sha256()
    digest.update(struct.pack(">I", len(vector)))
    for value in vector:
        digest.update(struct.pack(">f", float(value)))
    return digest.hexdigest()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ExpectedChunk:
    chunk_id: str
    paper_id: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ActualChunk:
    chunk_id: str
    paper_id: str
    content_sha256: str
    vector_sha256: str
    vector_dimension: int
    model_version: str | None = None
    chunker_version: str | None = None
    index_version: str | None = None
    write_id: str | None = None


@dataclass(frozen=True, slots=True)
class ParityReport:
    expected_papers: int
    actual_papers: int
    expected_chunks: int
    actual_chunks: int
    paper_id_parity: bool
    chunk_identity_parity: bool
    physical_version_parity: bool
    missing_paper_ids: tuple[str, ...]
    unexpected_paper_ids: tuple[str, ...]
    missing_chunk_ids: tuple[str, ...]
    unexpected_chunk_ids: tuple[str, ...]
    stale_content_chunk_ids: tuple[str, ...]
    conflicting_expected_chunk_ids: tuple[str, ...]
    conflicting_actual_chunk_ids: tuple[str, ...]
    unverifiable_version_chunk_ids: tuple[str, ...]
    expected_paper_ids_sha256: str
    actual_paper_ids_sha256: str
    expected_chunk_ids_sha256: str
    actual_chunk_ids_sha256: str

    @property
    def viable(self) -> bool:
        return (
            self.paper_id_parity
            and self.chunk_identity_parity
            and self.physical_version_parity
        )


def _hash_ids(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        encoded = value.encode("utf-8")
        digest.update(struct.pack(">I", len(encoded)))
        digest.update(encoded)
    return digest.hexdigest()


def compare_parity(
    expected: Sequence[ExpectedChunk], actual: Sequence[ActualChunk]
) -> ParityReport:
    expected_groups: dict[str, list[ExpectedChunk]] = {}
    for chunk in expected:
        expected_groups.setdefault(chunk.chunk_id, []).append(chunk)
    expected_by_id = {chunk_id: rows[0] for chunk_id, rows in expected_groups.items()}
    actual_groups: dict[str, list[ActualChunk]] = {}
    for chunk in actual:
        actual_groups.setdefault(chunk.chunk_id, []).append(chunk)
    actual_by_id = {chunk_id: rows[0] for chunk_id, rows in actual_groups.items()}

    expected_papers = {chunk.paper_id for chunk in expected}
    actual_papers = {chunk.paper_id for chunk in actual}
    expected_chunk_ids = set(expected_by_id)
    actual_chunk_ids = set(actual_by_id)
    shared_ids = expected_chunk_ids & actual_chunk_ids

    missing_papers = tuple(sorted(expected_papers - actual_papers))
    unexpected_papers = tuple(sorted(actual_papers - expected_papers))
    missing_chunks = tuple(sorted(expected_chunk_ids - actual_chunk_ids))
    unexpected_chunks = tuple(sorted(actual_chunk_ids - expected_chunk_ids))
    stale_content = tuple(
        sorted(
            chunk_id
            for chunk_id in shared_ids
            if expected_by_id[chunk_id].content_sha256
            != actual_by_id[chunk_id].content_sha256
        )
    )
    conflicting_expected = tuple(
        sorted(chunk_id for chunk_id, rows in expected_groups.items() if len(rows) != 1)
    )
    conflicting = tuple(
        sorted(chunk_id for chunk_id, rows in actual_groups.items() if len(rows) != 1)
    )
    unverifiable = tuple(
        sorted(
            chunk.chunk_id
            for chunk in actual
            if not all(
                (
                    chunk.model_version,
                    chunk.chunker_version,
                    chunk.index_version,
                    chunk.write_id,
                )
            )
        )
    )

    paper_parity = not missing_papers and not unexpected_papers
    chunk_parity = not (
        missing_chunks
        or unexpected_chunks
        or stale_content
        or conflicting_expected
        or conflicting
    )
    version_parity = chunk_parity and not unverifiable
    return ParityReport(
        expected_papers=len(expected_papers),
        actual_papers=len(actual_papers),
        expected_chunks=len(expected_chunk_ids),
        actual_chunks=len(actual),
        paper_id_parity=paper_parity,
        chunk_identity_parity=chunk_parity,
        physical_version_parity=version_parity,
        missing_paper_ids=missing_papers,
        unexpected_paper_ids=unexpected_papers,
        missing_chunk_ids=missing_chunks,
        unexpected_chunk_ids=unexpected_chunks,
        stale_content_chunk_ids=stale_content,
        conflicting_expected_chunk_ids=conflicting_expected,
        conflicting_actual_chunk_ids=conflicting,
        unverifiable_version_chunk_ids=unverifiable,
        expected_paper_ids_sha256=_hash_ids(expected_papers),
        actual_paper_ids_sha256=_hash_ids(actual_papers),
        expected_chunk_ids_sha256=_hash_ids(expected_chunk_ids),
        actual_chunk_ids_sha256=_hash_ids(actual_chunk_ids),
    )


def _primary_key_columns(conn: Any, table: str) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT a.attname AS column_name
        FROM pg_index i
        JOIN pg_attribute a
          ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = %s::regclass AND i.indisprimary
        ORDER BY array_position(i.indkey, a.attnum)
        """,
        (table,),
    ).fetchall()
    return tuple(row["column_name"] for row in rows)


def _capture_table(conn: Any, table: str) -> dict[str, Any]:
    keys = _primary_key_columns(conn, table)
    column_rows = conn.execute(
        """
        SELECT column_name, data_type, udt_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    columns = tuple(row["column_name"] for row in column_rows)
    order_columns = keys or columns
    quoted_order = ", ".join(f'"{column}"' for column in order_columns)
    query = f'SELECT * FROM "{table}" ORDER BY {quoted_order}'
    digest = hashlib.sha256()
    count = 0
    with conn.cursor() as cursor:
        cursor.execute(query)
        while True:
            batch = cursor.fetchmany(1000)
            if not batch:
                break
            for row in batch:
                row_bytes = canonical_json_bytes(dict(row))
                digest.update(struct.pack(">I", len(row_bytes)))
                digest.update(row_bytes)
                count += 1
    return {
        "table": table,
        "row_count": count,
        "primary_key": list(keys),
        "columns_sha256": hashlib.sha256(
            canonical_json_bytes([dict(row) for row in column_rows])
        ).hexdigest(),
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "ordered_rows_sha256": digest.hexdigest(),
    }


def capture_database_manifest(conn: Any) -> dict[str, Any]:
    tables = [_capture_table(conn, table) for table in QUERY_VISIBLE_TABLES]
    return {
        "projection_version": "slice-a-query-visible-db-v1",
        "tables": tables,
        "retrieval_active_rule_version": "retrieval-active-v1",
        "retrieval_active_rule_sha256": hashlib.sha256(
            RETRIEVAL_ACTIVE_V1_SQL.encode("utf-8")
        ).hexdigest(),
        "index_eligibility_rule_version": "index-eligibility-v1",
        "index_eligibility_rule_sha256": hashlib.sha256(
            INDEX_ELIGIBLE_V1_WHERE.encode("utf-8")
        ).hexdigest(),
        "manifest_sha256": hashlib.sha256(canonical_json_bytes(tables)).hexdigest(),
    }


def load_expected_chunks(conn: Any) -> tuple[ExpectedChunk, ...]:
    from src.data_agents.paper.chunker import chunk_paper

    query = f"""
        SELECT p.paper_id, p.title_clean AS title, p.year, p.venue,
               p.summary_zh, p.abstract_clean, pft.abstract, pft.intro
        FROM paper p
        LEFT JOIN paper_full_text pft ON pft.paper_id = p.paper_id
        WHERE {INDEX_ELIGIBLE_V1_WHERE}
        ORDER BY p.paper_id
    """
    expected: list[ExpectedChunk] = []
    with conn.cursor() as cursor:
        cursor.execute(query)
        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            for row in rows:
                abstract = (
                    row.get("summary_zh")
                    or row.get("abstract_clean")
                    or row.get("abstract")
                )
                chunks = chunk_paper(
                    paper_id=row["paper_id"],
                    title=row.get("title") or "",
                    year=row.get("year"),
                    venue=row.get("venue"),
                    abstract=abstract,
                    intro=row.get("intro"),
                )
                expected.extend(
                    ExpectedChunk(
                        chunk_id=chunk.chunk_id,
                        paper_id=chunk.paper_id,
                        content_sha256=hashlib.sha256(
                            chunk.content_text.encode("utf-8")
                        ).hexdigest(),
                    )
                    for chunk in chunks
                )
    return tuple(expected)


def _milvus_schema_manifest(client: Any) -> dict[str, Any]:
    description = client.describe_collection(collection_name=PAPER_COLLECTION)
    indexes: list[Any] = []
    for index_name in client.list_indexes(collection_name=PAPER_COLLECTION):
        indexes.append(
            client.describe_index(
                collection_name=PAPER_COLLECTION, index_name=index_name
            )
        )
    schema_payload = {"description": description, "indexes": indexes}
    return {
        "collection": PAPER_COLLECTION,
        "schema_index_sha256": hashlib.sha256(
            canonical_json_bytes(schema_payload)
        ).hexdigest(),
        "fields": [field.get("name") for field in description.get("fields", [])],
        "vector_dimension": _vector_dimension_from_description(description),
        "index_count": len(indexes),
    }


def _vector_dimension_from_description(description: Mapping[str, Any]) -> int:
    for field in description.get("fields", []):
        if field.get("name") != "content_vector":
            continue
        params = field.get("params") or {}
        dimension = params.get("dim")
        if dimension is not None:
            return int(dimension)
    return 0


def _milvus_vector_dimension(client: Any) -> int:
    return _vector_dimension_from_description(
        client.describe_collection(collection_name=PAPER_COLLECTION)
    )


def load_actual_chunks(client: Any) -> tuple[tuple[ActualChunk, ...], dict[str, Any]]:
    rows: list[ActualChunk] = []
    physical_rows: list[dict[str, Any]] = []
    vector_dimension = _milvus_vector_dimension(client)
    iterator = client.query_iterator(
        collection_name=PAPER_COLLECTION,
        batch_size=500,
        filter="",
        output_fields=[
            "chunk_id",
            "paper_id",
            "chunk_type",
            "segment_index",
            "year",
            "venue",
            "content_text",
        ],
    )
    try:
        while True:
            batch = iterator.next()
            if not batch:
                break
            for row in batch:
                content = str(row.get("content_text") or "")
                actual = ActualChunk(
                    chunk_id=str(row["chunk_id"]),
                    paper_id=str(row["paper_id"]),
                    content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    # Vector bytes are covered by the full physical Milvus Lite
                    # file checksum captured before/after the ordered query.
                    vector_sha256="physical-target-checksum",
                    vector_dimension=vector_dimension,
                    # The current collection has no version/write tuple fields.
                    model_version=row.get("model_version"),
                    chunker_version=row.get("chunker_version"),
                    index_version=row.get("index_version"),
                    write_id=row.get("write_id"),
                )
                rows.append(actual)
                physical_rows.append(
                    {
                        **asdict(actual),
                        "chunk_type": row.get("chunk_type"),
                        "segment_index": row.get("segment_index"),
                        "year": row.get("year"),
                        "venue": row.get("venue"),
                    }
                )
    finally:
        iterator.close()
    schema = _milvus_schema_manifest(client)
    schema.update(
        {
            "entity_count": len(rows),
            "ordered_physical_rows_sha256": hash_canonical_rows(
                physical_rows, identity_fields=("chunk_id", "paper_id")
            ),
        }
    )
    return tuple(rows), schema


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _relevant_code_hash() -> str:
    digest = hashlib.sha256()
    for path in RELEVANT_CODE_PATHS:
        data = path.read_bytes()
        relative_path = path.relative_to(REPO).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(struct.pack(">I", len(data)))
        digest.update(data)
    return digest.hexdigest()


def _milvus_physical_path() -> Path | None:
    configured = os.environ.get("CHAT_MILVUS_URI") or os.environ.get("MILVUS_URI")
    if configured and "://" in configured:
        return None
    path = (
        Path(configured)
        if configured
        else REPO / "apps" / "miroflow-agent" / "milvus.db"
    )
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path if path.is_file() else None


def _write_json(path: Path, payload: Any) -> None:
    content = (
        json.dumps(_json_value(payload), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"immutable artifact conflict: {path}") from None


def run_preflight() -> tuple[Path, ParityReport, bool]:
    from backend.deps import _get_milvus_client, get_pg_pool

    pool = get_pg_pool()
    client = _get_milvus_client()
    physical_path = _milvus_physical_path()
    if physical_path is None:
        raise RuntimeError(
            "Slice A requires a trusted immutable physical checksum for this Milvus target"
        )

    with pool.connection() as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            db_before = capture_database_manifest(conn)
            expected = load_expected_chunks(conn)

    physical_before_sha256 = hash_file(physical_path)
    actual_before, milvus_before = load_actual_chunks(client)
    milvus_before["physical_target_sha256"] = physical_before_sha256
    milvus_before["physical_target_bytes"] = physical_path.stat().st_size
    parity = compare_parity(expected, actual_before)

    with pool.connection() as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            db_after = capture_database_manifest(conn)
    actual_after, milvus_after = load_actual_chunks(client)
    physical_after_sha256 = hash_file(physical_path)
    milvus_after["physical_target_sha256"] = physical_after_sha256
    milvus_after["physical_target_bytes"] = physical_path.stat().st_size

    stable = (
        db_before["manifest_sha256"] == db_after["manifest_sha256"]
        and milvus_before["ordered_physical_rows_sha256"]
        == milvus_after["ordered_physical_rows_sha256"]
        and milvus_before["schema_index_sha256"] == milvus_after["schema_index_sha256"]
        and physical_before_sha256 == physical_after_sha256
    )
    snapshot_seed = canonical_json_bytes(
        {
            "db": db_before["manifest_sha256"],
            "milvus": milvus_before["ordered_physical_rows_sha256"],
            "schema": milvus_before["schema_index_sha256"],
            "physical_target": physical_before_sha256,
        }
    )
    snapshot_id = f"paper-snapshot-{hashlib.sha256(snapshot_seed).hexdigest()[:16]}"
    head = _git_head()
    relevant_hash = _relevant_code_hash()
    code_id = f"{head[:12]}-eval-{relevant_hash[:12]}"
    artifact_dir = RUN_ROOT / "artifacts" / snapshot_id / code_id

    manifest_payload = {
        "schema_version": "slice-a-snapshot-manifest-v1",
        "snapshot_id": snapshot_id,
        "code_sha": head,
        "evaluator_code_sha256": relevant_hash,
        "database_before": db_before,
        "database_after": db_after,
        "milvus_before": milvus_before,
        "milvus_after": milvus_after,
        "before_after_stable": stable,
    }
    parity_payload = {
        "schema_version": "slice-a-paper-chunk-parity-v1",
        **asdict(parity),
        "viable": parity.viable,
        "snapshot_stable": stable,
    }
    environment_payload = {
        "schema_version": "slice-a-environment-v1",
        "python": sys.version.split()[0],
        "database_url_configured": bool(os.environ.get("DATABASE_URL")),
        "milvus_uri": os.environ.get("CHAT_MILVUS_URI")
        or os.environ.get("MILVUS_URI")
        or "apps/miroflow-agent/milvus.db",
        "proxy_variables_removed": all(
            not os.environ.get(name)
            for name in (
                "http_proxy",
                "https_proxy",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "all_proxy",
                "ALL_PROXY",
            )
        ),
    }
    _write_json(artifact_dir / "manifest.json", manifest_payload)
    _write_json(artifact_dir / "parity.json", parity_payload)
    _write_json(artifact_dir / "environment.json", environment_payload)

    hashes = {
        name: hashlib.sha256((artifact_dir / name).read_bytes()).hexdigest()
        for name in ("manifest.json", "parity.json", "environment.json")
    }
    _write_json(artifact_dir / "artifact-hashes.json", hashes)
    return artifact_dir, parity, stable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    artifact_dir, parity, stable = run_preflight()
    print(
        json.dumps(
            {
                "artifact_dir": str(artifact_dir.relative_to(REPO)),
                "snapshot_stable": stable,
                "expected_papers": parity.expected_papers,
                "actual_papers": parity.actual_papers,
                "missing_papers": len(parity.missing_paper_ids),
                "unexpected_papers": len(parity.unexpected_paper_ids),
                "expected_chunks": parity.expected_chunks,
                "actual_chunks": parity.actual_chunks,
                "missing_chunks": len(parity.missing_chunk_ids),
                "unexpected_chunks": len(parity.unexpected_chunk_ids),
                "stale_content_chunks": len(parity.stale_content_chunk_ids),
                "unverifiable_version_chunks": len(
                    parity.unverifiable_version_chunk_ids
                ),
                "viable": parity.viable,
            },
            sort_keys=True,
        )
    )
    return 0 if stable and parity.viable else 1


if __name__ == "__main__":
    raise SystemExit(main())

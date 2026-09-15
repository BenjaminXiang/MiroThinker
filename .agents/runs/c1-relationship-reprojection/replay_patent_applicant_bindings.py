"""C1 replay: how many patent→company bindings reach the relationship layer?

Reconstructs the run15 seeding inputs from the sealed pack plus the staged
released-objects database (both read-only), then runs the production seed
function twice:

- **pre-fix universe** — only `s12a-released-objects-full-v1` rows, which is
  what the old `payload["id"]` filter over the raw landed rows could index;
- **post-fix universe** — every admitted object (`row_by_object`), rebuilt here
  from the pack's `source_identity_assignments` (one entry per object) and the
  objects' field assertions (`core_facts` view).

It also runs the new D0 reconciliation with both seed sets: the pre-fix set must
be rejected, the post-fix set must be accepted with `unexplained_missing = 0`.

Read-only: the pack and the staged source are only opened for reading, and the
optional scratch copy is written under `--scratch` (default `/tmp`).  Nothing is
written under `/var/tmp/mirothinker-data-v2/`.

Usage:
    cd apps/miroflow-agent
    uv run python ../../../.agents/runs/c1-relationship-reprojection/replay_patent_applicant_bindings.py \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-run15-sealed \
        --released-objects-db /var/tmp/mirothinker-data-v2/staging-v2/7dd904de3cf6bc1aaaef54b1be4658d7320061a096d203d156b4f5d640bf951e.source \
        --json-out ../.agents/runs/c1-relationship-reprojection/replay-run15.json
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import sys

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "apps" / "miroflow-agent")
)

from src.data_agents.canonical_v2 import knowledge_build_isolated as build  # noqa: E402

NOW = datetime(2026, 9, 13, 15, 31, 39, tzinfo=timezone.utc)
RELEASED_OBJECTS_DB_SHA256_FILENAME = (
    "7dd904de3cf6bc1aaaef54b1be4658d7320061a096d203d156b4f5d640bf951e.source"
)


@dataclass(frozen=True, slots=True)
class _ReplayRecord:
    """Stand-in for SourceRecord: the seed stage reads record_id/parsed_at only."""

    record_id: str
    parsed_at: datetime


@dataclass(frozen=True, slots=True)
class _ReplayArtifact:
    artifact_id: str


def _replay_row(object_id: str, payload: dict[str, object], source_id: str):
    return build._ParsedReleasedObject(
        source_id=source_id,
        source_batch_id="replay",
        record=_ReplayRecord(record_id=f"record:replay:{object_id}", parsed_at=NOW),
        artifact=_ReplayArtifact(artifact_id="artifact:replay"),
        payload=payload,
    )


def _load_pack(pack_dir: Path) -> dict[str, object]:
    with (pack_dir / "relationships.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def _released_object_ids(db_path: Path, scratch: Path) -> set[str]:
    scratch.mkdir(parents=True, exist_ok=True)
    local = scratch / RELEASED_OBJECTS_DB_SHA256_FILENAME
    if not local.exists():
        shutil.copyfile(db_path, local)
    connection = sqlite3.connect(f"file:{local}?mode=ro", uri=True)
    try:
        return {row[0] for row in connection.execute("select id from released_objects")}
    finally:
        connection.close()


def _core_facts_by_object(assertions: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Rebuild each object's `core_facts` view from its retained field assertions."""

    core: dict[str, dict[str, object]] = {}
    wanted = {"name", "normalized_name", "applicants", "company_ids", "company_roles"}
    for assertion in assertions:
        field_path = assertion.get("field_path")
        if field_path not in wanted:
            continue
        object_id = str(assertion["source_identity_id"]).removeprefix(
            "source-released-object:"
        )
        core.setdefault(object_id, {})[str(field_path)] = assertion["value"]
    return core


def _universe(
    *,
    object_ids: set[str],
    domain_by_object: dict[str, str],
    core_by_object: dict[str, dict[str, object]],
):
    source_ids = {
        "company": build._P4_COMPANY_FULL_SOURCE_ID,
        "patent": build._P4_PATENT_FULL_SOURCE_ID,
        "paper": build._P4_PAPER_SALVAGE_SOURCE_ID,
        "professor": build._P4_PROFESSOR_FULL_SOURCE_ID,
    }
    universe = {}
    for object_id in sorted(object_ids):
        domain = domain_by_object.get(object_id)
        universe[object_id] = _replay_row(
            object_id,
            {
                "id": object_id,
                "object_type": domain,
                "core_facts": core_by_object.get(object_id, {}),
            },
            source_ids.get(domain or "", "replay:unknown"),
        )
    return universe


def _bound_company_ids_by_patent(assertions: list[dict[str, object]]):
    bound: dict[str, tuple[str, ...]] = {}
    for assertion in assertions:
        if assertion.get("field_path") != "applicants":
            continue
        value = assertion.get("value")
        if not isinstance(value, list):
            continue
        patent_object_id = str(assertion["source_identity_id"]).removeprefix(
            "source-released-object:"
        )
        bound_ids = tuple(
            entry["canonical_company_id"]
            for entry in value
            if isinstance(entry, dict)
            and isinstance(entry.get("canonical_company_id"), str)
            and entry["canonical_company_id"].startswith("company-")
        )
        if bound_ids:
            bound.setdefault(patent_object_id, bound_ids)
    return bound


def _seed_counts(
    *,
    universe,
    canonical_by_source,
    domain_by_canonical,
    bound,
    released_ids: set[str] | None,
):
    if released_ids is not None:
        universe = {
            object_id: row
            for object_id, row in universe.items()
            if object_id in released_ids
        }
    seeds = build._typed_relationship_seeds(
        object_rows_by_id=universe,
        supplemental_rows=(),
        canonical_by_source=canonical_by_source,
        canonical_domains=domain_by_canonical,
        bound_company_ids_by_patent=bound,
    )
    pairs = {
        (
            canonical_by_source[f"source-released-object:{seed.source_object_id}"],
            canonical_by_source[f"source-released-object:{seed.target_object_id}"],
        )
        for seed in seeds
        if seed.relationship_type_id == "patent_has_applicant"
    }
    lanes: dict[str, int] = {}
    types: dict[str, int] = {}
    for seed in seeds:
        types[seed.relationship_type_id] = types.get(seed.relationship_type_id, 0) + 1
        if seed.relationship_type_id != "patent_has_applicant":
            continue
        lane = str(
            seed.evidence_metadata.get("match_kind")
            or seed.evidence_metadata.get("source_field")
            or "unknown"
        )
        lanes[lane] = lanes.get(lane, 0) + 1
    return seeds, pairs, lanes, types


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--released-objects-db", required=True, type=Path)
    parser.add_argument("--scratch", default=Path("/tmp/c1-relationship-scratch"), type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    payload = _load_pack(args.pack)
    request = payload["relationship_projection_request"]
    public = request["internal_reference_projection_request"][
        "public_domain_projection_request"
    ]
    canonical_by_source = {
        item["source_identity_id"]: item["canonical_identity_id"]
        for item in public["source_identity_assignments"]
    }
    domain_by_canonical = {
        item["canonical_identity_id"]: item["entity_type"]
        for item in public["canonical_identities"]
    }
    object_ids = {
        key.removeprefix("source-released-object:") for key in canonical_by_source
    }
    domain_by_object = {
        object_id: domain_by_canonical[canonical_id]
        for object_id, canonical_id in (
            (key.removeprefix("source-released-object:"), value)
            for key, value in canonical_by_source.items()
        )
        if canonical_id in domain_by_canonical
    }
    core_by_object = _core_facts_by_object(public["source_assertions"])
    bound = _bound_company_ids_by_patent(public["source_assertions"])
    released_ids = _released_object_ids(args.released_objects_db, args.scratch)

    universe = _universe(
        object_ids=object_ids,
        domain_by_object=domain_by_object,
        core_by_object=core_by_object,
    )
    document_pairs = {
        (
            canonical_by_source[f"source-released-object:{patent_object_id}"],
            company_canonical_id,
        )
        for patent_object_id, company_ids in bound.items()
        if f"source-released-object:{patent_object_id}" in canonical_by_source
        for company_canonical_id in company_ids
    }

    report: dict[str, object] = {
        "pack": str(args.pack),
        "admitted_objects": len(object_ids),
        "released_objects": len(released_ids),
        "document_binding_entries": sum(len(v) for v in bound.values()),
        "document_binding_pairs": len(document_pairs),
        "document_bound_patents": len({p for p, _ in document_pairs}),
        "document_bound_companies": len({c for _, c in document_pairs}),
        "relationship_edges_in_pack": sum(
            1
            for item in request["candidates"]
            if item["relationship_type_id"] == "patent_has_applicant"
        ),
    }

    for label, released_filter in (
        ("pre_fix", released_ids),
        ("post_fix", None),
    ):
        seeds, pairs, lanes, types = _seed_counts(
            universe=universe,
            canonical_by_source=canonical_by_source,
            domain_by_canonical=domain_by_canonical,
            bound=bound,
            released_ids=released_filter,
        )
        rejected = False
        try:
            build._reconcile_patent_company_bindings(
                bound_company_ids_by_patent=bound,
                seed_object_rows=build._relationship_seed_object_rows(
                    universe
                    if released_filter is None
                    else {
                        object_id: row
                        for object_id, row in universe.items()
                        if object_id in released_filter
                    }
                ),
                canonical_by_source=canonical_by_source,
                typed_seeds=seeds,
            )
        except build.IsolatedKnowledgeBuildError:
            rejected = True
        report[label] = {
            "patent_has_applicant_edges": len(pairs),
            "seeding_lanes": dict(sorted(lanes.items())),
            "typed_seed_types": dict(sorted(types.items())),
            "missing_document_pairs": len(document_pairs - pairs),
            "missing_sample": sorted(
                [list(pair) for pair in (document_pairs - pairs)][:5]
            ),
            "reconciliation_rejected": rejected,
        }

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.json_out is not None:
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

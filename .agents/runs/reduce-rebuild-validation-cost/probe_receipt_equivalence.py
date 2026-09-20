"""Equivalence probe (slice B): recomputed hash vs the manifest's receipt.

One pack load, every substitution slice B would make, each row printed as it is
computed. Nothing is modified; the production loader is used as-is.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ARGS = json.loads(Path("/tmp/boot-prof/probe-args.json").read_text())

from src.data_agents.canonical_v2 import serving_pack_loader as loader  # noqa: E402

authority = loader.open_serving_pack_authority(
    pack_dir=Path(ARGS["pack_dir"]),
    expected_release_id=ARGS["release_id"],
    expected_index_marker_sha256=ARGS["marker"],
    expected_forbidden_milvus_path=Path(ARGS["milvus"]),
)
manifest = authority.manifest
bundle = authority.release_bundle
index_request = authority.index_projection_request

verdicts: list[bool] = []


def compare(label: str, recomputed: str, receipt: str) -> None:
    equal = recomputed == receipt
    verdicts.append(equal)
    print(f"{'EQUAL   ' if equal else 'MISMATCH'}  {label}", flush=True)
    if not equal:
        print(f"          recomputed={recomputed}", flush=True)
        print(f"          manifest  ={receipt}", flush=True)


def receipt_of(model: object, field: str) -> str:
    return getattr(model, field)


# --- B1/B3: the value the planner and the consumer runtime recompute -----------
compare(
    "B1/B3 index_projection_request_sha256  [dump WITHOUT exclude_unset — as the two call sites compute it]",
    loader._canonical_sha256(index_request.model_dump(mode="json")),
    manifest.index_projection_request_sha256,
)
compare(
    "       index_projection_request_sha256  [dump WITH exclude_unset — as the loader's own check computes it]",
    loader._canonical_sha256(index_request.model_dump(mode="json", exclude_unset=True)),
    manifest.index_projection_request_sha256,
)

# --- B2: the value create_serving_pack_knowledge_read recomputes ---------------
relationship_request = getattr(bundle, "relationship_projection_request", None)
if relationship_request is None:
    print("SKIP    B2 relationship_request — bundle has no relationship_projection_request")
else:
    compare(
        "B2    relationship_request_sha256  [bundle.relationship_projection_request]",
        loader._canonical_sha256(relationship_request.model_dump(mode="json")),
        manifest.relationship_request_sha256,
    )

# --- content hashes the pack also carries, to show they already come from models
for label, model, receipt in (
    ("candidate_projection_result.content_sha256",
     index_request.candidate_projection_result,
     manifest.candidate_projection_result_content_sha256),
    ("internal_reference_projection_result.content_sha256",
     getattr(index_request.candidate_projection_request,
             "internal_reference_projection_result", None),
     manifest.internal_reference_projection_result_content_sha256),
    ("index_result.content_sha256",
     getattr(bundle, "index_result", None),
     manifest.index_result_content_sha256),
    ("institution_catalog.content_sha256",
     authority.institution_catalog,
     manifest.institution_catalog_content_sha256),
):
    if model is None:
        print(f"SKIP    {label} (absent)", flush=True)
        continue
    compare(f"       {label}", receipt_of(model, "content_sha256"), receipt)

# --- for information: the manifest's own self-hash check ----------------------
compare(
    "       manifest_sha256 (self-binding check, _validate_manifest_hash)",
    loader._canonical_sha256(bundle.manifest.model_dump(mode="json", exclude={"manifest_sha256"})),
    bundle.manifest.manifest_sha256,
)

print()
print(("ALL EQUAL" if all(verdicts) else "MISMATCH PRESENT"), f"({len(verdicts)} rows)", flush=True)
sys.exit(0 if all(verdicts) else 1)

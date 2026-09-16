"""In-process conservation replay (admit-unanchored-papers validation).

Answers ONE question at minutes-scale instead of a 10h build: do
salvage-created papers (anchored AND unanchored) survive identity
resolution with the new admission gate?

Method: feed REAL rows from the live candidate DB's landing layer
(released 5,561 + professor_full + professor-paper links + small s12
batches + a salvage SAMPLE) straight into _map_public_authority, and
abort at the decision seam (a stub adapter) — the decision request then
carries identity_result.current_canonical_identities, which we count by
population.

Gate-pinning makes a batch-subset *build* impossible; this replay is the
subset equivalent that the tamper-proofing still allows.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path

import psycopg

WORKTREE = Path("/home/longxiang/MiroThinker/.worktrees/data-rebuild")
APP_ROOT = WORKTREE / "apps/miroflow-agent"
sys.path.insert(0, str(APP_ROOT))

DSN = "postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_v2_20260819_r1"
SALVAGE_SAMPLE = 300
NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)

module = import_module(
    "src.data_agents.canonical_v2.knowledge_build_isolated"
)


class _Abort(Exception):
    pass


captured: dict[str, object] = {}


class _CapturingAdapter:
    authority_sha256 = "replay-conservation"

    def adjudicate(self, request, /):
        captured["source_identities"] = len(request.source_identities)
        identities = request.canonical_identities
        by_type = Counter(i.entity_type for i in identities)
        captured["by_type"] = dict(by_type)
        captured["canonical_ids"] = {i.canonical_identity_id for i in identities}
        raise _Abort("decision seam reached — capture complete")


def _authority_key(batch_id: str) -> str:
    return next(
        key
        for key, value in module._SUPPLEMENTAL_SOURCE_AUTHORITIES.items()
        if value.source_batch_id == batch_id
    )


def load_rows() -> tuple[tuple, set[str]]:
    conn = psycopg.connect(DSN)
    included_batches = {
        "s12a-released-objects-full-v1": None,
        "p4-professor-full-v1": None,
        "p4-professor-paper-links-v1": None,
        "p4-patent-full-v1": None,
        "p4-company-full-v1": None,
        "p4-applicant-binding-full-v1": None,
        "s12f-applicant-binding-v1": None,
        "s12f-company-backfill-v1": None,
        "s12e-professor-backfill-v1": None,
        "s12c-r7-company-workbook-supplement-v1": None,
        "s12c-r7-company-knowledge-v1": None,
        "s12c-r7-professor-company-roles-v1": None,
        "s12c-r7-patent-identifiers-v1": None,
        "s12c-r7-paper-identifiers-v1": None,
    }
    rows: list = []
    salvage_rows: list = []
    salvage_paper_ids: set[str] = set()
    artifacts: dict[str, object] = {}
    for batch_id in list(included_batches) + ["p4-paper-salvage-v1"]:
        cur = conn.execute(
            "SELECT record_id, payload, record_locator FROM landing.source_record "
            "WHERE source_batch_id = %s ORDER BY record_ordinal",
            (batch_id,),
        )
        n = 0
        for record_id, payload, locator in cur.fetchall():
            if batch_id == "p4-paper-salvage-v1":
                if n >= SALVAGE_SAMPLE and "Crop selection reduces" not in (
                    payload.get("title") or ""
                ):
                    n += 1
                    continue
                salvage_paper_ids.add(payload.get("paper_id") or "")
            elif batch_id == "s12a-released-objects-full-v1":
                raw = payload.get("payload_json")
                if isinstance(raw, str):
                    payload = json.loads(raw)
            source_id = (
                module._RELEASED_OBJECTS_SOURCE_ID
                if batch_id == "s12a-released-objects-full-v1"
                else _authority_key(batch_id)
            )
            if batch_id not in artifacts:
                artifacts[batch_id] = module.EvidenceArtifact(
                    artifact_id=f"artifact:replay:{batch_id}",
                    source_kind="historical_jsonl",
                    source_locator=batch_id,
                    content_sha256="0" * 64,
                    byte_size=1,
                    acquired_at=NOW,
                    run_id="replay-run",
                )
            record = module.SourceRecord(
                record_id=record_id,
                artifact_id=artifacts[batch_id].artifact_id,
                source_batch_id=batch_id,
                record_locator=locator or batch_id,
                parse_run_id="replay-run",
                parser_name="historical_jsonl",
                parser_version="v1",
                schema_version="historical-jsonl-record-v1",
                parse_status=module.ParseStatus.parsed,
                payload=payload,
                parsed_at=NOW,
            )
            row = module._ParsedReleasedObject(
                source_id=source_id,
                source_batch_id=batch_id,
                record=record,
                artifact=artifacts[batch_id],
                payload=payload,
            )
            if batch_id == "p4-paper-salvage-v1":
                salvage_rows.append(row)
            else:
                rows.append(row)
            n += 1
        print(f"loaded {batch_id}: {n} rows", flush=True)
    conn.close()
    return (*rows, *salvage_rows), salvage_paper_ids


def main() -> None:
    rows, salvage_ids = load_rows()
    print(f"TOTAL replay rows: {len(rows)} (salvage sample {len(salvage_ids)})", flush=True)
    request = module.BuildCandidateRequest(
        run_id="replay-conservation-v1",
        candidate_release_id="candidate-v2-20260819-r1",
        source_batch_ids=(
            "s12a-released-objects-full-v1",
            "p4-professor-full-v1",
            "p4-professor-paper-links-v1",
            "p4-paper-salvage-v1",
            "s12f-company-backfill-v1",
            "s12e-professor-backfill-v1",
            "s12c-r7-company-workbook-supplement-v1",
            "s12c-r7-company-knowledge-v1",
            "s12c-r7-professor-company-roles-v1",
            "s12c-r7-patent-identifiers-v1",
            "s12c-r7-paper-identifiers-v1",
        ),
        parser_versions={
            "released_objects_sqlite": "canonical-v2-s12a-full-table-v1",
            "historical_jsonl": "v1",
            "historical_xlsx": "v1",
        },
        policy_versions={
            "released_objects_mapper": "canonical-v2-released-objects-mapper-v2",
            "path_eligibility": "path-eligibility-v1",
        },
        model_versions={"embedding": "recorded-embedding-v1"},
    )
    result = module._map_public_authority(
        request=request,
        rows=rows,
        initial_gaps=(),
        decision_adapter=_CapturingAdapter(),
        now=NOW,
    )
    (
        identity_request,
        identity_result,
        decision_result,
        domain_request,
        domain_result,
        links,
        gaps,
    ) = result
    from collections import Counter as _C
    by_type = _C(i.entity_type for i in identity_result.current_canonical_identities)
    canon_ids = {i.canonical_identity_id for i in identity_result.current_canonical_identities}
    print("\n=== CONSERVATION REPORT (full _map_public_authority) ===")
    print("source_identities input:", len(identity_result.source_identities))
    print("canonical identities by type:", dict(by_type))
    paper_ids = {cid for cid in canon_ids if cid.startswith("paper")}
    print("paper canonical identities:", len(paper_ids))
    salvage_source_ids = {
        f"source-released-object:{pid}" for pid in salvage_ids if pid
    }
    sample_canonical = [
        i.canonical_identity_id
        for i in identity_result.current_canonical_identities
        if salvage_source_ids & set(i.source_identity_ids)
    ]
    print(
        f"salvage sample survival (source-lineage matched): "
        f"{len(sample_canonical)}/{len(salvage_ids)} "
        f"({len(sample_canonical) * 100 // max(1, len(salvage_ids))}%)"
    )
    if sample_canonical:
        sample_set = set(sample_canonical)
        unanchored_sample = [
            d
            for d in domain_result.inclusion_decisions
            if d.subject_identity_id in sample_set
            and d.limitations == ("paper_unanchored",)
        ]
        anchored_sample = [
            d
            for d in domain_result.inclusion_decisions
            if d.subject_identity_id in sample_set and not d.limitations
        ]
        print(
            f"  sample inclusion: anchored-admitted={len(anchored_sample)} "
            f"unanchored-limited={len(unanchored_sample)}"
        )
    print("domain projection counts_by_domain:", domain_result.counts_by_domain)
    incl = _C(
        (d.domain if hasattr(d, "domain") else "?", d.outcome.value, d.limitations)
        for d in domain_result.inclusion_decisions
    )
    print("inclusion outcomes (domain, outcome, limitations) -> count:")
    for key, n in sorted(incl.items(), key=lambda kv: -kv[1])[:12]:
        print("   ", key, "->", n)
    anchor_gaps = [g for g in gaps if "professor_anchor" in str(getattr(getattr(g, "signal", None), "affected_paths", ()))]
    print("anchor-gap count (unanchored papers, kept):", len(anchor_gaps))
    print("links:", len(links))

    # ---- full-chain extension: relationship + index authorities ----------
    (
        internal_request,
        internal_result,
        candidate_request,
        candidate_result,
    ) = module._internal_candidate_authority(
        request=request,
        domain_request=domain_request,
        domain_result=domain_result,
        now=NOW,
    )
    relationship_request, relationship_result = module._relationship_authority(
        request=request,
        identity_result=identity_result,
        decision_result=decision_result,
        domain_result=domain_result,
        internal_request=internal_request,
        internal_result=internal_result,
        links=links,
        now=NOW,
        source_rows=rows,
    )
    rel_counts = _C(
        d.relationship_type_id for d in relationship_result.relationship_decisions
    )
    print("\n=== RELATIONSHIP AUTHORITY ===")
    print("relationship decisions by type:", dict(rel_counts))
    current_rels = _C(
        cr.relationship_type_id
        for cr in relationship_result.current_relationships
    )
    print("current relationships by type:", dict(current_rels))

    _, _, index_request, pure_index_result = module._index_authority(
        request=request,
        candidate_request=candidate_request,
        candidate_result=candidate_result,
        now=NOW,
    )
    print("\n=== INDEX AUTHORITY ===")
    doc_domains = _C(d.domain for d in pure_index_result.lookup_documents)
    print("lookup documents by domain:", dict(doc_domains))
    doc_limits = _C(
        (d.domain, tuple(d.eligibility_limitations))
        for d in pure_index_result.lookup_documents
        if d.eligibility_limitations
    )
    print("documents with limitations:", dict(doc_limits))
    print("vector points:", len(pure_index_result.points))


if __name__ == "__main__":
    main()

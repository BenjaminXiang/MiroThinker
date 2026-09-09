#!/usr/bin/env python3
"""B1 round-3 evidence: Gate C — scan candidates survive `_apply_constraints`.

Round-2 repro of the g17-t1 ("优必选有哪些专利") loss point, flipped to a
GREEN guard after the Gate C fix. Scan-built `EvidenceItem`s carry no
`local_projection_trace` by design; `_apply_constraints` now derives a
displayed-anchor witness from the value endpoint of the candidate's own claim
binding (mirror of the selector's `_claim_binding_binds_anchor`), so the
displayed_entity_set slot admits the candidate instead of hard-rejecting it.

Run from the worktree's apps/miroflow-agent:

    cd .worktrees/canonical-v2-s11-consolidation/apps/miroflow-agent
    uv run python ../../../../.agents/runs/close-workbook-gaps/repro_constraint_gate_scan_items.py

Expected output (round 3, 2026-09-10): eligible: 1, outcome accepted.
Read-only: builds models in memory, touches no data.
"""

import json

from src.data_agents.canonical_v2.knowledge_read import (
    EvidenceClaimBinding,
    EvidenceItem,
    FusedCandidate,
    ProtectedSlot,
    _apply_constraints,
)

COMPANY = "company-c-64e631c0e0cd9e91d032d209"  # 优必选 (s12f pack)
PATENT = "patent-c-6073ea45292c7f4009cae8d5"  # CN117873146A

# Exact replica of the EvidenceItem built by _direct_patent_applicant_scan
# (knowledge_read_isolated.py): claim_binding present, local_projection_trace
# absent by design (scan edges have no per-edge relationship authority).
scan_evidence = EvidenceItem(
    evidence_id=f"evidence:direct-patent:{PATENT}",
    object_id=PATENT,
    domain="patent",
    lane="relationship",
    source_nature="local",
    source_locator=f"artifact:patent:{PATENT}#applicants",
    snippet=json.dumps(
        {
            "patent_number": "CN117873146A",
            "title": "一种机器人的落地控制方法、机器人及终端设备",
            "applicant": "深圳市优必选科技股份有限公司",
            "company_name": "优必选",
        },
        ensure_ascii=False,
        sort_keys=True,
    ),
    score=0.8,
    claim_binding=EvidenceClaimBinding(
        subject_id=f"canonical:patent:{PATENT}",
        predicate="patent_has_applicant",
        value=f"canonical:company:{COMPANY}",
        status="accepted",
    ),
)
fused = FusedCandidate(
    result_id=f"fused-result:{PATENT}",
    canonical_id=PATENT,
    display_name="一种机器人的落地控制方法、机器人及终端设备",
    domain="patent",
    raw_candidate_ids=(f"direct-patent:{PATENT}",),
    evidence_ids=(scan_evidence.evidence_id,),
    evidence=(scan_evidence,),
    quality_flags=(),
    raw_score=0.8,
    identity_kind="canonical",
    resolution_state="resolved",
    origin_lane="relationship",
    origin_attempt=1,
    adapter_versions=("canonical-v2-isolated-relationship-v1",),
    provider_versions=(),
)
# The slot Gate A adds once the bare short name binds (knowledge_read.py
# _extract_protected_slots emits it from request.displayed_entity_ids).
slot = ProtectedSlot(
    kind="displayed_entity_set",
    value="displayed_entity_set",
    raw_text="",
    entity_ids=(COMPANY,),
)

eligible, receipts, rejected = _apply_constraints((fused,), (slot,))
print("scan-only candidate -> eligible:", len(eligible))
for receipt in receipts:
    print("  outcome:", receipt.outcome)
    for failure in receipt.failed_slots:
        print(
            "  failed slot:", failure.slot_kind,
            "| required:", failure.required_value,
            "| observed:", failure.observed_values,
        )
print("  rejected raw ids:", rejected)
assert len(eligible) == 1 and not rejected, (
    "Gate C regression: the scan-only candidate must be admitted via its "
    "claim-binding value witness"
)
print("GREEN: claim-binding value witness admits the scan candidate "
      "(round-2 rejection fixed).")

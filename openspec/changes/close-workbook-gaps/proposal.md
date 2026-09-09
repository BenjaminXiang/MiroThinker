# Proposal: close-workbook-gaps

> Stages B/C of the system-completion plan approved 2026-09-10 (human docs:
> `docs/plans/2026-09-09-testset-baseline-and-repair-plan.md` §九; plan
> doc 2026-09-10). Agent-governed per AGENTS.md §3.
> Behavior-affecting: YES — retrieval paths, answer rendering, and serving
> data. Capability: `canonical-v2-chat` (deltas added per slice).

## Why

The 2026-09-09 workbook baseline (17 groups / 25 turns, three runs:
template 17/25, LLM 22/25) plus offline analysis produced a 16-item gap
list (evidence doc §九). Three turns fail outright, three pass only because
keyword judgment is too loose, and cross-cutting gaps (local citations, web
pollution, LLM guard hard-fail) plus foundation gaps (field quality,
aliases, stale 5.6k-document pack vs 47k run14, paper↔professor links) cap
the system's ceiling. The user directive: fix toward a system that
**satisfies requirements with no known gaps** — simple, direct
implementations preferred over the existing over-engineered layers.

## What Changes

### Stage B — core gap fixes (serving line)

| Slice | Gap | Change | Acceptance |
|---|---|---|---|
| B1 | GAP-01 company→patent unreachable | Port the G3-simple direct scan (`790f4d1`, data line) into deployment-line `knowledge_read_isolated.py`: read field-level patent→applicant bindings from the pack lookup SQLite by company_id | g17-t1 ≥3 CN ids + ≥1 local citation |
| B2 | GAP-04 context narrowing incomplete | Layer D narrowing intersects the previous turn's displayed id set with the filter condition | g2-t2 / g5-t2 coverage ≥ 80% of GT set |
| B3 | GAP-02 enumeration incomplete | Enumeration path self-checks key-entity coverage before rendering | g2-t1 all five GT companies present |
| B4 | GAP-07/08 citation floor + web pollution | Local answers must carry ≥1 local citation; web citations filtered against navigation/error templates | citations_local ≥1 where local data answered; no boilerplate strings in web citations |
| B5 | GAP-09 LLM guard hard-fail | Guard hit degrades to template rendering instead of an SSE error / empty answer | injected guard hit → non-empty templated answer |
| B6 | GAP-03 multi-constraint person retrieval | Combine education × region × industry constraints in retrieval (depends on C1 field quality) | g7-t1 ≥2 gold persons/companies |

### Stage C — data groundwork

| Slice | Gap | Change | Acceptance |
|---|---|---|---|
| C1 | GAP-13/14 field quality | Field-quality contract + cleanup: professor boilerplate/placeholders, company placeholders, alias closure, key_personnel education structuring | per-field thresholds met (contract in design.md) |
| C2 | GAP-15 stale data | Bring run14 (47,071 docs) online via thin-load path; reconciliation report | reconciliation thresholds met; workbook score not regressed |
| C3 | GAP-01 data side | Full company→patent relations + professor→company coverage (90 candidates) | relation hit turns green; 10-sample manual check |
| C4 | GAP-16 paper↔professor | Author records gain canonical person ids | paper detail lists involved professors |
| C5 | over-design | Delete taxonomy dead path (curated vocabulary + dedicated fields; measured 0/7,089 used, zero serving references) | deletion removes no capability |

## Impact

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` (B1 scan)
- `apps/admin-console/backend/services/canonical_v2_chat.py` + Layer D module (B2–B5)
- Data-line build/cleanup modules (C1–C5)
- Serving pack content (C2/C3) — new pack version, reconciliation report

## Acceptance (stage-level)

- Workbook three-layer judgment **25/25** at stage E.
- Each slice's acceptance assertion from the gap registry turns GREEN with
  evidence archived under `.agents/runs/close-workbook-gaps/`.
- Replay gate 7/7 held after every serving-line slice.
- No regression in canonical_v2 suites beyond the known pre-existing
  failures list.

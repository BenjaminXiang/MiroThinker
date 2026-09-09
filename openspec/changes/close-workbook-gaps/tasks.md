# Tasks: close-workbook-gaps

## Stage B — core gap fixes

- [x] B1.1 Port `_company_to_patent_relationship_candidates` G3-simple scan
       into deployment-line `knowledge_read_isolated.py` (no new imports).
       (commit `b20161d`, +79 lines incl. path-eligibility guardrail the
       source block lacked)
- [ ] B1.2 Restart 18188; RED→GREEN on g17-t1 assertion (≥3 CN ids,
       citations_local ≥1); replay gate 7/7.
- [ ] B1.3 Gate A: patent-intent patterns cover "有哪些专利/的专利有哪些";
       derived short-name channel with uniqueness guard binds 优必选.
- [ ] B1.4 Gate B: shared `_direct_patent_applicant_scan` helper called
       from `_source_bound_relationship_candidates` for company→patent;
       positive control (普渡 17) not regressed.
- [ ] B1.5 Relationship-lane local citations surface in the answer.
- [ ] B2.1 Layer D narrowing = displayed-id set ∩ condition; g2-t2/g5-t2
       coverage ≥80% of GT.
- [ ] B3.1 Enumeration key-entity self-check; g2-t1 five GT companies all
       present.
- [ ] B4.1 Local-citation floor at render; local answers carry ≥1 local
       citation.
- [ ] B4.2 Web-citation boilerplate filter (navigation/error templates).
- [ ] B5.1 LLM-guard hit degrades to template rendering; injected-fault
       test + trace token.
- [ ] B6.1 Education × region × industry combined person retrieval;
       g7-t1 ≥2 gold entities. (depends C1)

## Stage C — data groundwork

- [ ] C1.1 Field-quality contract + cleanup (professor boilerplate /
       placeholders; company placeholders; alias closure; key_personnel
       education).
- [ ] C2.1 run14 thin-load online (47,071 docs) + reconciliation report;
       workbook score not regressed.
- [ ] C3.1 Company→patent full relations + professor→company coverage (90
       candidates); 10-sample manual check.
- [ ] C4.1 Paper↔professor canonical id links; paper detail lists involved
       professors.
- [ ] C5.1 Delete taxonomy dead path after zero-reference sweep.

## Spec deltas

- [ ] S-delta B1: `canonical-v2-chat` — company→patent local traversal
       requirement (added with B1).
- [ ] S-deltas for B2–B5 added with their slices.

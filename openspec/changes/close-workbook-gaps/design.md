# Design: close-workbook-gaps

> Standard change. Design decisions are recorded per slice; slices B2–B6 /
> C1–C5 get their detailed section when their slice starts. B1 is designed
> in full because it starts immediately.

## Guiding constraints

1. **Simple path first** (user directive 2026-09-10): the current stack is
   over-engineered — audit/proof layers are frozen, traceability degrades
   to "point at the source when possible". New code takes the shortest
   correct path inside the existing serving architecture; no new proof
   scaffolding.
2. **Thin-load / direct-scan over assembly-contract repair** (risk R1):
   the run14 pack fails 42 cascading loader validations. We do NOT repair
   the assembly contract chain in this change; data reaches serving through
   direct reads of the pack lookup SQLite / Milvus Lite.
3. **No regression without evidence**: every serving-line slice re-runs the
   replay gate (7/7) and the focused workbook turns.

## B1 — company→patent direct scan (full design)

**Facts (measured 2026-09-09/10).** The s12f serving pack's relationship
tables hold 121 `patent_has_applicant` rows covering 48 companies — 优必选
not among them. The same pack's lookup SQLite carries 1,704 field-level
patent→applicant bindings (58 for 优必选; run14: 7,650 total, 459 for
优必选). Data exists; the read path does not.

**Chosen approach.** Port `_company_to_patent_relationship_candidates`
(the "G3-simple" block, ~60 lines, data-line commit `790f4d1`, file
`knowledge_read_isolated.py` in `.worktrees/data-rebuild`) into the
deployment line
`.worktrees/canonical-v2-s11-consolidation/apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`.

- The deployment-line function of the same name sits at ~`:3194`; the new
  scan block inserts before the final
  `return tuple(candidates[: request.max_candidates])` (~`:3801`).
- `EvidenceItem`, `RecallCandidate`, `PatentProjection` are already
  imported in the deployment line — the port must not add new imports or
  new dependencies.
- Scan semantics: from the pack lookup SQLite, select patent rows whose
  applicant binding matches the requested company_id (exact id match, not
  name fuzzy match); project each to the existing patent candidate shape;
  order deterministically (e.g. by publication date desc when available);
  cap by `request.max_candidates`; merge with relationship-table
  candidates, de-duplicated by patent id.
- Citations: candidates produced by this scan carry local evidence items so
  the answer renderer can emit local citations (GAP-07 alignment).

**Rejected alternatives.** ① Repairing the assembly contract so
`patent_has_applicant` fills completely — contract chain is the R1 swamp,
deferred to the data line. ② Name-based fuzzy matching against patent
applicant strings — ungrounded; id-based bindings already exist.

**RED → GREEN.** RED: hardened runner g17-t1 assertion (≥3 `CN\d{9,}` ids
AND citations_local ≥1) fails today (baseline: 1 CN id, citations_local=0,
answer sourced from web/Tianyancha). GREEN: same assertion passes on the
live 18188 endpoint after restart; replay gate stays 7/7.

## B2–B6, C1–C5 — design stubs (filled at slice start)

- **B2**: narrowing = previous displayed-id set ∩ filter; the displayed-id
  manifest already exists from the Layer D work.
- **B3**: enumeration completeness self-check against the retrieval set
  before rendering; shortfall triggers one supplemental probe, then honest
  wording (not fabricated completeness).
- **B4**: citation floor enforced at render; web boilerplate filtered by a
  template blocklist at citation-assembly time.
- **B5**: guard-hit path returns the template-rendered answer with a
  degradation token in the turn trace.
- **B6**: combine structured education/region/industry constraints; blocked
  on C1 field quality for `key_personnel.education_structured`.
- **C1**: field-quality contract thresholds — professor profile_summary
  boilerplate <10%, paper_summary placeholder 0%, title placeholder <5%,
  email placeholder 0%, aliases coverage ≥30% for companies with known
  aliases.
- **C2**: thin-load run14 (47,071 docs) into the serving pack format
  without the assembly contract; reconciliation report (counts per domain,
  relationship counts, spot checks).
- **C3/C4**: relationship backfills as data-line jobs; serving reads them
  through the same direct-scan pattern as B1.
- **C5**: delete the taxonomy dead path (curated vocabulary + dedicated
  fields) after a serving-wide reference sweep shows zero reads.

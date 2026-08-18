# Tasks: full-column-serving-pack-rebuild

- [x] 4.1 Source recon: locate the full-column legacy Postgres (creds/DB),
       confirm ~45k object count and column availability; record findings.
       (2026-08-19: original Postgres volume is empty post-incident; the
       full-column sources are the surviving file families — company workbook
       6,528x16col, patent release jsonl 11,408 (+11,408 type-inference
       backfill), salvage ready papers 24,101, professor jsonl union 3,736;
       total ~45.8k. Links: 18,655 salvage verified prof-paper links
       name-anchored; company-patent via applicant normalization. Findings in
       docs/plans/2026-08-19-p4-data-rebuild-log.md R1.)
- [ ] 4.2 Build plan: assemble the runner invocation (mirror the s12f
       manifest arg pattern; NEW database + NEW /var/tmp roots; new run-id;
       full-column parser switch; relationship backfill batches).
- [ ] 4.3 Execute the build (embedding via school API batch; fallback per
       ruling); monitor and log.
- [ ] 4.4 Reconciliation report: domain counts / field non-null rates /
       four-path reachability sampling vs the audit baseline.
- [ ] 4.5 Scratch-port smoke serve of the v2 pack (G2/G4/G7-form queries)
       + evidence archive.

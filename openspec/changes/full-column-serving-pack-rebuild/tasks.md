# Tasks: full-column-serving-pack-rebuild

- [ ] 4.1 Source recon: locate the full-column legacy Postgres (creds/DB),
       confirm ~45k object count and column availability; record findings.
- [ ] 4.2 Build plan: assemble the runner invocation (mirror the s12f
       manifest arg pattern; NEW database + NEW /var/tmp roots; new run-id;
       full-column parser switch; relationship backfill batches).
- [ ] 4.3 Execute the build (embedding via school API batch; fallback per
       ruling); monitor and log.
- [ ] 4.4 Reconciliation report: domain counts / field non-null rates /
       four-path reachability sampling vs the audit baseline.
- [ ] 4.5 Scratch-port smoke serve of the v2 pack (G2/G4/G7-form queries)
       + evidence archive.

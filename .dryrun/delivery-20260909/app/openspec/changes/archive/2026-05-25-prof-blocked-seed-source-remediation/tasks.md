## 1. Source Audit

- [x] 1.1 Reproduce current fetch diagnostics for seed ids 5 and 25-28 without mutating `miroflow_real`.
- [x] 1.2 Verify the UESTC yjsjy source URLs for seed ids 25-28, including HTTP status, candidate counts, and mentor detail links.
- [x] 1.3 Search for official reachable SZU CSSE replacement roster/API sources and record accepted or rejected candidates.
- [x] 1.4 Update `acceptance.md` and `.agents/runs/prof-blocked-seed-source-remediation/verification.md` with the source-audit matrix.

## 2. UESTC Official Mentor Adapter

- [x] 2.1 Add a named resolver or fallback mapping for UESTC yjsjy mentor roster URLs.
- [x] 2.2 Implement the UESTC yjsjy roster extraction path with source detail URL preservation.
- [x] 2.3 Add unit tests for seed-to-zydm mapping, adapter resolution, roster parsing, and detail URL evidence.
- [x] 2.4 Run preview or bounded sample E2E for seed ids 25-28 and record candidate counts and terminal outcomes.

## 3. SZU CSSE Remediation

- [x] 3.1 If an official reachable CSSE replacement source exists, implement the source mapping or adapter path for seed id 5.
- [x] 3.2 If no official reachable replacement exists, refresh seed 5 `fetch_blocked` evidence with current direct and browser diagnostics.
- [x] 3.3 Add regression coverage proving seed id 5 is either runnable through an official source or remains explicitly blocked with remediation context.
- [x] 3.4 Update `acceptance.md` and verification evidence with the seed 5 decision.

## 4. P5 E2E Matrix

- [x] 4.1 Run the P5 row-level E2E matrix for seed ids 5 and 25-28.
- [x] 4.2 Re-run the professor seed adapter coverage guard against `miroflow_real` and capture post-P5 classifications.
- [x] 4.3 Run targeted admin seed API tests proving adapter-missing and accepted-trigger semantics still hold.
- [x] 4.4 Record every command, result, skipped check, and issue id in `.agents/runs/prof-blocked-seed-source-remediation/verification.md`.

## 5. Validation and Close-Out

- [x] 5.1 Run `openspec validate prof-blocked-seed-source-remediation --strict`.
- [x] 5.2 Run targeted professor adapter, roster, seed-runner, and source-remediation tests.
- [x] 5.3 Run ruff checks for touched scripts, adapters, and tests.
- [x] 5.4 Ensure `tasks.md`, `acceptance.md`, and `.agents/runs/prof-blocked-seed-source-remediation/verification.md` have current evidence before marking P5 complete.

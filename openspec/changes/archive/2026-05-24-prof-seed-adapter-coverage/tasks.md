## 1. Coverage Guard

- [x] 1.1 Add a deterministic professor seed adapter coverage guard script under `apps/miroflow-agent/scripts/`.
- [x] 1.2 Make the guard load `professor_seed` rows from the configured database and print seed id, school, department, seed URL, current status, resolver result, coverage state, diagnostic status, and issue id or reason.
- [x] 1.3 Make the guard fail non-zero when any seed has neither a resolver result nor an approved blocked classification.
- [x] 1.4 Add unit or integration coverage proving missing resolver rows fail the guard and full matrices are emitted.

## 2. SUIT/SZIIT Adapter Coverage

- [x] 2.1 Add matcher coverage for `suit-sz.edu.cn` / `zd.suit-sz.edu.cn` roster pages.
- [x] 2.2 Register a named SUIT/SZIIT adapter in the professor roster adapter registry.
- [x] 2.3 Reuse or extend the roster extractor so seed id 24 produces professor candidates from `https://zd.suit-sz.edu.cn/jyjx/jsfc.htm`.
- [x] 2.4 Add adapter dispatch and parser tests for the SUIT/SZIIT seed URL.
- [x] 2.5 Run a real preview or bounded sample E2E for seed id 24 and record resolver result, candidate count, terminal status, and issue outcome.

## 3. UESTC/SIAS Fetch Outcome

- [x] 3.1 Add tests proving UESTC/SIAS tokenized 202 pages with 0 Chinese characters and 0 anchors are classified as `fetch_blocked`, not successful parser output.
- [x] 3.2 Implement a durable UESTC/SIAS fetch/parser path if a usable roster body can be obtained, or implement approved `fetch_blocked` persistence for the four current UESTC/SIAS seeds.
- [x] 3.3 Ensure `pipeline_issue.evidence_snapshot` records seed identity, trigger mode, HTTP status, response shape, fetch method, browser diagnostic when available, and `failure_class`.
- [x] 3.4 Run real preview or bounded sample E2E for seed ids 25, 26, 27, and 28 and record terminal outcome for each row.

## 4. Current Seed Matrix

- [x] 4.1 Run the coverage guard against `miroflow_real` and capture the full 20-row resolver matrix.
- [x] 4.2 Run preview or bounded sample E2E for every currently covered seed family: SUSTech, HITSZ, SZU, SIGS, and CUHK.
- [x] 4.3 Fix seed-URL-specific parser or fetch issues found by the current 20-row E2E matrix without broadening beyond the current seed inventory.
- [x] 4.4 Confirm no current seed remains unclassified as resolver-covered or approved blocked.

## 5. Verification and Evidence

- [x] 5.1 Run `openspec validate prof-seed-adapter-coverage --strict`.
- [x] 5.2 Run targeted professor adapter, roster, seed-runner, and admin seed API tests.
- [x] 5.3 Run lints for touched professor seed adapter and seed runner code.
- [x] 5.4 Update `openspec/changes/prof-seed-adapter-coverage/acceptance.md` with requirement-by-requirement evidence.
- [x] 5.5 Update `.agents/runs/prof-seed-adapter-coverage/verification.md` with exact commands, outputs, skipped checks, risks, and the final 20-row E2E matrix.

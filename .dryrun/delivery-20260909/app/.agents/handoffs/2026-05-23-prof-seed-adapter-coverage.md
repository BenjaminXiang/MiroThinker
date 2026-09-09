# Handoff: prof-seed-adapter-coverage

Date: 2026-05-23

## Goal

Open and implement a Standard OpenSpec change, recommended id
`prof-seed-adapter-coverage`, for P4 of the current P0-P10 execution goal.

P4 is blocked until every current `professor_seed` row in `miroflow_real` has
either:

1. a registered school-specific roster adapter or API path with E2E evidence,
   or
2. an OpenSpec-approved blocked classification with actionable
   `pipeline_issue` evidence.

## Current State

- Active OpenSpec changes: none.
- `openspec validate --specs --strict`: 12 passed, 0 failed.
- `miroflow_real.professor_seed`: 20 rows.
- Resolver coverage:
  - 15 rows covered.
  - 5 rows missing.
- Current audit artifact:
  `.agents/runs/prof-seed-adapter-coverage-audit.md`.

Codex must not edit production adapter/crawler behavior until an active
OpenSpec change owns this behavior.

## Required Invariant

This is the important P4 rule: seed coverage is row-level and school-specific.

- Every current `professor_seed` school/URL must have an explicit registered
  school crawler, roster adapter, or API path.
- If a current seed URL has no crawler/adapter/API path, implementing that
  crawler is in scope for this change. It is not a future cleanup item.
- A broad generic parser may be used inside a school adapter, but it does not
  count as coverage unless the seed URL resolves to a named adapter/API path and
  has per-seed E2E evidence.
- Existing covered schools still need row-level verification. A registered
  adapter name alone is not completion evidence.
- A seed that cannot be crawled durably must end in an approved blocked class
  such as `fetch_blocked` with actionable `pipeline_issue` evidence. It must
  not be counted as successful coverage.

## Missing Seed Coverage

| ID | School | Department | Seed URL | Status |
|---:|---|---|---|---|
| 24 | 深圳信息职业技术大学 | 中德机器人学院 | `https://zd.suit-sz.edu.cn/jyjx/jsfc.htm` | `adapter_missing` |
| 25 | 电子科技大学（深圳）高等研究院 | 电子信息 | `https://sias.uestc.edu.cn/rcpy/dsjs1/dzxx2.htm` | `never_run` |
| 26 | 电子科技大学（深圳）高等研究院 | 计算机技术 | `https://sias.uestc.edu.cn/rcpy/dsjs1/jsjjs/jsjjs.htm` | `never_run` |
| 27 | 电子科技大学（深圳）高等研究院 | 软件工程 | `https://sias.uestc.edu.cn/rcpy/dsjs1/rjgc/rjgc.htm` | `never_run` |
| 28 | 电子科技大学（深圳）高等研究院 | 机械 | `https://sias.uestc.edu.cn/rcpy/dsjs1/jx/gyhlwyznzz.htm` | `never_run` |

## Current Diagnostics

- Seed id 24, SUIT/SZIIT:
  - Direct no-env fetch returned the roster page successfully.
  - Current generic extraction can recover 10 professor entries from the page.
  - Required implementation is still a named school adapter/crawler, not a
    generic-parser completion claim.
- Seed ids 25-28, UESTC/SIAS:
  - Direct no-env fetch returned status 202 challenge-like pages of about 2.4KB
    with 0 Chinese characters and 0 anchors.
  - The SIAS root page, parent mentor directory, HTTPS seed URL, and HTTP seed
    URL variant all returned the same 202 tokenized XHTML shape.
  - Playwright navigation failed with `net::ERR_CONNECTION_CLOSED`.
  - Ambient env/proxy direct requests failed with `SSLEOFError`.
  - Jina reader attempts timed out for the current project URL shape and two
    alternate reader URL shapes.
  - Treat this as a fetch-strategy or approved-blocked problem, not a
    parser-only problem.

## Required OpenSpec Scope

The change must make per-seed adapter coverage a first-class contract:

- Add a coverage guard that loads current `professor_seed` rows and reports
  resolver coverage per seed id, school, department, URL, and adapter name.
- Implement SUIT/SZIIT coverage for seed id 24.
- Investigate UESTC/SIAS fetch behavior for seed ids 25-28 and either:
  - implement a durable adapter/fetch/parser path, or
  - classify the seeds with an approved blocked state such as
    `fetch_blocked`, including structured `pipeline_issue` evidence.
- Do not count blocked UESTC/SIAS seeds as successful coverage unless they can
  be crawled and parsed durably.
- Run real-seed E2E for every current seed, or document each skipped seed with
  an OpenSpec-approved rationale.

## Suggested Tasks

- [ ] T1.1: Create OpenSpec change `prof-seed-adapter-coverage`.
- [ ] T1.2: Add per-seed coverage requirement and acceptance scenarios.
- [ ] T2.1: Add current-seed resolver coverage guard.
- [ ] T2.2: Add SUIT/SZIIT roster adapter for seed id 24.
- [ ] T2.3: Add unit and sample E2E coverage for SUIT/SZIIT.
- [ ] T3.1: Add UESTC/SIAS fetch diagnostics for seed ids 25-28.
- [ ] T3.2: Implement durable UESTC/SIAS adapter or approved blocked
  classification.
- [ ] T3.3: Persist actionable issue evidence for blocked seeds.
- [ ] T4.1: Run per-seed real E2E matrix.
- [ ] T4.2: Update `tasks.md`, `acceptance.md`, and
  `.agents/runs/prof-seed-adapter-coverage/verification.md`.

## Acceptance Gates

- `resolve_seed_adapter_name()` returns a non-null adapter/API path for every
  current seed that is considered runnable.
- Seed id 24 no longer resolves to missing.
- Seed ids 25-28 are either runnable with E2E evidence or explicitly blocked
  by an approved status and issue evidence.
- No `adapter_missing` seed is silently treated as complete.
- P4 completion evidence includes the full 20-row matrix.

## Implementation Map

Use this map when the OpenSpec change exists. Keep changes small and traceable.

### OpenSpec Artifacts

- Create `openspec/changes/prof-seed-adapter-coverage/proposal.md`.
- Create `openspec/changes/prof-seed-adapter-coverage/design.md`.
- Create `openspec/changes/prof-seed-adapter-coverage/tasks.md`.
- Add a spec delta under
  `openspec/changes/prof-seed-adapter-coverage/specs/.../spec.md` defining:
  - per-seed adapter coverage;
  - row-level coverage guard output;
  - runnable vs approved blocked outcomes;
  - required E2E evidence for every current seed row.
- Record commands in
  `.agents/runs/prof-seed-adapter-coverage/verification.md`.

### Runtime Files

- `apps/miroflow-agent/src/data_agents/professor/adapter_resolution.py`
  - `resolve_seed_adapter_name()` is the runtime gate.
  - It must return a named adapter/API path for runnable seeds.
- `apps/miroflow-agent/src/data_agents/professor/roster.py`
  - `_SCHOOL_ROSTER_ADAPTERS` is the current adapter registry.
  - Add new school matchers/extractors here unless the OpenSpec design splits
    the registry into smaller files first.
- `apps/miroflow-agent/src/data_agents/professor/school_adapters.py`
  - Keep the `SchoolRosterAdapter` contract stable.
  - Do not bypass the registry to make one seed pass.
- `apps/miroflow-agent/src/data_agents/professor/discovery.py`
  - Touch only if UESTC/SIAS requires a fetch-policy change rather than a
    parser-only adapter.
- `apps/miroflow-agent/src/data_agents/professor/seed_runner.py`
  - Preserve the `adapter_missing` guard. Do not let missing adapters run the
    pipeline implicitly.
- `apps/admin-console/backend/api/seeds.py`
  - Already rechecks `_seed_has_registered_adapter()` when an
    `adapter_missing` seed is triggered. Add/update tests if new adapter names
    change this behavior.

### Proposed Guard

Add a deterministic guard script such as:

```text
apps/miroflow-agent/scripts/audit_professor_seed_adapter_coverage.py
```

Minimum output columns:

```text
seed_id, school, department, seed_url, last_run_status, resolver_result,
coverage_state, diagnostic_status, issue_id_or_reason
```

Minimum behavior:

- Load `professor_seed` from the configured database.
- Resolve every row through `resolve_seed_adapter_name()`.
- Fail non-zero when a seed has no resolver result and no approved blocked
  classification.
- Print the full 20-row matrix so acceptance evidence can be copied into
  `acceptance.md`.

### School-by-school Work

| Seed IDs | School / URL family | Current path | Required work |
|---|---|---|---|
| 9 | 南方科技大学 / `sustech.edu.cn` | `sustech-roster` | Run and record row-level preview/sample E2E. |
| 19-20 | 哈尔滨工业大学（深圳） / `hitsz.edu.cn` | `hitsz-college-teacher-family` | Run and record E2E for both departments. |
| 24 | 深圳信息职业技术大学 / `zd.suit-sz.edu.cn` | missing | Implement a named SUIT/SZIIT adapter, likely `suit-sz-teacher-family`; verify seed id 24 sample E2E. |
| 5, 10-15, 18, 21 | 深圳大学 / `*.szu.edu.cn` | `szu-teacher-family` | Run and record E2E per seed URL; add URL-specific fixes only for failing departments. |
| 8 | 清华大学深圳国际研究生院 / `sigs.tsinghua.edu.cn` | `sigs_teacher_api` | Run and record API-path E2E. |
| 25-28 | 电子科技大学（深圳）高等研究院 / `sias.uestc.edu.cn` | missing | Implement a named UESTC/SIAS crawler/fetch/parser path if durable; otherwise classify as approved `fetch_blocked` with issue evidence. |
| 6-7 | 香港中文大学（深圳） / `*.cuhk.edu.cn/teacher-search` | `cuhk_teacher_search` | Run and record E2E for both schools/departments. |

### Tests

- `apps/miroflow-agent/tests/data_agents/professor/test_school_adapters.py`
  - Unit-test adapter matching and bypass behavior for new adapter families.
- `apps/miroflow-agent/tests/data_agents/professor/test_roster_validation.py`
  - Add parser/adapter dispatch tests for SUIT/SZIIT and any UESTC/SIAS parser
    path.
- `apps/miroflow-agent/tests/postgres/test_run_single_seed.py`
  - Preserve the `adapter_missing` short-circuit.
  - Add regression coverage for a formerly missing seed resolving and running
    through sample/preview mode.
- `apps/admin-console/tests/test_seeds_api.py`
  - Preserve the 422 response when a seed is still adapter-missing.
  - Preserve 202 behavior when an `adapter_missing` seed later has a registered
    adapter.

### E2E Matrix

For every current seed row, record:

```text
seed_id, resolver_result, trigger_mode, command, terminal status,
items_processed, items_failed, pipeline_run status, pipeline_issue outcome
```

P4 is not complete until this evidence is present in `acceptance.md` and
`.agents/runs/prof-seed-adapter-coverage/verification.md`.

## Verification Commands

Use these after the OpenSpec change exists and implementation starts:

```bash
openspec validate prof-seed-adapter-coverage --strict
cd apps/miroflow-agent
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python <coverage-guard-script>
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/<dedicated-test-db> uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q
uv run --no-sync pytest tests/data_agents/professor/test_roster_validation.py -q
uv run --no-sync ruff check src/data_agents/professor tests/postgres/test_run_single_seed.py tests/data_agents/professor/test_roster_validation.py
```

Replace `<coverage-guard-script>` with the implementation chosen by the
OpenSpec change.

## Do Not

- Do not add generic parser tweaks and claim seed coverage without row-level
  evidence.
- Do not count anti-scraping challenge pages as successful crawls.
- Do not mutate `miroflow_real` during exploratory diagnostics except through
  approved E2E commands for the active change.
- Do not mark P4 complete until `tasks.md`, `acceptance.md`, and
  `.agents/runs/prof-seed-adapter-coverage/verification.md` are updated.

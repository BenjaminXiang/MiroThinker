# Professor Seed Adapter Coverage Audit

Date: 2026-05-23

Scope:
- Audit the current `professor_seed` rows before continuing the staged P0-P10
  execution plan.
- Verify whether every current seed URL has a registered professor roster
  adapter/API path.
- Do not write to any database and do not change production crawler behavior.

## Commands and Evidence

- `openspec list --json`
  - Initial 2026-05-23 result: 5 active changes. No active
    `prof-school-adapter-framework`, `prof-seed-adapter-coverage`, or
    equivalent seed adapter coverage change.
  - Refresh after archiving `prof-lifecycle-state`: 4 active changes remain
    and none own seed adapter coverage.
  - Refresh after archiving `prof-admin-workbench-ui`: no active changes
    remain (`{"changes":[]}`).
  - Refresh after adding the implementation map: no active changes remain
    (`{"changes":[]}`).
  - 2026-05-24 resume attempt after user requested
    `继续执行 prof-seed-adapter-coverage`: no active changes remain
    (`{"changes":[]}`).

- `openspec validate --changes --strict`
  - Result: 5 passed, 0 failed.
  - Refresh after archiving all completed changes: no active changes found to
    validate.
  - Refresh after adding the implementation map: no active changes found to
    validate.

- `openspec validate --specs --strict`
  - Result: 7 passed, 0 failed.
  - Refresh after archiving all completed changes: 12 specs passed, 0 failed.
  - Refresh after adding the implementation map: 12 specs passed, 0 failed.

- `openspec status --change prof-seed-adapter-coverage --json`
  - 2026-05-24 resume attempt result: command failed with
    `Change 'prof-seed-adapter-coverage' not found. No changes exist. Create
    one with: openspec new change <name>`.

- `openspec instructions apply --change prof-seed-adapter-coverage --json`
  - 2026-05-24 resume attempt result: command failed with the same
    change-not-found error.

- Read-only database inventory via psycopg against local Postgres on
  `localhost:15432`.
  - Databases found: `miroflow_real`, `miroflow_scratch`, `miroflow_test`,
    `miroflow_test_mock`, `miroflow_test_profile_raw_text`,
    `miroflow_test_quality_status_rework`, `postgres`.
  - `professor_seed` exists in `miroflow_real` and `miroflow_test_mock`.

- Read-only resolver inventory against `miroflow_real` using
  `src.data_agents.professor.adapter_resolution.resolve_seed_adapter_name`.
  - Result: `total_seeds=20`, `covered=15`, `missing=5`.
  - Refresh after adding the implementation map: unchanged
    (`total=20`, `covered=15`, `missing=5`).
  - Current adapter registration points:
    `src/data_agents/professor/adapter_resolution.py` and
    `src/data_agents/professor/roster.py`.

## Coverage Matrix

`miroflow_test_mock`:

| School | Department | Seed URL | Resolver result |
|---|---|---|---|
| SUSTech |  | `https://www.sustech.edu.cn/zh/letter/` | `sustech-roster` |

`miroflow_real`:

| ID | School | Department | Seed URL | Current status | Resolver result |
|---|---|---|---|---|---|
| 9 | 南方科技大学 |  | `https://www.sustech.edu.cn/zh/letter/` | `never_run` | `sustech-roster` |
| 19 | 哈尔滨工业大学（深圳） | 计算机科学与技术学院 | `http://cs.hitsz.edu.cn/szll1.htm` | `never_run` | `hitsz-college-teacher-family` |
| 20 | 哈尔滨工业大学（深圳） | 集成电路学院 | `http://ic.hitsz.edu.cn/szll.htm` | `never_run` | `hitsz-college-teacher-family` |
| 24 | 深圳信息职业技术大学 | 中德机器人学院 | `https://zd.suit-sz.edu.cn/jyjx/jsfc.htm` | `adapter_missing` | missing |
| 12 | 深圳大学 | 化学与环境工程学院 | `https://chem.szu.edu.cn/szdw/zyjs/hxx.htm` | `never_run` | `szu-teacher-family` |
| 21 | 深圳大学 | 微众金融科技学院 | `https://swift.szu.edu.cn/szdw/jsfc.htm` | `never_run` | `szu-teacher-family` |
| 10 | 深圳大学 | 数学科学学院 | `https://math.szu.edu.cn/szdw/szyl.htm` | `never_run` | `szu-teacher-family` |
| 14 | 深圳大学 | 机电与控制工程学院 | `https://cmce.szu.edu.cn/szdw/szdw.htm` | `never_run` | `szu-teacher-family` |
| 15 | 深圳大学 | 材料学院 | `https://cmse.szu.edu.cn/szdw1/jsml.htm` | `never_run` | `szu-teacher-family` |
| 11 | 深圳大学 | 物理与光电工程学院 | `https://cpoe.szu.edu.cn/szdw.jsp?urltype=tree.TreeTempUrl&wbtreeid=1111` | `never_run` | `szu-teacher-family` |
| 13 | 深圳大学 | 生命与海洋科学学院 | `https://bio.szu.edu.cn/szdw/szdw/js.htm` | `never_run` | `szu-teacher-family` |
| 18 | 深圳大学 | 电子与信息工程学院 | `https://ceie.szu.edu.cn/szdw/ysfc.htm` | `never_run` | `szu-teacher-family` |
| 5 | 深圳大学 | 计算机与软件学院 | `https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1` | `never_run` | `szu-teacher-family` |
| 8 | 清华大学深圳国际研究生院 |  | `https://www.sigs.tsinghua.edu.cn/7644/list.htm` | `success` | `sigs_teacher_api` |
| 28 | 电子科技大学（深圳）高等研究院 | 机械 | `https://sias.uestc.edu.cn/rcpy/dsjs1/jx/gyhlwyznzz.htm` | `never_run` | missing |
| 25 | 电子科技大学（深圳）高等研究院 | 电子信息 | `https://sias.uestc.edu.cn/rcpy/dsjs1/dzxx2.htm` | `never_run` | missing |
| 26 | 电子科技大学（深圳）高等研究院 | 计算机技术 | `https://sias.uestc.edu.cn/rcpy/dsjs1/jsjjs/jsjjs.htm` | `never_run` | missing |
| 27 | 电子科技大学（深圳）高等研究院 | 软件工程 | `https://sias.uestc.edu.cn/rcpy/dsjs1/rjgc/rjgc.htm` | `never_run` | missing |
| 6 | 香港中文大学（深圳） | 人工智能学院 | `https://sai.cuhk.edu.cn/teacher-search` | `never_run` | `cuhk_teacher_search` |
| 7 | 香港中文大学（深圳） | 数据科学学院 | `https://sds.cuhk.edu.cn/teacher-search` | `never_run` | `cuhk_teacher_search` |

Summary:
- `miroflow_real` has 20 seeds.
- 15/20 have a resolver match.
- 5/20 currently have no registered resolver match.

## Missing Coverage

1. 深圳信息职业技术大学 / 中德机器人学院
   - URL: `https://zd.suit-sz.edu.cn/jyjx/jsfc.htm`
   - Current DB status: `adapter_missing`
   - Current resolver result: missing
   - Low-level discovery without the adapter gate resolved 10 professor
     profiles from the roster page using existing generic extraction.
   - First discovered examples: 夏林中, 陈敏娜, 高波, 赖周艺, 赵振宇.
   - 2026-05-23 refresh:
     - Direct request with `trust_env=False` returned status 200, 16,765
       characters, 2,056 Chinese characters, and 66 anchors.
     - `extract_roster_entries()` on that response returned 10 entries; first
       names: 夏林中, 陈敏娜, 高波, 赖周艺, 赵振宇, 卢鑫, 郑洪英, 周小明.
     - Direct request with ambient env/proxy enabled failed with
       `SSLEOFError`; Playwright returned `net::ERR_CONNECTION_CLOSED`.
       Therefore this site should use the existing direct no-env request path
       and does not appear to require a browser path.
   - Implementation shape: add a targeted SUIT/SZIIT roster adapter resolver
     matching `suit-sz.edu.cn` / `zd.suit-sz.edu.cn` teacher roster pages,
     then verify via single-seed sample E2E.

2. 电子科技大学（深圳）高等研究院 / 电子信息
   - URL: `https://sias.uestc.edu.cn/rcpy/dsjs1/dzxx2.htm`
   - Current resolver result: missing
   - Direct fetch returned an anti-scraping JavaScript challenge body with no
     Chinese page text or anchors.
   - 2026-05-23 refresh: direct no-env request returned status 202 and a
     2,452-character XHTML page with 0 Chinese characters, 0 anchors, 4 script
     blocks, and a tokenized meta tag/script payload using `$_ts`.

3. 电子科技大学（深圳）高等研究院 / 计算机技术
   - URL: `https://sias.uestc.edu.cn/rcpy/dsjs1/jsjjs/jsjjs.htm`
   - Current resolver result: missing
   - Direct fetch returned an anti-scraping JavaScript challenge body with no
     Chinese page text or anchors.
   - 2026-05-23 refresh: direct no-env request returned status 202, 2,469
     characters, 0 Chinese characters, and 0 anchors; extraction returned 0
     entries.

4. 电子科技大学（深圳）高等研究院 / 软件工程
   - URL: `https://sias.uestc.edu.cn/rcpy/dsjs1/rjgc/rjgc.htm`
   - Current resolver result: missing
   - Direct fetch returned an anti-scraping JavaScript challenge body with no
     Chinese page text or anchors.
   - 2026-05-23 refresh: direct no-env request returned status 202, 2,401
     characters, 0 Chinese characters, and 0 anchors; extraction returned 0
     entries.

5. 电子科技大学（深圳）高等研究院 / 机械
   - URL: `https://sias.uestc.edu.cn/rcpy/dsjs1/jx/gyhlwyznzz.htm`
   - Current resolver result: missing
   - Direct fetch returned an anti-scraping JavaScript challenge body with no
     Chinese page text or anchors.
   - 2026-05-23 refresh: direct no-env request returned status 202, 2,467
     characters, 0 Chinese characters, and 0 anchors; extraction returned 0
     entries.

Additional UESTC fetch observations:
- `requests` against HTTPS failed with `SSLEOFError`.
- Project direct fetch received a challenge body around 2.4-2.6 KB.
- Playwright navigation failed with `net::ERR_CONNECTION_CLOSED`.
- Jina reader returned the same challenge body.
- 2026-05-23 refresh with no ambient env/proxy:
  - Direct requests returned status 202 challenge-like pages for all four seed
    URLs.
  - The SIAS root page (`https://sias.uestc.edu.cn/`) and the parent mentor
    directory path (`https://sias.uestc.edu.cn/rcpy/dsjs1/`) also returned the
    same 202 tokenized XHTML shape: 0 Chinese characters, 0 anchors, and 4
    script blocks.
  - The `http://.../dzxx2.htm` variant redirected to HTTPS and returned the
    same 202 challenge-like page.
  - Ambient env/proxy direct requests failed with `SSLEOFError`.
  - Jina reader requests timed out in this run for the current project shape
    (`https://r.jina.ai/http://https://...`) and for alternate
    `https://r.jina.ai/http://sias...` / `http://http://sias...` shapes.
  - Playwright still failed with `net::ERR_CONNECTION_CLOSED`.
- The future UESTC adapter work therefore needs both resolver coverage and a
  fetch strategy, not just a parser selector.

## OpenSpec Gate

Adding or enabling new school-specific seed adapters changes runtime behavior:
affected rows move from `adapter_missing`/unrunnable to runnable. Per
`AGENTS.md` OpenSpec gate, this needs an active OpenSpec change before code
edits.

Current status:
- No active seed-adapter implementation change exists.
- There are currently no active OpenSpec changes.
- Archived `prof-seed-admin-console` explicitly names
  `prof-school-adapter-framework` as a separate planned change.
- Therefore P4 cannot be marked complete and production adapter code should not
  be edited until that change is created or an existing active change is
  explicitly designated to own this behavior.

## Required Plan Invariant: Per-seed School Adapter Coverage

This is now a hard execution gate for the professor seed path:

- Every current row in `professor_seed` must map to a school-specific crawler,
  registered roster adapter, or registered API path before the seed pipeline is
  considered complete.
- If a current seed URL has no crawler/adapter/API path, implementation of that
  crawler is part of the seed-adapter work; it is not a follow-up that can be
  skipped silently.
- The implementation unit is the real seed inventory, not a generic school
  family alone. Evidence must show each seed row, URL, resolved adapter name,
  preview/sample crawl result, and final status.
- If a site cannot be crawled durably because of anti-scraping or transport
  behavior, the outcome must be explicit: classify it as `fetch_blocked` or an
  equivalent OpenSpec-approved failure class, write actionable `pipeline_issue`
  evidence, and keep the seed out of successful coverage counts.
- P4 is done only when all 20 current `miroflow_real` seeds are either covered
  by runnable school-specific crawler paths with E2E evidence, or are explicitly
  classified by an approved blocked state with evidence.

## Confirmed Implementation Entrypoints

Current code already has the right gating shape; the missing work is adapter
coverage and evidence, not bypassing the guard.

- Runtime gate:
  `apps/miroflow-agent/src/data_agents/professor/adapter_resolution.py`
  - `resolve_seed_adapter_name()` returns `sigs_teacher_api`,
    `hit_teacher_api`, `cuhk_teacher_search`, or a registered
    `_SCHOOL_ROSTER_ADAPTERS` name.
- School adapter contract:
  `apps/miroflow-agent/src/data_agents/professor/school_adapters.py`
  - `SchoolRosterAdapter(name, matcher, extractor)`.
  - `PROFESSOR_SCHOOL_ADAPTER_BYPASS` disables matching and must not be used as
    a completion path.
- Adapter registry:
  `apps/miroflow-agent/src/data_agents/professor/roster.py`
  - `_SCHOOL_ROSTER_ADAPTERS` currently includes:
    `sustech-roster`, `szu-teacher-family`,
    `hitsz-college-teacher-family`, `suat-teacher-family`,
    `cuhk-teacher-search`, and `sysu-faculty-staff`.
  - New SUIT/SZIIT and UESTC/SIAS support should be registered here unless the
    future OpenSpec design splits adapters into separate modules.
- Seed runner:
  `apps/miroflow-agent/src/data_agents/professor/seed_runner.py`
  - `run_single_seed_with_conn()` stops before the pipeline when
    `resolve_seed_adapter_name()` returns `None`.
  - It writes `adapter_missing` status and `pipeline_issue` evidence.
- Admin trigger:
  `apps/admin-console/backend/api/seeds.py`
  - An `adapter_missing` seed can only be triggered after
    `_seed_has_registered_adapter()` starts returning true.

Test entrypoints already covering this contract:

- `apps/miroflow-agent/tests/data_agents/professor/test_school_adapters.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_roster_validation.py`
- `apps/miroflow-agent/tests/postgres/test_run_single_seed.py`
- `apps/admin-console/tests/test_seeds_api.py`

## Implementation Map for the Next OpenSpec Change

Recommended change id: `prof-seed-adapter-coverage`.

The change must implement and verify the current real seed inventory by school
and URL:

| Seed IDs | School / URL family | Current resolver | Required implementation outcome |
|---|---|---|---|
| 9 | 南方科技大学 / `sustech.edu.cn` | `sustech-roster` | Keep adapter; add row-level E2E evidence. |
| 19-20 | 哈尔滨工业大学（深圳） / `hitsz.edu.cn` | `hitsz-college-teacher-family` | Keep adapter; add row-level E2E evidence for both seed URLs. |
| 24 | 深圳信息职业技术大学 / `zd.suit-sz.edu.cn` | missing | Implement a named SUIT/SZIIT school adapter/crawler. Existing low-level generic extraction found 10 candidates, but P4 requires a named adapter and E2E. |
| 5, 10-15, 18, 21 | 深圳大学 / `*.szu.edu.cn` | `szu-teacher-family` | Keep adapter; run every seed URL; fix any department-specific parser failures discovered by E2E. |
| 8 | 清华大学深圳国际研究生院 / `sigs.tsinghua.edu.cn` | `sigs_teacher_api` | Keep API path; add row-level E2E evidence. |
| 25-28 | 电子科技大学（深圳）高等研究院 / `sias.uestc.edu.cn` | missing | Implement a named UESTC/SIAS crawler if durable fetch can be achieved; otherwise produce an approved `fetch_blocked` outcome with structured issue evidence. |
| 6-7 | 香港中文大学（深圳） / `*.cuhk.edu.cn/teacher-search` | `cuhk_teacher_search` | Keep API/search path; add row-level E2E evidence for both seed URLs. |

The coverage guard should live in an explicit script, for example:

```text
apps/miroflow-agent/scripts/audit_professor_seed_adapter_coverage.py
```

It should print the full row matrix and fail non-zero when any seed has neither
a resolver result nor an approved blocked classification.

## Proposed P4 Change Scope

Change ID recommendation: `prof-seed-adapter-coverage`.

Minimum tasks:
- Add a real-seed coverage guard that loads current `professor_seed` rows and
  reports resolver coverage by seed.
- Add a SUIT/SZIIT roster adapter and sample E2E for seed id 24.
- Add UESTC/SIAS fetch diagnostics and either:
  - implement a durable fetch/parser path, or
  - classify the four UESTC seeds as `fetch_blocked` with actionable
    `pipeline_issue` evidence rather than `adapter_missing`.
- Run per-seed preview/sample E2E for all 20 real seeds or an explicitly
  bounded representative set with skipped-check rationale.
- Update `tasks.md`, `acceptance.md`, and
  `.agents/runs/<change-id>/verification.md` before P4 is considered complete.

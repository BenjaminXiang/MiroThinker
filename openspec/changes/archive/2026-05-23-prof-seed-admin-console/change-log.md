# Change Log: prof-seed-admin-console

## 2026-05-12 - Phase B seed validation preflight

- Validated the live admin seed registry after manual additions: 15 seed rows
  are visible through API, DB, and browser UI; all remain `never_run`.
- Confirmed trigger wiring is still absent: `POST /api/seeds/{id}/trigger`
  returns HTTP 405 and the frontend "立即爬取" buttons remain disabled.
- Found a discovery priority defect before enabling trigger: roster pages from
  SUSTech/SZU could be misclassified as `direct_profile_seed_fetched`, causing
  the formal crawler path to return one pseudo-profile instead of roster
  entries.
- Fixed the priority guard so roster-like seeds can use existing adapters
  before direct-profile noise handling. Targeted regression and existing
  direct-profile/SIGS/HIT/CUHK tests passed.
- Re-ran non-mutating crawler smoke from the 15 admin seeds:
  `discovered_professor_count` increased from 398 to 1766 after the priority
  fix.
- Captured support classification for subsequent execution:
  supported = 10, parser_low_quality = 5, adapter_missing = 0.
- Next execution rule: do not generalize a single crawler across schools.
  Preserve currently supported adapters and split targeted adapters for the
  low-quality seeds.

## 2026-05-12 - Targeted adapters for low-quality seeds

- Added a narrowly matched `hitsz-college-teacher-family` roster adapter for
  HIT Shenzhen college `szll` pages. This fixed `HIT CS` and `HIT IC` without
  touching the existing `homepage.hit.edu.cn` API path.
- Narrowed SZU chemistry extraction to the current department file stem
  (`hxx.htm` -> `hxx/...`) so teacher links are captured without navigation
  pollution.
- Added CEIE-only continuation from `szdw/ysfc.htm` into explicit teacher
  category pages (`教授`, `副教授`, `讲师/助理教授`) so the seed is no longer
  limited to the academician page.
- Re-ran the 15-seed non-mutating smoke: discovered count is now 1982, with
  14 supported seeds and one remaining parser_low_quality/fetch-blocked seed
  (`SZU csse`, HTTP 412 JS challenge).
- `SZU csse` should remain blocked from dirty generic ingestion. Phase B should
  surface it as fetch failure / pipeline_issue unless a dedicated browser-safe
  adapter is implemented.

## 2026-05-12 - Phase B trigger, runner, cron, and UI activation

- Added V023 to extend `pipeline_issue.stage` with `adapter_missing`.
  Downgrade converts existing `adapter_missing` issues to
  `stage='discovery'` with an explicit description prefix before restoring
  the V022 CHECK constraint, so rollback remains possible after live runs.
- Added a reusable adapter-resolution helper that consults existing
  professor roster adapters and explicit API-backed paths (SIGS, HIT
  homepage API, CUHK teacher-search).
- Added `run_single_seed` / `run_single_seed_with_conn` for admin-managed
  seeds. The runner:
  - marks no-adapter seeds as `adapter_missing`;
  - writes idempotent `pipeline_issue.stage='adapter_missing'` rows;
  - marks fetch/parser fatal results as `failure` with discovery issue
    evidence;
  - writes `success` only after at least one profile is persisted.
- Wired `POST /api/seeds/{id}/trigger` to synchronously claim the seed as
  `in_progress`, open a `pipeline_run`, and enqueue the single-seed runner
  in a bounded ThreadPoolExecutor.
- Kept `adapter_missing` re-trigger semantics conservative: still 422 while
  no adapter matches, but accepted once a matching adapter has been
  registered.
- Activated the React "立即爬取" button. It is disabled only for
  `in_progress`; for `adapter_missing`, it remains clickable so the backend
  can re-check adapter availability.
- Added APScheduler monthly cron with admin-console environment config. Cron
  reuses the same trigger path, iterates by id, and skips `in_progress` /
  `adapter_missing`.
- Updated OpenSpec text from stale `kind` / Hydra / BackgroundTasks wording
  to the actual Phase B contract: `pipeline_issue.stage`,
  `ADMIN_PROFESSOR_SEED_*` config, and process-local ThreadPoolExecutor.
- Verified a live test-DB smoke:
  `never_run -> in_progress -> adapter_missing`, with corresponding
  `pipeline_issue` and `pipeline_run` rows, plus browser render of `/seeds`.

## 2026-05-13 - SIGS seed trigger repair

- Investigated the live failure for `professor_seed.id=8`
  (`https://www.sigs.tsinghua.edu.cn/7644/list.htm`). The roster API
  itself returned 250 teachers successfully; the failure was in canonical
  writeback.
- Root cause: admin seed runner uses the shared Postgres `connect()` helper,
  which defaults to `dict_row`. `professor.canonical_writer` still used
  tuple-style `row[0]` for `RETURNING page_id` and update IDs, causing
  `KeyError: 0` before any professor rows were written.
- Fixed canonical writer row access for tuple and dict row factories and
  added a dict-row regression test covering repeated source page, affiliation,
  and fact writes.
- Added SIGS profile layout extraction for `.teacher_right` /
  `.col_news_con`, so successful SIGS runs now persist official profile raw
  text and page-header titles such as professor and doctoral-supervisor labels.
- Restarted the live admin backend on `0.0.0.0:18188`, triggered seed `8`
  through `POST /api/seeds/8/trigger`, and verified success:
  run `1f6a8f23-7c82-4d00-96cf-8db3c3d5a633` processed `250` professors,
  failed `0`, created no new `professor_seed_runner` pipeline issues, and
  wrote `profile_raw_text` for `250/250` rows plus titles for `246/250`.

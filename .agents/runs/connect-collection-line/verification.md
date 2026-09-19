# Verification: connect-collection-line

Per AGENTS.md §6 (layered verification) and §7. Human log: `docs/plans/`.

## A/B — console DSN contract and gate injection

Scope: tasks.md A1–A4, B1, and the backend half of E3 (the page half is another
agent's slice).

### 1. RED — before the change

```bash
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  --continue-on-collection-errors \
  tests/test_console_dsn_single_source.py tests/test_canonical_v2_jobs_runner.py \
  tests/test_canonical_v2_seeds_api.py
```

Observed (exit 1): **1 error, 23 failed, 7 passed, 1 skipped**.

- `ERROR tests/test_console_dsn_single_source.py` —
  `ImportError: cannot import name 'resolve_console_dsn' from 'backend.deps'`
- `tests/test_canonical_v2_jobs_runner.py` — every `runtime_factory` case failed
  (`TypeError: __init__() got an unexpected keyword argument 'console_dsn'`),
  including the four new child-env assertions.
- `tests/test_canonical_v2_seeds_api.py::test_seed_runs_carry_the_outcome_fields`
  — `KeyError: 'stderr_excerpt'`.

### 2. GREEN — targeted suites after the change

Exact command run (the brief's list):

```bash
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/test_console_dsn_single_source.py tests/test_canonical_v2_jobs_runner.py \
  tests/test_canonical_v2_seeds_api.py tests/test_canonical_v2_uploads_api.py \
  tests/test_canonical_v2_operations_api.py
```

Observed (exit 0): **47 passed, 1 skipped in 4.28s** (the skip is the pre-existing
`DATABASE_URL_TEST`-gated seed CRUD integration case).
`test_canonical_v2_operations_api.py` stays green: `DATABASE_URL` still must not
substitute for `CANONICAL_V2_DATABASE_URL` on the V2 operations surface.

Widened runs used while implementing (not part of the required list):

- `tests/test_canonical_v2_uploads_runtime.py tests/test_canonical_v2_admin_config_api.py`
  added → **81 passed, 1 skipped**.
- `tests/test_console_dsn_single_source.py tests/test_canonical_v2_jobs_runner.py`
  alone → **31 passed**.

Lint: `uv run ruff check` on the touched files reports only the two pre-existing
F401s in `backend/deps.py` (unused `BochaSearchProvider` / `WebSearchProvider`,
present at HEAD — verified against `git show HEAD:.../deps.py`). `ruff format`
was not run: the bulk of this repo is not ruff-0.8-format-clean at HEAD either,
so reformatting would create unrelated churn.

### 3. New tests written this slice

Layer ① — 13 new cases, all fixture-driven (temporary dirs, stub probes, no live
state directory, no database writes):

| File | Cases |
|---|---|
| `tests/test_console_dsn_single_source.py` (new) | resolver precedence, blank-as-unset, `CANONICAL_V2_DATABASE_URL` not accepted, probe `resolved_dsn()` ignores the serving name, and a gated endpoint answering 503 `console_database_not_configured` (never 500) in both unconfigured shapes |
| `tests/test_canonical_v2_jobs_runner.py` | child env carries the resolved DSN; `DATABASE_URL_TEST` stands in; key absent when unresolved; explicit `console_dsn` wins over the probe environment |
| `tests/test_canonical_v2_seeds_api.py` | `GET /seeds/{id}/runs` items carry `status` / `exit_code` / `stderr_excerpt` |

Fixture source: constructed scenarios (stub probes, `_Spawn` recording double,
scratch SQLite — the same doubles the pre-existing cases use).

Layer ② — pre-existing regression suites in the targeted run: `test_canonical_v2_jobs_runner.py`
(22 cases incl. `test_child_environment_is_never_persisted`, `test_probe_is_cached_and_fail_soft`),
`test_canonical_v2_seeds_api.py`, `test_canonical_v2_uploads_api.py`,
`test_canonical_v2_operations_api.py`, `test_canonical_v2_uploads_runtime.py`,
`test_canonical_v2_admin_config_api.py` — all green.

Layer ③ — not applicable to this slice (no RAG/chat behavior); the live-line
evidence belongs to C/F.

### 4. Edits (file:line)

| File | Line | Change |
|---|---|---|
| `apps/admin-console/backend/deps.py` | 40 | `resolve_console_dsn()` — the single reader of `DATABASE_URL` / `DATABASE_URL_TEST`, blank counts as unset |
| `apps/admin-console/backend/deps.py` | 4–7, 89 | docstring names the resolver as the single reader; `get_pg_pool()` uses it (same RuntimeError message) |
| `apps/admin-console/backend/main.py` | 39, 94, 105, 122 | resolve once when the app object is built, store on `app.state.console_dsn`, log `console_database=configured/unconfigured` (never the DSN) |
| `apps/admin-console/backend/api/canonical_v2_seeds.py` | 17, 57 | resolver import; `CONSOLE_DATABASE_NOT_CONFIGURED` constant |
| `apps/admin-console/backend/api/canonical_v2_seeds.py` | 95, 103, 110–116 | gate built with `app.state.console_dsn`; `_console_dsn()`; `require_postgres(request, gate)` picks 503 detail by configured/unreachable |
| `apps/admin-console/backend/api/canonical_v2_seeds.py` | 119, 125, 129 | `_seed_connection` / `_seed_exists` / `_with_seed_connection` now take the request and resolve through it |
| `apps/admin-console/backend/api/canonical_v2_seeds.py` | 141, 148, 163, 177, 199, 220, 259, 272 | endpoints pass the request; `/runs` collects `as_dict(include_samples=True)` (E3) |
| `apps/admin-console/backend/api/upload.py` | 19, 1256 | `_resolve_upload_dsn()` routes through `resolve_console_dsn()`; the fail-soft batch-detail path is untouched |
| `apps/admin-console/backend/services/canonical_v2_admin_status.py` | 25, 509, 516 | freshness text reads the console value; reason names `DATABASE_URL` |
| `apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py` | 1142 | `PostgresProbe.ENV_ORDER = ("DATABASE_URL", "DATABASE_URL_TEST")` |
| `apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py` | 1164 | public `resolved_dsn()`; `available()` uses it |
| `apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py` | 1318, 1343 | `JobRuntime(console_dsn=…)`; `_default_console_dsn()` (explicit value, else the probe's resolution) |
| `apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py` | 1614–1619 | `_execute` injects `DATABASE_URL` when resolved; absent otherwise |
| `apps/admin-console/tests/test_console_dsn_single_source.py` | new file | see §3 |
| `apps/admin-console/tests/test_canonical_v2_jobs_runner.py` | 106, 380, 454–484 | factory takes `console_dsn`; probe fixture uses `DATABASE_URL`; four new cases |
| `apps/admin-console/tests/test_canonical_v2_seeds_api.py` | 36, 77, 121, 159 | stub probe implements `resolved_dsn()`; degradation case declares a configured database; `_seed_exists` stub signature; E3 case |
| `apps/admin-console/tests/test_canonical_v2_uploads_api.py` | 36 | stub probe implements `resolved_dsn()` |
| `apps/admin-console/tests/test_canonical_v2_uploads_runtime.py` | 83 | stub probe implements `resolved_dsn()` |
| `apps/admin-console/tests/test_canonical_v2_admin_config_api.py` | 235 | also clear `DATABASE_URL_TEST` so the freshness case locks the unconfigured branch |

### 5. Notes for the parent

- `JobRuntime` calls `self._probe.resolved_dsn()`, so any duck-typed probe must
  now expose it. Only test doubles did not; the three in this repo are updated.
  A defensive `getattr` fallback was considered and rejected (it would hide an
  incomplete probe and silently lose the injection).
- `roster.py` carried another agent's uncommitted, import-breaking edit
  (`NameError: _extract_pkusz_szdw_hub_adapter_entries`). To run the suites the
  file was temporarily restored to HEAD and then restored byte-identically
  (md5 `74b1a6f11d04b74f4dded1175aa2d5db` before and after). That WIP still
  breaks `import data_agents.professor` in this worktree.
- Sites that still read a DSN name directly, outside the resolver (legacy
  routers, all unmounted on the serving line): `backend/api/chat.py:1885`,
  `backend/api/pipeline.py:1542/1657/1786/2060`, `backend/api/seeds.py:278`.
  None of them is reachable from `create_canonical_v2_candidate_app`.

## D — roster import and adapter coverage

Scope: tasks.md D1 (`import_professor_seeds.py`), D2 (pkusz registry matcher, corrected
SZTU URLs, re-run of the classifier). Files touched:

| File | State |
|---|---|
| `apps/admin-console/scripts/import_professor_seeds.py` | new |
| `apps/admin-console/tests/test_import_professor_seeds.py` | new |
| `apps/miroflow-agent/src/data_agents/professor/roster.py` | +35 lines (`_matches_pkusz_szdw_hub`, `_extract_pkusz_szdw_hub_adapter_entries`, registry entry) |
| `apps/miroflow-agent/tests/data_agents/professor/test_pkusz_adapters.py` | new |
| `apps/miroflow-agent/scripts/e2e_seeds/liang_yongsheng_20260417.md` | URL corrected |

### 1. New tests (layer ①) — 15 cases, fixture/stub-driven, no database, no crawl

`apps/admin-console/tests/test_import_professor_seeds.py` (10 cases, all against an
in-memory `StubRegistry` and a monkeypatched `psycopg.connect`):

- parse + dedupe across two markdown files (1 folded duplicate, 4 distinct URLs, file
  order preserved) — `test_load_roster_seeds_deduplicates_urls_across_files`
- plan classification: `skipped_existing` / `would_create` / `skipped_unresolved`, plus
  school/department extraction (`深圳技术大学 / 人工智能学院`) and the adapter names
  (`sztu-teacher-family`, `pkusz-szdw-hub`) — `test_plan_classifies_every_distinct_url_and_reads_school_department`
- dry-run writes nothing even with `--include-unresolved`
- `--apply` creates only the missing rows and the second `--apply` creates 0
  (idempotency) — `test_apply_creates_only_missing_rows_and_is_idempotent`
- `--include-unresolved` turns the unresolved row into `created`
- report text: parsed/duplicate/distinct counts, per-state counts, unresolved URL named,
  "dry-run: nothing written" line
- an entry with no institution is a real error (`SeedImportError`), not a silent skip
- CLI: dry-run writes nothing and never echoes the DSN password; `--apply` writes; a
  second `--apply` writes nothing more; the connection is closed
- CLI: `--apply` without a DSN exits 2 with `--apply needs a database`
- CLI: missing `--seeds-dir` exits 2

`apps/miroflow-agent/tests/data_agents/professor/test_pkusz_adapters.py` (5 cases):

- `https://www.pkusz.edu.cn/szdw.htm` → `pkusz-szdw-hub` (both
  `resolve_seed_adapter_name` and `find_matching_school_adapter` on the live registry)
- unrelated pkusz URLs match nothing: `/`, `/xydh.htm`, `/bygk/byjs.htm`,
  `scbb.pkusz.edu.cn/szdw.htm`, `www.ece.pku.edu.cn/szdw.htm`
- the registered adapter neither invents entries on the hub nor swallows the hub links
  (`extract_roster_entries == []`, `extract_roster_page_links` still returns 信息工程学院 /
  化学生物学与生物技术学院)
- corrected SZTU roster URLs resolve to `sztu-teacher-family`
  (`ai.sztu.edu.cn/szdw/jytd/js.htm`, `sgim.../szdw2022/...`, `nmne.../szdw.htm`)
- the legacy `nmne.../picturers.jsp?...wbtreeid=1004` URL stays unresolved (the narrow
  matcher deliberately excludes it — see §5)

### 2. Pre-existing regression suites (layer ②)

```bash
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/test_import_professor_seeds.py
```

→ exit 0, **10 passed in 0.36s**.

```bash
cd apps/miroflow-agent && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/data_agents/professor -k "adapter or roster"
```

→ exit 0, **249 passed in 41.15s**. Includes both pre-existing pkusz hub locks
(`test_extract_roster_page_links_prefers_pkusz_teacher_queue_links`,
`test_extract_roster_entries_skips_pkusz_hub_navigation_page`) and the SZTU/SYSU adapter
suites.

```bash
cd apps/miroflow-agent && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/data_agents/professor -k "pkusz or pku"
```

→ exit 0, **15 passed in 35.14s** (all pre-existing pkusz behaviour, entry and page-link
paths).

Lint: `uv tool run ruff@0.8.0 check` on the four touched Python files → `All checks
passed!`. `ruff@0.8.0 format` applied to the three new files only (the repo is not
format-clean at HEAD; `roster.py` was left untouched by the formatter).

### 3. Importer dry-run over the real corpus (layer ③ — exact output)

Read-only against the local collection database (SELECTs only; no `--apply`, nothing was
written). `professor_seed` held 0 rows at that moment, so no row reports
`skipped_existing`.

```bash
cd apps/admin-console && uv run python scripts/import_professor_seeds.py \
  --dsn postgresql://miroflow@127.0.0.1:55458/miroflow_collection_v1
```

```
seeds dir: /home/longxiang/MiroThinker/.worktrees/collection-line/apps/miroflow-agent/scripts/e2e_seeds
mode: dry-run | registry: database (existing rows checked)

status             adapter                    school / department  seed_url
----------------------------------------------------------------------------------------
would_create       cuhk_teacher_search        香港中文大学（深圳） / 理工学院  https://sse.cuhk.edu.cn/teacher-search
would_create       cuhk_teacher_search        香港中文大学（深圳） / 人工智能学院  https://sai.cuhk.edu.cn/teacher-search
would_create       hit_teacher_api            哈尔滨工业大学（深圳） / -  https://homepage.hit.edu.cn/school-dept?id=1&browseName=%E6%A0%A1%E5%86%85%E5%8D%95%E4%BD%8D&browseEnName=DEPARTMENT
would_create       sztu-teacher-family        深圳技术大学 / 人工智能学院  https://ai.sztu.edu.cn/szdw/jytd/js.htm
would_create       pkusz-szdw-hub             北京大学深圳研究生院 / -  https://www.pkusz.edu.cn/szdw.htm
would_create       sigs_teacher_api           清华大学深圳国际研究生院 / -  https://www.sigs.tsinghua.edu.cn/7644/list.htm
would_create       sustech-roster             南方科技大学 / -  https://www.sustech.edu.cn/zh/letter/
would_create       suat-teacher-family        深圳理工大学 / 计算机科学与人工智能学院  https://csce.suat-sz.edu.cn/szdw.htm
would_create       suat-teacher-family        深圳理工大学 / 合成生物学院  https://synbio.suat-sz.edu.cn/szll2/qb.htm
would_create       suat-teacher-family        深圳理工大学 / 生命健康学院  https://lhs.suat-sz.edu.cn/szdw.htm
would_create       suat-teacher-family        深圳理工大学 / 生物医学工程学院  https://suat-sz.edu.cn/swyxgcxy/szll/jxky.htm
would_create       suat-teacher-family        深圳理工大学 / 材料科学与能源工程学院  https://msee.suat-sz.edu.cn/szdw.htm
would_create       suat-teacher-family        深圳理工大学 / 算力微电子学院  https://cme.suat-sz.edu.cn/szdw/dsjs.htm
would_create       cuhk_teacher_search        香港中文大学（深圳） / 数据科学学院  https://sds.cuhk.edu.cn/teacher-search
would_create       cuhk_teacher_search        香港中文大学（深圳） / 医学院  https://med.cuhk.edu.cn/teacher-search
would_create       sysu-faculty-staff         中山大学（深圳） / 医学院  https://szmed.sysu.edu.cn/zh-hans/teachers/professor
would_create       sysu-faculty-staff         中山大学（深圳） / 公共卫生学院（深圳）  http://phs.sysu.edu.cn/zh-hans/faculty
would_create       sysu-faculty-staff         中山大学（深圳） / 材料学院  http://materials.sysu.edu.cn/faculty/staff
would_create       sysu-faculty-staff         中山大学（深圳） / 生物医学工程学院  http://bme.sysu.edu.cn/teacher/index.htm
would_create       sysu-sece-faculty          中山大学（深圳） / 电子与通信工程学院  http://sece.sysu.edu.cn/szll/index.htm
would_create       sysu-ise-teachers          中山大学（深圳） / 智能工程学院  http://ise.sysu.edu.cn/teachers
would_create       sysu-faculty-staff         中山大学（深圳） / 航空航天学院  http://saa.sysu.edu.cn/faculty
would_create       sysu-faculty-staff         中山大学（深圳） / 农业与生物技术学院  http://sa.sysu.edu.cn/zh-hans/teacher/faculty
would_create       sysu-faculty-staff         中山大学（深圳） / 生态学院  http://eco.sysu.edu.cn/teachers
would_create       sysu-sic-members           中山大学（深圳） / 集成电路学院  https://sic.sysu.edu.cn/members/index.htm
would_create       sysu-am-teacher            中山大学（深圳） / 先进制造学院  https://am.sysu.edu.cn/szdw/index.htm
would_create       sysu-faculty-staff         中山大学（深圳） / 先进能源学院  https://ae.sysu.edu.cn/faculty
would_create       sysu-scst-teacher          中山大学（深圳） / 网络空间安全学院  https://scst.sysu.edu.cn/faculty
would_create       sysu-science-teacher       中山大学（深圳） / 理学院  https://science.sysu.edu.cn/faculty
would_create       sysu-sofe-teacher          中山大学（深圳） / 柔性电子学院  http://sofe.sysu.edu.cn/zh-hans/teachers/full-time
would_create       sztu-teacher-family        深圳技术大学 / 中德智能制造学院  https://sgim.sztu.edu.cn/szdw2022/jytd/jxsjzzjqzdh.htm
would_create       sztu-teacher-family        深圳技术大学 / 人工智能学院  https://ai.sztu.edu.cn/szdw/jytd/jxjs.htm
skipped_unresolved -                          深圳技术大学 / 新材料与新能源学院  https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004
would_create       sztu-teacher-family        深圳技术大学 / 城市交通与物流学院  https://utl.sztu.edu.cn/szdw1/qbjs.htm
would_create       sztu-teacher-family        深圳技术大学 / 健康与环境工程学院  https://hsee.sztu.edu.cn/szdw.htm
would_create       sztu-teacher-family        深圳技术大学 / 工程物理学院  https://cep.sztu.edu.cn/szdw/szdw.htm
would_create       sztu-teacher-family        深圳技术大学 / 药学院  https://cop.sztu.edu.cn/szdw/jxky.htm
would_create       sztu-teacher-family        深圳技术大学 / 集成电路与光电芯片学院  https://icoc.sztu.edu.cn/szdw/jytd/jxjs.htm
would_create       szu-teacher-family         深圳大学 / -  https://www.szu.edu.cn/szdw/jsjj.htm

parsed entries: 50 (11 duplicate URL(s) folded)
distinct urls: 39
created: 0 | would_create: 38 | skipped_existing: 0 | skipped_unresolved: 1
unresolved urls (no registered adapter):
  - https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004
pass --include-unresolved to register them anyway; the crawl will then mark the seed adapter_missing
dry-run: nothing written (pass --apply to create the missing rows)
```

### 4. Classifier before/after (real corpus)

Parsed with `parse_roster_seed_markdown()` over `scripts/e2e_seeds/*.md`, de-duplicated by
URL, classified with `resolve_seed_adapter_name()`:

| | distinct URLs | resolve | unresolved |
|---|---|---|---|
| before D2 | 39 | 36 | pkusz hub, `ai.sztu…/info/1332/6055.htm`, `nmne…picturers.jsp…` |
| after D2 | 39 | **38** | `nmne…picturers.jsp…` (left untouched — see §5) |

### 5. Live-page evidence for the pkusz hub

One GET of `https://www.pkusz.edu.cn/szdw.htm` (HTTP 200, 40 KB) shows the page carries
`div.szdw_jsdw` / `szdw_bd` and a 教师队伍 block. Running the changed code on that real
HTML with `source_url=https://www.pkusz.edu.cn/szdw.htm`:

- `extract_roster_entries(...)` → `[]` (the registered adapter invents nothing)
- `extract_roster_page_links(...)` → 8 college rosters, e.g.
  `https://www.ece.pku.edu.cn/szdw.htm` (信息工程学院),
  `https://scbb.pkusz.edu.cn/szdw.htm` (化学生物学与生物技术学院),
  `https://see.pkusz.edu.cn/szdw/jsfc.htm` (环境与能源学院), `…/szdw/zzjs.htm`
  (新材料学院), `https://www.phbs.pku.edu.cn/teacher/teachers/fulltime/` (汇丰商学院),
  `https://stl.pku.edu.cn/Faculty_Research/Resident_Faculty.htm` (国际法学院),
  `https://rw.pkusz.edu.cn/szll.htm` (人文社会科学学院)

That is the same pre-adapter behaviour: the seed is now admissible, the hub still only
navigates, and entries keep coming from the college rosters through the existing
`_is_pkusz_teacher_page` + `_extract_pkusz_profile_links` path. Not verified here: the
college roster pages themselves were not fetched, so end-to-end professor discovery for
this seed still needs a live crawl (the parent's F2 preview/sample run).

### 6. Notes for the parent / deviations

1. **The pkusz extractor is deliberately empty on the hub.** The matched URL is the
   school *navigation* hub; the existing entries path (`_extract_site_specific_html_profile_links`
   → `_is_pkusz_teacher_page` → `_extract_pkusz_profile_links`) only ever answers profile
   pages, and `_should_skip_direct_entry_extraction` already pins this URL to zero direct
   entries (two pre-existing tests lock that). So the adapter reuses that dispatch as-is;
   there is no honest PKUSZ *entries* extractor for the hub. The registration makes the
   seed admissible and lets the existing page-link path do the navigation.
2. **`nmne.sztu.edu.cn` was not fixed.** The line was left untouched: the college's home
   page has no `/szdw…` link, the 师资队伍 page is only served from
   `picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004` (a 200 response, no redirect),
   and `/szdw.htm`, `/szdw/jytd.htm`, `/szdw/jytd/jxjs.htm`, `/szdw/ysfc.htm`,
   `/xygk/szdw.htm`, `/szdw2022/jytd.htm`, `/szdw1/qbjs.htm` all answer 404. Matching the
   legacy path would mean broadening the SZTU matcher, which design §6 rejects. 38/39 is
   therefore the accountable maximum; the remaining seed needs either a matcher decision
   or a different source URL from the college.
3. **`liang_yongsheng_20260417.md` shape.** The URL was swapped to the college roster
   (`https://ai.sztu.edu.cn/szdw/jytd/js.htm`, HTTP 200) and the person name kept as the
   markdown-link label: `深圳技术大学 人工智能学院 [梁永生](…)`. That yields a clean row
   (`深圳技术大学 / 人工智能学院`) and keeps `label=梁永生` for the pipeline; a plain
   trailing name would have been folded into `department` by the parser
   (`人工智能学院 梁永生`). `label` is inert for `/szdw…` URLs in discovery
   (`_looks_like_labeled_direct_profile_seed_url` excludes "szdw"), so the crawl treats
   this as a roster.
4. **`roster.py` was reverted mid-run by a sibling agent.** §A/B's note ("restored to HEAD
   to run the suites") explains the window in which the file briefly had no pkusz adapter.
   It is now present and import-clean; `roster.py` md5 after the final re-apply is
   `74b1a6f11d04b74f4dded1175aa2d5db` and `git diff --stat` shows `+35` lines. Anyone
   re-running the suites should re-check that md5 first.
5. No f-string / DSN leakage: the importer prints only a configured/not-configured state
   and redacts the DSN from driver messages; the CLI test asserts the password never
   appears on stdout.

## F2 — real runs on the live collection database (`miroflow_collection_v1`)

Run through the same entry the gate spawns (`scripts/run_admin_seed_refresh.py`) with
`DATABASE_URL` exported exactly as `JobRuntime._execute` now injects it; seed 11 =
`南方科技大学 / https://www.sustech.edu.cn/zh/letter/`.

| run | mode | wall clock | result | written |
|---|---|---|---|---|
| 1st preview | preview | killed by the operator's own 280 s timeout | row left `running` (see finding) | 0 |
| 2nd preview | preview | 23:26:18 → 23:33:48 (**7.5 min**) | `succeeded`, `items_processed: 1`, `seed_status: success` | 0 (discovery-only by design) |
| sample | sample, limit 5 | 23:33:48 → (seconds) | `succeeded`, `items_processed: 5` | **professor 5, professor_affiliation 5, source_page 9, homepage_recursion_page_ledger 0** |

Registry view at the end (what `/seeds` renders — `list_seeds`):
`id=11 → last_run_status='success', last_run_at=2026-09-18T15:33:48Z`.

### Finding fixed while verifying: run durations read as zero

`open_pipeline_run` / `close_pipeline_run` used `now()`, which in Postgres is the
**transaction start**. A crawl writes everything inside one transaction, so
`finished_at` was written equal to `started_at` — a 7.5-minute crawl recorded as
3 ms, and `/seeds`'s 最近运行 time came from that value.

Reproduced on the real database (open a run, sleep 2 s inside one transaction, close):

```
before:  started 15:34:37.721167  finished 15:34:37.721167  delta 0:00:00
after:   started 15:34:52.864469  finished 15:34:54.866702  delta 0:00:02.002233
```

Fix: `clock_timestamp()` in both statements
(`apps/miroflow-agent/src/data_agents/storage/postgres/pipeline_run.py`).
Regression test `test_close_records_elapsed_time_not_the_transaction_start`
(`apps/miroflow-agent/tests/storage/test_pipeline_run.py`), run against a throwaway
database created + migrated for the purpose (then dropped):

- RED (fix stashed): `1 failed, 3 passed`
- GREEN: `4 passed in 16.45s`

### Finding recorded, not fixed: a killed crawl leaves a permanent `running` row

The first preview was killed by the operator's timeout; its `pipeline_run` row stayed
`running` (no heartbeat, no timeout finalizer, no stale sweep in
`storage/postgres/pipeline_run.py`). The registry would show that seed as
"进行中" forever while `/jobs` knows the truth. The row was released by hand with an
explanatory `error_summary` (`operator_killed`). Candidate slice.

### Effective input budget

Sample with `limit 5` wrote 5 profiles; the SUSTech letter page yields a bounded
roster. Full runs (`full`) have no limit and are gated by the 5400 s task timeout.

## Round 4 — `/seeds` page: Chinese actions and layout (2026-09-19)

Driven by the operator's report ("操作列要中文、排版有点乱"). Verified in a real
browser: scratch instance on port 18297 (own auth store, `DATABASE_URL` pointing at
`miroflow_collection_v1`, 38 real rows), measured through CDP rather than by eye.

| metric | before | after |
|---|---|---|
| URL cells ellipsized @1440 | 5–7 / 38 | **3 / 38** |
| URL cell width @1024 | 153 px (38/38 ellipsized) | **308 px (10/38)** |
| page-level horizontal scroll @1024 | present (table stretched the grid) | **none** (wrapper scrolls 927 → 1092) |
| row heights | ragged (rows without a department were shorter) | **66 px × 38 rows** |
| action buttons per row | wrapped on some rows | **one line, all 38 rows** |
| click 运行记录 | no visible reaction (panel sits ~3000 px down) | **panel scrolled into view** (scrollY 0 → 1977) |
| page tests | — | **52 passed** (shell / gating / upload page included) |

Changes: Chinese action labels with title hints and a confirm on 抽样抓取; fixed table
layout with an explicit `min-width` and `.card { min-width: 0 }`; the 编号 column
folded into the school cell as a `#id` chip (the list is school-ordered, so a
standalone id column read as a scrambled sequence); neutral pill for 未运行 with no
empty timestamp; local `YYYY-MM-DD HH:mm` times; banner and run panel scroll into
view on action; primary button darkened to `#0f6f68` (white-on-teal was 4.16:1,
below AA).

Test-pinned strings preserved: `failureReason(run)`, `exit_code`, `stderr_excerpt`,
`escapeHtml`, `clip(run.stderr_excerpt, 160)`, `console_database_not_configured`,
`DATABASE_URL`.

Deliberately not done: the nav label `Seed 管理` stays (six pages share it and a test
pins it); `list_seeds` still orders by `(school, department, id)` — changing it needs
a service restart, and the page-level fix addressed the symptom.

## Round 5 — inline edit of a seed's school / department / roster URL (2026-09-19)

Motivation from the operator: school sites reorganise, so a roster URL cannot be
assumed stable; previously the only way to change one was delete + create, which
loses the id and its run history.

Implementation: 修改 turns the row into inputs (school / department / URL) with
保存 / 取消; the URL field is focused and selected on entry; Enter saves, Escape
cancels; a scheme-less URL gets `https://`; saves go through the existing
`PUT /api/canonical-v2/admin/seeds/{id}`; a duplicate URL (409) shows
该名册 URL 已存在 and the row stays editable.

Evidence (real browser, scratch console on 18297 against `miroflow_collection_v1`,
38 real rows):

| path | result |
|---|---|
| click 修改 | row switches to inputs, prefilled, URL focused+selected, hint 回车保存 · Esc 取消 |
| edit URL → 保存 | banner 已更新采集源 30，下次触发生效；database row changed (`seed_url` + `updated_at`) |
| save a URL that already exists | banner 该名册 URL 已存在；row kept in edit mode |
| restore the original URL → 保存 | database restored; table still 38 rows |
| page tests | 47 passed, 1 skipped (the skip needs a test database) |

Not done: no URL history/audit trail (the change overwrites), no bulk edit.

## jobs page — operator clarity (2026-09-19)

`/jobs` was a flat 15-row table whose 任务 column led with the script path
(`企业新闻采集（scripts/run_company_news_ingest.py）`), with no grouping and no statement of
when an operator should press anything. This slice adds the two operator-facing columns to
the closed white list, locks them with an invariant test, and rewrites the page around them.

### Files changed

| file | lines | what |
|---|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py` | 158-172 | `JobTask` gains required `group: Literal["collection","import","seed","ops"]` + `operator_hint: str` (docstring states the page contract) |
| " | 250-257 | `as_dict()` exports `group` and `operator_hint` next to `description` |
| " | 287-305 | `_collection_task()` takes the hint and stamps `group="collection"` |
| " | 306-560 | all 15 declarations carry the exact operator copy (7 collection, 3 import, 2 seed, 3 ops) |
| `apps/admin-console/backend/static/jobs.html` | 1-813 | rewritten task list (see below) |
| `apps/admin-console/tests/test_canonical_v2_jobs_registry.py` | 56-92 | invariant test: groups in the four allowed values, non-empty hint, no `scripts/` leak, exact id set per group, both keys in `as_dict()` |
| `apps/admin-console/tests/test_canonical_v2_jobs_api.py` | 132-138, 258-269 | list payload carries `group`/`operator_hint`/`token_params`; page-shell markers |
| `apps/admin-console/tests/test_canonical_v2_jobs_{runner,uploads_api,uploads_registry,uploads_runtime}.py` | +2 each | stub `JobTask`s pass the now-required fields |

Page landmarks: explainer card `jobs.html:247`, grouped task list `jobs.html:261` (`#taskGroups`),
运行历史 `jobs.html:272`; `GROUPS` 349, `PARAM_LABEL` 372, `UNAVAILABLE_TEXT`/`TOKEN_PAGE` 377/379,
`when()` 415, `duration()` 427, `failureReason()` 454, `lastRunCell()` 465, `tagPills()` 491,
`techDetails()` 516, `actionsCell()` 544, `renderGroups()` 598, `loadHistory()` 684, `trigger()` 754.

### New payload keys

`GET /api/canonical-v2/admin/jobs` → `tasks[]` now also carries:

- `group` — `"collection" | "import" | "seed" | "ops"` (required field, so a task cannot be
  declared without one)
- `operator_hint` — one Chinese sentence: what the task does and when an operator would use it

Everything else in the payload is unchanged (`task_id`, `label`, `description`, `domain`,
`command_display`, `cwd_relative`, `timeout_seconds`, `schedule_cron`, `schedule_display`,
`params`, `token_params`, `collection_gated`, `quota`, `requires_postgres`, `window_bound`,
plus the runtime columns `next_run_at`, `switch_enabled`, `quota_limit`, `available`,
`unavailable_reason`, `last_run`, `failure_flag`, `consecutive_failures`, `breaker_open`,
`last_success_at`, `last_failure_at`). No endpoint, parameter or response shape changed.

### Verification

Layer ① — new tests this slice (fixture source: the real declared table; page half driven by a
real `task_views()` payload):

```bash
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/test_canonical_v2_jobs_registry.py
# 47 passed
```

`test_every_task_carries_operator_copy_for_the_page` and
`test_task_payload_exports_the_operator_columns` are the new invariant. RED before the catalog
change (with `jobs.py` restored to HEAD and only the test file updated):

```
E  AttributeError: 'JobTask' object has no attribute 'group'     (line 78)
E  KeyError: 'group'                                            (line 91)
2 failed, 45 deselected
```

GREEN after: `47 passed`.

Layer ② — pre-existing suites (all pass; the one failure below is pre-existing at HEAD):

```bash
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/test_canonical_v2_jobs_api.py tests/test_nav_postgres_gating.py \
  tests/test_admin_console_shell.py tests/test_admin_gate.py          # 47 passed
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/test_canonical_v2_jobs_{registry,api,runner,store}.py \
  tests/test_canonical_v2_uploads_{api,registry,runtime}.py \
  tests/test_canonical_v2_seeds_api.py                                # 140 passed, 1 skipped
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/test_console_dsn_single_source.py tests/test_seed_background_tasks.py \
  tests/test_upload_pipeline_trigger.py tests/test_canonical_v2_real_preview_ui.py
# 1 failed, 248 passed — test_public_chat_uses_guoxian_brand_identity, which also fails at HEAD
# with the whole slice stashed (chat branding, untouched here)
uv tool run ruff@0.8.0 check <the eight changed Python files>       # All checks passed
```

`cd apps/miroflow-agent && uv run pytest tests -k "job_task or jobs_runner"` selects **no tests**
there (`no tests ran`): the jobs module lives in the agent app but is exercised by the
admin-console suites above, so that command is a no-op rather than a pass.

Layer ③ — page-level evidence. The page is static HTML/JS with no test harness of its own, so
its own inline script was executed against a real payload in a DOM stub
(`.agents/runs/connect-collection-line/jobs-page-harness/`, not part of the app):

```bash
cd apps/admin-console
uv run python ../../.agents/runs/connect-collection-line/jobs-page-harness/make_payload.py
node ../../.agents/runs/connect-collection-line/jobs-page-harness/render_check.cjs
# OK — all /jobs render assertions passed
# groups: <h3>日常采集</h3> | <h3>数据导入</h3> | <h3>教授采集源</h3> | <h3>构建与运维</h3>
# rows per group: 日常采集=8, 数据导入=4, 教授采集源=3, 构建与运维=4   (each count includes its header row)
# history rows: 7
```

What those assertions lock: the four group sections render in order with their purpose lines;
every task shows its label + `operator_hint` and never the raw `description`; ids / command /
timeout / cron sit inside `<details>`; 成功/失败/跳过（窗口外）/从未运行 badges with local
`YYYY-MM-DD HH:mm`; `失败 · 连续失败 2 次 · 已熔断`; the five capability tags; three disabled
`立即运行` buttons each followed by `需要构建期数据库`; two `/seeds` links and three `/upload`
links with no trigger for token tasks; `需构建库`; Chinese `domain`/`mode`/`limit` option labels;
history rows with Chinese status, local start times, 秒/分 durations and an escaped truncated
failure reason (`&lt;img src=x onerror=alert(1)&gt;` never reaches the DOM unescaped); and the
trigger POST body (`{"params": {"domain": "professor"}}`, `{"params": {}}`) unchanged.

### Deviations from the brief, and why

1. **The three upload tasks point at `/upload`, not `/seeds`.** The brief said "token_params
   非空的（两条 seed 任务）… /seeds" — but `upload-company|patent|professor-import` carry
   `token_params=["upload_id"]` too. A blanket `/seeds` link would send an operator importing a
   patent spreadsheet to the professor-roster page. Routing is therefore keyed on the token
   name (`seed_id` → `/seeds`, `upload_id` → `/upload`), with a disabled button + `需在对应页面操作`
   for an unmapped token.
2. **`mode` / `limit` pickers are currently unreachable.** They are declared only by the two seed
   tasks, and those render a link instead of a trigger, so the page renders only the `domain`
   picker today. The Chinese label maps for all three are declared (`jobs.html:372`) for a future
   non-token task that needs them.
3. **A failed history row shows `exit_code` inline and the stderr excerpt only when the payload
   carries one.** `GET /{task_id}/runs` serialises runs with `JobRun.as_dict(include_samples=False)`
   (`jobs.py:703-719`), which omits `stdout_excerpt` / `stderr_excerpt`; the page copies `/seeds`'
   `failureReason()` so it renders whichever fields exist. Enabling the excerpt in the list needs
   one backend change (`as_dict(include_samples=True)` for failed rows in
   `api/canonical_v2_jobs.py`), which this slice's constraints ("do not touch
   `apps/admin-console/backend/**` Python") forbid — raised, not worked around. The full excerpt
   stays one click away in 运行详情, which already fetches it.
4. **`受采集开关约束` gained a parenthetical when the switch is off** (`受采集开关约束（当前已关闭）`,
   warn colour). The old page showed 采集开关：关; dropping it entirely would have hidden why a
   manual trigger is about to be skipped.

### Page values that stay technical (deliberately)

- 运行详情 keeps the raw argv (`命令：uv run python …`), the `summary` JSON blob and the run id —
  it is the engineering surface, one click behind `查看`.
- The trigger/breaker banners still print the run id (`运行记录 <uuid>`) — the handle the operator
  quotes; the task name in them now uses the Chinese label.
- 技术细节 keeps 任务 ID / 命令 / 超时 / cron, folded per task.


## I (backend) — presets + model discovery

Backend half of the `/admin` model-config slice (I2/I3/I4/I5). No static page file touched
(`backend/static/**` is the sibling page agent's; it was being rewritten while these tests
ran — see "not mine" below). No service restart, no live state directory, no outbound call
in any test.

### Files and line refs (worktree HEAD + this slice)

| File | What changed |
|---|---|
| `apps/admin-console/backend/services/canonical_v2_connection_tests.py` | `MODEL_LIST_*` bounds + `MODEL_LIST_TIMEOUT_SECONDS = 3.0` (43–50); `ProviderPreset` (140) + `PROVIDER_PRESETS` (168–215) + `_LLM_PROFILE_LABELS` (217) + `llm_profile_options()` (228–248); `get_json()` bounded GET (466–489); `_model_ids()` (491–520); `_body_excerpt()` with key redaction (522–537); `_model_failure()` (539–555); `fetch_model_list()` (557–627); `__all__` |
| `apps/admin-console/backend/api/canonical_v2_admin_config.py` | `GET /connections/presets` (416–446); `POST /connections/{key}/models` (448–493); imports (18–38) |
| `apps/miroflow-agent/src/data_agents/canonical_v2/managed_config.py` | `serving.chat_llm_profile` → `CHAT_LLM_PROFILE` in `_FIELD_ENV_VARS` (59); two `PAGE_READONLY_FIELDS` rows (86–96) + updated header comment (72–75); `ExtractionEndpoints` docstring (154–164); `ServingSettings.chat_llm_profile` (228); `FIELD_CATALOG` row order 12 (505–512); `_validate_chat_llm_profile_choice()` called from `patch()` (745) and defined (913–941) |
| `apps/admin-console/tests/test_canonical_v2_model_discovery_api.py` | new: 20 tests (I2/I3) |
| `apps/admin-console/tests/test_managed_config_catalogue.py` | +3 tests (I4/I5) |
| `apps/admin-console/tests/test_managed_runtime_bootstrap.py` | +1 test (`CHAT_LLM_PROFILE` projection) |

### Response shapes as implemented

`GET /api/canonical-v2/admin/connections/presets` (200, session-gated, no outbound call):

```json
{"presets": [{"id": "local-openai", "label": "本机 OpenAI 兼容服务（vLLM / SGLang）",
              "base_url": "http://127.0.0.1:8000/v1", "needs_key": true,
              "docs_url": null, "note": "把主机与端口换成你自己的服务；本机部署常见端口见下"},
             {"id": "deepseek", ...}, {"id": "dashscope", ...}, {"id": "openai", ...},
             {"id": "siliconflow", ...}, {"id": "custom", "base_url": "", ...}],
 "llm_profiles": [{"name": "deepseekv4flash", "model": "deepseek-v4-flash",
                   "base_url": "https://api.deepseek.com", "key_env": "DEEPSEEK_API_KEY",
                   "label": "DeepSeek V4 Flash"}, ... 7 rows, sorted by name],
 "chat_profile": "deepseekv4flash",
 "embedding_frozen": {"base_url": "http://100.64.0.27:18005/v1", "model": "Qwen/Qwen3-Embedding-8B",
                      "note": "服务线向量由发布包冻结：…（只读展示）"}}
```

`embedding_frozen.note` is the *same* string as
`PAGE_READONLY_FIELDS["extraction_endpoints.embedding_base_url"]` (one source of copy for
both the field row and the role card). `chat_profile` is what `chat_llm_profile(os.environ)`
resolves in **this process** (so the page can show the running selection, aliases normalised).
`llm_profiles[*]` uses each profile's **local** endpoint — the one the answer/rewrite path uses.

`POST /api/canonical-v2/admin/connections/{key}/models`, body `{"base_url"?: str, "api_key"?: str}`
(unsaved values allowed, resolved through the same `_resolve_connection_request` as
`/connections/test`, nothing stored):

```json
// 200 success (one bounded GET to {base_url}/v1/models, 3 s timeout, ≤512 KB read)
{"connection": "llm", "ok": true, "models": [{"id": "a-model"}, {"id": "b-model"}],
 "count": 2, "request_url": "http://127.0.0.1:18006/v1/models", "elapsed_ms": 0}
// + "truncated": true only when the 500-id cap cut the list

// 200 failure (never a 5xx): status present iff there was an HTTP response
{"connection": "llm", "ok": false, "error": "unauthorized", "status": 401,
 "request_url": "http://127.0.0.1:18006/v1/models", "elapsed_ms": 4,
 "body_excerpt": "{\"error\":\"invalid api key\"}"}

// 429 (same limiter/scopes as /connections/test) and 422 (unknown key / unsafe endpoint)
{"detail": {"error": "rate_limited", "connection": "llm", "retry_after_seconds": 1}}
```

Error mapping: 401/403 → `unauthorized`; 404 → `not_supported`; other non-2xx → `bad_response`
(status included); connection error → `unreachable`; timeout (bare `TimeoutError` or
`URLError(reason=TimeoutError)`) → `timeout`; unparseable/empty body → `bad_response`;
**no endpoint resolved at all → `unreachable` with `request_url: ""`, `status: null`, no call**
(the honest report for e.g. rerank without `CANONICAL_V2_RERANK_BASE_URL`; the page should
refuse an empty base URL itself before calling).

Secrecy: the key travels only in `Authorization: Bearer`; `body_excerpt` is clipped to 200
chars, single-lined, and any echoed copy of the resolved key is replaced with `[redacted]`;
no handler logs anything.

### Test command and result

```bash
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/test_canonical_v2_admin_config_api.py tests/test_managed_config_catalogue.py \
  tests/test_managed_runtime_bootstrap.py tests/test_canonical_v2_model_discovery_api.py \
  tests/test_canonical_v2_connection_tests.py tests/test_canonical_v2_admin_secrets_api.py \
  tests/test_admin_config_single_channel.py tests/test_canonical_v2_runtime_sources.py \
  tests/test_managed_settings_store.py
# 133 passed
```

Layer ① (new, this slice): `tests/test_canonical_v2_model_discovery_api.py` **20 passed**
(preset table shape + no deployment host; profile table == `_LLM_PROFILES[*].local`;
`chat_profile`; 401 for both routes without a session; success sorting/dedupe/`_join`;
500-cap + `truncated`; 9 parametrised failure shapes; key-never-echoed incl. upstream echo;
runtime-default fallback through the managed settings file; unsafe endpoint 422 with zero
calls; 429 rate limit; works with no console DSN; and **one un-stubbed test** against a
loopback `ThreadingHTTPServer` on 127.0.0.1 — real `urllib` GET, real JSON, real 401, real
key redaction, so `get_json()` itself is exercised and not only its stub). Layer ①:
`test_managed_config_catalogue.py` +3 and `test_managed_runtime_bootstrap.py` +1
**passed** (catalogue row + `CHAT_LLM_PROFILE` projection + unknown-name refusal + the two
display-only embedding rows). The three suites together: **40 passed** (`-q`:
`tests/test_canonical_v2_model_discovery_api.py tests/test_managed_config_catalogue.py
tests/test_managed_runtime_bootstrap.py`).

RED before the production edits: `AttributeError: … has no attribute 'get_json'` (16 errors)
+ `ManagedSettingsUnsupportedError: field is not in the managed settings whitelist:
serving.chat_llm_profile` and the missing `PAGE_READONLY_FIELDS` keys (6 failed) → `6 failed,
17 passed, 16 errors`.

Layer ② (pre-existing, re-run here): the seven earlier suites in that command are all green;
the command's total is **133 passed** (final run, zero failures) — including
`test_canonical_v2_admin_config_api.py`, `test_canonical_v2_connection_tests.py`,
`test_admin_config_single_channel.py`, `test_canonical_v2_runtime_sources.py`,
`test_managed_settings_store.py`.

**Note on the two page-shell tests** (`test_admin_page_renders_the_credentials_card`,
`test_shell_keeps_the_four_cards_and_the_snapshot`): mid-run they failed, because they assert
markers of `backend/static/admin.html` ("连接与密钥", `id="card-connections"`) that the **page
agent's in-flight rewrite** had removed (their file changed at 01:39–01:42; this slice touches
no static file — `git diff --stat` shows all 984 static lines coming from them). The page agent
then updated both tests (01:45:47/01:45:51) and the final run is fully green. Nothing here was
worked around or weakened.

`ruff check` / `ruff format --check` clean on every file touched here (the 5 `F401`s reported
for `apps/admin-console/backend` are in `deps.py` / `canonical_v2_query_interpreter.py`,
untouched and already recorded as pre-existing).

### I5 — what the embedding fields really are (read before writing the copy)

- The **serving** line loads its embedding authority from the release bundle:
  `load_content_addressed_embedding_adapter()` (`knowledge_build_isolated.py:8155-8210`)
  compares the bundle against a frozen document (`base_url "http://100.64.0.27:18005/v1"`,
  `model_id "Qwen/Qwen3-Embedding-8B"`, dimension, `content_sha256`) and raises
  `release embedding bundle differs from frozen authority` on any difference; the serving
  bundle check is repeated at load (`knowledge_serving_isolated.py:6594`).
- **Nothing reads `CANONICAL_V2_EMBEDDING_BASE_URL` / `CANONICAL_V2_EMBEDDING_MODEL`.** A
  repo-wide grep finds them only in `managed_config.py:53-54` (`_FIELD_ENV_VARS`) and in
  historical run artifacts — so today the page's two "editable" embedding fields are worse
  than frozen: saving them projects two variables no code reads, and behaviour does not
  change at all. (`apps/admin-console/backend/deps.py:130` builds
  `EmbeddingClient(api_key=load_local_api_key())`, whose base URL/模型 are the class defaults
  in `company/vectorizer.py:22-23` — also env-independent.)
- The collection/build lane's real override is the **unprefixed** `EMBEDDING_BASE_URL` /
  `EMBEDDING_API_KEY`, read by scripts (`scripts/run_batch_reprocess_v3.py:160-163` and the
  professor e2e scripts), and is not part of the managed file.

Copy chosen (both rows in `PAGE_READONLY_FIELDS`, `managed_config.py:86-96`) — the frozen-bundle
sentence plus the "no runtime reader" fact, which is the part the operator would otherwise
have no way to learn:

> 服务线向量由发布包冻结：发布包的 embedding bundle 必须等于钉死的 base_url
> （含校验和，不符即拒绝加载），改它需要重建全部向量；这两个受管字段没有运行期读者，
> 保存它不会改变任何行为（采集/构建侧另有脚本级覆盖 EMBEDDING_BASE_URL，不经受管配置）（只读展示）

> 服务线向量由发布包冻结：模型名来自发布包 embedding bundle（与发布包不符即拒绝加载），
> 改它需要重建全部向量；这两个受管字段没有运行期读者，保存它不会改变任何行为
> （采集/构建侧另有覆盖，不经受管配置）（只读展示）

### I4 — validation placement (deliberate deviation, stated)

The strict name check lives on the **write path** (`ManagedSettingsStore.patch`, via
`_validate_chat_llm_profile_choice`), not in the pydantic schema. Reason: the schema also
validates the *effective* document (environment overrides) and hand-edited files, and the
serving line deliberately tolerates an unknown `CHAT_LLM_PROFILE` (it falls back to its
default profile). A schema validator would therefore turn one stale environment variable into
a 503 on every admin read, and would make a single bad key in a hand-edited file drop the
whole file's settings at boot (`managed_runtime._file_owned_values` validates the payload).
Save-time rejection is where the operator's decision is made, and it is atomic: the patch is
refused before anything is written. The refusal names the value and lists the available
profiles.

Live-line note for the page: the service unit sets `CHAT_LLM_PROFILE=deepseekv4flash`
(`deploy/README.md:19`, the serve command), so on this installation the new row shows
`source: "env"`, `editable: false` — exactly like every other env-pinned field. It becomes
page-writable once the unit stops setting it; the save→restart path is proven by the new
bootstrap test.

### What the page agent must know

1. `GET …/connections/presets` is session-gated (401 without a cookie) and makes **no**
   outbound call — safe to load with the page.
2. `POST …/connections/{key}/models` takes the same body as `/connections/test`
   (`base_url`, `api_key`; `model` is accepted and ignored) and is rate-limited **together with**
   the test button (same per-connection + per-client window, 6/min, 1 s interval). A 429 body is
   `{"detail": {"error": "rate_limited", …}}` with a `Retry-After` header.
3. Failure responses are **200** with `ok: false` + `error` + `status` + `request_url` +
   `elapsed_ms` + `body_excerpt`; only a bad request (unknown `key`, unsafe `base_url`,
   non-string `api_key`) is 422, and only the limiter is 429. Never a 5xx.
4. `truncated: true` appears **only** when the list was cut at 500 ids; treat it as optional.
5. `request_url` is always present on a probe outcome, so the page can show "will call /
   called …" without rebuilding the URL itself (do not duplicate `_join`'s `/v1` rule).
6. `serving.chat_llm_profile` is a plain `text` catalogue row (no `connection`, no `test_arg`);
   the choice list comes from `llm_profiles` in the presets payload, and `chat_profile` says
   what the running process uses today.
7. The two `extraction_endpoints.embedding_*` rows now come back `editable: false` with a
   `readonly_reason`; a PATCH touching them is 422 with `display-only` and the reason
   (`config/patch` is atomic — nothing else in the same patch is written either).

---

## I (page) — 模型与连接

The connection card became five role blocks, driven by the payloads the backend agent
shipped in the same worktree. Implemented and verified after their endpoints landed, so
every fixture below is a **real** payload (no hand-copied shapes) — except the three
transports listed at the end.

### Files and line refs

| File | What |
|---|---|
| `apps/admin-console/backend/static/admin.html:120-187` | `card-models` shell: five `<section class="role" data-role="…">` in the required order (chat 132, collection 142, embedding 152, rerank 163, web 173), each with a `role-<id>-state` badge, `<id>Effective` rows container, `<id>Body`, `<id>Actions`; the embedding warning line at `:157`; the 保存 ≠ 测试 footnote at `:182-186` |
| `apps/admin-console/backend/static/admin.js:453-1425` | the whole card: role table `ROLES` (`:480`), `ROLE_PROFILE_FIELD` (`:459`), `MODEL_PICKER_LIMIT`/`MODELS_TIMEOUT_MS` (`:460-461`), `TEST_PATH_BY_KIND` (`:465`), `MODEL_ERROR_TEXT` (`:470`), `joinUrl` (`:501`), `embeddingFrozen` (`:569`), `keyStatusRow` (`:590`), `renderRoleUrlPreviews` (`:661`), `renderRoles` (`:710`), per-role renderers (`:732`, `:839`, `:884`, `:922`, `:957`), `presetRow` (`:1020`), `fetchRow` (`:1073`), `fetchModels` (`:1098`), `describeModelOutcome` (`:1141`), `renderModelPicker` (`:1182`), `roleActions` (`:1242`), `roleTestBody` (`:1284`), `saveRoleBlock` (`:1357`), `loadPresets` (`:1593`) |
| `apps/admin-console/backend/static/admin.css:93, 205, 207, 242-330` | `.card { min-width: 0 }`, `.row .value`, `.table-wrap`, the role block / preset row / key row / picker / spinner / warnline / `details.advanced` styles — same variables, no framework |
| `apps/admin-console/tests/test_admin_model_roles_page.py` (new, 10 tests) | the invariants |
| `apps/admin-console/tests/test_admin_config_page_shell.py:144-221` | shell markers for the five roles, per-role containers, duplicate-id guard, `el()` lookup guard, the embedding consequence line, "probe buttons stay script-built" |
| `apps/admin-console/tests/test_canonical_v2_admin_secrets_api.py:419-433` | the old card marker updated (`模型与连接` + `roleBlocks`) |
| `.agents/runs/connect-collection-line/model-roles-harness/` | `dump_fixtures.py` (real payloads), `fixtures.json`, `render_check.cjs` (DOM harness), `stub_server.py` (scratch static+API stub), `admin-models-card.png` (screenshot) |

### What each role block renders

1. **对话模型（回答与改写用它）** — a 档位 `<select>` built from `presets.llm_profiles`
   (options labelled `label（name）`; the catalogue value is added when it is not in the list),
   the selected profile's model + base_url as static text beside it, a write-only key row
   (`llm.api_key`, and the profile's `key_env` named in the effective rows), the **runtime**
   profile row (`presets.chat_profile`) next to the **saved** one with 「本进程仍跑 X；重启后切到 Y」,
   测试连通性, and the request-URL preview. 保存 writes
   `serving.chat_llm_profile` through the existing `PATCH /config`; when `CHAT_LLM_PROFILE` is
   set in the environment (the live unit does — the backend agent's note 6) the field comes
   back `editable: false` and the page disables the select and prints the env-override reason
   instead of pretending it can save. **No 拉取模型列表 here** (deviation 6 below): the profile
   owns the model id and no field in this role could receive a picked one.
2. **采集模型（摘要与富化用它）** — the `llm` connection's catalogue fields
   (`extraction_endpoints.llm_base_url` / `llm_model`), the provider preset dropdown (fills
   base_url, never bypasses the field), 拉取模型列表, 测试, URL preview, and a **read-only**
   credential line pointing at the chat block: the collection LLM's key is the profile's own
   (`llm.api_key`), so that block owns the single key entry (报告里说明的那一处选择).
   **Chosen connection key for its 测试/拉取: `llm`** — the same key the old card used for
   these fields (`FIELD_CATALOG[*].connection == "llm"`); there is no separate collection-LLM
   connection in the server's `CONNECTIONS`.
3. **嵌入模型（检索向量用它）** — read-only: base_url/model from `presets.embedding_frozen`
   (falling back to the `embedding` connection row that `/secrets` resolves from the release
   bundle, labelled as such), the fixed warning line, the server's `readonly_reason` when the
   catalogue carries one, a key row (the key *is* writable), 测试连通性 (`embedding`, no
   overrides — the frozen endpoint is what the runtime uses), and the collection-side override
   (`extraction_endpoints.embedding_*`) only inside `<details>` 「高级：采集侧覆盖」 with the
   note 「只影响后续采集/构建，不改服务线索引」 plus the server's reason. No preset dropdown and
   no model list (nothing to pick for a frozen value).
4. **重排模型** — `extraction_endpoints.rerank_base_url` / `rerank_model` + preset + 拉取 +
   手填 + 测试 (connection `rerank`) + key row (`rerank.api_key`) + the runtime enabled/note rows.
5. **Web 搜索** — one sub-block per `kind == "web_search"` connection (Bocha / Serper): the
   pinned provider host as read-only text, mask/origin, write-only key row, 测试, 保存本卡
   (writes only the key), URL preview. Base URL stays non-editable.

Cross-cutting: every field still comes from `/config`'s catalogue (the single-channel guard
`test_the_page_holds_no_endpoint_field_knowledge` stays green — no `extraction_endpoints.*`
literal is in the page), per-field dirty tracking + the three-state save are unchanged, and
each block's 保存本卡 submits only that block's own dirty paths.

### 拉取模型列表 — behaviour on success / failure / oversize

- Request: `POST connections/{key}/models` with **the values on screen** — `base_url` from the
  role's base_url field (or the selected profile / frozen value) and `api_key` from the key box
  *of that block* only. The chat block sends the selected profile's `base_url` + `model` to the
  probe; a block that does not own the key row never sends one (so saving/serving one role
  cannot flush another role's half-typed key).
- Inline spinner (`role-<id>-spinner`) + disabled button while in flight; a **3 s client guard**
  (`AbortController`) fires first if the endpoint hangs, reporting
  「3 秒内没有响应（页面在 3 秒后放弃等待） · 请求 <url>」，and the button returns to normal.
- Success: 「拉取到 N 个模型 · HTTP 耗时 X ms · 请求 <request_url>」 (+「服务端只返回了前面一部分」
  when `truncated`). ≤ 200 ids render as a `<select>` (`从 N 个模型里选一个…` + every id +
  「手填模型 ID（保留上面输入框里的值）」); more than 200 render a filter `<input list>` over a
  `<datalist>` carrying every id. Picking (or typing a known id into the filter) writes the
  role's model field through the same widget as manual typing, so it is marked 未保存 and saves
  through the normal 保存本卡.
- Failure: the code maps 1:1 to the server's error codes and always carries the URL and the
  elapsed ms — unauthorized → 「密钥被拒绝（401/403）」；unreachable → 「连不上该地址」；
  timeout → 「3 秒内没有响应」；not_supported → 「该端点没有 /v1/models，请直接手填模型 ID」；
  bad_response → 「返回内容无法解析」. HTTP status and the server's redacted `body_excerpt` are
  appended when present; a 429 shows the limiter copy; no picker is rendered.

### Request-URL derivation (报告要求说明)

The preview mirrors the server's own builder instead of guessing:

- test paths — `TEST_PATH_BY_KIND` (`admin.js:465`) is `llm → /chat/completions`,
  `rerank → /v1/rerank`, `embedding → /v1/embeddings`, taken from
  `backend/services/canonical_v2_connection_tests.py` `_CHAT_PATH` / `_RERANK_PATH` /
  `_EMBEDDING_PATH`, and locked by `test_the_preview_paths_are_the_ones_the_server_posts_to`
  (imports those constants and compares them to the page's table).
- join rule — `joinUrl` (`admin.js:501`) re-implements `_join` (`…/v1` bases are not doubled,
  a base already ending in the path is used as-is). The harness asserts page-vs-server parity
  against a `request_url` the live server produced (`render_check.cjs`, "the page's preview must
  equal the URL the server called").
- model list — `{base_url}/v1/models` per the I3 contract; the page shows its own derivation
  *before* the call (「模型列表将请求：…（页面推算；服务端会在结果里给出 request_url）」) and the
  server's `request_url` afterwards, which is authoritative.
- web search — the pinned provider host from the connection row (the runtime posts to it; the
  page cannot and must not move it).
- chat — the **selected** profile's `base_url` (so 「测试」 tests what the operator is about to
  save, not what the process runs today; the runtime row above still reports the running profile).

### 3 s guard / 保存 ≠ 测试

保存 writes the managed file (secrets first, then the config patch) and its result line always
ends with 「保存 ≠ 测试；重启后生效：systemctl --user restart canonical-v2-backend」; the test
result ends with 「测试不改配置，保存才写文件」. The restart banner above the cards is reused
(dirty count + 已保存的改动需重启生效 + copy button) and the card footnote repeats the separation.

### Verification

**① New tests this slice (31 assertions-bearing tests / 12 pytest cases + 4 harness
scenarios + 1 browser pass), fixture source = real payloads unless stated:**

| Cluster | What it locks | Fixture |
|---|---|---|
| `tests/test_admin_model_roles_page.py` (10) | every value role has an effective-rows block; every backend connection is reachable from exactly one role; preview paths equal the server's constants + `/v1/models`; the model probe sends unsaved values; picker shape switches at 200 with 手填 in both; the five error codes and their Chinese copy; the 3 s AbortController guard; no `state.keys` write into text; the embedding read-only contract; 保存 ≠ 测试 copy | shipped static files + the real `canonical_v2_connection_tests` constants |
| `tests/test_admin_config_page_shell.py` (7 new/updated) | five role titles in order; per-role containers; **no duplicate ids**; every literal `el("…")` exists in the shell; the embedding consequence line; no probe control in the shell (`>测试连通性<` / `>拉取模型列表<` absent — the labels may appear in prose); API calls present in the script | real route graph + shipped assets |
| `render_check.cjs` (4 scenarios) | role blocks render from the payloads (state badges land in their own block, card 1's rows survive); picker select ≤ 200 / datalist > 200 with the real 500-id truncation; failure copy with URL + status + `[redacted]` excerpt; the 3 s guard; per-role save bodies; a typed key never rendered; a 404 presets endpoint degrades; an empty endpoint is refused locally without a call | `fixtures.json` |

**② Pre-existing regression suites** — `uv run pytest -q -p no:randomly -p no:cacheprovider
tests/test_admin_config_page_shell.py tests/test_admin_config_single_channel.py
tests/test_canonical_v2_admin_config_api.py tests/test_canonical_v2_admin_secrets_api.py
tests/test_nav_postgres_gating.py tests/test_admin_model_roles_page.py
tests/test_canonical_v2_model_discovery_api.py tests/test_managed_config_catalogue.py
tests/test_canonical_v2_connection_tests.py tests/test_admin_gate.py
tests/test_admin_console_shell.py` → **138 passed** (includes the backend agent's new
`test_canonical_v2_model_discovery_api.py`). `/admin`'s own four cards, the banner, the snapshot,
the three-state gesture and the per-card saves are untouched by this slice.

**③ Behaviour evidence (no browser → browser):**

- `node …/model-roles-harness/render_check.cjs` → four `OK` lines (see above). Fixtures produced
  by `uv run python …/dump_fixtures.py`: real `GET /config`, `GET /secrets`,
  `GET /connections/presets` through the live handlers in-process (temp managed stores, ambient
  credential variables removed, fake keys written through the real store) plus real
  `fetch_model_list()` outputs (3-id success, 500-id truncation, 401 with the credential
  redacted, read timeout, closed port).
- **Real Chromium pass** against a scratch static+API stub (`stub_server.py 18321`, loopback
  only, killed afterwards; 18188 untouched, no service restarted): five blocks in order with
  their state badges; card 1's rows intact; chat select options = the 7 real profiles; the
  saved-vs-running profile row («本进程仍跑 gemma4；重启后切到 deepseekv4flash»);
  `测试将请求：https://api.deepseek.com/chat/completions`; collection preview
  `http://127.0.0.1:8000/v1/chat/completions`; embedding frozen rows + collapsed 高级 details with
  both override inputs disabled; 拉取模型列表 on the 采集模型 block (`llm`) → `<select>` of 3 + 手填,
  picking `deepseek-v4-flash` filled the field and turned on 未保存 (the 对话模型 block offers no
  list: the profile owns the model id); on the oversize mode → filter +
  `<datalist>` of 500 with the truncation note; on `unauthorized` →
  「密钥被拒绝（401/403） · HTTP 401 · 请求 http://127.0.0.1:9000/v1/models · 0 ms · 响应片段：{"error":"invalid api key: [redacted]"}」;
  on the 3.5 s-hang mode → 「3 秒内没有响应（页面在 3 秒后放弃等待） · 请求 http://127.0.0.1:9000/v1/models」
  at 3102 ms with the spinner cleared; a typed key never appeared in `document.body.innerText`;
  no element inside the card overflows it and the document has no horizontal scroll
  (`scrollWidth == clientWidth` at 1425 px, card 1232 px wide, role blocks on `--blue-soft`,
  warning line on `--amber-soft`, `details` collapsed). Screenshot:
  `model-roles-harness/admin-models-card.png`.

### Defect found and fixed while verifying (RED → GREEN)

The first browser pass showed the collection role's state pill landing in **card 1**: the role
block reused `id="collectionState"`, which card 1 already owns (`admin.html:63`). `getElementById`
returns the first match, so the role wrote into another card's rows and its own badge stayed
empty. Fixed by moving every role status node to `role-<id>-state`; three guards now exist:
`test_the_shell_has_no_duplicate_element_ids`, `test_every_id_the_script_looks_up_exists_in_the_shell`,
and the harness's `duplicateShellIds` check (the harness's `getElementById` now reproduces the
browser's first-wins rule, so the DOM stub catches it too — RED verified by restoring the
duplicate: `+ [ 'collectionState' ] - []`).

### Deviations / what the backend agent must know

1. The page **does** re-derive the models URL for the pre-flight preview (their note 5 asked not
   to). The brief requires showing the final request URL *before* testing, and a call has to
   happen before a server-side `request_url` exists; the derivation is one small function,
   parity-tested against a real server `request_url`, and the server's value is shown as
   authoritative after every call. If they prefer no duplication, the endpoint would have to
   expose the URL for a *not* performed request (e.g. `GET …/connections/{key}/models-url`).
2. `truncated` is treated as optional (their note 4) — the note only appears when the field is true.
3. The chat 测试 uses the **selected** profile's base_url + model + the typed key, not the
   runtime profile: 测试 must be able to fail *before* saving (`/connections/test` accepts
   `base_url`/`model`, and the resolved key is the profile's own variable — an unsaved switch
   therefore reports 401 until the new profile's key is saved or provided). The runtime profile
   is still displayed above, with the pending-switch sentence.
4. The write-only key lives in exactly one block (`llm` → 对话模型, `rerank` → 重排模型,
   `embedding` → 嵌入模型, web → their own sub-blocks). 采集模型 deliberately has no key input
   (its credential is the profile's) — if the collection LLM ever gets its own connection key,
   that block should gain the row and the pointer line should go.
5. Untouched by this slice: card 2's 测试 Rerank 连通性 button still exists beside the new
   重排模型 block's probe; card 2's is the runtime-state probe, the block's uses the unsaved
   values. Worth folding into one button when someone next touches card 2.
6. The 对话模型 block has **no** model list: the profile owns the model id and the role has no
   field to pick into, so a picker there would have no destination. A model list that is only
   informational would be noise; the collection/rerank blocks keep it, and the chat block can
   gain it the day a "model" field exists for the chat role.
7. The page refuses locally when a role has no usable endpoint (their note 8): the result line
   says 「还没有可用端点：先填 Base URL（或选一个预设/档位），再拉取模型列表。」 and no request is
   made — locked by the harness's degraded scenario (config served with an empty rerank base_url,
   `page.apiCalls.length` unchanged).
8. The card footnote tells the operator that 拉取模型列表 and 测试连通性 share the server's
   6/min window (their note 7); a 429 shows 请 N 秒后再试 for both controls.

## 后续批次（页面）— 去重 + 全部测试

Round 10 (2026-09-19)。范围：`/admin` 一个页面批次 —— 卡片 2 里那条重复的 rerank 探针去重，
「模型与连接」卡头新增一个串行的「全部测试」。只动静态资源 + 两个标记套件 + 渲染 harness；
未改后端 Python、未重启服务、未碰 18188。

### 1. 改了什么（文件 · 行）

| 文件 | 改动 |
|---|---|
| `apps/admin-console/backend/static/admin.html:92-97` | 卡片 2 的「测试 Rerank 连通性」按钮与 `rerankTestResult` 结果节点删除；换成一句指向角色块的弱化提示「Rerank 连通性测试已移到「模型与连接 › 重排模型」：…」（原 footnote 里描述该测试的那句并入同一行，其余字段/徽章/保存不动） |
| `apps/admin-console/backend/static/admin.html:120-127` | 卡片头右侧改为 `.card-tools`（`secretsPath` + `allTestsControls`），卡头下加结果容器 `<div class="rows alltests" id="allTestsPanel" hidden>` |
| `apps/admin-console/backend/static/admin.html:188-189` | 卡尾 footnote 补一句：三种控件共用服务端限频，「全部测试」按顺序逐个探针、不并发 |
| `apps/admin-console/backend/static/admin.js:478-487` | `ALL_TEST_GAP_MS = 1200`、`ALL_TEST_ROLES`（6 个探针：llm×2 / embedding / rerank / bocha / serper） |
| `apps/admin-console/backend/static/admin.js:1335-1394` | `testConnection` 拆出共用件：`probeConnection`（一次请求）+ `describeConnectionTest`（响应→措辞，单一映射）；单点按钮的行为与措辞逐字不变 |
| `apps/admin-console/backend/static/admin.js:1396-1476` | `delay`、`attachAllTests`（卡头按钮 `#test-all-roles` + 进度节点 `#allTestsStatus`）、`allTestEndpoint`/`allTestBody`、`probeRoleConnection`（跳过 / 可用 / 不可用 / 未测 四态）、`runAllConnectionTests`（串行 + 间隔 + `finally` 复位） |
| `apps/admin-console/backend/static/admin.js:1664` | `attachHandlers()` 里改为挂「全部测试」；删掉卡片 2 的旧接线与 `renderServing()` 里已死的 `testRerank` 分支 |
| `apps/admin-console/backend/static/admin.css:115,243-247` | `.card header .card-tools`（卡头右侧工具行）、`.alltests` / `.alltests[hidden]`（`.rows` 的 `display:grid` 会盖住 `[hidden]`，单独一条） |
| `apps/admin-console/tests/test_admin_model_roles_page.py:175-261` | 新标记 6 条（覆盖表、串行+间隔、脚本内建控件、跳过、措辞共用、卡片 2 去重） |
| `apps/admin-console/tests/test_admin_config_page_shell.py:121,223` | 旧 `id="testRerank"` 断言 → 指针文案；探针控件必须脚本内建：新增 `>全部测试<` 不在 shell |
| `.agents/runs/connect-collection-line/model-roles-harness/render_check.cjs:245-273,859-981` | 新场景 `allRolesProbeScenario`（6 次串行、实测间隔、逐行结果、429、按钮复位）与 `okTestRoute`/`summaryLines`/`wait` 助手 |
| `.agents/runs/connect-collection-line/model-roles-harness/render_check.cjs:1020-1070` | 修正失效断言：空字段 ≠ 无端点（round 9 的 `roleBaseUrl` 运行期回退），另加**真**无端点页以覆盖「未配置端点，已跳过」 |
| `.agents/runs/connect-collection-line/model-roles-harness/stub_server.py:36-39,125-160,190-201` | 真浏览器用的 `test:<connection>=ok\|fail\|rate_limited` 模式（默认不变） |

### 2. 汇总行的确切形状

`#allTestsPanel` 里每个角色一行（复用 `.rows/.row`，标签在 220px 的 `.key` 列）：

```text
对话模型            可用（63 ms）
采集模型            可用（63 ms）
嵌入模型            可用（63 ms）
重排模型            不可用：HTTP 401：端点可达，凭据被拒绝（请求 http://127.0.0.1:9000/v1/rerank）
Web 搜索（Bocha）   可用（63 ms）
Web 搜索（Serper）  未测：限频：请 43 秒后再试（服务端已拦截，未发起调用）
```

- 可用：`` `${label} 可用（${latency_ms} ms）` ``。
- 不可用：`` `${label} 不可用：${payload.detail}（请求 ${url}）` `` —— 原因用服务端自己的 `detail`，
  与单点测试同一份措辞映射（`describeConnectionTest`）；URL 用页面已展示的测试地址。
- 未测（429 / HTTP 拒绝 / 异常）：`` `${label} 未测：${映射出来的整句}` ``，即单点按钮那一句原文。
- 跳过：`${label} 未配置端点，已跳过`（本地拦截，不发请求；与「拉取模型列表」同一条判断）。
- 运行中：按钮 disabled，`#allTestsStatus` 显示 `测试中 2/6…`；结束显示
  `测试完成：可用 4 · 不可用 1 · 未测 1`（为 0 的类目不出现）；`finally` 里复位，出错也不留在 disabled。

### 3. 验证

**① 本片新增测试（6 条标记 + 2 个 harness 场景 + 1 次真浏览器实测）** — fixture = 仓库里真实静态
资源 + 真实 `canonical_v2_connection_tests.CONNECTIONS` 表 + `fixtures.json`（真 payload）+ 真浏览器：

| 检查 | 结果 |
|---|---|
| RED（改动前，本片测试 + 更新后的 shell 断言） | `7 failed, 49 passed in 1.71s`（5 条新标记因 `const ALL_TEST_ROLES = [` 不存在而 `ValueError: substring not found`；卡片 2 去重与指针两条失败） |
| GREEN（brief 指定的定向套件） | `56 passed in 1.28s` |
| harness `render_check.cjs` | 6 行 OK，exit 0（含新场景；此前 `degradedPresetScenario` 在 HEAD 上是红的 `5 !== 4`，本片修正为 shipped 契约后转绿） |
| ruff（改动/新增的 Python） | `All checks passed!` |

**② 既有回归套件** — brief 的定向命令：
`uv run pytest -q -p no:randomly -p no:cacheprovider tests/test_admin_model_roles_page.py
tests/test_admin_config_page_shell.py tests/test_admin_config_single_channel.py
tests/test_canonical_v2_admin_secrets_api.py tests/test_nav_postgres_gating.py` → **56 passed**。
（本 worktree 同一时刻有另一个 agent 在改 uploads/seeds/DSN 的后端文件，与本片文件无交集；
上述套件只覆盖本片。）

**③ 行为证据（harness + 真浏览器）** — 浏览器实测用 scratch 静态+接口桩
（`stub_server.py 18322`，仅监听环回，`test:rerank=fail test:serper=rate_limited`，用完即杀；
18188 未动、未重启任何服务）：

| 观测 | 值 |
|---|---|
| 跑之前的卡头 | `#allTestsPanel` `hidden` 且 `display: none`（`0` 行）；按钮在 `#card-models > header` 内、贴右边缘（`hr.right - r.right = 0`） |
| 运行中（点后 ~0.9 s） | `disabled=true`，状态 `测试中 2/6…`，已有 1 行 `对话模型 可用（63 ms）`（截图 `admin-all-tests-running.png`） |
| 结束后 | `disabled=false`，状态 `测试完成：可用 4 · 不可用 1 · 未测 1`，6 行如上（截图 `admin-all-tests.png`） |
| 串行间隔（`performance.getEntriesByType('resource')`） | 6 次 `POST …/connections/test` 起点 `13029, 14242, 15447, 16654, 17860, 19065`，相邻间隔 `1213/1205/1207/1206/1205 ms` —— 全部 ≥ 服务端 `min_interval_seconds=1` |
| 卡片 2 | 只剩「保存本卡」一个按钮，`#testRerank` 为 `null`；footnote 即上面那句指针文案 |
| 布局 | 卡片宽 1232 px、面板 1186 px 且在卡内；6 行各 31 px 单行；`scrollWidth - clientWidth = 0`（无横向滚动） |

### 4. 未做 / 不适用

- **没有在活线上验收**：本片约束不重启服务、不碰 18188；线上看到的仍是旧页面，直到下一次热更新。
- 真浏览器那一轮只跑了 `rerank=fail` + `serper=rate_limited`（有端点）；「未配置端点，已跳过」
  那条只在 DOM harness 里取证（同一 `row()` 渲染路径，CSS 与其它行完全一致）。
- 对话模型与采集模型共用 `llm`：6 次探针正好用满客户端 6 次/分钟的窗口，紧接着拉过模型列表再点
  「全部测试」，尾部几行会显示「未测：限频…」——如实报出，不掩盖。
- 人类侧文档（`docs/plans/` 第 10 轮日志 + 索引）不在本片范围内，由主线补。

## 后续批次 — 中断态 / 上传 503 / 启动行

Three small backend fixes from `openspec/changes/connect-collection-line/tasks.md`
("Findings recorded, not fixed here"). No schema change, no data mutation, no service
restart, no `backend/static/**`, no crawler module, no new dependency. Not committed.

### 1. A killed crawl no longer reads as "进行中" forever

The registry's display status is derived: `apps/admin-console/backend/storage/seeds.py`
`_SELECT_COLUMNS` maps the newest matching `pipeline_run` row to the seed's
`last_run_status` (`failed→failure`, `succeeded→success`, `running→in_progress`, else
`professor_seed.last_run_status`). A run killed by the gate timeout, a host restart or an
operator SIGTERM stays `running` forever, so that seed showed "进行中" indefinitely.

**Status string the page must map: `interrupted` (已中断).** Payload paths: `GET
/api/canonical-v2/admin/seeds` (list), `GET /api/canonical-v2/admin/seeds/{id}`, both as
`last_run_status`. `interrupted` is a **read-side value only** — it is never written to
`professor_seed.last_run_status`, so the page must treat it as a terminal state (no
"重新爬取" needed to clear it, and the trigger path keeps working because
`claim_seed_for_trigger` reads the *column*, which still says `in_progress`).

| File | Line | Change |
|---|---|---|
| `apps/admin-console/backend/storage/seeds.py` | 19–23 | `STALLED_RUN_AFTER_HOURS = 6` with the rationale (longest declared task timeout 5400 s) |
| " | 29–41 | read-side type now carries `interrupted`; comment states why the write-side tuple does not |
| " | 148, 169–178 | `_SELECT_COLUMNS` is an f-string; the `running` branch becomes `COALESCE(started_at, created_at) < now() - interval '6 hours' → 'interrupted'`, else `'in_progress'`; every other mapping untouched |
| `apps/admin-console/tests/test_seed_storage_models.py` | 59, 71, 76, 97 | new no-DB locks (see below); the 51–56 assertions updated to the new SQL shape |
| `apps/admin-console/tests/test_canonical_v2_seeds_api.py` | 231 (`_insert_running_run`), 266 (case) | Postgres-backed end-to-end case |

`VALID_LAST_RUN_STATUSES`: **not** extended, and deliberately so. A repo-wide search
(incl. ignored files) finds the tuple only at its own definition — nothing imports it, so
it validates neither reads nor writes. It mirrors
`V022_professor_seed.PROFESSOR_SEED_LAST_RUN_STATUSES`, i.e. the column's CHECK
constraint, and the constraint refuses `interrupted` (verified against a real database):

```
constraint: CHECK ((last_run_status = ANY (ARRAY['success','failure','in_progress','never_run','adapter_missing'])))
column accepts 'interrupted': no (CheckViolation)
column accepts 'in_progress': yes
VALID_LAST_RUN_STATUSES: ('success', 'failure', 'in_progress', 'never_run', 'adapter_missing')
```

What *did* need the value is the Pydantic API-response type (`SeedLastRunStatus`), which
`Seed.model_validate` applies to every row the endpoints return — without it the first
`interrupted` row would fail validation and the endpoint would 500. Locked by
`test_seed_accepts_the_derived_interrupted_status`.

**Runs list is left alone, as instructed.** `GET /api/canonical-v2/admin/seeds/{seed_id}/runs`
(`backend/api/canonical_v2_seeds.py:254-274`) builds each item from
`gate.history(task_id)` → `JobRun.as_dict(include_samples=True)`, i.e. the **jobs ledger**
(`jobs.sqlite3`), not `pipeline_run`. It is a different ledger with its own status
vocabulary (the runner's own rows), so no second rule was invented there.

### 2. The uploads precheck answers the stable 503 instead of raising

`runtime.register`'s preflight is `backend/api/canonical_v2_uploads.py:_postgres_preflight`,
which calls `backend/api/upload.py:_resolve_upload_dsn()` → `resolve_dsn(None)` **outside
any fail-soft wrapper**: with the console unconfigured that is a `RuntimeError`, i.e. a 500
(the sibling `_batch_progress` is the fail-soft one and was left exactly as it was).

| File | Line | Change |
|---|---|---|
| `apps/admin-console/backend/api/canonical_v2_uploads.py` | 17, 46 | `resolve_console_dsn` import; `CONSOLE_DATABASE_NOT_CONFIGURED` constant (same string as the seeds surface) |
| " | 155, 162–176 | `_console_dsn(request)` + `require_console_database(request, runtime)` — the `require_postgres` decision table: unconfigured **and** the probe found no source → `console_database_not_configured`; unconfigured but the probe has a source → this surface's own `upload_requires_postgres`; configured → return |
| " | 247–249 | the guard runs on commits only (`if not dry_run:`), before `runtime.register` |
| " | 270 | exported in `__all__` |
| `apps/admin-console/tests/test_canonical_v2_uploads_api.py` | 76, 113 (`_client(..., preflight=)`), 239 (`_clear_console_env`), 239–271 (new cases), 214 (degradation case declares a configured database) | see below |

Decision detail worth the reviewer's eye: the guard sits **before** `register`, so on an
unconfigured console a malformed payload answers 503 rather than 400/413/422. That is the
seeds surface's own precedence (its guard precedes id-existence checks: `GET /seeds/1`
answers 503, not 404) and it is what makes the *code* consistent across gated surfaces;
"console has no database" is a stronger statement than "that row/domain does not exist".
With a configured database nothing changed at all — the shape cases still answer
400/413/422, verified by the existing cases (they now declare a configured database, with
the reason in a comment, exactly as the seeds suite does).

### 3. The startup line is visible in the boot log

| File | Line | Change |
|---|---|---|
| `apps/admin-console/backend/main.py` | 104–109 | `state` hoisted; the `logging.info("console_database=%s", state)` call is **kept** and one `print(f"[canonical-v2] console_database={state}", flush=True)` is added — the shape `admin_auth.seed_initial_admin` uses for the first-boot password |
| `apps/admin-console/tests/test_console_dsn_single_source.py` | 107–137 | captures both channels for both states |

Announced state only: the test asserts the DSN's user/password/host (`hunter2`,
`db.internal`) never reach stdout, and the line never carries a credential.

### Verification (layered)

**① New tests this slice — 9 cases, fixture source stated per cluster.**

| Cluster | Cases | Fixture |
|---|---|---|
| `tests/test_seed_storage_models.py` | `test_a_stale_running_run_is_reported_as_interrupted` (SQL derives the value, threshold is the constant, judged by `COALESCE(started_at, created_at)`), `test_the_stall_threshold_is_wider_than_every_declared_task_timeout` (6 h > 5400 s, read from the real task table), `test_seed_accepts_the_derived_interrupted_status` (the response model cannot 500 on it), `test_interrupted_is_not_a_column_value` (write-side tuple stays the five column values) | constructed values + the real `JOB_TASKS_BY_ID` table; no database |
| `tests/test_canonical_v2_seeds_api.py` | `test_a_killed_run_reads_as_interrupted_not_in_progress` — inserts a `running` `pipeline_run` 7 h old → registry says `interrupted` (detail + list); a fresh one → `in_progress`; closed as `failed` → `failure` | **real Postgres** (see below), rows written through the production `open_pipeline_run` / `close_pipeline_run` so the fixture cannot drift from the writer |
| `tests/test_canonical_v2_uploads_api.py` | `test_a_commit_without_a_configured_console_database_is_a_stable_503` (parametrised over both unconfigured shapes, with the **production** preflight wired and the probe reporting the database available — the exact shape that raised) + dry-run 202 / list 200 / detail 200 in the same case | constructed scenario, stub probe + recording spawn; the production preflight callback is imported, not re-implemented |
| `tests/test_console_dsn_single_source.py` | `test_the_boot_announcement_states_the_console_database_never_its_dsn` (parametrised configured/unconfigured; `capsys` + `caplog`) | constructed scenario |

**② Pre-existing regression suites** (the brief's command list, run unmodified):

```bash
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/test_canonical_v2_seeds_api.py tests/test_canonical_v2_uploads_api.py \
  tests/test_canonical_v2_uploads_runtime.py tests/test_managed_runtime_bootstrap.py
# → 42 passed, 2 skipped   (the two skips are the DATABASE_URL_TEST-gated cases)
```

With the two extended files added:

```bash
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/test_canonical_v2_seeds_api.py tests/test_canonical_v2_uploads_api.py \
  tests/test_canonical_v2_uploads_runtime.py tests/test_managed_runtime_bootstrap.py \
  tests/test_console_dsn_single_source.py tests/test_seed_storage_models.py
# without a test database → 57 passed, 2 skipped
# with the throwaway database → 59 passed   (both gated cases now execute)
```

Adjacent suites that touch the changed code paths (not in the brief's list, run because
they read the changed SQL / the widened type):
`tests/test_migration_v022.py tests/test_seeds_api.py tests/test_seed_cron.py
tests/test_import_professor_seeds.py tests/test_admin_console_shell.py
tests/test_nav_postgres_gating.py` → **31 passed, 31 skipped**. The skips are the
`postgres_data_ready` fixture, which cannot run in this worktree at all: it needs
`ALEMBIC_DATABASE_URL` / `ALEMBIC_EXPECTED_DATABASE` / `ALEMBIC_TARGET_KIND` (the
fail-closed destructive-target contract) **and** `docs/专辑项目导出1768807339.xlsx`, which
does not exist here — pre-existing, unrelated to this slice (same errors with the slice
stashed: setup fails inside `conftest.postgres_data_ready` before any changed code runs).

Lint: `uv tool run ruff@0.8.0 check` on all seven touched files → `All checks passed!`.
`ruff format --check` reports the same four files before and after the change (they are
format-dirty at HEAD); a formatted copy diff confirms none of the new lines is the
offender, so no reformatting was done (it would only add unrelated churn).

**③ Real-database evidence (the throwaway-database procedure, reproducible).**

`test_a_killed_run_reads_as_interrupted_not_in_progress` needs a *disposable* database
(it writes `pipeline_run` rows). Created + marked + migrated for the run, dropped after
(nothing else was touched; `miroflow_collection_v1` was never connected to):

```bash
# 1. create + mark (marker = the fail-closed destructive-target identity)
CREATE DATABASE miroflow_collection_line_fixbatch;
COMMENT ON DATABASE miroflow_collection_line_fixbatch
  IS 'miroflow:destructive-target:v1:disposable:miroflow_collection_line_fixbatch';
# 2. migrate
ALEMBIC_DATABASE_URL=postgresql://miroflow@127.0.0.1:55458/miroflow_collection_line_fixbatch \
ALEMBIC_EXPECTED_DATABASE=miroflow_collection_line_fixbatch ALEMBIC_TARGET_KIND=disposable \
  uv run python -c 'from alembic import command; from alembic.config import Config; command.upgrade(Config("alembic.ini"), "head")'
# 3. run the tests, 4. DROP DATABASE … WITH (FORCE)
```

RED → GREEN on the real database (production code restored to HEAD for the RED run only):

```
# RED (old CASE restored)
E           AssertionError: assert 'in_progress' == 'interrupted'
E             - interrupted
E             + in_progress
tests/test_canonical_v2_seeds_api.py:301
FAILED tests/test_seed_storage_models.py::test_a_stale_running_run_is_reported_as_interrupted
FAILED tests/test_canonical_v2_seeds_api.py::test_a_killed_run_reads_as_interrupted_not_in_progress
2 failed, 12 passed
# GREEN (fix in place) → 14 passed
```

RED → GREEN for the 503 (the flagged call site, `backend/api/upload.py:1257`) and for the
boot line (both production edits reverted for the RED run):

```
# RED
E           RuntimeError: DATABASE_URL is required. Example: postgresql+psycopg://user:pass@localhost:5432/miroflow
../miroflow-agent/src/data_agents/storage/postgres/connection.py:44: RuntimeError
backend/api/upload.py:1257: in _resolve_upload_dsn
4 failed in 1.40s
# GREEN → 4 passed in 0.45s
```

Incidental confirmation of fix 3 inside pytest's captured stdout of the RED run above:
`[canonical-v2] console_database=configured`.

### Notes for the parent / not verified

1. **Page side (not mine).** `backend/static/seeds.html` must map the new value; the
   string is `interrupted`. The React SPA (`frontend/src/api.ts:768`
   `SeedLastRunStatus` union, `frontend/src/pages/Seeds.tsx:40` `STATUS_LABELS`) does
   **not** know it either — it renders `undefined` for an unknown status. Left untouched
   (out of scope here); it needs the same one-line addition if that surface is still
   served anywhere.
2. **`COALESCE(started_at, created_at)`** is kept for symmetry with the `last_run_at`
   sub-select, but it is currently unreachable: `pipeline_run.started_at` is `NOT NULL`
   (verified against the real schema). A stale row is therefore always judged by its
   start time.
3. **Residual inconsistency, deliberately not papered over:** an unconfigured console
   with a *real* probe answers the stable code only on the commit path, which is what was
   asked; the read paths never needed the DSN, the dry run still works, and the detail
   path stays fail-soft. If the page should also see `console_database_not_configured`
   from `GET /uploads` (`uploads.postgres.available=false` today), that is a further
   decision, not a bug.
4. **The guard's 3-line `_console_dsn` mirrors `canonical_v2_seeds._console_dsn`.** Sharing
   it would mean either a private cross-module import or a move into `backend/deps.py`;
   both are wider than this slice, so the mirror is local and named after the model.
5. **Human docs (`docs/plans/` log + index) were not touched** — per the brief this batch
   appends evidence only; the round log/index entry stays with the main line.

## 后续批次（页面）— 构建与运维的甲方语言

Round 11 (2026-09-19)。范围：`/jobs` 一个页面批次 —— 把 ops 组的三条工程任务收进默认折叠的
「高级操作」块，把页面上的构建期词汇换成甲方运维看得懂的说法。只动 `jobs.py` 的 label/hint
（三条 ops 任务）、静态页 `jobs.html`、两个标记套件、渲染 harness；未改后端 Python 其它文件、
未加依赖、未重启服务、未碰 18188、未提交。

### 1. 改了什么（文件 · 行）

| 文件 | 改动 |
|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py:394,397` | `ops-milvus-backfill` → label「更新检索索引」，hint「把新入库的数据写进检索索引——做完这一步，用户才能检索到新内容。」 |
| " `:415,418` | `ops-milvus-backfill-dry-run` → 「更新检索索引 · 预演」/「只统计将要更新多少内容，不真正写入。正式更新前先跑它，确认影响范围。」 |
| " `:437,440` | `ops-retrieval-validation` → 「检索自检」/「对当前服务跑一遍检索自检，确认更新之后检索仍然正常。」 |
| `apps/admin-console/backend/static/jobs.html:161-169` | CSS：`details.group-advanced` 的 summary 字号/字重、展开时的间距、状态那段 `.when` 收进同一行 |
| " `:278` | 页脚换成「运行安排由系统固定，页面只能查看；手动执行与自动执行受同样的安全限制：同一任务不会重复运行，连续失败会自动暂停。」 |
| " `:379-381` | `GROUPS.ops` 加 `collapsed: true`；标题换成 summary 文案，purpose 换成大白话，新增 `guide` 三步顺序 |
| " `:390,392` | `UNAVAILABLE_TEXT.postgres_unavailable` →「当前不可用：需要本机数据库」；新增 `SCHEDULE_TEXT {"手动触发": "人工触发"}` |
| " `:458,485` | 「从未运行」→「尚未运行」（`runBadge` 空跑分支 + `lastRunCell`） |
| " `:508-531` | `tagPills()`：不再画 `requires_postgres` 标签；额度/时间窗/开关四种标签改词 |
| " `:596-598,611` | `scheduleText()`：下发值 `手动触发` 在页面上显示为「人工触发」 |
| " `:621-634` | `groupStatusLine()`：折叠组的摘要状态行（`最近一次：…`） |
| " `:637-656` | `groupSection()`：前三个分组照旧 `<h3>` 展开，ops 组渲染成 `<details class="group-advanced">`（默认不 open），表头「节奏（下次运行）」→「运行安排」（`:645`），`renderGroups()` 收敛成 `GROUPS.map(groupSection)`（`:658-665`） |
| `apps/admin-console/tests/test_canonical_v2_jobs_registry.py:95-124` | 新增 `test_ops_tasks_speak_the_operators_language`：三条 ops 的 label/hint 逐字相等 + 不得出现 `Milvus / 构建期 / 干跑 / 配额 / 闸门` |
| `apps/admin-console/tests/test_canonical_v2_jobs_api.py:275-311` | 新增 `test_jobs_page_folds_the_build_group_away`：折叠块标记、摘要、三步指南、大白话标签、新页脚、「当前不可用：需要本机数据库」、三条新 label，以及旧词（构建与运维 / 需构建库 / 需要构建期数据库 / 节奏（下次运行）/ 从未运行）全部不再出现 |
| ".py 同上 `:253-273` | `test_jobs_page_is_served` 的标记表去掉「构建与运维」（该词已不在页面上） |
| `.agents/runs/connect-collection-line/jobs-page-harness/render_check.cjs` | 断言改写：3 个 `<h3>` + 折叠块、摘要状态、大白话标签、禁用的「立即运行」+ 新原因；新增 4b 场景（available 的 PG 任务不画任何标签、摘要行跟随最新一次运行）；末行输出改为 3 组 + 高级操作 |
| `.agents/runs/connect-collection-line/jobs-page-harness/stub_server.py` | 新增（stdlib、仅环回）：把 shipped `jobs.html` + 真 `task_views()` payload 供真浏览器看，用于本片实测 |
| `.agents/runs/connect-collection-line/jobs-page-harness/jobs-advanced-collapsed.png` / `-open.png` | 真浏览器截图（折叠 / 展开） |

未动：`as_dict()` 的字段、任何 task_id、任何 argv/params/gate 字段、任何端点、任何 POST body。
`requires_postgres` 仍在 payload 里（页面不再为它画标签，只在按钮禁用时用它当原因）。

### 2. 操作者现在看到的确切字符串（真浏览器 `innerText`，非源码转述）

折叠状态（首屏）：

```text
▸ 高级操作：数据更新与检索自检（一般不需要手动执行） 最近一次：尚未运行
```

展开后（三行任务，取自真浏览器）：

```text
任务                最近运行      运行安排    操作
更新检索索引        尚未运行      人工触发    [企业 ▾] 立即运行（禁用） 当前不可用：需要本机数据库
把新入库的数据写进检索索引——做完这一步，用户才能检索到新内容。
[会消耗大模型调用额度（本轮上限 500）]  [技术细节]

更新检索索引 · 预演  尚未运行      人工触发    [企业 ▾] 立即运行（禁用） 当前不可用：需要本机数据库
只统计将要更新多少内容，不真正写入。正式更新前先跑它，确认影响范围。

检索自检            尚未运行      人工触发    立即运行（禁用） 当前不可用：需要本机数据库
对当前服务跑一遍检索自检，确认更新之后检索仍然正常。

你导入了新数据或刚跑完采集后，用下面三步让检索能看到新内容，并确认检索正常。
建议顺序：① 预演（看影响范围）→ ② 更新检索索引 → ③ 检索自检。耗时从几十秒到几分钟不等。
```

其它分组（同一套标签，真浏览器读到的企业新闻采集行）：

```text
[会消耗网络检索额度（本轮上限 200）] [仅在允许的时间段运行] [受采集开关控制]
页脚：运行安排由系统固定，页面只能查看；手动执行与自动执行受同样的安全限制：同一任务不会重复运行，连续失败会自动暂停。
```

`listHint` 仍是「共 15 个任务 · 生成于 …」；`技术细节`（任务 ID / 命令 / 超时 / cron）逐任务保留；
摘要行在有运行记录时形如「最近一次：更新检索索引 成功 2026-09-19 03:10」（DOM harness 里用一条
`ops-milvus-backfill` 的成功 run 取证；真浏览器那一轮 ops 三条都没有运行记录，所以显示「尚未运行」）。

### 3. 验证

**① 本片新增/改写的测试** — fixture：真 `JOB_TASKS` 表 + 真静态页 + 真 `task_views()` payload。

| 命令 | 结果 |
|---|---|
| 新增两条（`test_ops_tasks_speak_the_operators_language`、`test_jobs_page_folds_the_build_group_away`）对 HEAD 生产代码（`git restore --source=HEAD --worktree` 两个生产文件、测试保持新版） | **RED：`2 failed in 0.23s`** — `AssertionError: assert ('Milvus 回填（干…' == ('更新检索索引 · 预演…')`；`AssertionError: <details class="group-advanced"><summary>` in … |
| 同一对测试、恢复本片代码 | **GREEN：`2 passed`** |
| harness 对 HEAD 页面（payload/断言为新版） | **RED：`FAILED: the three everyday groups keep their heading — 4 !== 3`** |
| harness 对本片页面 | **GREEN：`OK — all /jobs render assertions passed`（exit 0）** |

**② 既有回归套件**（brief 指定的定向命令 + jobs 家族同批）：

```bash
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/test_canonical_v2_jobs_registry.py tests/test_canonical_v2_jobs_api.py \
  tests/test_canonical_v2_jobs_runner.py tests/test_canonical_v2_jobs_store.py \
  tests/test_nav_postgres_gating.py tests/test_admin_console_shell.py
# 117 passed in 5.61s
uv tool run ruff@0.8.0 check <jobs.py + 两个测试 + stub_server.py>   # All checks passed!
cd apps/miroflow-agent && uv run python -c "from src.data_agents.canonical_v2.jobs import JOB_TASKS; …"
# 直接打印三条 ops 的新 label/hint（agent 侧 venv 自证可导入，秒级返回）
```

`cd apps/miroflow-agent && uv run pytest tests -k "job_task or jobs or registry"` **在本 app 里选不到
任何测试**（`apps/miroflow-agent/tests` 无一处引用 jobs 注册表；该命令在收集阶段阻塞 7+ 分钟后仍
0% CPU，已停掉）——与 round 6 的记录一致：这个模块住在 agent app，但由 admin-console 套件行使。

**③ 页面级证据（harness + 真浏览器）**：

```bash
cd apps/admin-console
uv run python ../../.agents/runs/connect-collection-line/jobs-page-harness/make_payload.py
node ../../.agents/runs/connect-collection-line/jobs-page-harness/render_check.cjs
# OK — all /jobs render assertions passed
# groups: <h3>日常采集</h3> | <h3>数据导入</h3> | <h3>教授采集源</h3> | <summary>高级操作…</summary>
# rows per group: 日常采集=8, 数据导入=4, 教授采集源=3, 高级操作=4
# history rows: 7
# 4b 场景追加：available 的 ops-retrieval-validation 行既无标签也无原因、出现可点按钮；给
# ops-milvus-backfill 喂一条成功 run 后摘要变成「最近一次：更新检索索引 成功 2026-…」
```

真浏览器（scratch 静态 + 桩接口 `stub_server.py`，**127.0.0.1:18325 仅环回，用完即杀**；18188 未动、
未重启任何服务）：

```bash
cd apps/admin-console && uv run python ../../.agents/runs/.../jobs-page-harness/stub_server.py 18325
agent-browser open http://127.0.0.1:18325/jobs
# collapsed: true（页面里 <details open> 计数 0）
# summary: 高级操作：数据更新与检索自检（一般不需要手动执行）最近一次：尚未运行
# h3s: 日常采集 | 数据导入 | 教授采集源      header: 任务 | 最近运行 | 运行安排 | 操作
# 摘要行与状态同一行（间距 8px）、::marker display=inline（三角保留）、
# documentElement.scrollWidth - clientWidth = 0（无横向滚动）
# 截图：jobs-advanced-collapsed.png / jobs-advanced-open.png
```

未做的检查：没有点「立即运行」真跑一条任务（ops 三条都因本机无库而禁用；collection 任务的
POST body 由 harness 第 7 段锁定 `{"params": {"domain": "professor"}}` / `{"params": {}}`）。

### 4. 未做 / 留给主线

- **页首说明卡没动**（`jobs.html:252,257` 仍写「看它们各自的节奏…」「手动触发与周期运行共用同一道
  闸门：采集开关、配额、采集时间窗都不会被绕过」）。brief 只点名页脚那一句，卡片的「闸门/配额」
  属于同一次投诉的词汇，但不在本片范围内 —— 记在这里，别让它成为漏网之词。
- **`schedule_display` 的 API 值没改**（`jobs.py:178` 默认仍是「手动触发」）：本片是页面批次，
  改词在 `scheduleText()` 一层完成；payload 兼容性不受影响。
- **ops 三条的 `description` 仍带「Milvus / 构建期 / 干跑」**（`jobs.py:395,416,438`，brief 只许改
  label/hint）。页面从不渲染 `description`（harness 断言它的原文不出现在页面上），但它是 API
  可见字段，若要让接口也脱敏需另开一条。
- **没有在活线（18188）上看到新页面**：本片约束不重启服务，线上仍是旧页面，直到下一次热更新。
- **人类侧文档（`docs/plans/` 第 11 轮日志 + 索引）与 OpenSpec `tasks.md`/`acceptance.md` 未动**，
  按本片范围只追加本证据；round log / index / 勾选留给主线。

## 后续批次（页面）— 抓取动作白话化

Round 12 (2026-09-19)。范围：`/seeds` 一个页面批次 —— 行首两个触发按钮改成结果语言
（「检查名册」/「开始抓取」），抓取条数收成表头上一处「抓取范围」选择器（前 20 / 前 50 / 前 100 条 /
全部），确认与横幅一律白话，并把「全部」从不可达变成可达；未改后端 Python（除测试）、未加依赖、
未重启服务、未碰 18188、未提交。

### 1. 改了什么（文件 · 行）

| 文件 | 改动 |
|---|---|
| `apps/admin-console/backend/static/seeds.html:237-246` | CSS：`.toolbar label.scope`（行内标签 + 下拉对齐）与 `.toolbar label.scope select`（`width: auto; min-width: 112px`，不再吃满 100%） |
| " `:311-325` | 工具栏：`刷新` 右边加「抓取范围」`<select id="scopeSelect">`（四个选项，`sample:20` 默认）；脚注那句模式术语换成「「检查名册」只验证能不能解析，不写入数据；「开始抓取」按上面选的抓取范围真实抓取并写入（同样受系统安全限制）。」 |
| " `:409-414` | 新增 `SCOPE_OPTIONS`：选项值 → `{ label, banner, body }` 三件套，四组 body 就是接口唯一承认的四组 |
| " `:598-601` | 行内按钮：`data-action="preview"`/`"sample"` → `"check"`/`"collect"`，标签「检查名册」「开始抓取」，title 换成两句白话（顺带补上「约 1 分钟」「会真实访问学校网站」） |
| " `:640-674` | `handleAction`：两条触发分支；抽出 `seedById()` 与 `trigger(seedId, body, label)`（POST + 横幅 + 重载运行记录/清单）。`修改 / 运行记录 / 删除`、就地编辑保存、删除确认、降级分支、`loadRuns()` 的 scrollIntoView 全部未动 |
| `apps/admin-console/tests/test_nav_postgres_gating.py:103-188` | 新增 6 条页面锁（见 §3 ①）；文件顶部加 `import re` |
| `.agents/runs/connect-collection-line/seeds-page-harness/render_check.cjs` | 新增（node stdlib + `vm`，无依赖）：把页面自己的内联脚本放进 DOM 桩里跑，按真实点击驱动 `handleAction`，锁住五个动作的请求体、确认文案、取消不写、失败原因、行内按钮顺序 |
| `.agents/runs/connect-collection-line/seeds-page-harness/stub_server.py` | 新增（stdlib、仅环回）：shipped `seeds.html` + 四条仿真采集源，供真浏览器实测 |
| `.agents/runs/connect-collection-line/seeds-page-harness/seeds-actions-1440.png` / `-1024.png` | 真浏览器截图（1440 / 1024） |

未动：任何端点、任何 task_id、任何 argv/params/gate 字段；`MODE_LABEL`（运行记录「模式」列，见 §4）；
`nav_auth.js` 与其它静态页。

### 2. 五个动作的确切请求体（真浏览器内点出来，桩服务端日志原文）

| 界面动作 | 确认（`window.confirm`，原文） | `POST /api/canonical-v2/admin/seeds/{id}/trigger` body | 成功横幅 |
|---|---|---|---|
| 「检查名册」 | 无 | `{"mode": "preview"}` | `已开始：深圳大学 · 检查名册` |
| 范围=前 20 条 + 「开始抓取」 | `确认抓取「哈尔滨工业大学（深圳）」的前 20 条教授主页？会真实访问学校网站。` | `{"mode": "sample", "limit": 20}` | `已开始：<学校> · 抓取前 20 条` |
| 范围=前 50 条 + 「开始抓取」 | 同上句式，`前 50 条` | `{"mode": "sample", "limit": 50}` | `已开始：<学校> · 抓取前 50 条` |
| 范围=前 100 条 + 「开始抓取」 | `确认抓取「南方科技大学」的前 100 条教授主页？会真实访问学校网站。` | `{"mode": "sample", "limit": 100}` | `已开始：南方科技大学 · 抓取前 100 条` |
| 范围=全部 + 「开始抓取」 | `确认抓取「清华大学深圳国际研究生院」的全部教授主页？会真实访问学校网站。` ⏎ `全部抓取可能耗时较长（上千条时可能超过任务上限）。` | `{"mode": "full"}` | `已开始：清华大学深圳国际研究生院 · 全部抓取` |

桩服务端的原始记录（`/tmp/seeds-stub.log`）：

```text
trigger #1: /api/canonical-v2/admin/seeds/18/trigger {'mode': 'full'}
trigger #2: /api/canonical-v2/admin/seeds/30/trigger {'mode': 'sample', 'limit': 100}
trigger #3: /api/canonical-v2/admin/seeds/31/trigger {'mode': 'preview'}
```

取消确认后桩服务端日志里**没有任何** trigger 行 ——「开始抓取」不确认就绝不写。

### 3. 验证

**① 本片新增的测试** — fixture：真静态页（`authorized_client` 走真路由图）+ 页面自己的内联脚本。

| 测试 | 锁住什么 |
|---|---|
| `test_seeds_page_offers_the_two_outcome_actions` | 两个新标签 + 两条 title 原文 |
| `test_seeds_page_scope_selector_carries_the_legal_combinations_only` | `<select id="scopeSelect">` 的存在、「抓取范围」标签就在它前面、四个选项的 value↔文案逐字与顺序、第一项默认 |
| `test_seeds_page_scope_options_map_to_the_documented_request_bodies` | 五组 body 原文都在页面上，且 `limit:` 只出现 20/50/100（不许第五种组合） |
| `test_seeds_page_never_writes_without_the_confirm` | 确认文案三段原文 + 全部抓取的耗时提醒 + `if (!window.confirm(message)) return;` 位于触发调用之前 |
| `test_seeds_page_drops_the_internal_mode_vocabulary` | `预览抓取 / 抽样抓取 / 触发抓取走闸门 / 预览 = 只跑发现阶段 / 抽样 = 抓取上限 20 条画像 / data-action="preview" / data-action="sample"` 全部不在页面里 |
| harness `render_check.cjs`（7 组断言） | 每行五个按钮及其顺序、四个选项的 value/文案/默认、五个动作的 body 与横幅、取消不发请求、第二行的确认报自己的学校、503 时横幅仍是 `控制台没有配置数据库（DATABASE_URL）：seed 管理不可用。` |

```bash
cd apps/admin-console
uv run pytest -q -p no:randomly -p no:cacheprovider tests/test_nav_postgres_gating.py
# 新增 6 条打 HEAD 页面（git show HEAD:… > seeds.html）：
#   5 failed, 10 passed in 0.27s   ← RED（新页面恢复后 15 passed）
node ../../.agents/runs/connect-collection-line/seeds-page-harness/render_check.cjs
# HEAD 页面：FAILED: Expected values … （行内按钮仍是 预览抓取|抽样抓取…）
# 本片页面：OK — all /seeds render assertions passed
#   buttons per row: 检查名册 | 开始抓取 | 修改 | 运行记录 | 删除
#   scopes: 前 20 条 → sample:20 | 前 50 条 → sample:50 | 前 100 条 → sample:100 | 全部 → full
#   bodies: {"mode":"preview"} {"mode":"sample","limit":20} {"mode":"sample","limit":50}
#           {"mode":"sample","limit":100} {"mode":"full"} {"mode":"full"} {"mode":"preview"}
```

**② 既有回归套件**（brief 指定的定向命令，两个生产/测试文件保持本片版本）：

```bash
cd apps/admin-console && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/test_nav_postgres_gating.py tests/test_admin_console_shell.py \
  tests/test_canonical_v2_seeds_api.py tests/test_canonical_v2_admin_secrets_api.py
# 44 passed, 2 skipped in 2.16s
uv tool run ruff@0.8.0 check tests/test_nav_postgres_gating.py      # All checks passed!
uv tool run ruff@0.8.0 format --check tests/test_nav_postgres_gating.py  # 1 file already formatted
```

保留的既有断言全部仍在：`failureReason(run)`、`exit_code`、`stderr_excerpt`、`escapeHtml`、
`clip(run.stderr_excerpt, 160)`、`console_database_not_configured`、`DATABASE_URL`、`已中断`、
就地编辑标记、`/api/canonical-v2/admin/seeds/{id}/trigger` 的 body 语义（`test_canonical_v2_seeds_api.py`
的 `{"mode": "preview"}` / `{"mode": "sample", "limit": 20}` 用例未改也未破）。

**③ 页面级证据（真浏览器，桩服务端 + 真页面）**：

```bash
cd apps/admin-console && uv run python ../../.agents/runs/connect-collection-line/seeds-page-harness/stub_server.py 18326
agent-browser open http://127.0.0.1:18326/seeds      # 1440×900 与 1024×800 两个视口
```

- 行内五个按钮**全在一行**：`oneLine: true`、五个按钮 `getBoundingClientRect().top` 只有一个值、
  行高 66px（与 Round 4 的测量一致）；`.actions` 的 `scrollWidth 344 / clientWidth 320`
  在改前（HEAD 页面）与改后**逐值相同** —— 本片没有让行变宽（剩下的 13px 溢出是既有现象，
  见 §4）。
- 页面级横向滚动 `documentElement.scrollWidth - clientWidth = 0`（1440 与 1024 均是）；
  1024 下仍是表格容器自己滚（`wrapOverflowX 173`），与 Round 4 的设计一致。
- 真浏览器点的三跳：`检查名册`（无对话框→直接 POST）、`全部`+`开始抓取`（确认里带耗时提醒→
  接受→POST）、`前 100 条`+`开始抓取`（接受→POST），横幅与 §2 表格逐字一致；
  点「开始抓取」后 `dialog dismiss` → 桩日志无 trigger 行。
- 点「运行记录」：面板刷新（`runHint=采集源 31`、2 行历史、失败行显示
  `exit_code 1 · stderr：TimeoutError: …`，即 `clip(…, 160)` + `failureReason` 路径未变）。

### 4. 未做 / 留给主线

- **运行记录表的「模式」列仍显示 预览 / 抽样 / 全量**（`seeds.html:402-406` 的 `MODE_LABEL`，
  键就是接口的三个 mode 值）。brief 第 4 条点名的字符串（`预览抓取 / 抽样抓取 / 触发抓取走闸门`…）
  已从页面上消失，但这一列仍是同一类词汇；brief 第 5 条要求「运行记录面板保持原样」，
  所以没有动它 —— 若要一并白话化（例如 preview→「检查名册」、full→「全部抓取」），
  是一行映射的改动，请主线定夺。
- **活线 18188 上没有看到新页面**：本片不重启服务，线上仍是旧页面，直到下一次热更新。
- **没有真“抓一次”**（会真实访问学校网站、且本片约束不动活线）：请求体的正确性由真浏览器 +
  桩服务端日志与 node harness 锁定，真运行留给热更新后的验收。
- **人类侧文档（`docs/plans/` 第 12 轮日志 + 索引）与 OpenSpec `tasks.md`/`acceptance.md` 未动**，
  按本片范围只追加本证据；round log / index / 勾选留给主线。

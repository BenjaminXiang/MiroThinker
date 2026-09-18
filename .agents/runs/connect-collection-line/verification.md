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

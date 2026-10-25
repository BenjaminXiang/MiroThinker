# Verification: fix-answer-guards-and-job-timezone

Date: 2026-10-25
Line: serving worktree `switch/embedding-model-to-qwen37-flash`

## 1. Protocol marker leak

`_PROSE_PRIVATE_MARKER_PATTERNS[0]` widened from

```python
r"<\|canonical_v2[A-Za-z0-9_]{0,48}\|>"
```

to

```python
r"</?\|canonical_v2[A-Za-z0-9_]{0,48}\|>"
```

Regression: `test_prose_decoder_redacts_closing_answer_marker` feeds
`前文</|canonical_v2_answer_v1|>后文` char-by-char through
`_ProseWireDecoder`; the marker is absent from the output, `前文`/`后文` remain,
and the redaction list contains the marker. Passed.

## 2. Unknown named company

New helpers in `followup_referents.py`:

- `query_company_name` — rejects question words, anaphora, `的`, and relation
  verbs (`创办/创立/参与/投资/收购/旗下/子公司/母公司`); rejects matches whose
  stripped core is shorter than two characters.
- `company_names_match` — strips city/legal/industry scaffolding and requires
  one core to contain the other.

`_answer_selector` now skips a local `company` claim when a non-enumeration
query names a company and the handle name does not match. Web claims are
untouched.

Unit evidence:

| Test | Result |
|---|---|
| `test_query_company_name_excludes_scaffolding` (8 phrasings) | passed |
| `test_company_names_match_rejects_a_neighbour_name` | passed |
| `test_company_names_match_resolves_partial_forms` (3) | passed |
| `test_selector_drops_local_company_claims_for_an_unknown_named_company` | passed |
| `test_selector_keeps_local_company_claim_for_a_matching_partial_name` | passed |
| `test_followup_referents.py` total | 163 passed |
| `test_knowledge_serving_isolated.py` total | 315 passed |

## 3. Jobs next-run timezone

The customer bundle's `jobs.py` already carried `_resolve_job_timezone`
(`JOB_TIMEZONE_ENV = MIROTHINKER_JOB_TIMEZONE`) and passed it to
`cron_next_fire`; `run.sh` exports `Asia/Shanghai`. Customer-machine probe:

```text
tz: Asia/Shanghai
next: 2026-10-26T02:00:00+08:00
```

The worktree-side helper/tests (`job_timezone`,
`test_next_fire_in_job_timezone_uses_local_wall_clock`,
`test_job_timezone_uses_the_launcher_env`) also pass; the admin-console jobs
registry suite is 50 passed.

## 4. Deployment incident (recorded)

The first deploy copied the **worktree** `jobs.py` over the bundle's file. The
worktree version is older in that area and lacks `JOB_DATABASE_URL_ENV`, so the
service failed at startup with:

```text
ImportError: cannot import name 'JOB_DATABASE_URL_ENV'
```

The bundle's own backup `jobs.py.bak-limit-20261022-170050` was restored
(md5 `2ca7f184…`), which contains the constant and the timezone fix. The
deployed admin-console imports `backend.api.canonical_v2_jobs` successfully
again. No data was touched.

Lesson: the serving bundle carries hotfixes not present in the worktree; diff
before overwriting a bundle module.

## 5. Live verification

Pending the service restart (the bundle's cold mount is slow under memory
pressure). Planned probes:

- `严格验收机器人公司是做什么的` → no 普渡 citation/profile.
- `丁文伯创办的公司是哪家` → 深圳无界智航 (guard must not fire on relation
  phrasing).
- `普渡科技公司是做什么的` → 普渡 still resolves (partial-name control).
- `深圳哪些公司做激光雷达` → enumeration unchanged.
- Jobs list `next_run_at` → `…T02:00:00+08:00`.

# Acceptance: add-admin-jobs-console (W2)

Source: `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §3.2(d), §4 C3,
§5.2, §5.5, §6 (W2 row).

## §6 W2 acceptance line

> 任选白名单任务手动触发成功并入历史；运行中重复触发被锁拒绝并提示；失败任务红点

| # | Acceptance clause | How it is satisfied | Evidence |
|---|---|---|---|
| A1 | 任选白名单任务手动触发成功并入历史 | `POST /api/canonical-v2/admin/jobs/{task_id}/run` starts the declared command on a background thread, writes a `running` row, then closes it with status/duration/items; the task history and the run detail expose it. Exercised end-to-end on scratch port 18291 against a stub task (a real collection run is forbidden by this slice's cost rule). | `scratch-18291-*.json`; `test_canonical_v2_jobs_api.py`; `test_canonical_v2_jobs_runner.py` (R3) |
| A2 | 运行中重复触发被锁拒绝并提示 | `flock(LOCK_EX\|LOCK_NB)` per task, held for the whole run, shared with any other process (the future W6 cron entry); refusal is 409 with detail `job_already_running`, which the page renders as a Chinese message. | `scratch-18291-locked.json`; R3 concurrent-trigger test |
| A3 | 失败任务红点 | `job_task_state.consecutive_failures` / `last_status` drive `failure_flag` per task in the list payload; the page renders the red dot and the failure-sample entry. | `scratch-18291-failure-*.json`; R4 list payload test |

## §3.2(d) additions carried by this slice

| Clause | Implementation | Evidence |
|---|---|---|
| 调度任务清单与下次运行时间 | declared cadence (`schedule_display` + `schedule_cron`) in the white list; `next_run_at` computed from the expression in the server's local timezone | R1 cron tests; scratch list payload |
| 历史运行（成功/失败/耗时/条数） | `job_run` rows with status, duration, exit code, item counts | R2/R3; scratch history |
| 失败样例入口 | run detail endpoint + page panel with bounded, redacted stdout/stderr excerpts | R2 redaction test; scratch run detail |
| 立即采集（同一闸门） | the same `JobRuntime.trigger` path for `manual` and `schedule` sources; switch/quota/lock/breaker identical | R3 gate tests (switch-off, quota-zero, lock, breaker) |

## §4 C3 additions

| Clause | Implementation | Evidence |
|---|---|---|
| Milvus 回填并入 W2 白名单 | `ops-milvus-backfill` with a closed `domain` parameter and optional `--dry-run`, fixed argv, PG-required | R1 registry tests |
| 检索验证并入 W2 白名单 | `ops-retrieval-validation` = `bash apps/admin-console/scripts/host_e2e_agentic_rag.sh`, PG-required | R1 registry tests |
| 依赖 PG 的运维动作优雅降级（§2.4/原则 4） | `PostgresProbe` (fail-soft, cached) ⇒ `available: false` + hidden trigger + 503 on POST; never blocks process start | R3/R4 degradation tests; scratch PG-degraded payload |

## §5.5 guardrail coverage

| Guardrail | W2 scope | Evidence |
|---|---|---|
| 连续 2 轮失败熔断 | implemented: 2 consecutive failures open the breaker, all later triggers refused, operator reset recorded | R3 breaker tests; scratch |
| 每脚本每轮 max calls | gate + audit at W2 (cap 0 refuses; effective caps exported to the child and stored on the run row); the in-script counter is §5.5/W6 instrumentation and is declared as such in design.md §3 | R3 quota test |
| 夜间窗口 | enforced for scheduled triggers, recorded (not enforced) for manual triggers — decision flagged for ratification in design.md §3 | R3 window test |
| 节奏不进 UI | the page renders the declared cadence read-only; changing cadence remains an OS-cron/change-process action | scratch page |

## Explicitly not claimed

- No real collection run, no search/LLM spend, no cron installation, no `pipeline_run` write.
- No §3.2(a) freshness integration: making W1's system-status treat the jobs store as the serving-host
  freshness source is a follow-up (the design's "取 pipeline_run 历史最晚成功记录" has no source on a
  PG-less serving host — see `current-state.md` §3/§6).

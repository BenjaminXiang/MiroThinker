# Recall-regression protocol — embedding-model switch gate

Owner slice: `feat/recall-regression` (worktree `.worktrees/recall-regression`).
Authority: `docs/plans/2026-09-21-embedding-model-switch-plan.md` §4 — "换了模型之后要充分测试，
保证召回不发生退化". §4.3 requires the baseline to be captured **before** the switch; §4.4 fixes
the verdict rules the harness implements.

Status: **baseline and one control captured** (`baseline.json`, `control.json`). The after-switch
run is one command away (§3); §6 holds the verdict rules **calibrated by the measured noise floor**
(full analysis in `noise-floor.md`).

---

## 1. What the harness is

`apps/admin-console/scripts/eval_recall_canonical_v2.py` — runs every case through the production
`POST /api/chat/stream` path against a live canonical-v2 instance and records, per turn:

| Field | Source |
|---|---|
| query, answer text, `query_type`, `answer_style`, `understood_subject` | SSE `answer` event |
| citations (type / id / label / url) + local-vs-web nature | SSE `answer` event (`ChatCitation.type == "web"` ⇒ network) |
| per-lane candidate counts (`vector` / `lexical` / `exact` / `structured` / `web` / `relationship`) | SSE `retrieval_done` event |
| lane `in` / `retained` / `filtered`, web provider `attempted`/`cache_hit`, degradation token | serving instance's turn-trace journal (`TURN_TRACE_DIR`) |
| candidate layer: recalled entity handles, committed names, protected slots, evidence split by lane | serving instance's per-turn debug dump (`CANONICAL_V2_TURN_DEBUG_DIR`) |

Case files: `.agents/runs/embedding-model-switch/testset-cases.json` (25 turns / 17 groups,
entity GT reviewed by hand from the 关键点 column) and `semantic-probes.json` (12 vector-lane
probes, 4 with an explicit expected entity).

`--cases` also accepts `docs/测试集答案.xlsx` directly (entities then come from
`parse_testset`'s heuristics, **not** the reviewed list — the harness prints a warning).

## 2. Why it exists next to the replay gate

`replay_fix_round1.py` locks the *behaviour* contract (7 sessions: wording, clarification,
citation shape, multi-turn anchoring) and never measures recall. A vector-lane regression shows
up as "same answer shape, fewer of the right companies/papers" — invisible to the replay gate.
The legacy `eval_recall*.py` scripts target the pre-canonical stack (Milvus + Postgres +
`backend.deps`) and cannot run against canonical-v2 at all.

## 3. The two commands

Baseline (already run — §5):

```bash
cd apps/admin-console && UV_OFFLINE=1 uv run python scripts/eval_recall_canonical_v2.py \
  --base-url http://127.0.0.1:18295 --label baseline-qwen3-8b-4096 \
  --cases ../../.agents/runs/embedding-model-switch/testset-cases.json \
          ../../.agents/runs/embedding-model-switch/semantic-probes.json \
  --turn-debug-dir /var/tmp/recall-295/turn-debug \
  --turn-trace-dir /var/tmp/recall-295/turn-trace \
  --out /var/tmp/recall-295/runs/baseline.json
```

After the switch (point `--base-url` at the switched instance, and its own debug/trace dirs).
The capture must be run **twice** and the second one judged — the first pass fills the web cache
and is discarded, which is what keeps the web lane from timing out (§7):

```bash
cd apps/admin-console && UV_OFFLINE=1 uv run python scripts/eval_recall_canonical_v2.py \
  --base-url <switched-instance> --label after-warmup \
  --cases ../../.agents/runs/embedding-model-switch/testset-cases.json \
          ../../.agents/runs/embedding-model-switch/semantic-probes.json \
  --turn-debug-dir <instance CANONICAL_V2_TURN_DEBUG_DIR> \
  --turn-trace-dir <instance TURN_TRACE_DIR> \
  --out /tmp/after-warmup.json          # discard: fills the cache

cd apps/admin-console && UV_OFFLINE=1 uv run python scripts/eval_recall_canonical_v2.py \
  --base-url <switched-instance> --label after-<model>-<dim> \
  --cases ../../.agents/runs/embedding-model-switch/testset-cases.json \
          ../../.agents/runs/embedding-model-switch/semantic-probes.json \
  --turn-debug-dir <instance CANONICAL_V2_TURN_DEBUG_DIR> \
  --turn-trace-dir <instance TURN_TRACE_DIR> \
  --out .agents/runs/embedding-model-switch/after.json     # judged pass
```

Verdict — the plan's gate is the `baseline ↔ after` pair; the `control ↔ after` pair answers the
same question with the web-lane noise removed:

```bash
cd apps/admin-console && uv run python scripts/eval_recall_canonical_v2.py \
  --diff .agents/runs/embedding-model-switch/baseline.json after.json
cd apps/admin-console && uv run python scripts/eval_recall_canonical_v2.py \
  --diff .agents/runs/embedding-model-switch/control.json after.json
```

Exit codes: **0 PASS, 1 FAIL, 2 REVIEW**. Add `--strict-concepts` for the plan's literal reading of
the 关键点 strings (`noise-floor.md` §6 explains why the default is review-level).

## 4. Instance requirements (else the gate is weak)

The instance under test must be started with:

* `CANONICAL_V2_TURN_DEBUG_DIR=<dir>` — otherwise there is no candidate layer and L1 entity
  checks cannot run; `--diff` then reports REVIEW per case.
* `TURN_TRACE_DIR=<dir>` — otherwise lane `in/retained/filtered` and web outcomes are missing.

Scratch recipe used for the baseline (the live 18188 line was never touched):
`.agents/runs/embedding-model-switch/serve-18295-command.sh` — a copy of the live command file
(`.worktrees/canonical-v2-s11-consolidation/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18188-command.sh`)
with **only** the port and the state paths rebased:

| live | scratch |
|---|---|
| port 18188 | **18295** |
| `CANONICAL_V2_ACCESS_LOG_DB=/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3` | `/var/tmp/recall-295/logs/access-logs.sqlite3` |
| `CANONICAL_V2_CORRECTIONS_DB=…/mirothinker-canonical-v2-s12f/corrections.sqlite3` | `/var/tmp/recall-295/corrections.sqlite3` |
| `CANONICAL_V2_TURN_DEBUG_DIR=<close-workbook-gaps>/turn-debug` | `/var/tmp/recall-295/turn-debug` |
| `TURN_TRACE_DIR` (default `var/turn-trace`) | `/var/tmp/recall-295/turn-trace` |

Unchanged on purpose: `--database-url …miroflow_candidate_v2_20260916_r1`, `--serving-pack
/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound`, `--index-root
/var/tmp/mirothinker-data-v2/index-v3-v2`, `--candidate-release-id candidate-v2-20260916-r1`,
`CANONICAL_V2_LEXICAL_INDEX=0`, `CHAT_CONTEXTUAL_INTERPRETATION=on`, `DATABASE_URL=<console>`.
The pack/index are read-only for a `--serve --serve-existing` boot; the only shared file written
is the pack's mount receipt (`serving-pack-run16-readerbound.mount-receipt.json`), which the
mount rewrites with the same identity the live boot recorded — verified after the run:
`pack_dir` / `release_id` / `index_root` / `index_marker_sha256` / `pack_manifest_sha256` /
`verification` all unchanged (only `generated_at` and `mount_seconds` differ), and a receipt that
did not bind would fall back to full verification rather than fail the boot. Nothing under
`.worktrees/canonical-v2-s11-consolidation/` was modified (`git status` clean) and the live access
log (`/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3`) was last written at 15:01,
before this work started.

Session identity: one session per **turn group** (`session:chat:<run-id>-<group slug>`), fresh
random `run-id` per run, so (a) follow-ups keep their antecedent (`他` / `上述企业` / `这论文`)
and (b) a re-run against the same process cannot inherit a previous run's session state. The
serving process names its debug dump after the last 12 characters of the session id, which is
why the run id is 4 hex characters.

## 5. Baseline (pre-switch, Qwen3-Embedding-8B / 4096-dim)

Captured 2026-09-21 12:41 UTC (`run_id=85ee`) against the scratch instance on 18295 serving
`--candidate-release-id candidate-v2-20260916-r1`, pack `serving-pack-run16-readerbound`,
index `index-v3-v2` — i.e. exactly the live 18188 configuration. **37/37 turns succeeded, 0
errors, wall clock 698.7 s.**

| Aggregate | Value |
|---|---|
| cases | 37 (25 test-set + 12 probes; 18 labeled, 5 concept, 6 unlabeled, 8 structural) |
| expected entity assertions | 37 |
| hit in answer / citations | **31** |
| hit in candidate layer | **22** (of 37 checked; all 37 turns had a candidate layer) |
| cases with every entity hit | 20 |
| vector-lane candidates | median **61.0**, min 1, max 128, n = **34** (3 turns planned no vector lane) |
| vector distribution | 1×1, 16×15, 58×1, 64×2, 128×15, none×3 — **bimodal** (16 vs 128) |
| citations | 239 local / 80 web |
| LLM-synthesized turns | 35 of 37 (2 template: the q3t1 safety_guidance refusal and one other) |
| web provider calls | 323 attempted, 40 cache hits, **17 timeouts** |
| wall clock | 698.7 s |

> **This capture ran with a degraded web lane.** 17 provider timeouts (0 in the control run) make
> the baseline's web-dependent turns a conservative anchor: on those turns the answer used local
> evidence where a healthy run would have used web evidence too (measured: `q12t1` 0 → 104 web
> candidates between the two runs). The vector and candidate layers are unaffected — the vector
> metric moved on 0/34 cases across the pair. See `noise-floor.md` §5 and §7.

**Baseline assertions that already miss (6 of 37)** — recorded so the reviewer knows the gate has
6 fewer live assertions than it looks like:

| case | entity | why |
|---|---|---|
| `q12t1` | 遥操作, 动捕数据, 真机实测 | the answer went to local-company SCADA/AI-dataset collection and never used the 关键点's words — a pre-existing follow-up topic drift, not a harness artefact |
| `q16t1` | 本体感知数据, 环境感知数据 | the answer says "本体状态与关节轨迹类数据" / "视觉、触觉、力觉"; the 关键点 strings are answer wording, not KB entities |
| `s09` | 爱博合创 | the category probe "深圳做医疗机器人" answers with 精锋/元化/迈步… and never names 爱博合创, although the name query `q10t1` recalls it — a real (pre-existing) recall gap worth re-checking after the switch |

Also recorded: `q17t1` (优必选有哪些专利) names the company in the answer but its recalled
handles are the patents, so the candidate layer does not contain 优必选 — the candidate layer is
entity-handle based, which is why every rule checks the answer layer as well. No forbidden entity
appeared anywhere (q4t2's 深圳智航无人机 is clean).

### Per-case baseline

`ans` = expected entities hit in answer/citations, `cand` = hit in the candidate layer
(`(Y)` = candidate layer available), `vec` = vector-lane candidates, `cit` = citations local/web.

| case | suite | kind | ans | cand | vec | cit | s |
|---|---|---|---|---|---|---|---|
| `q1t1` | testset | labeled | 1/1 | 1/1 (Y) | 16 | 1/1 | 3.23 |
| `q1t2` | testset | labeled | 1/1 | 1/1 (Y) | — | 1/0 | 5.8 |
| `q2t1` | testset | labeled | 5/5 | 5/5 (Y) | 128 | 4/8 | 24.4 |
| `q2t2` | testset | unlabeled | — | — (Y) | 64 | 26/0 | 18.41 |
| `q2t3` | testset | labeled | 1/1 | 1/1 (Y) | 58 | 26/0 | 19.95 |
| `q3t1` | testset | unlabeled | — | — (Y) | — | 0/0 | 1.17 |
| `q4t1` | testset | labeled | 1/1 | 1/1 (Y) | 16 | 1/8 | 6.09 |
| `q4t2` | testset | labeled | 1/1 | 1/1 (Y) | 16 | 1/7 | 7.52 |
| `q5t1` | testset | labeled | 3/3 | 3/3 (Y) | 128 | 5/7 | 21.98 |
| `q5t2` | testset | unlabeled | — | — (Y) | 64 | 31/0 | 15.14 |
| `q6t1` | testset | labeled | 1/1 | 1/1 (Y) | 16 | 1/2 | 9.03 |
| `q6t2` | testset | labeled | 1/1 | 1/1 (Y) | 1 | 1/1 | 7.16 |
| `q7t1` | testset | unlabeled | — | — (Y) | 128 | 1/0 | 17.6 |
| `q8t1` | testset | labeled | 1/1 | 1/1 (Y) | 16 | 1/6 | 10.09 |
| `q8t2` | testset | unlabeled | — | — (Y) | 16 | 1/7 | 11.32 |
| `q9t1` | testset | labeled | 1/1 | 1/1 (Y) | 16 | 1/6 | 9.21 |
| `q10t1` | testset | labeled | 1/1 | 1/1 (Y) | 16 | 1/7 | 11.33 |
| `q11t1` | testset | concept | 2/2 | 0/2 (Y) | 128 | 1/2 | 18.66 |
| `q12t1` | testset | concept | 0/3 | 0/3 (Y) | 128 | 6/0 | 40.61 |
| `q13t1` | testset | concept | 2/2 | 0/2 (Y) | 128 | 5/0 | 25.88 |
| `q14t1` | testset | unlabeled | — | — (Y) | 128 | 12/0 | 41.52 |
| `q15t1` | testset | concept | 3/3 | 0/3 (Y) | 128 | 2/0 | 37.75 |
| `q16t1` | testset | concept | 1/3 | 0/3 (Y) | 128 | 10/0 | 27.7 |
| `q17t1` | testset | labeled | 1/1 | 0/1 (Y) | — | 12/0 | 23.04 |
| `q17t2` | testset | labeled | 1/1 | 1/1 (Y) | 16 | 1/0 | 6.61 |
| `s01` | probes | labeled | 1/1 | 1/1 (Y) | 128 | 21/0 | 21.2 |
| `s02` | probes | structural | — | — (Y) | 16 | 3/1 | 5.3 |
| `s03` | probes | labeled | 1/1 | 1/1 (Y) | 16 | 1/7 | 21.91 |
| `s04` | probes | structural | — | — (Y) | 128 | 14/0 | 28.65 |
| `s05` | probes | labeled | 1/1 | 1/1 (Y) | 128 | 11/0 | 34.7 |
| `s06` | probes | structural | — | — (Y) | 16 | 2/1 | 14.86 |
| `s07` | probes | structural | — | — (Y) | 16 | 3/4 | 16.42 |
| `s08` | probes | structural | — | — (Y) | 16 | 1/0 | 15.82 |
| `s09` | probes | labeled | 0/1 | 0/1 (Y) | 128 | 21/0 | 36.46 |
| `s10` | probes | structural | — | — (Y) | 128 | 8/4 | 27.33 |
| `s11` | probes | structural | — | — (Y) | 128 | 0/0 | 33.11 |
| `s12` | probes | structural | — | — (Y) | 16 | 2/1 | 21.27 |

Concept rows show `0/n` in the candidate column because 关键点 strings such as 合成数据 are not
entity handles: that cell is informational and is never a gate input (a `False → False` pair
cannot produce a regression flag).

**Median caveat.** The vector lane is bimodal (16 for subject/name plans, 128 for category
plans, i.e. a saturation cap). The 61.0 median sits exactly between the two modes, so a handful of
cases changing plan class can move the median a lot without a real per-case loss. Read the
per-case `vecA/vecB` column first; the median is a coarse tripwire, and §4.4.3 is what makes it a
FAIL.

### Quota spent on the baseline

| Item | Baseline run | Whole scratch instance today |
|---|---|---|
| chat turns | 37 | 40 (37 + 1 smoke probe + 2 multi-turn smoke turns) |
| LLM-synthesized turns | 35 | — |
| web provider calls | 323 attempted / 40 cache hits | **bocha-v1 172, serper-v1 170** (the instance's own `web_quota` counters) |
| LLM calls | not observable from the service (no usage ledger). Lower bound ≈ 37 contextual-interpretation + 35 synthesis ≈ **72**; the serving path also issues batched LLM judge calls (`knowledge_serving_isolated.py:4027,4122,1747`) that this harness cannot count — take the exact figure from the gateway dashboard for the key in use. | |
| wall clock | 698.7 s | |

Three earlier turns (an aborted first attempt with a per-case-session defect) plus the two smoke
turns are included in the instance-level provider counters but not in `baseline.json`.

### Harness self-check

`--diff baseline.json baseline.json` on the frozen artifact returns **PASS, 0 fail-level, 0
review-level** (37/37 candidate layers present, so no coverage REVIEW either). This is the
no-regression control that proves the diff path itself is not noisy on identical input — it is
*not* the same-configuration noise floor (§7), which needs a second independent run.

## 6. Verdict rules (`--diff`, plan §4.4 — calibrated by `noise-floor.md`)

The plan's §4.4 rules were written before any noise was measured. A control capture of the
identical configuration (see `noise-floor.md`) showed the vector lane moving on **0 of 34 cases**,
the labeled assertions on **0 of 18 cases**, and the 关键点 concept strings on 6 of 11 — all of
those on turns whose web lane had timed out. The rules below are §4.4 with that calibration
applied; `--strict-concepts` restores the plan's literal reading for a paper trail.

| Rule | Condition | Verdict |
|---|---|---|
| §4.4.1 retrieval loss | a labeled entity was in the candidate set **and** the answer in A, and is gone from both in B | **FAIL** |
| §4.4.1 answer-only loss | the entity is gone from the answer/citations but the candidate set still holds it | **REVIEW** (measured: this is what a web-evidence/synthesis change looks like) |
| §4.4.1 candidate-only loss | the answer still names it but the candidate set lost it | **REVIEW** |
| §4.4.1 concept strings | a 关键点 string that is answer wording (合成数据 / 遥操作 / …) disappears from the answer | **REVIEW** by default, **FAIL** with `--strict-concepts` |
| §4.4.2 probes | a probe loses its expected entity from the answer or the candidate set | **REVIEW** (human re-check; still a miss after review ⇒ gate fails) |
| §4.4.2 lane halving | any case loses > 50 % of its vector candidates, anchor ≥ 8 | **REVIEW** |
| §4.4.3 median lane | median vector-lane candidate count drops > 30 % (shared cases) | **FAIL** — keep as written: measured noise on this metric is zero, so it cannot fire spuriously |
| coverage | candidate layer unavailable in either run, or the two runs do not contain the same case ids | **REVIEW** |

Concept strings are never scored in the candidate layer (they are not entity handles), and every
verdict line carries `[web timeouts=n]` when the run of record had a degraded web lane.

Output: a per-case table (answer hits, candidate-layer availability, A's web-lane candidates,
vector count A→B, % change, timeout marker), aggregate deltas (answer entity hits, candidate hits,
citation local/web mix, vector median for all / test set / probes, wall clock), then
`VERDICT: PASS|FAIL|REVIEW` with one line per reason.

**Honest approximation:** canonical-v2 exposes per-lane *counts*, not per-lane ranked lists, and
`_map_response` returns empty `evidence`/`structured_payload`. So §4.4.2's "GT 掉出 top-k" is
implemented as "GT disappeared from the recalled candidate set" (turn-debug `recalled_handles` +
`committed_names` + protected slots + the public `web_items` titles/URLs), which is a weaker
statement: it catches loss, not rank movement inside the top-k.

## 7. Quota, cost and noise

* One run = 37 turns (25 test-set + 12 probes) ≈ 40–80 LLM-bearing turns. The harness reports
  `turns_with_llm_synthesis`, `web_provider_attempts` and `web_provider_cache_hits` from the
  trace journal; the *exact* LLM call count is not observable from the service (no usage ledger),
  so it stays an estimate: one contextual-interpretation call plus one synthesis call per
  answered turn (`CHAT_CONTEXTUAL_INTERPRETATION=on`).
* **Measured noise floor** (`noise-floor.md`, two captures of the identical configuration):
  vector lane 0/34 cases changed and the median was identical; labeled assertions 0/18 cases;
  concept strings 6/11 flipped; answer text byte-identical on only 3/37 turns; the driver of every
  flip was web-lane availability (the baseline ran cold at ~27 provider calls/min and timed out 17
  times; the control ran warm at ~8/min with zero timeouts).
* **After-run protocol:** run the full pass **twice** and judge the second one — the first fills
  the web cache and is discarded, which is the condition under which the labeled rule was stable
  here (measured: 94 live provider calls instead of 323, zero timeouts). Cost: one extra pass.
  Without it, expect the baseline's web-timeout noise back and treat web-dependent answer-layer
  deltas as ambiguous — the vector and candidate layers are unaffected either way.

## 8. Run log

| When (UTC) | What | Result |
|---|---|---|
| 2026-09-21 12:22 | scratch boot on 18295 from the live pack (launcher committed) | up in ~300 s, `/api/health` 200; live 18188 untouched |
| 2026-09-21 12:27 | harness smoke, 1 probe (`s02`) | 8.75 s turn, vector=16, candidate layer Y, lane counts from both sources agree |
| 2026-09-21 12:28 | first capture attempt (per-case sessions) | aborted after 3 turns: follow-ups lost their antecedent (`q1t2` answered in 0.86 s with no retrieval) — fixed to one session per turn group, locked by `test_group_slugs_share_one_session_per_turn_group` |
| 2026-09-21 12:29 | 2-turn smoke on group 问题1 | `q1t2` resolved 丁文伯 → 深圳无界智航科技有限公司; both turns' debug dumps found by name |
| 2026-09-21 12:29–12:41 | **baseline capture, 37/37 ok** | `<baseline.json>` (§5) |
| 2026-09-21 12:45 | `--diff baseline.json baseline.json` | PASS, 0 fail / 0 review |
| 2026-09-21 12:52 | scratch instance stopped (both PIDs), live 18188 verified still 200 | no production or other-scratch dir written |
| 2026-09-21 12:48–12:53 | scratch re-booted on 18295 (same command file, same state dirs) | up in ~285 s, health 200 |
| 2026-09-21 12:53–13:04 | **control capture, 37/37 ok** (`control.json`) | 489.8 s, 94 live provider calls / 260 cache hits / **0 timeouts** |
| 2026-09-21 13:05 | `--diff baseline.json control.json` | calibrated **REVIEW** (3 concept rows); `--strict-concepts` → **FAIL** (same 3 rows) |
| 2026-09-21 13:02–13:08 | rule calibration from the control (`noise-floor.md`), 24 tests pass | concept → review-level, per-case lane halving → review for every suite with an anchor floor, labeled answer-only loss → review |
| 2026-09-21 13:08 | scratch stopped again (both PIDs); live 18188 verified 200, `.worktrees/canonical-v2-s11-consolidation` git-clean | |

To re-boot the scratch for a control run or a re-capture:
`bash .agents/runs/embedding-model-switch/serve-18295-command.sh > /var/tmp/recall-295/logs/serve-18295.log 2>&1 &`
(~300 s to health; the warm web cache and the mount receipt under `/var/tmp/recall-295` persist).

## 9. What this gate does not cover

1. **Answer quality / precision** — only presence of expected entities. A regression that keeps
   the entity but gets the facts wrong passes this gate. `scripts/eval_precision.py` and the
   replay gate cover parts of that, on the pre-canonical / behavioural level respectively.
2. **Rank movement inside the vector top-k** — see §6; only membership of the recalled candidate
   set is observable.
3. **Multi-turn referent resolution** — the sessions are replayed in order, but "did 他 resolve
   to 丁文伯" is checked only through the entity the answer names, not through the session
   snapshot (`answer_subject` is recorded for the reviewer).
4. **Refusal / clarification contracts** — those stay the replay gate's job; the recall harness
   records the outcome but does not judge it.
5. **Cases without ground truth** — see §10; they can only be reviewed by a human reading the
   captured `answer.text` in the JSON.
6. **The embedding switch itself** — this harness only measures the serving surface; it does not
   verify the new index's identity/bundle (that is the rebuild slice's job), nor latency.

## 10. Cases whose recall cannot be machine-judged

`testset-cases.json` carries `kind` per case: `labeled` (entity GT), `concept` (关键点 strings
that are answer wording, not KB entities) and `unlabeled` (关键点 is a grading instruction such
as 获取知识库 / 上下文识别 / 不能回答, or empty). One of the 25 turns has a forbidden entity
instead of an expected one (`q4t2`: 深圳智航无人机 must not appear).

The 11 concept assertions are **not** hard assertions: the control run flipped 6 of them between
two captures of the identical configuration (`noise-floor.md` §4). They stay in the artifact
because a wholesale topic drift is still worth seeing, but they are review-level by default.

Unlabeled turns (6/25) can only be reviewed by a human reading the captured answer text —
`q2t2`, `q3t1` (refusal), `q5t2`, `q7t1` (早稻田企业家), `q8t2` (光基多维力传感), `q14t1`
(深圳具身智能/灵巧手厂商). `q7t1` and `q14t1` are the two highest-value ones: both are pure
vector-lane enumeration queries with no frozen entity list.

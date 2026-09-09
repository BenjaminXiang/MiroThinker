# Design: prof-seed-admin-console

This document captures the architectural decisions behind the spec
deltas in `specs/professor-seed-management/spec.md` and explicitly
maps each decision back to its origin in the Audit doc and the
2026-05-10 user Review.

## 1. Decision: 5-column schema (no `discipline_tag` / no `granularity`)

**Source**: Review §3.1 Theme 2 (locked).

**Decision**: Schema has exactly `school` / `department` / `seed_url` /
`last_run_at` / `last_run_status` (plus surrogate `id`).

**Alternatives considered**:

| Alternative | Why rejected |
|---|---|
| Audit §2.6 original (`school + department + seed_url + discipline_tag(STEM/HSS/MIXED)`) | User: "没必要纠结，在文档中一定要简化这一点，不要过度设计". `discipline_tag` adds explanation cost (especially MIXED) without behavioral effect since admin self-decides what to add |
| Add `granularity` enum (school / dept) | User clarified this is implicit from `department` being NULL; no need for explicit enum |
| Add `notes`, `created_by`, `updated_by` audit fields | User: "MVP 先不用用户登录" — `created_by`/`updated_by` would be NULL anyway in MVP |

**Implication for migration**: New table `professor_seed`. Alembic V022 (V019/V020/V021 already exist; survey 2026-05-10).

## 2. Decision: `last_run_status` is a 5-value enum (not 4 + error_message)

**Source**: Review §3.1 Theme 3 follow-up (locked).

**Decision**: Five values: `success / failure / in_progress / never_run /
adapter_missing`. The fifth value (`adapter_missing`) is its own status,
not a sub-case of `failure`.

**Why a separate enum value (not `failure` + structured error)**:

- Admin UI discoverability. Admin reading the seed list must immediately
  see "this seed needs an adapter author" vs. "the adapter ran but
  crashed". Mixing them under `failure` requires admin to expand error
  messages or read pipeline_issue, raising friction.
- Cron behavior diverges. Cron MUST skip `adapter_missing` seeds (no
  point retrying until adapter exists). Cron should retry `failure`
  seeds (transient network errors, etc.). Distinct enum values make the
  cron logic obvious.
- Trigger endpoint behavior diverges. Trigger on `adapter_missing`
  returns 422 (admin error: precondition unmet); trigger on `failure`
  returns 202 (will retry).

**Why `setup_required` was rejected as the name**: more abstract but
loses information. The bottleneck is specifically *adapter registration*,
not generic setup. `adapter_missing` is more actionable.

**Implication**: Postgres CHECK constraint enforces enum at DB level;
Pydantic model uses `Literal` type.

## 3. Decision: Per-row trigger button (not "queue for next batch" flag)

**Source**: Review §3.1 Theme 2 (locked).

**Decision**: Trigger is an action endpoint `POST /api/seeds/{id}/trigger`
that synchronously flips `last_run_status='in_progress'` and asynchronously
runs the pipeline.

**Alternative considered**: Persist a `crawl_now` boolean column. Worker
poll picks up flagged seeds. Rejected because:

- Requires a worker poll loop on top of cron — two scheduling mechanisms.
- "Click button → see status flip in 1s" vs. "click → wait for next poll
  cycle" UX gap.
- The user's phrasing was "点了这个按钮后台就去走" (click → it goes), not
  "mark for later".

**Async execution mechanism** (implementation choice, not in spec):

| Option | Pro | Con | Recommendation |
|---|---|---|---|
| ThreadPoolExecutor owned by admin-console process | Shared by manual trigger and cron; simple concurrency cap; no request-lifetime coupling | Dies with worker; no durable retry on crash | Use for MVP; pipeline runs are bounded and status is observable |
| FastAPI `BackgroundTasks` | Built-in, no new dep | Request-scoped; harder to share with cron and cap globally | Rejected for Phase B |
| Celery / RQ | Robust queue, retry semantics | New infra; not currently used in repo | Phase 2 if pipeline reliability becomes an issue |
| In-process asyncio task | Simple | Same crash semantics as BackgroundTasks | Not selected; sync pipeline work belongs in bounded worker threads |

Decision: **MVP uses a process-local `ThreadPoolExecutor`** with
`ADMIN_PROFESSOR_SEED_CONCURRENCY` defaulting to 4. Spec is implementation-
agnostic (just says "async"); design.md records this choice for the
implementer.

## 4. Decision: Admin cannot mutate `last_run_at` / `last_run_status`

**Source**: Review §3.1 Theme 2 (locked: status is auto, not user-input).

**Decision**: PUT `/api/seeds/{id}` ignores `last_run_*` fields in the
request body, even if present.

**Why not return 422 on attempt**: Pragma — frontend may roundtrip the
full row on edit (read → modify school → submit). Stripping vs.
rejecting is a UX choice; stripping is more forgiving and matches the
user's "don't over-design" guidance.

## 5. Decision: Cron monthly schedule + manual button (dual-track)

**Source**: Review §3.1 Theme 9.4 (locked: cron + 手动按钮 双轨).

**Decision**: Monthly cron + per-row manual trigger; no per-seed cron
schedule.

**Why not per-seed schedule**:

- Adds a column (`cron_schedule` enum or text).
- User decided MVP "不要 per-seed cron"; if specific seeds need different
  cadence, admin can use manual trigger.
- Phase 2 extension is straightforward.

**Cron implementation choice**:

| Option | Recommendation |
|---|---|
| APScheduler in-process | Default for MVP; simple |
| External cron (host crontab calling FastAPI endpoint) | Phase 2 if HA needed |

Spec is implementation-agnostic; this design doc records the choice.
Schedule is configured in the admin-console process via environment
variables:
`ADMIN_PROFESSOR_SEED_CRON_ENABLED`,
`ADMIN_PROFESSOR_SEED_CRON_DAY`,
`ADMIN_PROFESSOR_SEED_CRON_HOUR`,
`ADMIN_PROFESSOR_SEED_CRON_MINUTE`, and
`ADMIN_PROFESSOR_SEED_CRON_TIMEZONE`.

## 6. Decision: Adapter resolution is *gated* in pipeline, not in trigger endpoint

**Source**: Review §3.1 Theme 3 follow-up + this change's Requirement
"Adapter-missing detection".

**Decision**: When `POST /api/seeds/{id}/trigger` is called, the endpoint
does NOT pre-check adapter availability. The pipeline's first step does.

**Trade-off**:

- Pro: trigger endpoint stays simple (no adapter registry import).
- Pro: adapter registry is the pipeline's concern, not the admin
  console's.
- Con: a click triggers a pipeline that immediately fails-with-
  adapter_missing → wasted task enqueue.

The "Trigger on `adapter_missing` is blocked" scenario in the spec
introduces a soft pre-check **in the trigger endpoint** based on the
seed's *current* `last_run_status`. So:

- First-time click (`last_run_status='never_run'`): endpoint accepts,
  enqueues task, pipeline checks adapter, sets status to
  `adapter_missing`. Task wasted once.
- Subsequent clicks: endpoint re-checks current adapter availability.
  If no adapter is available, it rejects with 422 immediately; if an
  adapter has since been registered, it accepts the trigger and flips the
  seed back to `in_progress`.

This is a 1-time penalty per (seed, adapter-missing-discovery) pair.
Acceptable.

## 6.1 Decision: New seed URLs enter an adapter onboarding loop

**Source**: 2026-05-12 execution feedback: different schools and
departments have materially different roster page structures; do not
expect one crawler to solve all pages, and do not break currently
working adapters while adding new ones.

**Decision**: Adding a seed URL is an operations action, not proof that
the crawler supports that URL. Each new seed follows this loop:

1. Admin records the seed URL in `/seeds`.
2. Preflight classifies the URL as one of:
   - `supported`: matched adapter and non-empty roster extraction.
   - `adapter_missing`: no registered adapter family matches the URL.
   - `parser_low_quality`: adapter/generic path ran but extracted too few
     or obvious non-person rows.
   - `fetch_blocked`: URL family is known, but fetch failed because of
     anti-scraping, JS challenge, timeout, or connection failure.
3. Only `supported` seeds should proceed to real ingestion.
4. `adapter_missing` enters the adapter development queue.
5. `parser_low_quality` / `fetch_blocked` must be fixed with targeted
   school/department adapters or remain blocked; they must not fall
   through to broad generic parsing that creates dirty rows.

**Adapter extension contract**:

- A custom adapter is a small unit with:
  `name`, `matcher(source_url)`, `extractor(html, institution,
  department, source_url)`.
- Matchers must be narrow enough to avoid taking over unrelated schools
  or departments.
- Extractors must emit `DiscoveredProfessorSeed` rows with structured
  `name`, `institution`, `department`, `profile_url`, and `source_url`.
- New adapters require:
  - one fixture/unit test for the new page structure;
  - one sibling regression test or targeted `-k` run proving existing
    supported adapters still pass;
  - one non-mutating preflight/smoke against the affected seed URL.

**Status semantics after Phase B trigger wiring**:

- No matching adapter: `run_single_seed` sets
  `last_run_status='adapter_missing'` and writes
  `pipeline_issue.stage='adapter_missing'`.
- Matching adapter but fetch/parser fatal: `run_single_seed` sets
  `last_run_status='failure'` and writes a `pipeline_issue` under the
  actual failed stage, typically `discovery`.
- The system deliberately does not add a sixth `last_run_status` for
  `fetch_blocked`; the specific cause lives in `pipeline_issue` and
  evidence snapshot.

## 7. Decision: Hard delete (no soft delete)

**Source**: Review §3.1 Theme 2.5 (MVP 5 CRUD; "不做" 三项排除批量
导入但未谈 soft delete).

**Decision**: DELETE removes the row permanently.

**Why**: simplification; if admin deletes wrongly, they re-add. No
downstream FK depends on `professor_seed.id`.

## 8. Decision: No FK from `professor_seed` to other tables

**Source**: design choice driven by Review §3.1 Theme 2 simplification.

**Decision**: `professor_seed` is an **independent** table. Pipeline
runs that originate from a seed write to `professor`, `pipeline_issue`,
etc. but those rows do NOT carry a `seed_id` FK.

**Why not add `professor.seed_id`**:

- A professor may be discovered via multiple seeds over time (e.g. a
  professor moves from a department-level seed to a school-wide seed
  during a year).
- `evidence` already records source URL per-evidence.
- Adding `seed_id` FK creates referential coupling for unclear value.

**Consequence**: deleting a seed has no cascading effect on professor
data. (Audit trail for "which seed produced this professor row" is
preserved via `evidence.source_url` substring match against
`professor_seed.seed_url`.)

## 9. Decision: Out-of-scope items have explicit cross-references

**Source**: Review §5 P1 priority list (locked sequencing).

The spec explicitly disclaims:

| Out of scope | Rationale | Tracked under |
|---|---|---|
| Per-school adapter framework | Sized as separate Standard change | `prof-school-adapter-framework` |
| Paper / patent extraction from prof page | Sized as separate Standard change | `prof-paper-patent-from-page-flow` |
| `paper_summary` / `patent_summary` fields | Sized as separate Standard change | `prof-summary-fields` |
| Double Milvus collection split | Sized as separate Standard change | `prof-double-milvus-collection` |
| `lifecycle_state` field | Sized as separate Lite+ change; can run in parallel with this one | `prof-lifecycle-state` |
| Bulk Excel import | Phase 2 decision; scope-creep risk if pulled in here | n/a (Phase 2) |
| User login / RBAC | Phase 2 decision; admin console has no auth across all pages today | n/a (Phase 2) |

This spec change stays focused on a single capability: seed management.

## 10. Verification approach

`acceptance.md` lists concrete verification commands. High-level approach:

- Spec validation: `openspec validate prof-seed-admin-console` (CLI) MUST
  pass.
- Schema-spec consistency: when implementation lands, the
  `professor_seed` Alembic migration MUST match the column list in the
  Schema requirement byte-for-byte.
- Endpoint contract: implementation MUST emit OpenAPI matching the
  Endpoint Requirement; verified by integration test that exercises
  each scenario.
- UI behavior: integration test or manual screenshot for each scenario
  in the trigger / cron / adapter-missing requirements.

## 11. Source traceability matrix

Every Requirement in `spec.md` has a source citation.

| Requirement | Audit ref | Review ref |
|---|---|---|
| Seed table schema | §2.6 + §8 Step-3/4/8 | §3.1 Theme 2 schema table |
| Seed CRUD endpoints | §2.5 + §8 Step-7 | §3.1 Theme 2 MVP function set |
| Per-seed manual trigger | §2.4 + §7.5 + §9.4 | §3.1 Theme 2 trigger semantics + Theme 9.4 |
| `last_run_status` enum | (new — derived from §8 + §9.4 + Theme 3 follow-up) | §3.1 Theme 2 5-value enum + Theme 3 follow-up |
| Pipeline upsert | §5.3 + §7.4 | §3.1 Theme 2 trigger semantics |
| Cron monthly | §7.1 + §9.4 | §3.1 Theme 9.4 dual-track |
| Adapter-missing | (new — derived from Theme 3 hard-block decision) | §3.1 Theme 3 follow-up |

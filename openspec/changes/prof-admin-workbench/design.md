# Design: prof-admin-workbench (Epic)

Technical design for the Epic and its three child changes. Behavior
contracts (`specs/` deltas) and execution detail (`tasks.md`) are
carried by each child change; this document is the cross-child
technical design and the rationale record.

## Context

### Current state (verified against `miroflow_real`, 2026-05-14)

- `professor`: 495 rows, **all at `quality_status = needs_review`,
  `identity_status = resolved`**. `ck_professor_quality_status` already
  permits `needs_review / ready / low_confidence / needs_enrichment /
  partial / rejected`.
- `canonical_writer.py` contains no `quality_status` write — rows keep
  the column default `needs_review`.
- `quality_gate.evaluate_quality()` exists: a 3-level (L1 hard blocks /
  L2 quality markers / L3 statistical) evaluator over
  `EnrichedProfessorProfile`. It checks name, institution, official
  evidence, academic signal, reader artifacts, and summary
  presence/length/boilerplate. It is **not** wired into the canonical
  write path, operates on the pipeline object rather than persisted
  state, does not consider `identity_status` / same-name conflicts /
  field contradictions / `pipeline_issue` rows, and routes
  merely-incomplete records to `needs_review`.
- `professor_fact` carries only `contact` (488), `homepage` (495),
  `research_topic` (116). `ck_professor_fact_type` already permits
  `education / work_experience / award / academic_position` — the
  vocabulary exists; extractors and data were never written.
- `professor_fact` rows carry per-fact provenance: `source_page_id`,
  `evidence_span`, `confidence`, `status`, `run_id`.
- `professor_affiliation` carries affiliation history each with its own
  `source_page_id`. `source_page` carries `url / url_host / page_role /
  is_official_source / fetched_at / http_status / title`.
  `pipeline_issue` carries `stage / severity / description /
  evidence_snapshot / resolved / resolution_notes`.
- `/api/professor/{id}` (in `apps/admin-console/backend/api/domains.py`,
  `_row_to_released_object`) returns `core_facts + summary_fields +
  evidence:[]`. The professor detail page (`RecordDetail.tsx`) is a
  generic 4-domain viewer.

### Locked decisions (brainstorming 2026-05-14)

1. **Workbench scope** — read-only display + diagnosis + backend
   quality logic + **lightweight marking actions** (`confirm_ready` /
   `send_to_review` / `flag_recrawl`). No field editing, no same-name
   merge in v1.
2. **API contract** — new `/api/admin/professor/*` namespace for the
   rich read payload and marking endpoints. `/api/professor/{id}`
   stays lean and unchanged.
3. **Quality logic location** — a pure `evaluate_professor_quality(...)`
   function with two write call sites (canonical write-time +
   standalone re-evaluation), plus a read-only call from the admin API.
4. **Summary backfill method** — full LLM `generate_summaries` path for
   the eligible no-summary professors (those with non-empty
   `profile_raw_text`); the eligible count is established by the
   fact-extraction child preflight, not assumed.
5. **Experience fields** — v1 also adds extraction of `education /
   work_experience / award / academic_position`.

## Epic decomposition

Three child changes, sequenced quality-first and then data-first. The
crisis (every professor stuck at `needs_review`) is resolved by a
pure-backend change with no UI risk before either backfill or frontend
work begins. After Child 1, the administrator can already use the
existing list-level `quality_status` filters while Child 2 improves the
underlying collected facts before the dedicated workbench UI ships.

| Order | Child change | Surface | Migration |
|---|---|---|---|
| 1 | `prof-quality-status-rework` | backend only | none |
| 2 | `prof-fact-extraction-expansion` | extractors + backfill | none |
| 3 | `prof-admin-workbench-ui` | admin API + frontend | `professor_admin_action` (the Epic's only migration) |

Dependencies: Child 2 depends on Child 1's re-evaluation entry point
(to re-grade after backfill). Child 3's API and frontend depend on
Child 1's `evaluate_professor_quality` (for the quality-diagnosis
payload). Child 3 should render populated experience facts when Child 2
has already landed, but its API contract remains forward-compatible
with `status: "not_extracted"` placeholders for environments where
Child 2 has not yet been run.

## Child 1 — prof-quality-status-rework

### Corrected 4-state semantics

The core bug is the existing mapping, which routes incompleteness to
`needs_review`. Corrected mapping:

| Status | Meaning | Triggers |
|---|---|---|
| `ready` | Machine-accepted; display + retrieval directly | Official source present, `identity_status = resolved`, key fields present, no anomalies |
| `needs_enrichment` | Trustworthy but incomplete | Missing key fields (research directions, papers, summary, experience), no anomaly |
| `low_confidence` | Scrape/parse quality low; re-crawl or fix adapter | Reader artifacts, non-person name, profile blob, no official source |
| `needs_review` | True anomaly; human judgment required | Same-name conflict, field contradiction, `identity_status` not resolved, untrustworthy source |

Priority cascade when multiple signals fire: anomaly (`needs_review`) >
low-quality parse (`low_confidence`) > complete (`ready`) > incomplete
(`needs_enrichment`).

### `evaluate_professor_quality`

```
evaluate_professor_quality(
    canonical_state,            # professor row + facts + affiliations
                                # + identity_status + EXTERNAL open
                                # pipeline_issue rows (reported_by !=
                                # professor_quality_gate)
    latest_admin_action=None,   # most recent professor_admin_action,
                                # carrying its observed_data_updated_at
) -> QualityEvaluation
```

`QualityEvaluation` carries:
- `status` — one of the four values above.
- `reasons: list[QualityReason]` — each `{rule_id, severity, message,
  fields}`. This is the data the workbench renders as "why this is not
  ready".

The function is pure (inputs → output, no I/O). It reuses the existing
`quality_gate.py` L1/L2 check helpers where they apply, but is
re-shaped to take persisted canonical state rather than
`EnrichedProfessorProfile`, and is extended with the
identity/conflict/contradiction/external-`pipeline_issue` signals the
current evaluator omits.

**No self-feedback.** The evaluation persists its own reasons to
`pipeline_issue` (see "Reason persistence") and also reads open
`pipeline_issue` rows as a blocking signal — unguarded, those two
facts form a loop where the gate's own output re-enters as input and
the status sticks or wrongly escalates. The guard: every row this gate
writes carries the fixed `reported_by = professor_quality_gate`, and
the evaluation treats **only** rows with `reported_by !=
professor_quality_gate` (external issues — adapter failures,
identity-gate flags, coverage alerts) as blocking signals. The gate's
own prior reason rows are explanation / triage records, never
re-consumed as evaluation input.

**Human override.** The override decision is anchored on a **canonical
watermark** — the latest change timestamp across everything the
evaluation depends on: `max(updated_at)` over the `professor` row, its
`professor_fact` rows, and its `professor_affiliation` rows, together
with `max(reported_at)` over its EXTERNAL open `pipeline_issue` rows
(`reported_by != professor_quality_gate`). Each `professor_admin_action`
row carries `observed_data_updated_at`, the watermark at the moment the
action was recorded. If `latest_admin_action` is a `confirm_ready` or
`send_to_review` whose `observed_data_updated_at >=` the current
watermark — i.e. nothing the evaluation depends on has changed since
the admin acted — the function returns that status with a single
reason `rule_id = "human_override"`. If anything has changed since
(including a newly-filed external issue), the override is stale and
ignored. Whether `source_page` re-fetches (provenance freshness)
should also advance the watermark is a Child 1 open question. The
function stays pure — the watermark is derived from `canonical_state`
and the action is an input; no branching on global state.

### Call sites

- **Write — `canonical_writer`**: computes and persists `quality_status`
  on every canonical write, and persists the resulting `reasons` to
  `pipeline_issue` (see "Reason persistence"). This is the missing
  wiring that causes the `needs_review` default.
- **Write — standalone re-evaluation entry point**: a script/CLI that
  reads canonical state for a set of (or all) professors, evaluates,
  persists `quality_status`, and reconciles `pipeline_issue` reason
  rows. Used to re-grade the existing 495 and, in the fact-extraction
  child, after backfill.
- **Read — admin API** (`/api/admin/professor/{id}`): calls the
  function to surface the live `status + reasons` for display. The
  durable record of reasons is the `pipeline_issue` rows the write
  call sites maintain.

### Reason persistence

`docs/Data-Agent-Shared-Spec.md §7.2` requires the failure reasons of
`needs_enrichment` and `low_confidence` objects to be written to
`pipeline_issue` (V006 onward) so the pipeline review console can see
them. `evaluate_professor_quality` stays a pure function; the **write
call sites** own persistence:

- Every row this gate writes carries the fixed `reported_by =
  professor_quality_gate`. This is both the self-feedback guard (see
  "No self-feedback" above) and the idempotency discriminator.
- After evaluating, each write call site idempotently upserts one
  `pipeline_issue` row per non-`ready` `reason`. Idempotency uses the
  **existing `uq_pipeline_issue_open` index dimensions** —
  `(COALESCE(professor_id,''), COALESCE(link_id::text,''),
  COALESCE(institution,''), stage, reported_by, description_hash)
  WHERE resolved = false`. Because `reported_by` is fixed and the
  professor reasons carry only `professor_id` (no `link_id` /
  `institution`), the canonical-write and re-evaluation call sites
  converge on the same row rather than creating duplicates.
- Stale-reason reconciliation marks `resolved = true` on the gate's
  **own** previously-open rows (`reported_by = professor_quality_gate`)
  that the current evaluation no longer produces. It never touches
  rows from other reporters.
- `needs_review` reasons (true anomalies) are persisted the same way —
  they are the rows an admin triages.
- Issue `stage` is mapped from `reason.rule_id` onto an existing
  V006/V023 `stage` value (`affiliation`, `research_directions`,
  `identity_gate`, `coverage`, `data_quality_flag`, …). The exact
  `rule_id → stage` map is pinned in Child 1's `specs/` delta. **No new
  `stage` value is introduced.**

### No migration

`ck_professor_quality_status` already permits all four values;
`quality_status` and `pipeline_issue` already exist. Child 1 only
populates the `quality_status` column and reconciles `pipeline_issue`
rows.

## Child 3 — prof-admin-workbench-ui

### `GET /api/admin/professor/{id}` payload

Sections, aggregated from canonical state:

- `identity` — name (zh/en), institution, department, title,
  `discipline_family`, `identity_status`, aliases.
- `contact` — email, homepage, office, official profile URL.
- `research_and_output` — research directions, paper count,
  representative papers, h-index, citation count.
- `experience` — education / work / awards / positions. The section
  renders populated facts when the fact-extraction child has run, and
  remains contract-compatible with `status: "not_extracted"`
  placeholders if those facts are absent.
- `cleaned_summary` — `profile_summary` (fact-type contract output).
- `sources_and_evidence` — per-field provenance: each key fact's
  `value / source_url / source_page (host, role, is_official) /
  fetched_at / evidence_span / confidence`; affiliation history each
  with its `source_page`; plus the `source_page` list.
- `quality_diagnosis` — `quality_status + reasons[]` (recomputed on
  read via `evaluate_professor_quality`) + open `pipeline_issue` rows.
  The `reasons[]` and the open `pipeline_issue` rows describe the same
  facts from the two angles — the live re-computation and the durable
  record the write call sites maintain.

### `GET /api/admin/professor` — triage list

The Epic's premise (`proposal.md` "Why") is that one-by-one review does
not scale. The workbench therefore also exposes a triage list endpoint
so an administrator can find the records that need attention.

`GET /api/admin/professor?...` returns a paginated professor list with,
per row: `professor_id`, display name, institution, `quality_status`,
open `pipeline_issue` count, latest admin action (type + timestamp),
and whether an official source is present. It MUST support filtering
and sorting by: `quality_status`, reason `rule_id` (via the persisted
`pipeline_issue` rows), open issue count, latest admin action, and
official-source presence.

This is the operational entry point; `/api/admin/professor/{id}` is the
per-record drill-down. The existing data-browser list
(`DomainList.tsx`, which only filters by `quality_status`) is not
extended — the admin triage list is a distinct admin-namespace surface.

### Marking actions

`POST /api/admin/professor/{id}/mark` — body `{action, note?}` where
`action ∈ {confirm_ready, send_to_review, flag_recrawl}`.

- `confirm_ready` / `send_to_review` — write a `professor_admin_action`
  row and update `quality_status`. The override survives later
  machine re-evaluation via the `latest_admin_action` input to
  `evaluate_professor_quality` (see Child 1).
- `flag_recrawl` — write a `professor_admin_action` row and a
  `pipeline_issue` row using the existing `stage = data_quality_flag`,
  with the recrawl intent expressed in `reported_by` (e.g.
  `admin:flag_recrawl`) and `evidence_snapshot`; does not change
  `quality_status`. No new `stage` value is introduced, so the Epic's
  single-migration constraint holds. (Alternative considered: a Child 3
  migration extending the `pipeline_issue.stage` CHECK with
  `recrawl_requested` — kept as a planning-time option if the re-crawl
  pipeline needs a distinct stage. Default is the no-migration path.)

### `professor_admin_action` table (the Epic's only migration)

`{action_id, professor_id, action, actor, note,
observed_data_updated_at, created_at}`. Admin actions are a new concept
and are not "issues" — they get their own table rather than overloading
`pipeline_issue`.

`observed_data_updated_at` is the **canonical watermark** at the moment
the action was recorded — `max(updated_at)` across the `professor` row,
its `professor_fact` rows, and its `professor_affiliation` rows,
together with `max(reported_at)` over external open `pipeline_issue`
rows (`reported_by != professor_quality_gate`). It is the anchor that
lets `evaluate_professor_quality` decide whether a `confirm_ready` /
`send_to_review` override is still valid or has been invalidated by a
later data change or newly-filed external issue (see Child 1, "Human
override").

The migration is additive and reversible.

### Frontend — Layout A (diagnosis-pinned, single column)

Rebuild the professor detail page (currently the generic
`RecordDetail.tsx` path) as a single-column audit workbench:

- Quality-diagnosis banner pinned at the top — `quality_status`,
  `reasons[]`, and the three marking-action buttons. The admin sees the
  verdict on open.
- Six data sections below, in order: identity, contact (official),
  research & output, cleaned summary, experience, sources & evidence.
- Per-field provenance is inline — each key field carries an affordance
  that expands its source on demand.
- The `experience` section renders populated facts when available and a
  clear "not extracted yet" state when fact extraction has not produced
  rows.

The professor detail route may need to branch from the shared
`RecordDetail.tsx` viewer into a professor-specific workbench
component; the shared viewer stays for company/paper/patent.

## Child 2 — prof-fact-extraction-expansion

### Fact extraction

LLM structured extraction (not rule-based HTML parsing) of `education /
work_experience / award / academic_position` from `profile_raw_text`.
Rationale: these are prose-heavy fields; rule-based CSS-selector
parsing (as used for name/title in `prof-paper-patent-from-page-flow`)
will not generalize across dozens of school layouts. The user already
accepted LLM cost for summaries.

Each extracted fact is written to `professor_fact` with `value_raw,
value_normalized, source_page_id` (the official page), `evidence_span,
confidence, status = 'active'`. Low-confidence extractions are written
with a low `confidence` score so child 1's gate can flag
`low_confidence` rather than silently trusting them.

`ck_professor_fact_type` already permits the four `fact_type` values —
no migration.

### Backfill

A **preflight** first measures the eligible set: professors with no
`profile_summary` **and** non-empty `profile_raw_text`. (The earlier
`~492` figure came from an inflated `LEFT JOIN` and is not load-bearing
— the preflight count is.) A batch runner then processes that eligible
set, running both the fact extractor and `generate_summaries` (LLM
path) — both are LLM passes over the same `profile_raw_text`, so they
share one runner with a proxy-safe LLM client (reusing the pattern
`prof-paper-patent-from-page-flow` added to the paper `summary_zh`
backfill). Professors with no `profile_raw_text` are skipped and left
for the quality gate to mark `needs_enrichment`. The preflight count
and the processed/skipped/failed tallies are Child 2 acceptance
criteria.

### Re-evaluation closes phase 5

After backfill, the runner invokes child 1's re-evaluation entry
point. `evaluate_professor_quality` now sees the new facts and
re-grades — most trustworthy official-source professors move to `ready`
or `needs_enrichment`, leaving only true anomalies at `needs_review`.

## Cross-cutting concerns

### Error handling

- **Backfill LLM failures** — per-professor isolation; a failed LLM
  call is logged and that professor is left in its prior state, not
  fatal to the batch. The runner reports processed/failed counts.
- **Parser low-confidence** — surfaced via the fact's `confidence`
  score and the `low_confidence` quality status, never silently
  trusted.
- **Marking-action races** — last-write-wins on `quality_status`; the
  `professor_admin_action` log is append-only, so the history is never
  lost even if the status is overwritten.

### Testing

- **Child 1** — unit tests for `evaluate_professor_quality` covering
  each of the four states, the priority cascade, and the human-override
  path; a test for the re-evaluation entry point against seeded
  canonical state.
- **Child 2** — extractor unit tests per `fact_type`; backfill runner
  test with a mocked LLM client; an integration test that backfill →
  re-evaluation moves a seeded professor out of `needs_review`.
- **Child 3** — API contract tests for the seven-section payload shape
  (including the `experience` `not_extracted` placeholder); marking
  endpoint tests (status update, `professor_admin_action` row,
  `pipeline_issue` row for `flag_recrawl`); frontend render test for
  Layout A.

### Rollback

- **Child 1** — pure function + re-evaluation script are idempotent and
  re-runnable; no migration to roll back. A bad evaluation is corrected
  by re-running the entry point.
- **Child 2** — facts are inserted with `run_id` and `status =
  'active'`; rollback marks them `superseded` (allowed by
  `ck_professor_fact_status`); no migration.
- **Child 3** — the `professor_admin_action` migration is additive and
  reversible; the `/api/admin/professor/*` namespace is additive and
  does not touch existing endpoints.

## Relationship to registered changes

- **`prof-lifecycle-state`** — child 1 must **not** absorb lifecycle.
  `quality_status` answers "is the data trustworthy"; lifecycle ("is
  the person still active at that school") stays a separate axis owned
  by that change.
- **`prof-summary-fields`** — that change produces paper/patent
  *aggregate* summaries on the professor; Child 2's `generate_summaries`
  produces the `profile_summary` (the fact-type contract output). If
  both touch `summary_generator.py`, coordinate at implementation time.
- **`prof-double-milvus-collection`** — Child 1 and Child 2
  re-evaluation may re-trigger Milvus backfill; coordinate output
  fields if that change lands concurrently.

## Open questions for planning time

- The exact field list behind the `ready` gate's "key fields present"
  check — to be pinned in child 1's `specs/` delta.
- The eligible no-summary professor count (no `profile_summary` and
  non-empty `profile_raw_text`) — measured cleanly by the Child 2
  preflight, not assumed; the earlier `LEFT JOIN` count was inflated by
  the join fan-out.
- The `reason.rule_id → pipeline_issue.stage` map — pinned in Child 1's
  `specs/` delta, constrained to existing V006/V023 `stage` values.
- The LLM extraction prompt design and the `confidence` scoring rubric
  for Child 2 — a Child 2 design detail.
- Whether the professor workbench is a new component or a branch within
  `RecordDetail.tsx` — a Child 3 implementation detail.

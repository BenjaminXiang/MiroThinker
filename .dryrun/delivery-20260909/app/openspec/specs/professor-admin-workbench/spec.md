# professor-admin-workbench Specification

## Purpose
TBD - created by archiving change prof-admin-workbench. Update Purpose after archive.
## Requirements
### Requirement: Corrected four-state quality_status semantics

`quality_status` MUST be assigned by a machine evaluation of persisted
canonical state, using these four states with these meanings:

- `ready` — machine-accepted; the record may enter display and
  retrieval directly. Assigned when an official source is present,
  `identity_status` is resolved, the key profile fields are present,
  and no anomaly is detected.
- `needs_enrichment` — the record is trustworthy but incomplete.
  Assigned when key fields are missing and no anomaly is detected.
- `low_confidence` — scrape or parse quality is low; the record needs a
  re-crawl or an adapter fix. Assigned on reader artifacts, non-person
  names, profile blobs, or a missing official source.
- `needs_review` — a true anomaly requiring human judgment. Assigned
  ONLY on same-name conflict, field contradiction, unresolved
  `identity_status`, or an untrustworthy source.

`needs_review` MUST NOT be assigned for mere incompleteness. When
multiple signals fire, the priority cascade is: anomaly
(`needs_review`) > low-quality parse (`low_confidence`) > complete
(`ready`) > incomplete (`needs_enrichment`).

The evaluation MUST be a pure function of canonical state (the
`professor` row, its `professor_fact` rows, its `professor_affiliation`
rows, `identity_status`, and **external** open `pipeline_issue` rows)
plus an optional latest admin marking action. It MUST be invoked at
canonical write time and from a standalone re-evaluation entry point.

The non-`ready` `reasons` produced by the evaluation MUST be persisted
to `pipeline_issue` by the write call sites, per
`docs/Data-Agent-Shared-Spec.md §7.2`. Every row the quality gate
writes MUST carry the fixed `reported_by = professor_quality_gate`.
The evaluation MUST treat ONLY `pipeline_issue` rows with `reported_by
!= professor_quality_gate` as blocking signals — its own reason rows
are explanation / triage records and MUST NOT re-enter the evaluation
as input (no self-feedback loop). Persistence MUST be idempotent on the
existing `uq_pipeline_issue_open` index dimensions (`professor_id`,
`link_id`, `institution`, `stage`, `reported_by`, `description_hash`,
`WHERE resolved = false`), and MUST reconcile stale rows by marking
`resolved = true` on the gate's own previously-open rows the current
evaluation no longer produces — never touching rows from other
reporters. Reason `stage` values MUST be drawn from the existing
V006/V023 `pipeline_issue.stage` set; no new `stage` value is
introduced.

A human marking override is anchored on a **canonical watermark** — the
latest change timestamp across everything the evaluation depends on:
`max(updated_at)` over the `professor` row, its `professor_fact` rows,
and its `professor_affiliation` rows, together with `max(reported_at)`
over its external open `pipeline_issue` rows. A `confirm_ready` /
`send_to_review` action is honored only while the
`observed_data_updated_at` recorded with that action is not older than
the current watermark; once anything the evaluation depends on changes
— including a newly-filed external issue — the override is stale and
the machine evaluation applies.

#### Scenario: Complete official-source professor is ready

- **GIVEN** a professor with an official-source `source_page`,
  `identity_status = resolved`, institution, department, title,
  research directions, and a `profile_summary`
- **AND** no same-name conflict, field contradiction, or open
  blocking `pipeline_issue`
- **WHEN** `evaluate_professor_quality` runs
- **THEN** `quality_status` is `ready`

#### Scenario: Trustworthy but incomplete professor is needs_enrichment

- **GIVEN** a professor with an official-source `source_page`,
  `identity_status = resolved`, and institution
- **AND** no research directions and no `profile_summary`
- **AND** no anomaly signal
- **WHEN** `evaluate_professor_quality` runs
- **THEN** `quality_status` is `needs_enrichment`, NOT `needs_review`

#### Scenario: Low-quality parse is low_confidence

- **GIVEN** a professor whose `profile_summary` or `name` contains a
  reader artifact marker, or whose name is a non-person string
- **WHEN** `evaluate_professor_quality` runs
- **THEN** `quality_status` is `low_confidence`

#### Scenario: True anomaly is needs_review

- **GIVEN** a professor with an unresolved `identity_status`, or a
  detected same-name conflict, or a field contradiction
- **WHEN** `evaluate_professor_quality` runs
- **THEN** `quality_status` is `needs_review`

#### Scenario: Non-ready reasons are persisted to pipeline_issue

- **GIVEN** a professor evaluated as `needs_enrichment` with a reason
  indicating missing research directions
- **WHEN** the canonical write or re-evaluation call site persists the
  evaluation
- **THEN** a `pipeline_issue` row exists for that professor capturing
  the reason, with `reported_by = professor_quality_gate` and an
  existing `stage` value
- **AND** re-running the evaluation after the gap is filled marks that
  `pipeline_issue` row `resolved = true`

#### Scenario: Gate-authored reasons do not feed back as blocking signals

- **GIVEN** a professor with an open `pipeline_issue` row whose
  `reported_by` is `professor_quality_gate`
- **AND** no external `pipeline_issue` row and no other anomaly signal
- **WHEN** `evaluate_professor_quality` runs
- **THEN** the gate-authored row is not treated as a blocking signal
  and `quality_status` is not escalated to `needs_review` because of it

#### Scenario: Canonical write and re-evaluation converge on one issue row

- **GIVEN** a professor whose canonical write persisted a
  `needs_enrichment` reason as a `pipeline_issue` row
- **WHEN** the standalone re-evaluation entry point later persists the
  same reason
- **THEN** no duplicate open `pipeline_issue` row is created — both
  call sites use `reported_by = professor_quality_gate` and converge on
  the existing row via the `uq_pipeline_issue_open` index

#### Scenario: Newly-filed external issue invalidates a human override

- **GIVEN** a professor with a `confirm_ready` admin marking action
  whose `observed_data_updated_at` matched the watermark when recorded
- **AND** an external `pipeline_issue` row (`reported_by !=
  professor_quality_gate`) filed after that action
- **WHEN** `evaluate_professor_quality` runs
- **THEN** the override is stale and `quality_status` is the machine
  evaluation of the current canonical state

#### Scenario: Human override survives re-evaluation of unchanged data

- **GIVEN** a professor with a `confirm_ready` admin marking action
  whose `observed_data_updated_at` is not older than the professor's
  current canonical watermark
- **WHEN** `evaluate_professor_quality` runs with that action as the
  latest admin action
- **THEN** `quality_status` is `ready` with a reason of
  `human_override`

#### Scenario: Stale human override is ignored after a data change

- **GIVEN** a professor with a `confirm_ready` admin marking action
  whose `observed_data_updated_at` is older than the professor's
  current canonical watermark
- **WHEN** `evaluate_professor_quality` runs with that action as the
  latest admin action
- **THEN** the override is ignored and `quality_status` is the machine
  evaluation of the current canonical state

### Requirement: Admin can judge scrape quality without database access

The admin console MUST expose a professor audit workbench that
aggregates persisted canonical state into a single view sufficient for
an administrator to decide whether a professor was scraped correctly,
what is missing, where each field came from, and what to do next —
without querying the database directly.

The workbench MUST surface: identity, contact, research and output,
experience, the cleaned `profile_summary`, per-field provenance
(source URL, source page, fetched-at, evidence span, confidence), and
a quality diagnosis (the `quality_status`, the machine reasons behind
it, and open `pipeline_issue` rows).

#### Scenario: Workbench shows the quality verdict on open

- **GIVEN** a professor at `quality_status = needs_enrichment`
- **WHEN** an administrator opens that professor in the workbench
- **THEN** the quality diagnosis — status, the reasons it is not
  `ready`, and any open `pipeline_issue` rows — is visible without
  scrolling or further navigation

#### Scenario: Workbench shows where a field came from

- **GIVEN** a professor whose institution was extracted from an
  official `source_page`
- **WHEN** an administrator inspects the institution field in the
  workbench
- **THEN** the field's source URL, source page, fetched-at timestamp,
  and confidence are reachable from that field without leaving the page

### Requirement: Admin can triage professors at scale

The admin console MUST expose a triage list of professors so an
administrator can find the records that need attention without
reviewing every professor one by one — per the Epic premise, one-by-one
review does not scale to the expected professor volume.

The triage list MUST support filtering and sorting by `quality_status`,
by reason `rule_id` (via the persisted `pipeline_issue` rows), by open
`pipeline_issue` count, by latest admin marking action, and by whether
an official source is present.

#### Scenario: Admin filters the triage list to anomalies

- **GIVEN** a professor population spanning all four `quality_status`
  values
- **WHEN** an administrator filters the triage list to `needs_review`
- **THEN** only the professors with true anomalies are listed, each
  with its `quality_status`, open issue count, and latest admin action

#### Scenario: Admin sorts the triage list by open issue count

- **GIVEN** a professor population with varying numbers of open
  `pipeline_issue` rows
- **WHEN** an administrator sorts the triage list by open issue count
- **THEN** the professors with the most open issues appear first

### Requirement: Lightweight marking actions

The workbench MUST let an administrator record one of three marking
actions on a professor: `confirm_ready`, `send_to_review`, or
`flag_recrawl`. Every marking action MUST be recorded in an append-only
operation log capturing the action, the actor, an optional note, a
timestamp, and the canonical watermark observed at the time of the
action.

`confirm_ready` and `send_to_review` MUST update `quality_status` and
MUST survive a later machine re-evaluation of unchanged canonical data
(anchored on the observed watermark, per the four-state requirement).
`flag_recrawl` MUST NOT change `quality_status`; it records the re-crawl
request as a `pipeline_issue` row using an existing `stage` value.

v1 marking actions do NOT include in-page field editing or same-name
merge.

#### Scenario: confirm_ready overrides and is logged

- **GIVEN** a professor at `quality_status = needs_enrichment`
- **WHEN** an administrator records a `confirm_ready` marking action
- **THEN** `quality_status` becomes `ready`
- **AND** an operation-log row is appended with the action, actor,
  timestamp, and the observed canonical watermark
- **AND** a later machine re-evaluation of the unchanged professor
  keeps `quality_status = ready`

#### Scenario: flag_recrawl does not change quality_status

- **GIVEN** a professor at `quality_status = low_confidence`
- **WHEN** an administrator records a `flag_recrawl` marking action
- **THEN** `quality_status` stays `low_confidence`
- **AND** an operation-log row is appended
- **AND** a re-crawl request is recorded as a `pipeline_issue` row
  using an existing `stage` value, with the recrawl intent carried in
  `reported_by` and `evidence_snapshot` — no new `stage` value is
  introduced


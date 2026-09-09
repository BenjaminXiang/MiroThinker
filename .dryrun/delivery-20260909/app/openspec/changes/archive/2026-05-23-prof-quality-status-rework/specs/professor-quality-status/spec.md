# Spec: professor-quality-status

> Capability: Professor canonical rows receive a trustworthy
> `quality_status` computed from persisted canonical state, with
> non-ready reasons persisted to `pipeline_issue`.

## ADDED Requirements

### Requirement: Four-state professor quality evaluation

The system MUST evaluate professor quality from persisted canonical
state and assign exactly one of `ready`, `needs_enrichment`,
`low_confidence`, or `needs_review`.

The evaluator MUST treat `needs_review` as a true anomaly state only:
unresolved identity, same-name conflict, field contradiction, or
external blocking issue. Mere incompleteness MUST evaluate to
`needs_enrichment`. Scrape/parse-quality failures MUST evaluate to
`low_confidence`. Missing official source is a low-confidence signal,
not an enrichment gap: a row without an official source MUST evaluate
to `low_confidence` unless a higher-priority `needs_review` anomaly is
also present.

The evaluator MUST apply this priority cascade when multiple signals
fire: `needs_review` > `low_confidence` > `ready` >
`needs_enrichment`.

For this child change, `ready` requires all of these key fields/signals:

- at least one official source page linked to the professor;
- `identity_status = resolved`;
- non-empty canonical name;
- current institution;
- title or department;
- at least one active `research_topic` fact;
- non-empty `profile_summary`;
- a verified paper/link signal when paper/link candidates are present
  for the professor. Absence of a Publications section, or a professor
  whose paper collection has not yet run, MUST NOT by itself force
  `needs_review`; it remains `needs_enrichment` when no anomaly exists.

`field_contradiction` is a narrow, machine-detectable anomaly. It MUST
be raised only for contradictory active canonical facts, not for missing
fields or normal multi-source enrichment. The contradiction set for this
child is:

- more than one active/current primary affiliation for the same
  professor with different normalized institutions;
- canonical name conflict that cannot be normalized as the same person
  across the official source, aliases, and accepted name-identity gate
  output;
- mutually exclusive active `contact` facts of the same subtype from
  the same official source page, such as two different primary emails
  or two different official homepages;
- a current title/department pair from the same official source page
  that is internally contradictory after normalization, such as a title
  string stored as a department while a distinct department value also
  exists for the same extracted field.

The evaluator MUST NOT treat these as `field_contradiction`: absent
title, absent department, absent research topic, absent summary, multiple
historical affiliations, or complementary facts from different source
pages.

#### Scenario: Incomplete official professor needs enrichment

- **GIVEN** a professor has an official source and resolved identity
- **AND** the professor is missing research topic or profile summary
- **AND** no anomaly or low-quality parse signal exists
- **WHEN** professor quality is evaluated
- **THEN** `quality_status` is `needs_enrichment`
- **AND** it is not `needs_review`

#### Scenario: True anomaly needs review

- **GIVEN** a professor has unresolved identity status or an external
  identity-gate issue
- **WHEN** professor quality is evaluated
- **THEN** `quality_status` is `needs_review`

#### Scenario: Multiple primary institutions are a contradiction

- **GIVEN** a professor has two active/current primary affiliations with
  different normalized institutions
- **WHEN** professor quality is evaluated
- **THEN** `quality_status` is `needs_review`
- **AND** one reason has `rule_id = field_contradiction`

#### Scenario: Missing field is not a contradiction

- **GIVEN** a professor has an official source, resolved identity, and
  current institution
- **AND** the professor has no title and no department
- **AND** no anomaly or low-quality parse signal exists
- **WHEN** professor quality is evaluated
- **THEN** `quality_status` is `needs_enrichment`
- **AND** no reason has `rule_id = field_contradiction`

#### Scenario: Missing official source is low confidence

- **GIVEN** a professor has resolved identity and non-empty canonical
  fields
- **AND** no official source page is linked to the professor
- **AND** no higher-priority anomaly signal exists
- **WHEN** professor quality is evaluated
- **THEN** `quality_status` is `low_confidence`
- **AND** one reason has `rule_id = missing_official_source`

### Requirement: Quality reasons are persisted without self-feedback

The write call sites MUST persist one open `pipeline_issue` row per
non-ready reason with fixed `reported_by = professor_quality_gate`.
The evaluator MUST ignore open issue rows from
`professor_quality_gate` when computing blocking external issue
signals. Only issue rows from other reporters can block evaluation.

Persistence MUST be idempotent on the existing
`uq_pipeline_issue_open` dimensions. Re-evaluation MUST mark stale
quality-gate-authored rows resolved when the reason disappears, and
MUST NOT resolve rows from any other reporter.

The quality gate MUST use the following fixed `rule_id ->
pipeline_issue.stage` map. The map uses only V006/V023 stage values.

| `rule_id` | `pipeline_issue.stage` |
|---|---|
| `missing_canonical_name` | `name_extraction` |
| `non_person_name` | `name_extraction` |
| `missing_official_source` | `coverage` |
| `reader_artifact_detected` | `data_quality_flag` |
| `profile_blob_detected` | `data_quality_flag` |
| `missing_current_institution` | `affiliation` |
| `missing_title_or_department` | `affiliation` |
| `missing_research_topic` | `research_directions` |
| `missing_profile_summary` | `coverage` |
| `missing_verified_paper_signal` | `paper_attribution` |
| `identity_unresolved` | `identity_gate` |
| `same_name_conflict` | `identity_gate` |
| `field_contradiction` | `data_quality_flag` |

`human_override` is an evaluation reason for display only and MUST NOT
be persisted as a `pipeline_issue` row.

`external_blocking_issue` is also display-only. It reflects an existing
open `pipeline_issue` row from another reporter and MUST NOT cause the
quality gate to create a second quality-gate-authored issue row. The
existing external issue row remains the durable record.

#### Scenario: Gate-authored row does not block itself

- **GIVEN** a professor has an open `pipeline_issue` row with
  `reported_by = professor_quality_gate`
- **AND** no external issue or anomaly exists
- **WHEN** professor quality is evaluated
- **THEN** that row is not treated as a blocking signal

#### Scenario: Re-evaluation is idempotent

- **GIVEN** canonical write has persisted a missing-summary reason
- **WHEN** standalone re-evaluation persists the same reason
- **THEN** there is still only one open issue row for that reason

#### Scenario: External issue is not duplicated by the quality gate

- **GIVEN** a professor has an open external `pipeline_issue` row with
  `reported_by != professor_quality_gate`
- **WHEN** professor quality is evaluated and persisted
- **THEN** the evaluation may show `external_blocking_issue` as a
  display reason
- **AND** no new `pipeline_issue` row with
  `reported_by = professor_quality_gate` is created for that external
  blocking signal

### Requirement: Human overrides are watermark-bound

The evaluator MUST honor `confirm_ready` and `send_to_review` admin
actions only while the action's `observed_data_updated_at` is not older
than the current canonical watermark. The watermark MUST include the
latest timestamp across the professor row, its facts, its
affiliations, and external open `pipeline_issue` rows.

#### Scenario: External issue invalidates override

- **GIVEN** a professor has a fresh `confirm_ready` action
- **AND** a later external open `pipeline_issue` is filed
- **WHEN** professor quality is evaluated
- **THEN** the override is stale
- **AND** the machine evaluation applies

### Requirement: Existing professor rows can be re-evaluated

The system MUST provide a standalone re-evaluation entry point that can
dry-run or write quality-status updates for existing professor rows and
report before/after distributions.

#### Scenario: Official resolved non-anomalous rows are not needs_review

- **GIVEN** the existing professor population is loaded from
  `miroflow_real`
- **WHEN** the re-evaluation write pass completes
- **THEN** every sampled professor with official source, resolved
  identity, no external open issue, and no detected field contradiction
  is not assigned `needs_review`
- **AND** missing key fields in that cohort are represented as
  `needs_enrichment` or `low_confidence` reasons, not review anomalies

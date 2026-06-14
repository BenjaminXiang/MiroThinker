## ADDED Requirements

### Requirement: P7 full mode remains controlled and auditable

P7 full-mode execution MUST remain controlled, row-level auditable, and
separate from cleanup or publish refresh. Full-mode runs MUST record the same
run-scope fields used by existing seed-runner semantics, including trigger
mode, limit, failure class, diagnostic profile count when available, and
written profile count when available.

#### Scenario: Full run records run scope

- **WHEN** P7 executes a seed in `full` mode
- **THEN** the resulting `pipeline_run.run_scope` records
  `trigger_mode='full'`
- **AND** the run records the terminal failure class and write counts when
  available

#### Scenario: P7 does not bypass blocked evidence

- **WHEN** a seed has current blocked evidence and is not full-ready
- **THEN** P7 does not force a `full` run for that seed
- **AND** the skipped row remains visible in the evidence


## ADDED Requirements

### Requirement: Paper identity-status values and default

The system SHALL maintain `paper.identity_status` with the allowed values `{confirmed, unverified, rejected, merged}` (column introduced by Alembic V020), and every new paper row SHALL default to `unverified`.

#### Scenario: New paper defaults to unverified
- **WHEN** a paper row is inserted without an explicit identity verdict
- **THEN** `paper.identity_status` is `unverified`

### Requirement: Identity-status reflects resolved-identifier provenance

The system SHALL set `paper.identity_status='confirmed'` when the paper's canonical identity is resolved against a trusted identifier source (OpenAlex, arXiv, or a verified DOI lookup), and SHALL leave it `unverified` when no such resolution exists. This is the existing baseline behavior, now codified.

#### Scenario: Trusted-source resolution confirms identity
- **WHEN** a paper resolves via OpenAlex, arXiv, or DOI verification
- **THEN** `paper.identity_status='confirmed'`

#### Scenario: Prof-page-only paper without an identifier stays unverified
- **WHEN** a paper has `canonical_source='prof_page_only'` and no resolved DOI/arXiv/OpenAlex identifier
- **THEN** `paper.identity_status='unverified'`

### Requirement: Rejected or merged papers are excluded from retrieval

The system SHALL NOT index a paper into Milvus when `paper.identity_status` is `rejected` or `merged`. (Existing behavior of `paper/milvus_backfill._is_indexable_paper`; codified here so the rejection transition has a defined retrieval effect.)

#### Scenario: Milvus backfill skips rejected and merged papers
- **WHEN** a Milvus backfill selects candidate papers
- **THEN** rows with `identity_status in {rejected, merged}` are excluded from the index

### Requirement: LLM same-person-gate rejection transitions identity_status

The system SHALL transition `paper.identity_status` to `rejected` when, and only when, **all** of the following hold:
(a) the LLM same-person gate (`professor/paper_identity_gate.batch_verify_paper_identity`) has rejected the paper's professor attribution such that **no `professor_paper_link` with `link_status='verified'` remains** for that paper; and
(b) `paper.canonical_source='prof_page_only'`; and
(c) `paper.title_clean` is a plausible paper title — `paper/title_quality.is_plausible_paper_title(title_clean)` returns `True`.

> Rationale for (c): a 2026-06-16 dry-run found 92% of the otherwise-eligible population (1400/1519) had parser-garbage titles (root cause C2/C3) and were `rejected` only because the broken title defeated gate matching — not because of wrong attribution. Without (c), the transition would mislabel "unverifiable due to bad title" as "rejected/wrong-attribution" and wrongly exclude correct papers from retrieval. Garbage-title rows remain `unverified` for the parser-cleanup change (W1b).

#### Scenario: Last verified link rejected on a prof-page-only paper with a plausible title
- **WHEN** the gate rejects the final surviving `verified` `professor_paper_link` for a paper whose `canonical_source='prof_page_only'` AND whose `title_clean` is a plausible paper title
- **THEN** `paper.identity_status` transitions to `rejected`

#### Scenario: A verified link remains
- **WHEN** the gate rejects a link but at least one other `verified` `professor_paper_link` remains for the paper
- **THEN** `paper.identity_status` is unchanged

#### Scenario: Paper is not prof-page-only
- **WHEN** the paper has no remaining `verified` links but `canonical_source != 'prof_page_only'`
- **THEN** `paper.identity_status` is unchanged (the transition is conservative to identifier-backed papers)

#### Scenario: Paper has a garbage or malformed title
- **WHEN** the paper has no remaining `verified` link and `canonical_source='prof_page_only'` but `is_plausible_paper_title(title_clean)` is `False`
- **THEN** `paper.identity_status` is unchanged (left `unverified` for parser-cleanup; not mislabeled `rejected`)

### Requirement: Identity-status rejection is reversible

The rejection transition SHALL be reversible: a subsequent scan SHALL restore `identity_status` to its prior value when a `verified` `professor_paper_link` is re-established for the paper. The rejection path SHALL mutate `paper.identity_status` only and MUST NOT terminalize `paper.quality_status` (a rejected paper reaches a human-reviewable state, not an auto-deleted terminal).

#### Scenario: Re-scan restores identity after a verified link returns
- **WHEN** a re-scan runs after a `verified` link is restored for a previously-`rejected` paper
- **THEN** `paper.identity_status` is restored away from `rejected`

#### Scenario: Rejection does not terminalize quality_status
- **WHEN** the rejection transition sets `identity_status='rejected'`
- **THEN** `paper.quality_status` is not force-set to `rejected` by this transition

### Requirement: Identity-status scan is dry-run by default behind an independent flag

The system SHALL provide an identity-status scan that is **dry-run by default** (no writes unless `--apply` is passed), records each per-row decision (paper id, verdict, confidence, reasoning) to a JSONL archive, and reports counts. The scan SHALL be gated by an independent environment flag `PAPER_IDENTITY_GATE_ENABLED` that is **read in the scan script**, not in the gate module, and that is **separate** from `NAME_IDENTITY_GATE_ENABLED` and the professor `paper_collector` `identity_gate_enabled`. Until a dry-run demonstrates a sane reject rate, the flag default SHALL be the conservative (off) setting.

#### Scenario: Default invocation performs no writes
- **WHEN** the scan is run without `--apply`
- **THEN** no `paper.identity_status` value is changed and a JSONL of would-be decisions plus counts is produced

#### Scenario: Flag disabled skips the scan
- **WHEN** `PAPER_IDENTITY_GATE_ENABLED` is set to a falsy value
- **THEN** the scan exits without invoking the gate or writing

#### Scenario: Apply writes only qualifying rejections
- **WHEN** the scan is run with `--apply` and `PAPER_IDENTITY_GATE_ENABLED` enabled
- **THEN** only papers meeting the full rejection guard (no verified links AND `prof_page_only`) have `identity_status` set to `rejected`

### Requirement: Rejections carry evidence and run_id

For each **applied** rejection, the system SHALL record the gate decision (confidence, reasoning, source spans) and the producing `run_id`, persisted as a `pipeline_issue` row and/or a scan JSONL entry, preserving source traceability.

#### Scenario: Applied rejection is traceable
- **WHEN** a paper is rejected via `--apply`
- **THEN** an evidence record exists containing the gate confidence, reasoning, source spans, and `run_id`

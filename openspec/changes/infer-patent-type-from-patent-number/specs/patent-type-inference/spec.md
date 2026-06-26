## ADDED Requirements

### Requirement: patent_type is derived from patent_number when absent

When a patent row has no `patent_type` (NULL/empty), the system SHALL derive
`patent_type` from its `patent_number` using the Chinese patent kind-code
mapping:

- kind-code suffix `A` or `B` → `发明`
- kind-code suffix `U` or `Y` → `实用新型`
- kind-code suffix `S` or `D` → `外观设计`

If the kind-code suffix is absent or unrecognized, the system SHALL fall back to
the leading digit of the numeric portion (after any `CN` prefix): `1` → 发明,
`2` → 实用新型, `3` → 外观设计 (and `8`/`9` PCT → 发明/实用新型 respectively).
If neither signal is recognizable, `patent_type` SHALL remain NULL (the row
stays `partial`).

The inference SHALL be deterministic and pure (a function of `patent_number`
only). It SHALL NOT overwrite a non-null `patent_type` already present from the
source.

#### Scenario: Invention patent inferred from A suffix
- **GIVEN** a patent with `patent_number='CN115709471A'` and no `patent_type`
- **WHEN** `infer_patent_type` runs
- **THEN** `patent_type` is set to `发明`

#### Scenario: Utility model inferred from U suffix
- **GIVEN** a patent with `patent_number='CN2xxxxxxxxU'` and no `patent_type`
- **WHEN** `infer_patent_type` runs
- **THEN** `patent_type` is set to `实用新型`

#### Scenario: Design inferred from S suffix
- **GIVEN** a patent with `patent_number='CN3xxxxxxxxS'` and no `patent_type`
- **WHEN** `infer_patent_type` runs
- **THEN** `patent_type` is set to `外观设计`

#### Scenario: Leading-digit fallback when no kind code
- **GIVEN** a patent with `patent_number='CN123456789'` (no suffix) and no
  `patent_type`
- **WHEN** `infer_patent_type` runs
- **THEN** `patent_type` is set to `发明` (leading digit `1`)

#### Scenario: Existing patent_type is not overwritten
- **GIVEN** a patent with `patent_type='发明'` already set from the source
- **WHEN** the inference path runs
- **THEN** `patent_type` remains `发明` (inference only fills absent values)

#### Scenario: Unrecognizable number leaves type NULL
- **GIVEN** a patent with `patent_number=''` or a number with no recognizable
  type signal
- **WHEN** `infer_patent_type` runs
- **THEN** `patent_type` remains NULL (no fabricated type)

### Requirement: Inferred patent_type feeds the quality gate at write time

The patent import/canonical path SHALL run `infer_patent_type` to fill an absent
`patent_type` before the quality gate evaluates the row, so a newly imported
patent whose number encodes its type is `ready`-eligible at write time (given
the other required fields: patent_number, title, date, applicants/inventors).

#### Scenario: A newly imported patent is ready-eligible at write time
- **GIVEN** a patent imported with `patent_number='CN115709471A'`, title, a
  date, and applicants, but no `专利类型` column in the source
- **WHEN** the import path fills `patent_type` via inference and the gate runs
- **THEN** `quality_status` is `ready` (not `partial`)

### Requirement: Patent ready date-signal accepts publication_date

The patent quality gate's date requirement SHALL be satisfied by `filing_date`,
`grant_date`, OR `publication_date`. (The source xlsx provides only
`公开（公告）日` = `publication_date`; requiring `filing_date`/`grant_date`
excludes every collected patent from `ready`.) A patent with `publication_date`
but no `filing_date`/`grant_date` SHALL NOT be failed on the date signal. This
is the only gate relaxation in this change; the other `ready` criteria
(`patent_number`, `title`, `patent_type`, applicants/inventors), the
`quality_status` enum, the forward-monotonic invariant, and the
no-external-enrichment constraint are unchanged.

#### Scenario: A publication-date-only patent satisfies the date signal
- **GIVEN** a patent with `publication_date='2025-02-11'`, `filing_date=NULL`,
  `grant_date=NULL`, an inferred `patent_type`, title, patent_number, and
  applicants
- **WHEN** the quality gate evaluates it
- **THEN** the date signal is satisfied and `quality_status` is `ready` (not
  `partial`)

#### Scenario: A patent with no date at all stays partial
- **GIVEN** a patent with `filing_date=NULL`, `grant_date=NULL`,
  `publication_date=NULL`, and an inferred `patent_type`
- **WHEN** the quality gate evaluates it
- **THEN** the date signal is NOT satisfied and `quality_status` is `partial`

### Requirement: Inferred type makes patents retrievable

The system SHALL make patents with an inferred `patent_type` retrievable: after
the one-time backfill populates `patent_type` for existing rows and the existing
`evaluate_patent_promotion` gate promotes them to `ready`, a Milvus rebackfill
of `patent_profiles` SHALL index them so they are retrievable via the retrieval
service. The change SHALL NOT alter the Milvus indexability filter
(`_is_indexable_patent`), which already keys on `quality_status == 'ready'`.

#### Scenario: An inferred-type patent becomes retrievable after rebackfill
- **GIVEN** one of the 11,408 patents previously `partial` because `patent_type`
  was NULL
- **WHEN** the backfill infers `patent_type`, the gate promotes it to `ready`,
  and a Milvus rebackfill runs
- **THEN** the patent is present in `patent_profiles` and retrievable via the
  retrieval service

#### Scenario: No ready patent is degraded
- **GIVEN** the backfill only adds `patent_type` (never removes) and the gate is
  forward-monotonic
- **WHEN** the backfill runs
- **THEN** no `ready` patent is degraded (and since 0 were `ready` before, the
  net effect is 11,408 partial → ready)

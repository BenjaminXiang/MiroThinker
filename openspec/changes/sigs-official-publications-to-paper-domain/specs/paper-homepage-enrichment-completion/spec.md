## ADDED Requirements

### Requirement: Official professor-page ingest accepts all parsed publications

The homepage paper ingest path MUST process every parseable official professor-page publication entry returned by the extractor. It MUST NOT apply a fixed per-professor paper count cap to official page publications.

Run-level controls such as professor `limit`, resume checkpoints, provider backoff, and PDF fetch caps MAY still be used to keep jobs resumable and operationally bounded.

#### Scenario: More than five official papers are linked

- **GIVEN** a professor official profile page returns more than five parseable publication candidates
- **WHEN** homepage paper ingest runs for that professor
- **THEN** title resolution and paper/link upsert are attempted for every parseable candidate
- **AND** the bridge does not truncate the candidates to five papers

### Requirement: Official professor-page links preserve tier and official-list evidence

The homepage paper ingest path MUST write professor-paper links for official page publications with `link_status='verified'`, `is_officially_listed=true`, and the strongest derivable professor-page evidence tier.

#### Scenario: Official profile page evidence is retained

- **GIVEN** a publication is extracted from an official SIGS professor profile page with a mappable page role
- **WHEN** homepage paper ingest writes the professor-paper link
- **THEN** the link status is `verified`
- **AND** `is_officially_listed` is true
- **AND** `evidence_source_type` is `prof_homepage_tier2` or `prof_homepage_tier3`

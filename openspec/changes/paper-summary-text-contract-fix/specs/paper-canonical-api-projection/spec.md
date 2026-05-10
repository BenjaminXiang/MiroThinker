# Spec: paper-canonical-api-projection

> Capability: how Paper canonical row fields are projected into the
> admin API (and chat API) JSON response. Aligns API outputs with the
> Shared-Spec §4.2.1 / Paper-Data-Agent-PRD §4.3 contract for
> `summary_text`.

## ADDED Requirements

### Requirement: summary_text field aliases summary_zh

The admin API MUST return the value of `paper.summary_zh` for the
JSON field name `summary_text`. The admin API MUST NOT alias
`summary_text` to `paper.abstract_clean` (the original English
abstract column), the historic admin API behavior that violated the
contract.

When `paper.summary_zh` is NULL, the API MUST return `null` for
`summary_text` (no fallback to `abstract_clean`). Per Paper Review
§3.1 P3, `summary_text` is semantically equivalent to `summary_zh`
content (the Chinese paragraph 200-400 chars per P2); falling back to
the English abstract is incorrect.

#### Scenario: summary_zh present → summary_text returns it

- **GIVEN** a paper canonical row with `summary_zh="一段中文摘要..."`
  and `abstract_clean="An English abstract."`
- **WHEN** admin API `GET /api/paper/{id}` is called
- **THEN** the response `summary_fields.summary_text` equals
  `"一段中文摘要..."`
- **AND** `summary_fields.summary_zh` equals `"一段中文摘要..."`
  (both fields surface the same Chinese content)

#### Scenario: summary_zh null → summary_text null (no fallback)

- **GIVEN** a paper canonical row with `summary_zh=NULL` and
  `abstract_clean="An English abstract."`
- **WHEN** admin API `GET /api/paper/{id}` is called
- **THEN** the response `summary_fields.summary_text` is `null`
- **AND** the response `summary_fields.summary_zh` is `null`
- **AND** the API MUST NOT fall back to `abstract_clean`

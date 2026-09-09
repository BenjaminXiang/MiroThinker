## ADDED Requirements

### Requirement: Generic Serper source discovery uses identity-only queries

Generic Serper source discovery MUST generate queries only from company identity
terms: canonical company name, registered name, trusted XLSX project or short
name, and trusted LLM-extracted aliases. It MUST NOT append product, financing,
founder, recruiting, job, or industry keyword tails by default.

Yiou and 36Kr/PitchHub site-specific discovery MAY continue using project names,
aliases, founders, and distinctive keywords to broaden recall, but those terms
MUST NOT prove company identity by themselves. Accepted source rows MUST still
pass domain/path constraints and company identity checks.

All Serper payloads in this source-discovery path MUST include `gl='cn'` and
`hl='zh-cn'`.

#### Scenario: Generic query does not add news tail
- **GIVEN** a company named `深圳示例科技有限公司`
- **WHEN** generic Serper source discovery builds a query
- **THEN** the query is `深圳示例科技有限公司`
- **AND** it does not include `融资`, `发布`, `产品`, `招聘`, founder names, or industry keywords
- **AND** the Serper payload includes `gl='cn'` and `hl='zh-cn'`

#### Scenario: Site-specific query can broaden recall without proving identity
- **GIVEN** a PitchHub search uses alias plus founder to find a project page
- **WHEN** a result is returned
- **THEN** the result is accepted only if source domain, path, and company identity checks pass
- **AND** product keywords or founder names alone do not prove the result belongs to the company

### Requirement: Generic web source material requires LLM source judgment

Generic web search results MUST NOT be written as accepted source material or
used in synthesis until an LLM source-judgment step confirms both target-company
identity and fact attribution. The judgment MUST record accepted, rejected, or
needs-review status with a reason and evidence span.

The source workflow MUST inspect snippets before fetching full pages. It MUST
fetch full page text only when the snippet is potentially relevant but
insufficient for product, financing, application scenario, target customer,
team, or profile facts.

#### Scenario: Snippet-only rejection
- **GIVEN** a generic Serper result snippet clearly describes a different company
- **WHEN** source judgment evaluates the snippet
- **THEN** the result is rejected without fetching the page body
- **AND** the audit records `company_identity_failed`

#### Scenario: Full page accepted after snippet is insufficient
- **GIVEN** a generic Serper result snippet mentions the target company but lacks product details
- **WHEN** source judgment marks the snippet insufficient
- **THEN** the workflow fetches the page body
- **AND** the full page is accepted only if LLM judgment confirms company identity and fact attribution

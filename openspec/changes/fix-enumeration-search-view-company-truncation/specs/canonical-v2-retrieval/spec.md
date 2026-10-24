## ADDED Requirements

### Requirement: Question-word company matches never truncate the search view

When `_search_view` derives retrieval text from a query with no displayed
entity, a `COMPANY_NAME_PATTERN` match that contains a question word MUST NOT be
returned as the company name. The function MUST fall through to the full query
text so the content term survives into the lanes.

#### Scenario: Enumeration over a technology term

- **WHEN** the query is `深圳哪些公司做激光雷达`
- **THEN** the search view is the full query, not `深圳哪些公司`
- **AND** the web lane searches `激光雷达` rather than only the city and the
  question scaffolding

#### Scenario: A real company name still compacts

- **WHEN** the query is `深圳市优必选科技股份有限公司有哪些专利`
- **THEN** the search view remains the company name, because the match carries
  no question word

#### Scenario: Alternative enumeration phrasings

- **WHEN** the query is `深圳有哪些公司做激光雷达` or `深圳什么公司做激光雷达`
- **THEN** the search view keeps the full query and the technology term

# Proposal: fix-enumeration-search-view-company-truncation

Human doc: `docs/plans/2026-10-24-enumeration-search-view-truncation-log.md`.

## Why

`_search_view` (`src/data_agents/canonical_v2/followup_referents.py`) builds the
retrieval text for a query that names no displayed entity. Its company-name
branch returns the first `COMPANY_NAME_PATTERN` match **without** applying the
question-word reject list that `_has_explicit_company_name` already uses in the
same module.

Observed on the customer site (2026-10-23 01:51, session
`C4XrUsD91G4LegDYgkoomeezYIllcZ9d`):

- Query: `深圳哪些公司做激光雷达`
- `_search_view` returned `深圳哪些公司`, dropping the content term `激光雷达`
- All local lanes returned 0 candidates (lexical index disabled; exact/structured
  find no entity; the vector lane embeds the truncated text)
- The web lane searched `深圳哪些公司`, hit a cached CSDN list of large Shenzhen
  companies, and made that page the answer subject
- The answer then said no lidar company list exists, profiled 华为/中兴/比亚迪/
  腾讯/平安/招行/万科 (none of them lidar vendors), and appended a raw disclosure
  of 114 unrelated local companies

The serving pack has 61 Shenzhen companies whose structured fields mention
激光雷达 (镭神智能, 览沃科技, 海伯森, 砝石激光雷达, …), so this is a retrieval-text
defect, not a data gap. A sibling run 15 minutes earlier (session
`y2y5EhpHbQcWBWxIq5vvwzFwlPW2nbmX`) used the full query and produced a correct
lidar vendor list, which isolates the failure to the truncated search text.

## What Changes

1. `_search_view`: a `COMPANY_NAME_PATTERN` match that contains a question word
   (`哪些`, `什么`, `怎么`, `如何`, `哪里`, `几`, `多少`, `其他`, …) is not a
   company name. Reuse `_EXPLICIT_COMPANY_REJECT_MARKERS`; on rejection fall
   through to the existing full-query return.
2. Regression tests covering enumeration phrasings that previously truncated
   and named-company phrasings that must keep truncating.

## Impact

- Affects only queries whose candidate company-name match contains a question
  word. Named-company queries (`深圳市优必选科技股份有限公司有哪些专利`) keep the
  current company-only search text.
- No schema, API, or answer-contract change. The fix changes which text the
  lanes search, not their interfaces.

## Non-goals

- Enabling the lexical index (`CANONICAL_V2_LEXICAL_INDEX`) — a separate
  retrieval capability, not needed to restore this answer.
- The answer-side disclosure dump and the "no list" essay template; they are
  downstream of the wrong subject and are only re-checked here.

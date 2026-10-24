# Acceptance: fix-enumeration-search-view-company-truncation

| # | Criterion | Evidence |
|---|---|---|
| A1 | `_search_view('深圳哪些公司做激光雷达')` returns the full query | `test_search_view_keeps_content_term_after_question_word_company` |
| A2 | `_search_view('深圳有哪些公司做激光雷达')` returns the full query | same parametrized test |
| A3 | `_search_view('深圳什么公司做激光雷达')` returns the full query | same parametrized test |
| A4 | Named-company queries keep their company-only search text | `test_search_view_still_compacts_real_company_names` (优必选/这家公司/深圳激光雷达公司) |
| A5 | Followup-referents suite green | 152 passed |
| A6 | Planning + enumeration suites green | 11 passed |
| A7 | Serving isolated suite green | 312 passed |
| A8 | Live web views carry the technology term | trace `2026-10-24T14:29:33Z`: views include `深圳哪些公司做激光雷达`, `深圳 激光雷达 公司 厂商`, `深圳 激光雷达 企业 车载 机器人`, no `深圳哪些公司`-only view |
| A9 | Live local lanes participate | lexical 128, vector 128 (previously lexical 0) |
| A10 | Live answer is a structured vendor list | 12 vendors with one-line descriptions; subject 深圳市砝石激光雷达有限公司 |
| A11 | Live citations are local | 12 citations: 11 `company` + 1 `web` |
| A12 | Named-company control unchanged | `深圳市优必选科技股份有限公司有哪些专利` → 12 patent citations, structured |

## Residual

The member-coverage disclosure tail (up to 64 names) still ships. It now lists
lidar-related companies, and the sentence widens the session universe before
commit; shortening it is a product/UX decision tracked outside this change.

Evidence: `.agents/runs/fix-enumeration-search-view-company-truncation/verification.md`.

# Tasks: fix-enumeration-search-view-company-truncation

- [x] 1.1 Add the question-word rejection to `_search_view`'s company match.
- [x] 1.2 Add regression tests: `深圳哪些公司做激光雷达`,
      `深圳有哪些公司做激光雷达`, `深圳什么公司做激光雷达`, and a named-company
      control (`深圳市优必选科技股份有限公司有哪些专利`).
- [x] 1.3 Run the followup-referents suite plus the serving planning tests.
- [x] 1.4 Deploy the module to the customer bundle and restart the service.
- [x] 1.5 Live verify `深圳哪些公司做激光雷达` returns a structured lidar vendor
      list with citations, and a named-company query is unchanged.

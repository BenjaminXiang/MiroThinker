# Tasks: fix-answer-guards-and-job-timezone

- [x] 1.1 Widen the prose marker filter to the closing `</|…|>` form and add a
      streaming-decoder regression test.
- [x] 1.2 Add `query_company_name` / `company_names_match` with relation,
      description, question-word, and anaphora exclusions.
- [x] 1.3 Filter local company claims in `_answer_selector` for a named
      non-enumeration company; keep web claims and partial-name matches.
- [x] 1.4 Add the jobs timezone helper and pass it to `cron_next_fire`.
- [x] 1.5 Run the followup-referents, serving-answer, and jobs-registry suites.
- [x] 1.6 Deploy the three modules and restart the customer service.
- [x] 1.7 Live verify: unknown-company query no longer profiles 普渡; 丁文伯
      company answer unchanged; 普渡 partial name still resolves; lidar
      enumeration unchanged; jobs next-run shows 02:00+08:00.
- [x] 1.8 Compact the enumeration disclosure to 8 names + count; update the
      three AQ-S2d contract assertions (cap, recall-source, no-fabrication).
- [x] 1.9 Bind `它`/`该公司` attribute follow-ups to the single displayed
      company when the receipt anchored an incidental patent/web handle.

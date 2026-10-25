# Acceptance: fix-answer-guards-and-job-timezone

| # | Criterion | Evidence |
|---|---|---|
| A1 | Closing answer marker is stripped from prose | `test_prose_decoder_redacts_closing_answer_marker` (streaming, char-by-char, redaction recorded) |
| A2 | Opening marker still stripped | existing marker tests in `test_knowledge_serving_isolated.py` |
| A3 | Question/description/anaphora/relation phrases are not company names | `test_query_company_name_excludes_scaffolding` (`哪些`, `的`, `介绍一下`, `创办的公司`) |
| A4 | Partial names match the full company | `test_company_names_match_resolves_partial_forms` |
| A5 | A neighbour name does not match | `test_company_names_match_rejects_a_neighbour_name` |
| A6 | Unknown named company drops local company claims | `test_selector_drops_local_company_claims_for_an_unknown_named_company` |
| A7 | Partial name keeps the local claim | `test_selector_keeps_local_company_claim_for_a_matching_partial_name` |
| A8 | Followup + serving suites green | 163 + 315 passed (480 total) |
| A9 | Jobs timezone helper follows the launcher env | `test_job_timezone_uses_the_launcher_env` |
| A10 | Weekly cron renders 02:00+08:00 | `test_next_fire_in_job_timezone_uses_local_wall_clock`; customer-machine helper prints `2026-10-26T02:00:00+08:00` |
| A11 | Jobs registry suite green | 50 passed |
| A12 | Live unknown-company query no longer profiles 普渡 | `/api/chat` after restart |
| A13 | Live 丁文伯 company answer unchanged | `/api/chat` after restart |
| A14 | Live 普渡 partial name still resolves | `/api/chat` after restart |
| A15 | Live lidar enumeration unchanged | `/api/chat` after restart |
| A16 | Live jobs next-run shows 02:00+08:00 | jobs API or trace after restart |
| A17 | Disclosure caps at 8 names plus count | `test_member_coverage_sentence_caps_at_8_with_overflow_count` |
| A18 | Recall-source and no-fabrication assertions follow the compact contract | `test_member_coverage_sentence_sources_the_recalled_set_beyond_the_claim_window`; `test_member_coverage_sentence_names_all_resolve_to_recalled_handles` |
| A19 | Thing-pronoun binds the single displayed company | `test_thing_pronoun_binds_the_single_displayed_company` |
| A20 | Person pronoun keeps the professor anchor | `test_person_pronoun_keeps_the_professor_anchor` |

Evidence: `.agents/runs/fix-answer-guards-and-job-timezone/verification.md`.

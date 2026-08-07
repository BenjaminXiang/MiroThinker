# Change Log: fix-paper-topic-query-classification

## 2026-07-10 — Status corrected to Candidate

- Preserved the implemented classifier repair and its historical test/live observations.
- Superseded the earlier local Accepted decision because the response-wide scorer can pass through
  query echo and the Type4 token oracle changed between runs.
- Re-acceptance is governed by `close-retrieval-generation-contract` Slice A (fixed oracle) and
  Slice D (paper-level hybrid retrieval, frozen-topic Precision@5, citation, and semantics).
- Archive is blocked until those linked scenarios are Accepted. Then this record is accepted only
  as superseded history and archived with
  `openspec archive fix-paper-topic-query-classification --skip-specs` plus
  `superseded_by=close-retrieval-generation-contract`; default spec migration is forbidden.

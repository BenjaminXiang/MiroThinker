# Tasks — make-professors-retrievable-beyond-ready

> Implementation already done (filter change + tests). This file records the work + remaining
> verification. Behavior-affecting → eval-gated on breadth WITHOUT precision regression.

## 1. Implementation

- [x] 1.1 `retrieval._filter_ready_only`: professor branch admits `ready`/`needs_review`/
  `needs_enrichment`; excludes `low_confidence`. (comment: decouple retrievability from
  publication-completeness.)
- [x] 1.2 `test_retrieval_filter.py`: new `test_filter_admits_non_ready_professors_except_low_confidence`.
- [x] 1.3 `test_retrieval_quality_filter.py`: update `test_default_quality_status_filter_keeps_only_ready[professor]`
  to the new contract (needs_review admitted; ready ranks first).

## 2. Verification

- [x] 2.1 Service + quality + paper regression: **1038 passed** (independent re-run).
- [x] 2.2 `openspec validate` (run in step 4).
- [ ] 2.3 Breadth probe (backend up, new filter): professor-topic queries return MORE relevant
  professors (e.g. qid50-style → >9); record before/after counts.
- [ ] 2.4 Precision check: confirm no new false-positive professors dominate; spot-check that
  `ready` still ranks at or near the top for representative queries. (Full precision oracle is
  pending labels per benchmark-completion-spec.)
- [ ] 2.5 Recall eval (`eval_recall_chat.py`): expect 13/24 unchanged (oracle is insensitive —
  qid50 targets 王强/柯文德 already ready); no passing case regressed.

## 3. Acceptance (Claude review)

- [ ] 3.1 Breadth up (more professors returned for topic queries) WITHOUT precision regression;
  `ready` still ranks competitively; `openspec validate --strict` = 0; regression green.
- [ ] 3.2 Decision: Accept / Revise / Reject.

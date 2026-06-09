# Verification Contract: SIGS Official Publications To Paper Domain

## Scope

This slice covers the SIGS official-publication bridge pre-rollout gate:
supported SIGS professor pages may only write paper-domain records when the
publication title is a real paper title, not an author fragment, venue label,
statistics sentence, or section boilerplate. The Ding Wenbo JSAC citation is the
reported concrete regression inside this wider gate.

## RED

- `tests/data_agents/professor/test_homepage_publications_sigs.py::test_sigs_bracketed_venue_prefix_with_missing_closing_quote_extracts_title`
  must fail before the parser fix because the current rule parser emits
  `[JSAC] Wenbo Ding` instead of the real paper title.

## GREEN

- The same test must pass after the parser fix.
- Existing SIGS homepage publication and homepage ingest regression tests must pass:
  `uv run --no-sync pytest tests/data_agents/professor/test_homepage_publications_sigs.py tests/data_agents/paper/test_homepage_ingest.py -q -n0 --no-cov`.
- A Ding read-only live-page probe must show the JSAC entry title as
  `Spectrally Efficient Channel State Information Acquisition for Power Line Communications: A Bayesian Compressive Sensing Perspective`.
- A SIGS read-only profile crawl must discover and fetch all official professors
  from `https://www.sigs.tsinghua.edu.cn/7644/list.htm` with no profile fetch
  failures.
- A SIGS read-only publication parser audit must report no fetch failures and
  must be used to decide whether the full paper bridge runs with rule parsing
  only or with source-grounded LLM fallback enabled.
- Full SIGS rollout must include profile recollection, homepage paper bridge,
  paper summary backfill where abstracts/identifiers are available, and retrieval
  refresh/coverage verification.

## Non-Goals

- Do not move OpenAlex/arXiv title resolution into the professor seed recollection loop.
- Do not fabricate paper abstracts or summaries.

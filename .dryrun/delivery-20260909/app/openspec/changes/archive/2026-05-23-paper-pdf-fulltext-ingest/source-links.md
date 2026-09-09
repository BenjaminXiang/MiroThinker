# Source Links: paper-pdf-fulltext-ingest

- `apps/miroflow-agent/src/data_agents/paper/full_text_fetcher.py` -
  existing full-text fetcher.
- `apps/miroflow-agent/alembic/versions/V011_add_paper_full_text.py` -
  full-text storage schema.
- `apps/miroflow-agent/src/data_agents/professor/homepage_publications.py`
  - publication parser that can surface PDF links.
- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py` -
  page-first paper ingest path.

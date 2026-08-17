# Change Log: paper-homepage-enrichment-completion

## 2026-05-15 - Initial scope

- Created follow-up change for page-flow enrichment completion,
  identifier contradiction handling, and summary-to-Milvus refresh.

## 2026-05-15 - Implementation evidence

- Implemented tier-specific page evidence values and missing-tier
  diagnostic handling in the homepage paper ingest path.
- Completed enrichment merge behavior for author metadata, arXiv
  fallback injection, DOI/arXiv contradiction detection, and
  contradiction-driven quality review status.
- Added targeted paper chunk refresh support through
  `run_milvus_backfill.py --domain paper --paper-id <paper_id>`.
- Documented the chosen `summary_zh` refresh signal contract and
  recorded focused verification evidence in `acceptance.md`.

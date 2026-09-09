## ADDED Requirements

### Requirement: Web-search augmentation SHALL surface out-of-DB entities as web Evidence

The retrieval service SHALL augment recall with web-search results (object_type `web`) for
entities absent from the local DB or for broad-profile entities the DB under-ranks, so they
become citable candidates. Web augmentation SHALL be best-effort: on web-search failure, the
service SHALL return local results unchanged.

#### Scenario: an absent entity is surfaced via web augmentation
- **GIVEN** a well-known entity absent from the local DB that web-search returns for the query
- **WHEN** the query is retrieved with `augment_with_web=True`
- **THEN** the response includes an `object_type=web` candidate for that entity

#### Scenario: web-search failure degrades gracefully
- **GIVEN** the web-search provider is unavailable or errors
- **WHEN** the query is retrieved with `augment_with_web=True`
- **THEN** the response returns the local DB results unchanged (no exception to the caller)

### Requirement: Web-rescued evidence SHALL be source-traceable

Every web-rescued candidate SHALL carry an auditable `source_url`. Web candidates without a
source URL are a CLAUDE.md §5 provenance violation and SHALL be flagged by the precision oracle.

#### Scenario: a web candidate carries a source url
- **GIVEN** a web-search-augmented retrieval result
- **WHEN** the candidate is rendered
- **THEN** it exposes `object_type=web`, a snippet, and a `source_url` (or is flagged unsourced
  by the precision oracle)

## UNCHANGED Requirements
<!-- A–G routing semantics, RRF fusion, candidate window, per-domain recall mechanics unchanged
     (owned by fix-chat-retrieval-recall-gaps). This change only contracts web augmentation. -->

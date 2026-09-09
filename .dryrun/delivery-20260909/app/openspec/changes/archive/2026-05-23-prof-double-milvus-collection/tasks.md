# Tasks: prof-double-milvus-collection

## 1. Collection definitions

- [x] T1.1: Add Milvus definitions for
  `professor_identity_profiles` and `professor_research_profiles`.
- [x] T1.2: Keep the old `professor_profiles` collection available
  during migration.
- [x] T1.3: Add tests for collection schema names and vector fields.

## 2. Vector input builders

- [x] T2.1: Add identity text builder.
- [x] T2.2: Add research text builder.
- [x] T2.3: Ensure research builder consumes `paper_summary` and
  `patent_summary` when present.
- [x] T2.4: Add unit tests proving identity-only fields do not dominate
  research input.

## 3. Backfill

- [x] T3.1: Extend professor vector backfill to write selected
  collection(s).
- [x] T3.2: Add dry-run count mode.
- [x] T3.3: Add tests for identity-only and research-only refresh.

## 4. Retrieval routing

- [x] T4.1: Add query-intent routing for identity vs research
  professor searches.
- [x] T4.2: Add fusion behavior for ambiguous queries.
- [x] T4.3: Preserve source traceability and collection labels in
  retrieval results.
- [x] T4.4: Add retrieval tests for identity lookup and research-topic
  lookup.

## 5. Verification

- [x] T5.1: Run vectorizer and Milvus collection tests.
- [x] T5.2: Run retrieval tests.
- [x] T5.3: Run a bounded backfill sample and record collection counts.

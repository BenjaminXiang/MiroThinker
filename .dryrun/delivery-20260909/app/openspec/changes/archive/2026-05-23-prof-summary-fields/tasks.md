# Tasks: prof-summary-fields

## 1. Schema

- [x] T1.1: Choose storage shape: nullable columns on `professor` or a
  professor-summary table.
- [x] T1.2: Add reversible migration for `paper_summary` and
  `patent_summary` or the chosen equivalent.
- [x] T1.3: Add migration tests or schema assertions.

## 2. Input selection

- [x] T2.1: Add query for eligible paper links.
- [x] T2.2: Add query for eligible patent links.
- [x] T2.3: Exclude rejected, uncertain, and unresolved links.
- [x] T2.4: Add tests for inclusion/exclusion cases.

## 3. Summary generation

- [x] T3.1: Add professor output-summary generator with injected LLM
  client.
- [x] T3.2: Add deterministic fallback or explicit no-summary outcome
  when no eligible outputs exist.
- [x] T3.3: Add mocked-client tests for papers, patents, and mixed
  output.

## 4. Backfill runner

- [x] T4.1: Add a bounded backfill runner with dry-run mode.
- [x] T4.2: Report processed, skipped, failed, paper summaries written,
  and patent summaries written.
- [x] T4.3: Emit a refresh signal for professor research-vector rebuild.

## 5. Verification

- [x] T5.1: Run generator and query tests.
- [x] T5.2: Run migration tests or schema check.
- [x] T5.3: Run a bounded dry-run sample and record evidence.

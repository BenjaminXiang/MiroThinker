# Intent Classifier Benchmark Fixture

`intent_classifier_benchmark.jsonl` contains the W9-3 100-query intent-classifier benchmark for `/api/chat`.

Each JSONL row must include:

- `id`: stable `Q001` through `Q100` identifier.
- `query`: original user query text.
- `expected_type`: one of `A`, `B`, `C`, `D`, `E`, `F`, or `G`.
- `expected_topic`: optional expected topic; use an empty string when not asserted.
- `expected_name`: optional expected entity name; use an empty string when not asserted.
- `category_label`: short human-readable Chinese label.
- `rationale`: one-sentence labeling reason.
- `language`: `zh` or `en`.
- `source`: provenance such as `Agentic-RAG-PRD §2.1 type A example`, `derived from ...`, or `manual`.

Distribution is fixed by the W9-3 spec:

- A: 50
- B: 20
- C: 15
- D: 5
- E: 5
- F: 3
- G: 2

Editing rules:

- Keep exactly 100 non-empty rows.
- Keep IDs unique and stable unless the spec changes.
- Do not change `expected_type` to match current model behavior without a labeling rationale.
- If adding, replacing, or relabeling a row, update `rationale` and `source` in the same edit.
- Re-run the fixture integrity check and the classifier benchmark after any change.

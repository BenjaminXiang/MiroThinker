## Change Log

### 2026-05-29 - Validation Closure and Rollout Notes

- Unified this rollout on `deepseek-v4-pro` in non-thinking mode per operator
  direction. Model tiering is documented as a next-round optimization, not
  implemented in this change.
- Deferred multi-thread or concurrent LLM extraction to the next optimization
  round. The current implementation keeps bounded batch orchestration,
  checkpointing, and per-company state as the concurrency boundary.
- During 100-company live validation, XLSX product and scenario synthesis was
  wired into the upload-scoped XLSX/team stage so trusted XLSX baseline
  material can create publishable products and application scenarios even when
  external sources miss.
- Trusted XLSX product readiness was relaxed only for explicit XLSX-backed
  product evidence. Generic-web and third-party candidates remain review-gated
  unless source judgment and candidate-level attribution are strong.
- A source-product candidate-level LLM gate was added after validation exposed
  same-industry and other-company product pollution from Yiou, PitchHub, and
  generic web pages.
- Yiou/PitchHub identity acceptance was tightened so broad LLM aliases and
  product phrases can help recall but do not prove target-company identity.
- The final bounded validation report is recorded in
  `.agents/runs/company-synthesis-enrichment-pipeline/validation-100.md`.
# 2026-05-29 - Admin processing status visibility gap

- Added task 10.9 after upload-path validation showed that the backend can parse the XLSX quickly but operators cannot see the detached company enrichment batch status from the pipeline detail page.
- Added an acceptance scenario requiring backend detail payloads and the frontend run detail page to expose upload-scoped company enrichment progress and refresh while active.

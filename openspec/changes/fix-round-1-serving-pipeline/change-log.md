# Change Log: fix-round-1-serving-pipeline

## 2026-08-18 — Phase 5 scope extended by user requirement (iterative web research + progressive feedback)

User requirement (verbatim intent, recorded from session):

- Web search must not be single-shot: search → fetch → adjust direction based
  on fetched content → search and fetch again, iterating toward accurate and
  detailed information.
- The loop may take long; when initial results exist, give the user a
  reasonable intermediate feedback instead of silent waiting.
- Web is the universal fallback: user questions should always yield some
  information; hedge when confidence is low; guide the user to sharpen the
  question.

Accepted resolution (recorded same day):

- Phase 5 (`fetch-top-pages-for-enumerations`) scope extended to an
  **iterative research loop**: {search views → fetch top-k → gap judge →
  refine query} bounded by rounds ≤ 3, wall clock ≤ ~40 s, quota-watermark
  aware (Phase 1 counters). Ingredients already in the stack: dual web lane,
  tiered page fetcher, gap_judge, query rewriter, supplemental probes,
  SupplementalBudget.
- **Progressive feedback**: stream stage-level findings over the existing SSE
  (stage events + answer chunks); initial answer from round-1 evidence, later
  rounds enrich; budget exhaustion closes with accumulated content. /chat
  rendering lands with the P9/P7 frontend convergence.
- **Presentation policy (C-plus)**: query-class aware — entity/background
  queries present web-accumulated information fully and confidently with
  refinement guidance; structured enumerations (patent/paper lists) keep
  coverage-honest wording (open-web is genuinely weak there; packaging would
  produce hollow answers).
- **Attribution policy**: conditional on the traced cause — genuinely
  ambiguous question (detectable via the Phase 3 type-aware gate) → guide the
  user; data coverage gap → state it; channel outage → state it. Uniform
  "question-unclear" framing is rejected: detectable across turns, false for
  clear questions (G4), and erodes the product's core evidence-trust value.

No phase order changes; Phase 3 proceeds next as planned.

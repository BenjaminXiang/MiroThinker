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

## 2026-08-18 — Amendment: user rules B (confident attributed presentation) for the weak-web-evidence case

User picked **B** for the flagship edge case (专利 enumeration with only a
marketing-page "数百件专利" as web evidence): present it confidently WITH an
attribution marker (据公开报道), keep numbers at source precision, add the
entity's confirmed substance, and guide refinement as a capability offer
("我可以再细化") — never as question-blame, never as external-DB deflection.

Resulting policy (supersedes the C-plus query-class split for the
web-has-signal branch):

- web lane alive with ANY usable signal (incl. indirect/soft evidence) →
  B form (attributed confident presentation + substance + depth offer).
- web lane dead or zero hits → outage/coverage wording (cannot be packaged —
  a dead channel must not masquerade as a world fact).

Two hard lines retained: no fabricated specifics (exact counts/numbers/titles
require direct evidence; source-precise vagueness only) and no
external-database deflection. Implemented in the synthesis prompt as
degradation tier ②b (same day).

## 2026-08-18 — Enumeration answer contract redesigned (user ruling)

User rulings on the token cap and enumeration answers:

- **Token cap**: retained but re-purposed as a rarely-hit safety net (runaway
  loops / cost / wall-clock), raised to a generous value (~6000); it must
  never act as the quality ceiling it became (3000 fighting the 求全 prompt).
- **Enumeration contract**: completeness is the WRONG goal for large-universe
  queries (深圳具身智能公司 = hundreds). New contract: entry budget ≤ 12 by
  evidence-strength then leadership ranking; representative-list + explicit
  coverage statement is the DEFAULT form; exhaustive only for small finite
  universes; domain-leading companies must be included (G7 anchor names).
  The existing enumeration_coverage mechanism already supports this — the
  prompt's 宁多勿漏 directive is replaced by the budgeted-representative rule.

Effects: entry budget bounds answer length → token cap stops being hit →
trailing wire-format segments stop being corrupted (the suspected G7
fallback trigger) — one mechanism addresses four faults. Lands with Phase 5
enumeration scope; the G7-fallback repair principles (log 2026-08-18) remain
the immediate next-session task.

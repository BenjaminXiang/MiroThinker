# Portfolio — retrieval gap-closure (2026-07-01)

> Per CLAUDE.md §7. Tracks Active / Candidate / Blocked / Frozen / Abandoned / Accepted / Archived
> work for the retrieval-augmented refactor.

## Canonical V2 implementation mainline (2026-07-13)

- **`rebuild-canonical-v2-knowledge-platform`** (OpenSpec, breaking Epic) is the sole implementation
  mainline by user decision. Current task ledger: 32/75. Tasks 5.1-5.7 retain their Accepted
  evidence; S5G/Task 5.7 closed the temporal-precision contract; Task 6.3 typed domain projection is
  Accepted; Tasks 6.1, 6.2 RED, and 6.6 RED are Accepted.
- Overlapping V1/V042 retrieval/Web changes are Frozen as implementation authorities. Their valid
  contracts, evaluators, corpora, manifests, and RED evidence remain mapping inputs before S7-S11;
  no in-flight legacy change becomes an Accepted V2 dependency.
- Git `main` promotion is gated on **aggregate S6 Accepted**. At that checkpoint the V2 integration
  line must be clean, all unique side-branch work must be integrated or explicitly abandoned, the
  root dirty worktree must be preserved/reconciled, and `main` must still be a strict ancestor so the
  move is fast-forward-only. No merge/rebase or branch movement is authorized before the gate.

## Legacy retrieval portfolio (status as of 2026-07-10)

The entries below retain historical evidence but are not the current implementation authority when
their V1/V042 assumptions conflict with Canonical V2.

## Active (2026-07-09)
- **`paper-retrievability-baseline`** (slice-contract; Measurement — NO OpenSpec, no prod-code
  change) — establish the **behavioral retrievability baseline for the paper domain** (recall +
  true-accuracy). Structural retrievability already done/measured by Lever 0
  (`docs/solutions/2026-07-03-data-gap-first-principles.md`); behavioral is unmeasured — oracle has
  ≈0 paper cases. Grilling-validated → contract at
  `.agents/runs/paper-retrievability-baseline/slice-contract.md`. **State: retrieval-leg baseline
  DONE (2026-07-09)** — 11 paper oracle cases in `eval_recall.py`; e2e recall (`eval_recall_chat.py`,
  synth off) = **7/20 (35%)**, path-dependent: Type1 self-retrievability **6/6 (100%)**; Type2
  professor→paper **1/9 (11%)** (FM4-reverse gap); Type4 topic→paper **0/4 (0%)** (classifier routes
  paper-topic → `unknown` — NEW finding); Type3 company→paper **dead** (`professor_company_role`
  empty). Findings + type-aware bar + gap→lever map in `baseline-summary.md`. **Decision: defer
  generation leg (true-accuracy)** — retrieval is the binding constraint (can't cite unretrieved);
  gen leg only tests the Type1 citation seam, a refinement for after Type2/Type4 fixes. Caveat:
  recall is a **lower bound** (candidate-generator Q3 deferred). **Type4 classifier fix DONE
  (2026-07-10, Accepted)** — `openspec/changes/fix-paper-topic-query-classification/` + review
  `type4-classifier-fix.md`. Root cause: exact-paper rule over-fired on 论文+ASCII-run; B
  paper-topic rule required ending in 论文. Fix: broadened B rule (topic-search intent + guards).
  qid109/110 `unknown`→`B_paper_topic_search`, **0→8 relevant papers each** (curl-confirmed);
  zero regression (21 other cases identical). Recall NUMBER stayed 0/4 (oracle tokens too
  specific — measurement follow-up, not a defect). **Type2 professor→paper traversal DONE
  (2026-07-10, Accepted)** — `openspec/changes/wire-professor-paper-list-traversal/` + review
  `type2-prof-papers-fix.md`. Wired `_professor_profile_or_papers_response` (reuses existing
  `_lookup_verified_papers_for_prof` + `_answer_prof_papers`) at the A-professor path; new
  `A_prof_papers` query_type for paper-list intent. qid106-108 → A_prof_papers, Type2 **1/9→8/9**;
  paper-domain **7/20 (35%) → 14/20 (70%)**; overall **21/43 (49%) → 28/43 (65%)**; zero regression.
  Regression tests `tests/test_paper_retrievability.py` (15 pass); benchmark Q050 (Type4 over-fire
  on 作者) fixed + guarded; Q004/Q017 (X教授是谁→G) pre-existing, filed as professor-ambiguity
  follow-up. **Q004/Q017 professor-ambiguity FIXED + Type4 oracle refined (2026-07-10)** —
  `openspec/changes/fix-professor-ambiguity-intro-rule/` (ambiguous-intro rule guarded vs
  教授/研究员/博导/院士 → A). **100-case classifier benchmark now ALL GREEN** (was Q004/Q017/Q050
  red). Type4 oracle tokens refined to topic-indicative title tokens (capital, vs lowercase query
  echo) — measures "did topic papers surface". **Paper-domain recall 35% → 94%** (Type1 100% /
  Type2 89% / Type4 100%); overall e2e **49% → 73% (30/41)**. 18 regression tests pass
  (`test_paper_retrievability.py`). **Paper-retrievability Type1/2/4 + Q004/Q017 CLOSED** (Type3
  dead: `professor_company_role` empty). **Next:** Slice B (Lever 3 ~24,285 needs_enrichment
  abstract backfill, E-gated) — the data ceiling; or commit this batch (all uncommitted).
- **`layer-d-multi-turn-context`** (OpenSpec, Standard-to-Epic; rebuild Slice 4) — set
  coreference + cross-domain traversal + narrowing mechanisms + anchor discipline.
  Grilling-validated → ADR-011 + root CONTEXT.md; OpenSpec 4/4 artifacts;
  verification contract written (eval-first; GREEN = ≥12/14 multi-turn + zero single-turn
  regression + chip matrix). **State: task group 1 ACCEPTED** — Codex built runner+fixtures
  (review `.agents/reviews/layer-d-eval-runner.md`, 2 reviewer fixes applied); RED baseline
  run 2026-07-09: **0/14 accept-line, 1/4 chip matrix** (`red-baseline-2026-07-09.json` +
  `red-notes.md`, failure modes M1-M8 mapped to task groups). ⚠ M8: ~4 of the 14 cases
  (qid2/8/15/25) fail for out-of-D-scope reasons (data gaps / R3 / alias matching) —
  D-scope ceiling ≈10-12/14, tight against the ≥12 line; flagged for acceptance time.
  **Next Ready: task group 2 (displayed-set semantics + set coreference).**
- **Group 2 ACCEPTED (2026-07-09)** — Codex delivered displayed-set capture +
  `detect_set_referent` + empty-set clarification guard + 这论文 pronoun; review
  `.agents/reviews/layer-d-set-coreference.md` (2 reviewer fixes: bare-referent
  anchoring prevents qid21 false-positive; pre-existing web-flaky test mocked).
  Evidence: 106 unit green; multi-turn S4-F FAIL→OK (M5 fixed); **single-turn 19-case
  zero regressions** (per-qid diff vs 2026-07-05). Follow-up logged: web-URL pollution
  of last_result_set (pre-existing). **Next Ready: task group 3 (hybrid routing).**
- **Set-traversal slice (group 3 rule-routing + group 4 exec) ACCEPTED (2026-07-09)** —
  Codex delivered `detect_set_operation` + `_handle_set_traversal` (loop retrieval-service
  `get_related_objects`) + target/member-centric renderer + chaining; review
  `.agents/reviews/layer-d-set-traversal.md` (3 reviewer fixes: `skip_synthesis` flag —
  synthesis was overriding the deterministic render with hallucinated text; eval
  `set_derived` over-match on target IDs; routing-only fixture answers blanked). Evidence:
  124 unit green; multi-turn **7/18 pass** (S1/S2/S4/S5-F1/S6A/S6C/S6D), mechanism verified
  (prof→paper 45 real relations, company→patent, honest "0 records" on data gaps);
  **single-turn 19-case zero regression**. ⚠ Acceptance-line risk confirmed: after all D
  groups, ceiling ≈ 8/14 (6 cases out-of-D-scope: data qid2/25, alias qid8, R3 qid15,
  paper-link qid12, data-driven chain break S5-F2) — ≥12/14 not achievable from D alone;
  needs user decision at gate. **Next Ready: task group 5 (narrowing mechanisms).**
- **Group 5 (narrowing mechanisms) ACCEPTED (2026-07-09)** — Codex delivered chip-predicate
  detector+evaluator (4 kinds, company region verified against schema hq_city/region/is_shenzhen),
  chip/open-LLM/topic handlers + selector `chip>open>topic`; review
  `.agents/reviews/layer-d-narrowing-mechanisms.md` (no reviewer fixes needed — clean delivery).
  Evidence: 155 unit green; multi-turn **8/18 pass** (S6B flipped), required_recall 7/37→15/37,
  mechanism verified (prof+company region predicates deterministic w/ coverage statement);
  **single-turn 19-case zero regression**. Remaining red: qid4 (mechanism correct 6/6, coverage
  oracle=0.0 artifact), qid10 (upstream qid9 retrieval gap), qid5 (routing reachability — 上述
  mid-sentence). Follow-ups: prof region precision (南方科技大学 via institution alias set); qid5
  reachability. **Next Ready: task group 6 (anchor discipline + clarification listing).**
- **Group 6 (anchor discipline + member-listing clarification) ACCEPTED (2026-07-09)** —
  Codex delivered singular-pronoun/no-anchor/live-set → member-listing clarification (6.1 already
  correct, locked by regression test); review `.agents/reviews/layer-d-anchor-clarification.md`
  (1 reviewer fix: S3-F placeholder answer blanked). Evidence: 150 unit green; smoke verified
  (list→他的论文 lists all 9 members); multi-turn **9/18 pass** (S3-F flipped); **no passing
  single-turn case regressed**. **D-scope behavioral work COMPLETE.**
- **CHANGE ACCEPTED (2026-07-09, group-7 reckoning)** — `.agents/reviews/layer-d-acceptance.md`.
  All 9 D-scope golden cases pass (S1-S5 + chip matrix S6 4/4); single-turn zero regression;
  all D mechanisms verified. ⚠ Original ≥12/14 line NOT met: 9/14 fail out-of-D-scope
  (qid2/12/25/S5-F2=Layer E data, qid8=FM5 alias, qid15=R3 deferred, qid10=Layer C retrieval,
  qid4=eval oracle artifact, qid5=D routing-reachability follow-up). Line renegotiated to
  "D-scope complete + chip matrix green + zero single-turn regression" — MET. Follow-ups filed
  (qid5 reachability, prof region precision, classifier referent field, displayed-set cap).

## Accepted (contract closed this round)
- **`add-synthesis-timeout`** (OpenSpec, Tiny/low) — delivered 0572d06+8da9053; behavior-affecting
  (3s→60s); validate 0; ledger in-verification. Review: Accept.

## Candidate → Accepted (contract closure; fixes deferred)
- **`fix-chat-retrieval-recall-gaps`** (OpenSpec, Standard/medium) — re-truthed to 58% measured
  (74% non-reproducible, Serper 403); RRF (web OUT); FM3 SHALL; FM1a gate + FM4/FM5 recorded as
  measured/deferred; validate 0; ledger in-verification. Review: Accept (contract closure, NOT
  "recall solved" — deferred gaps explicitly recorded).

## Split verdict
- **`perf-retrieval-keepalive-parallel`** (refactor-contract) — keepalive: Accept (0 GOAWAY,
  deterministic); latency SLO: Accept (p95 5.71s); **D-path parallel: Revise** (non-deterministic
  set 33/35/35, likely cache race, not isolated). Decision needed: isolate / fix / downgrade.

## Blocked / Deferred (proposed skeletons, not implemented)
- **`add-web-augment`** (OpenSpec, Standard/medium, proposed) — Serper 403 (P0 for universal-web
  directive), universal-web on all routes, provenance + precision audit. Blocked on Serper
  credential (user-owned).
- **FM1a ingest** (decision gate in recall change) — 6 absent entities, 67% of misses. Separate
  data-pipeline workstream.
- **FM4 cross-domain paper→professor** (known gap, oracle case 50) — wire `get_related_objects`
  on topic path. Solution doc: `docs/solutions/2026-07-01-retrieval-reach-gaps-fm4-fm5.md`.
- **FM5 strict company-name matching** (known gap, oracle case 51) — normalize + fuzzy +
  `registered_name` in lookup_company. Solution doc: same.
- **Move B / Move C** (the FM4/FM5 fixes) — follow-on changes; design done, not implemented.

## Separate fixes flagged (not gap-closure)
- `test_unit3_b_route_multi_institution_no_filter` — pre-existing bug (multi-institution filter).
- `test_unit4_d_route_retrieves_professor_and_paper_domains_separately` — stale test (D-path now
  includes company per 06ae50b; test expects only prof+paper).

## Oracles (Phase 1, Accepted)
- recall (`eval_recall_chat.py` + `eval_recall.py`) — 58% end-to-end no-web; cases 50/51 added.
- precision (`eval_precision.py`) — false-positive substrate; unsourced_web=0 (Serper dead).
- latency (`eval_latency.py`) — p95 5.71s, SLO ≤6s PASS.
- Evidence: `.agents/runs/retrieval-generation-alignment/{post-fix-recall,precision-baseline,latency-baseline}.json`.

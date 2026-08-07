# Portfolio — retrieval gap-closure (2026-07-01)

> Per CLAUDE.md §7. Tracks Active / Candidate / Blocked / Frozen / Abandoned / Accepted / Archived
> work for the retrieval-augmented refactor.

> **Branch status (2026-08-07):** this branch is the historical retrieval-gap-closure line. The
> Canonical V2 implementation mainline lives in the worktree branch
> `codex/canonical-v2-s11-consolidation` (task ledger 90/92, S12G Candidate, 25-turn regression
> 23/25 as of 2026-08-07 — see that worktree's `.agents/portfolio.md` and
> `openspec/changes/rebuild-canonical-v2-knowledge-platform/`). Entries below are historical status
> snapshots, not current implementation authority.

## Canonical V2 mainline (2026-07-13)

- **`rebuild-canonical-v2-knowledge-platform`** (OpenSpec, behavior-affecting breaking Epic) is the
  sole implementation mainline by user decision. S1 database-target safety is Accepted (5/73 tasks
  complete). S2 read-only source/corpus baseline is the next candidate slice, but remains not Ready
  until its slice contract, checks, stop conditions, and acceptance evidence are written and
  reviewed. Original Postgres and Milvus remain frozen forbidden write targets.
- **`close-retrieval-generation-contract`** and overlapping retrieval/Web implementation changes
  are Frozen and superseded as implementation authorities by Canonical V2. Their contracts,
  evaluators, manifests, RED evidence, and reusable requirements remain evidence inputs for the V2
  refactor; no further production implementation or archive is authorized until their task/evidence
  mapping into V2 is complete and reviewed.

## Legacy retrieval portfolio (status as of 2026-07-10)

The entries below preserve their last independently evidenced state. They are not the current
implementation authority where Canonical V2 supersedes their pre-launch assumptions.

- **`close-retrieval-generation-contract`** (OpenSpec, behavior-affecting Epic) — canonical closure
  contract for paper retrieval → evidence → citation → semantic answer and Postgres-Milvus parity.
  **State: Slice A In Progress, stopped at substrate gate; Slices B-F Specified/blocked.** A added
  the allowlisted ID-grounded evaluator and captured stable read-only DB/Milvus manifests, but the
  current index is non-viable (16,777 expected papers missing, 13,438 unexpected; 36,835 expected
  chunks missing, 17,648 unexpected, 3,012 stale; all 46,035 actual chunks lack a verifiable
  model/chunker/index/write tuple). An explicit sequencing/substrate decision is required before A
  resumes; no production behavior or data/index write occurred. B canonicalizes evidence/claims/outcomes; C closes
  Q004/Q017 + natural Type1 + predicate-aware Type2; D closes Type4 hybrid/paper-level quality; E
  adds provenance-bearing Type3; F adds ledger/lanes/parity. Contract:
  `openspec/changes/close-retrieval-generation-contract/`; execution:
  `.agents/runs/close-retrieval-generation-contract/`. No later slice starts before its predecessor
  is Accepted. Dependency correction: `sigs-official-publications-to-paper-domain` retains its
  unique ingest capability but cannot archive normally until pending Task 5.20 aligns C0 exact-title
  identity partials and D1 removes historical ready-first suppression; `make-partial-papers-retrievable` remains the Accepted
  eligibility behavior dependency.
- **`paper-retrievability-baseline`** (slice-contract; Measurement — NO OpenSpec, no prod-code
  change) — **State: Candidate; not closed.** The stored baseline labeled the paper slice 7/20;
  recounting the same artifact yields 8/20, while the later paper set is 17/18 after the Type4
  expected set changed. The three local repairs remain useful implementation evidence. Their former
  Accepted/CLOSED labels are superseded: `fix-paper-topic-query-classification`,
  `wire-professor-paper-list-traversal`, and `fix-professor-ambiguity-intro-rule` are Candidate.
  The later 30/41 report cannot be compared as recall because the scorer includes query echo and the
  Type4 oracle changed; it also did not prove canonical citation or semantic generation. Current
  closure gaps are Type2 predicate/page completeness, Type4 paper-level Precision@5, Q004/Q017
  normalized entity/endpoint/IDs, canonical evidence/citations, Type3 two-hop provenance, and
  active-only embedding parity. Re-acceptance is governed only by
  `close-retrieval-generation-contract`; historical raw backlog totals are not the active
  enrichment worklist and must be recomputed by Slice F.
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
- **`make-partial-papers-retrievable`** (OpenSpec, behavior dependency) — **Accepted structural
  behavior remains in force:** partial papers are indexable only under the single derived rich-text
  predicate and must remain presentable through the accepted snippet/admission seams. Its historical
  ready-but-not-embedded D3 measurement was never completed and is not parity evidence; that
  disjoint full paper/chunk measurement is superseded by Slice F of
  `close-retrieval-generation-contract`. Archive normally only after its accepted spec deltas are
  migrated canonically; do not mark D3 measured.
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

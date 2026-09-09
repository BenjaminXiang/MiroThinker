# Tasks: fix-round-1-serving-pipeline

> Umbrella Epic. Each phase gets its own child OpenSpec change (created when the
> phase starts) with specs deltas and verification contracts; the checkboxes here
> track phase-level completion only. Narrative and rationale live in the human
> plan `docs/plans/2026-08-17-systematic-fix-round-1.md`.

## Phase 0 — freeze & baseline

- [x] 0.1 Replay harness `apps/admin-console/scripts/replay_fix_round1.py`
       (7 sessions / 13 turns, variance sessions ×3, per-group assertions,
       `--base-url` public-entry support).
- [x] 0.2 Baseline captured: `.agents/runs/fix-round-1-serving-pipeline/baseline-2026-08-17/`
       (G1/G3/G5/G7 stable RED; G2/G4 variance RED with user transcripts as
       admission evidence; G6 PASS → P7 resolved as cookie-carryover product
       contract issue).
- [x] 0.3 P9 discovered & registered (shadow frontend: static /chat streams,
       React SPA syncs).
- [x] 0.4 Human plan frozen (docs/plans) and this Epic created, cross-linked.

## Phase 1 — observability (child change: add-turn-trace-observability)

- [x] 1.1 Structured turn-trace: session snapshot, interpretation inputs/outputs,
       per-lane in/out/filtered counts, gate drop counts, fetch outcomes,
       degradation reason, final answer subject; journal reader tool.
- [x] 1.2 Trace verified by replaying the baseline sessions and reading each
       failure's stage from the trace alone.
- [x] 1.3 Web-lane resilience (verified zero-cache/zero-retry/silent-swallow
       2026-08-17): single retry with backoff per provider (idempotent search),
       web-result cache keyed by view+day (port the legacy V017
       web_search_cache pattern), per-provider health circuit-breaker with
       preference bias + probe recovery, quota-watermark counters. Acceptance:
       fault-injection (kill one provider key) shows retry/cache engaging and
       the lane serving from the surviving channel or cache, all visible in
       the trace.

## Phase 2 — never-refuse contracts (child change: enforce-never-refuse-contracts)

- [x] 2.1 Fallback/synthesis wording contracts: answer from confirmed evidence,
       name gaps explicitly, ban deflection (国知局/PatSnap/Incopat pattern),
       mandatory enumeration coverage statement.
- [x] 2.2 Lane-failure semantic correction: "no results" vs "lane unavailable"
       are distinct answer states — a web-lane failure MUST be reported as
       网络检索暂不可用 (with cached/prior/local evidence when available) and
       MUST NEVER be phrased as a negative factual claim about the world
       (the G2 failure mode: channel outage phrased as 未找到该机构). RED case:
       fault-injected empty web lane over a web-only subject.
- [x] 2.2 RED cases from verbatim transcripts (P2/P4/P5 wordings) → GREEN.

## Phase 3 — deterministic subject layer v2 (child change: harden-deterministic-subject-layer)

- [x] 3.1 Echo-guard relaxation (bare entity-name query = subject).
- [x] 3.2 Type-aware clarification gate + synthesis-side referent type check.
- [x] 3.3 Expansion base = session subject; no silent base substitution.
- [x] 3.4 News-headline guards on anchor names.
- [x] 3.5 Session-reset semantics verification (P7 product decision recorded).
- [x] 3.6 Merge accepted → release/customer-test → hot update R1; replay suite green run.

## Phase 4 — data line (child change: full-column-serving-pack-rebuild)

- [ ] 4.1 Restore source switch: full-column legacy Postgres extraction; evidence
       completeness as annotation; hash/parity envelope retained.
- [ ] 4.2 Company↔patent relation materialization from applicant names.
- [ ] 4.3 Resumable batch embedding (school endpoint default; hosted fallback).
- [ ] 4.4 Reconciliation report as build artifact (counts, facet non-empty rates,
       four-path reach spot checks).
- [ ] 4.5 Dual-pack A/B on a local port + golden smoke → serving-pack v2 switch
       (rsync; old pack retained for rollback).

## Phase 5 — evidence acquisition (child change: fetch-top-pages-for-enumerations)

- [x] 5.1 Top-2 result-page body fetch for enumeration/deep queries with
       anti-echo, parallel lanes, hard timeout, degrade-to-current.
- [ ] 5.2 G7 stability line (3/3 flagship) green; merge → hot update R2.

## Phase 6 — interpretation layer (child change: contextual-query-interpretation)

- [x] 6.1 Dialogue ring buffer (≤5 turns) in session state.
- [x] 6.2 Typed interpreter (subject/aspect/op) + five validators + kill switch;
       fallback = Phase 3 layer.
- [x] 6.3 GO/NO-GO gate evaluation (multi-turn ≥ Phase 3 baseline, single-turn
       zero regression, p95 delta ≤ 1.5s). No-go ships behind flag.

## Phase 7 — fusion floor, disclosure, frontend convergence (child change: fusion-recall-floor-and-disclosure)

- [ ] 7.1 Subject-gate recall floor; dual-source weighting.
- [ ] 7.2 查看检索过程 v2: "系统理解为：关于X" + evidence list.
- [ ] 7.3 P9 convergence: static streaming page declared the reference; React
       sync path upgraded or deprecated.

## Phase 8 — round acceptance

- [ ] 8.1 Full replay suite + golden set + latency against new code + pack v2.
- [ ] 8.2 User hands-on retest of the original seven sessions.
- [ ] 8.3 Merge R3; deliver pack v2; retrospective docs; Epic Accepted.

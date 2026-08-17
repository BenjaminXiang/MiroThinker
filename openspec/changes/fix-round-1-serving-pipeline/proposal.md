# Proposal: fix-round-1-serving-pipeline

> Umbrella Epic for systematic fix round 1 (frozen 2026-08-17).
> Human-facing plan (authoritative narrative, Chinese):
> `docs/plans/2026-08-17-systematic-fix-round-1.md` — cross-linked per AGENTS.md §15.0.
> Behavior-affecting: YES. Capabilities touched: `canonical-v2-chat` (primary),
  data-supply/release (via child changes).

## Why

The user's acceptance test (2026-08-17, seven sessions, verbatim in
`.agents/runs/2026-08-17-user-testing-round-1/`) surfaced nine defects (P1–P9)
across three cause layers — turn understanding (P1/P3/P4/P6, P7 product contract),
data coverage (P5/P8, audited in `.agents/runs/2026-08-17-serving-pack-coverage-audit.md`),
and degradation wording (P2/P4/P5) — amplified by zero observability, a
subject-gate that can filter the web lane to zero, and a shadow frontend (P9:
the served /chat is a static page on /api/chat/stream while the React SPA in
source uses sync /api/chat). A replay baseline (G1/G3/G5/G7 stable RED;
G2/G4 variance RED; G6 PASS resolving P7) is captured under
`.agents/runs/fix-round-1-serving-pipeline/baseline-2026-08-17/` with the
harness `apps/admin-console/scripts/replay_fix_round1.py`.

## What Changes

Ten phases on two parallel lines (full detail and rationale in the human plan):

- Phase 1 `add-turn-trace-observability` — structured per-turn trace (session
  snapshot, lane counts, gate drops, anchor decisions, degradation reason) +
  journal reader tool. Unblocks attribution for every later phase.
- Phase 2 `enforce-never-refuse-contracts` — fallback wording: answer from
  confirmed evidence, name gaps, ban deflection to external databases,
  mandatory enumeration coverage statements. RED cases from verbatim transcripts.
- Phase 3 `harden-deterministic-subject-layer` — echo-guard relaxation (P3),
  type-aware clarification gate + synthesis-side referent type check (P4),
  expansion base = session subject (P6), news-headline guards on anchor names
  (P1/P4), session-reset semantics verification (P7). Doubles as the fallback
  layer for Phase 6. Merged → hot update R1.
- Phase 4 `full-column-serving-pack-rebuild` (data line, parallel) — restore
  source switches to full-column legacy Postgres (~45k content-bearing objects,
  evidence completeness becomes annotation not admission), company↔patent
  relation materialization from applicant names (P5), resumable batch embedding,
  reconciliation report as a build artifact, dual-pack A/B + golden smoke before
  switching. Delivers serving-pack v2 via rsync (not git).
- Phase 5 `fetch-top-pages-for-enumerations` — fetch top-2 result-page bodies
  into evidence for enumeration/deep queries (existing tiered fetcher, anti-echo
  guard, parallel with local lanes, hard timeout + degrade). Hot update R2.
- Phase 6 `contextual-query-interpretation` — LLM proposer (typed subject/aspect/
  operation decision from query + ≤5 dialogue turns + session subjects) with five
  deterministic validators and kill switch; falls back to the Phase 3 layer.
  GO/NO-GO gate: multi-turn eval ≥ Phase 3 baseline, single-turn zero regression,
  p95 delta ≤ 1.5s; failing stays behind the flag.
- Phase 7 `fusion-recall-floor-and-disclosure` + P9 frontend convergence —
  subject-gate recall floor (never filter to zero), dual-source weighting;
  "查看检索过程" v2 shows "系统理解为：关于X" + evidence; converge the shadow
  frontend (static streaming page is the reference; React sync path upgraded or
  declared deprecated).
- Phase 8 `round-acceptance` — full replay suite + golden set + latency; user
  hands-on retest; merge → R3; data pack v2 delivery; retrospective.

## Non-goals

- Source-side recollection (66k paper shells, professor field completion,
  professor↔patent R17 wiring) — separate long-running track, not this round.
- No A–G semantics redesign beyond what the phases contract; no schema breaks
  on the serving-pack envelope (hash/parity discipline retained).

## Impact

- Code: `apps/admin-console/backend/**` (chat adapter, static chat page),
  `apps/miroflow-agent/src/data_agents/canonical_v2/**`, frontend convergence.
- Data: new serving pack build from legacy Postgres; embedding batches.
- Deliverables: hot updates R1–R3 on `release/customer-test`; serving-pack v2;
  replay suite as pre-hot-update regression gate; this Epic + child changes
  Accepted.

## Acceptance (round exit)

1. Seven-session replay all PASS including repetition-stability lines
   (G2/G4 variance cases supplemented by user confirmation);
2. Golden head-turn set zero regression;
3. Serving-pack v2 reconciliation report passing (domain counts, facet
   non-empty rates, four-path reach spot checks);
4. Both documentation systems consistent and Accepted; R3 merged; pack delivered.

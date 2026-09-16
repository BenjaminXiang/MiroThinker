# Tasks: fix-followup-domain-carryover

- [x] 1. `QueryPlanningRequest.prior_turn_query` optional field (contract-safe
       default; mirrors the soft_context_subject precedent).
- [x] 2. Chat layer passes the prior turn's raw query (turn >= 2, distinct).
- [x] 3. Planner inherits prior-turn inferred domains when the follow-up has
       no domain signal of its own (all-domain fallback).
- [x] 4. Unit tests 4/4; live G11 3-turn session: T2 now a synthesized
       taxonomy answer (was professor-noise candidate dump).

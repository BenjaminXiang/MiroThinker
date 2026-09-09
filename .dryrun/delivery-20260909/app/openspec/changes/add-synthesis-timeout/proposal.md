# Proposal: add-synthesis-timeout

## Why

The answer-synthesis step previously timed out at 3s, mis-killing answers that take 4–59s
(DeepSeek synthesis ~8–9s typical, per the perf commit `c4fa382`). The default was raised to 60s
with an env override (`CHAT_SYNTHESIS_TIMEOUT`) in commit `0572d06` (+ test `8da9053`). This is a
user-visible behavior change: answers that previously failed (timed out) now succeed. Per §8 that
makes it behavior-affecting (OpenSpec), not a behavior-preserving refactor — so it gets its own
small change rather than living under the recall change.

## What Changes

1. Default synthesis timeout 3s → 60s, overridable via `CHAT_SYNTHESIS_TIMEOUT` env (seconds, float).
2. No streaming, no retry — only the timeout knob.

## Capabilities
### Modified Capabilities
- `agentic-rag-retrieval` — synthesis timeout behavior (legacy baseline: `docs/Agentic-RAG-PRD.md`).

## Impact
- `apps/admin-console/backend/api/chat.py:70` (default constant) + `:1180` (use site).
- No schema/API-shape change; only which answers succeed vs time out.

## Status
Delivered in commits `0572d06` + `8da9053`. This change contracts it (behavior-affecting, small).

# Proposal: fusion-recall-floor-and-disclosure

> Phase 7 of Epic `fix-round-1-serving-pipeline` (opened 2026-08-19).
> Behavior-affecting: YES. Capability: `canonical-v2-chat`.

## Why

P9 governance gap (two coexisting frontends) and user-facing transparency
(the system never shows what it understood the query to be about).

## What Changes

1. **Subject-gate recall floor (7.1)**: the web subject-consistency gate's
   backfill floor already guarantees non-empty lanes; add dual-source
   weighting so local canonical evidence is preferred over web evidence at
   equal relevance (local-first tiebreaker in `_normalize_and_order_results`).
2. **Understanding disclosure (7.2)**: the SSE `answer` event carries
   `understood_subject` (from the trace's answer_subject); the chat UI
   renders「系统理解为：关于X」above the answer text when a subject is present.
3. **P9 frontend convergence (7.3)**: the static streaming page is the
   declared reference; the React SPA gets a deprecation notice pointing to
   /chat. Deployment docs updated.

## Impact

- `chat.html` — disclosure rendering
- `canonical_v2_chat.py` — understood_subject in answer payload
- `frontend/src/` — deprecation banner

# Proposal: add-web-augment

## Why

Web-search augmentation was the recall lever that the commit `1fb6449` claim (53→74%) relied on.
It is currently **broken**: Serper returns `403 Unauthorized` (dead/missing credential), so web
contributes 0 to the measured 58% recall. Beyond being broken, web-augment is also a precision
and provenance risk (CLAUDE.md §5): web-rescued entities are unverified for correctness and
must carry auditable source URLs. This change splits web-augment out of the recall change so
the recall contract is not held hostage to a dead credential, and gives web-augment its own
behavior + provenance + precision contract.

## What Changes (proposed — NOT implemented this round; skeleton)

1. **Serper 403 fix** — restore a valid Serper credential (runtime/config; owner: user). Recorded
   as the first blocker.
2. **Web-augment behavior contract** — when web-search augments recall (out-of-DB / broad-profile
   entities), how web Evidence is typed (`object_type=web`), and how it dedups/fuses with DB
   results.
3. **Provenance obligation** — every web-rescued candidate SHALL carry an auditable `source_url`;
   unsourced web candidates are a §5 violation.
4. **Precision audit** — once Serper is fixed, re-run the precision oracle to label web-rescued
   entities for correctness (false positives from web are a 准 risk).

Non-goals: ingest of the 6 absent entities (separate `fm1a-ingest-decision` workstream — web can
rescue some, but ingest is the durable fix); streaming/cache; generation rewrite.

## Capabilities
### Modified Capabilities
- `agentic-rag-retrieval` — web-search augmentation behavior + provenance (baseline:
  `docs/Agentic-RAG-PRD.md`; the recall change `fix-chat-retrieval-recall-gaps` removed web from
  its scope, this change owns it).

## Impact
- `apps/miroflow-agent/src/data_agents/service/retrieval.py` (`_augment_with_web` line 451) +
  Serper credential config.
- No schema change; adds a behavior contract + provenance rule to an already-shipped (but
  currently-broken) code path.

## Status
Proposed (skeleton). Implementation deferred — blocked on the Serper credential (user-owned).
This round only records the defect + the contract obligations so the recall change can close
without it.

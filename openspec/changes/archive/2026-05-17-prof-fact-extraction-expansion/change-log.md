# Change Log: prof-fact-extraction-expansion

## 2026-05-14 — Child scaffolded

- Created the child OpenSpec artifact set from the
  `prof-admin-workbench` parent.
- Sequenced this child after `prof-quality-status-rework` and before
  `prof-admin-workbench-ui` so the workbench can consume improved
  canonical facts.
- Added explicit preflight and child-spec review gates.

## 2026-05-14 — Fact idempotency clarified

- Pinned duplicate detection to the active-fact key
  `professor_id + fact_type + normalized_fact_key`.
- Confirmed `source_page_id` and `evidence_span` are provenance, not
  duplicate-key dimensions.

## 2026-05-15 — Implementation and verification

- Added `src/data_agents/professor/fact_extraction.py` with preflight,
  structured LLM response parsing, injected-client extraction,
  normalized-key fact persistence, failure-isolated runner logic, and
  Child 1 re-evaluation wiring.
- Added `scripts/run_professor_fact_backfill.py` for preflight and
  backfill execution.
- Reused the professor LLM profile resolver and pinned the OpenAI
  client to `httpx.Client(trust_env=False)` after a dry-run exposed
  ambient SOCKS proxy inheritance.
- Calibrated real-data verification to the current user instruction:
  record code-path evidence and preflight counts without deep-diving
  database quantities. A wet real sample remains blocked by the local
  configured LLM profile returning `401 Unauthorized`.

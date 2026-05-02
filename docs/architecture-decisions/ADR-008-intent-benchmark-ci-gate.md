---
id: ADR-008
title: Intent benchmark CI gate
status: proposed
date: 2026-05-02
owner: codex-ops
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
---

# ADR-008: Intent Benchmark CI Gate

## Context

The Agentic RAG classifier has a 100-case benchmark covering intent classes
A-G. Wave 13 V3 reran the LLM-backed benchmark locally against the internal
Gemma-4 profile and archived the result at:

- `docs/source_backfills/intent-classifier-benchmark-2026-05-02.log`

The 2026-05-02 run failed the validation gate:

| Metric | Result | Gate |
|---|---:|---:|
| Overall accuracy | 0.000 | >= 0.900 |
| A | 0.000 | >= 0.700 |
| B | 0.000 | >= 0.700 |
| C | 0.000 | >= 0.800 |
| D | 0.000 | >= 0.700 |
| E | 0.000 | >= 0.700 |
| F | 0.000 | >= 0.700 |
| G | 0.000 | >= 0.700 |

All 100 cases returned `UNKNOWN`. This is below the handoff stop condition
(`overall < 0.80`) and should be escalated to the W11-1 / classifier owner
before any gate is made blocking.

## Options

| Option | Benefits | Costs / Risks |
|---|---|---|
| A. systemd user timer, daily 02:00 | Runs inside the network that can reach Gemma-4; avoids public-to-internal networking; matches existing local dogfood timer pattern. | Requires one maintained internal machine; results land locally unless a notification/export step is added. |
| B. GitHub Action workflow | PR-coupled and naturally visible to reviewers; can block merges once stable. | Needs a self-hosted runner or secure internal model access; higher maintenance and secret/networking risk. |
| C. Manual-only | No new infrastructure. | High drift risk; classifier prompt or routing changes can regress silently. |

## Recommendation

Prefer option A, a systemd user timer with failure notification, after the
classifier path is healthy enough to pass the benchmark. Keep option B as a
future upgrade if a self-hosted runner already exists for internal model tests.
Do not accept option C as the long-term state.

## Decision Notes

- The timer must use the same local Gemma-4 configuration path:
  `resolve_professor_llm_settings("gemma4", include_profile=True)`.
- The timer must unset `https_proxy` and `HTTPS_PROXY` before running.
- The gate should start as reporting-only until two consecutive healthy runs
  meet `overall >= 0.90`, every class >= 0.70, and class C >= 0.80.
- Token cost was not emitted by the current pytest benchmark output; capturing
  token usage requires a follow-up change to the benchmark harness or
  classifier wrapper.

## Follow-up

1. Investigate why the 2026-05-02 run returned `UNKNOWN` for all cases.
2. Rerun V3 after the classifier LLM path is fixed.
3. Once stable, create a separate implementation spec for the systemd service,
   timer, log archive, and failure notification.

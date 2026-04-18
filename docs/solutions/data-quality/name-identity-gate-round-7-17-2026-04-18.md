---
title: Round 7.17 — canonical_name_en pollution & the LLM name-identity gate
date: 2026-04-18
module: professor
problem_type: data_quality
component: canonical_writer
tags: [name-mismatch, llm-gate, precision-first, gemma, homepage_crawler]
---

# Round 7.17 — name-identity gate

## Problem

Live `/browse` dashboard revealed `canonical_name` ↔ `canonical_name_en` mismatches in `miroflow_real.professor`. Sampling 30 of 557 non-empty rows:

| canonical_name | canonical_name_en | class |
|---|---|---|
| 张成萍 | Thomas Hardy | unrelated person |
| 舒阳 | Chunbo Li | co-author contamination |
| 曹磊峰 | Xiaoyang Guo | unrelated person |
| 张春香 | Laser Technol | journal abbreviation |
| 廖庆敏 | Senior Member | IEEE grade label |
| 苏阳 | Area Graphene | research area fragment |

Full scan result: **230 of 557 (41%) polluted** across all institutions. 深圳技术大学 was worst at 66 of 114 (58%).

## Root cause

`homepage_crawler._select_best_english_name_candidate` picks the most prominent English token sequence on the profile page. No verification that the tokens are the professor's English name. Polluted values typically come from:
- Other people's names in the bio (co-authors, advisors, cited researchers)
- Journal/publisher captions (`Laser Technol`, `Area Graphene`)
- Role labels (`Senior Member`, IEEE badges)
- Cited historical figures (Thomas Hardy appearing in a bio quote)

## Solution

Two-part LLM-based mitigation, added in Round 7.17:

1. **Write-time gate** in `src/data_agents/professor/name_identity_gate.py`.
   - Sync callable: `verify_name_identity(NameIdentityCandidate, llm_client, llm_model) -> NameIdentityDecision`.
   - Precision-first: `confidence < 0.8` → reject. Parse error → reject. LLM exception → reject.
   - Wired into `canonical_writer._upsert_professor_row`. Independent feature flag `name_identity_gate_enabled` separate from paper-gate flag (different blast radius).
   - Stays sync because the writer path is sync psycopg.

2. **Post-hoc scan** in `scripts/run_name_identity_scan.py`.
   - Reads all `professor.canonical_name_en IS NOT NULL` rows, calls gate, writes `pipeline_issue` rows for rejections.
   - Stable description template (no confidence/timestamp in text) to avoid duplicate rows against the partial unique index `uq_pipeline_issue_open`.
   - `--auto-clear-threshold` optional (off by default). Human review via `/browse` is authoritative.

## Learnings

### Rule vs LLM, revisited
A `pypinyin` heuristic covers "does candidate look like valid romanization?" but says nothing about "is this the right person?" The dominant failure mode here is well-formed English names that belong to someone else. LLM is the right tool for identity, not for romanization validity.

### Feature-flag separation
The plan reviewer flagged coupling to `identity_gate_enabled` as a footgun: a miscalibrated name-gate prompt would silently null out `canonical_name_en` across the whole professor table with no rollback. Split the flag. Operators can kill name-gate alone without losing paper-gate protection.

### Description hash footgun
`pipeline_issue` has a partial unique index where `description_hash = md5(description)`. If the scan's description embeds confidence (e.g. "rejected with conf=0.74") or a timestamp, every rerun creates a duplicate row. Fix: stable description template, variable data only in `evidence_snapshot` jsonb.

### Codex dev deviation pattern
Codex initially hardcoded `api_key=os.environ.get("GEMMA_API_KEY", "EMPTY")` in the scan script. The project has a shared resolver `llm_profiles.resolve_professor_llm_settings("gemma4")` that reads `.sglang_api_key` from the repo root and supports env overrides. Patched post-delivery. For future dispatches, brief Codex explicitly on the shared resolver path when external LLM calls are needed — it defaults to the openai-key pattern otherwise.

### Async/sync contract
`paper_identity_gate.batch_verify_paper_identity` is `async def` (runs in async paper_collector loop). `name_identity_gate` had to stay **sync** because `_upsert_professor_row` uses sync psycopg. Mixing an async callable into a sync transaction would need `asyncio.run()` inside a sync function inside an async caller — a deadlock waiting to happen. Wiring explicitly rejects async callables via `inspect.iscoroutinefunction`.

## References
- Plan: `docs/plans/2026-04-18-007-name-identity-gate.md`
- Reference pattern: `apps/miroflow-agent/src/data_agents/professor/paper_identity_gate.py` (Round 7.6)
- Migration driving pipeline_issue: `apps/admin-console/alembic/versions/V006_init_pipeline_issue.py`
- Dashboard: `apps/admin-console/backend/static/browse.html` review tab

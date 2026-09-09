# Sweep slice w12-4-m2-1-selector-expansion — ESCALATED

**Sweep slice outcome:** escalated (per spec §10.3 file-collision boundary)
**Date:** 2026-05-08
**Spec read:** `.agents/specs/2026-05-02-w12-4-m2-1-selector-expansion.md`

## Reported case

W9-5 dogfood: M2.1 `homepage_publications` selector detects publications
sections in 10 professor pages but extracts 0 papers from any. Spec proposes
adding 4 Shenzhen-CMS archetypes (清华 SIGS / 深圳理工 / 中大深圳 / 深圳技术)
to `homepage_publications.py` via a `_SHENZHEN_CMS_ARCHETYPES` dispatcher.

## Why escalated, not implemented

`apps/miroflow-agent/src/data_agents/professor/homepage_publications.py`
currently has **421 lines of unstaged drift in the working tree** (394 insertions
+ 27 deletions). Grep against the drift for Shenzhen / institutional markers:

```bash
git diff apps/miroflow-agent/src/data_agents/professor/homepage_publications.py \
  | grep -iE "shenzhen|tsinghua|sysu|sztu|sit-shen|清华|深圳|中大|archetype|_matches_"
```

→ **zero matches**. The drift is unrelated active refactor (most likely
extraction-strategy improvements based on the function naming pattern in the
file). It is NOT a W12-4 partial implementation.

If I add `_SHENZHEN_CMS_ARCHETYPES = [...]` and 4 new matcher/extractor
functions now, those changes interleave with the 421-line in-flight refactor
inside the same file. When that refactor commits, my W12-4 work is entangled
with it — the same boundary failure that forced the AGENTS.md/CLAUDE.md commit
amend earlier today.

Per `pattern-repair` skill §2 hard rule: **"If implementation reveals a bigger
boundary, stop and re-plan."** Per spec §10.3: **"Each sweep slice ≤ 1 day of
effort. Larger → escalate to a separate `.agents/specs/` plan."**

## Sibling search findings

- Lane 3 (per-domain paper):
  - `homepage_publications.py` — 421 lines drift, NO W12-4 markers
  - `homepage_publication_headings.py` — 1 added line (`代表性论文` keyword), unrelated to archetype work
  - `tests/data_agents/professor/test_homepage_publications.py` — drift present, scope unclear
  - HTML samples at spec-required path `logs/data_agents/paper/homepage_ingest_runs/2026-04-30/` — **DO NOT EXIST**
- Lane 4 (docs/migrations):
  - `docs/Paper-Data-Agent-PRD.md` — drift present in working tree
  - `docs/index.md` — Paper PRD row still 🟡 with "homepage selector 覆盖不足" pending (C2 stale-doc check: doc accurately reflects current state)

## What this slice actually needs to proceed safely

A new `.agents/specs/` document escalating the work in two stages:

1. **Stage A — coordinate / unblock**: drift owner commits or stashes the
   existing 421-line refactor. Working tree on `homepage_publications.py`
   becomes clean.
2. **Stage B — implement W12-4 fresh**: new pattern-repair invocation with
   clean file state. HTML samples regenerated via dry-run (requires
   `DATABASE_URL` + Postgres). Then add 4 Shenzhen archetypes.

These cannot run in parallel.

## Recommended next action

Suggested escalation spec slug:
`.agents/specs/2026-05-08-w12-4-impl-escalated.md`

Skeleton:
```md
---
status: blocked-on-drift
blockers:
  - `apps/miroflow-agent/src/data_agents/professor/homepage_publications.py`
    has 421-line unstaged refactor as of 2026-05-08
related_review: .agents/reviews/2026-05-08-sweep-w12-4-escalated.md
---

# W12-4 implementation (escalated from sweep)

## Stage A: drift coordination
... commit / stash plan ...

## Stage B: implement W12-4 per `.agents/specs/2026-05-02-w12-4-m2-1-selector-expansion.md`
... after Stage A clean working tree ...
```

I am NOT writing this escalation spec automatically because Stage A requires
human judgment about the drift's commit-readiness.

## Defect class (final)

- L1 (single dispatcher missing 4 archetypes) + C1 (test matrix gap)
- Compounded by **operational hazard**: in-flight unrelated drift on the same file

## Files touched by this slice

None. No code changes. Only this review report.

## Verification commands not run

- `pytest tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py` — N/A, test file does not exist; would need to be created in Stage B
- `scripts/run_homepage_paper_ingest.py --dry-run --limit 10` — not run; would need DATABASE_URL + Postgres

## Self-review

- Scope control: ✅ stopped at boundary; did not write code into a drifting file
- Invariants preserved: ✅ no V001–V018, no public APIs, no evidence shape touched
- Patch-only risk: N/A — no patch made
- Rollback / checkpoint: nothing to roll back; this is a status-only slice

## Skip-but-note epilogue

Sibling risk: 421 lines of unrelated drift on `homepage_publications.py` and
related files in `apps/miroflow-agent/src/data_agents/professor/` — origin and
intent unknown to this session. Triage classified as `active` W13-wave work,
but no commit links it to a specific spec. Worth surfacing to the drift's
author before the next pattern-repair pass.

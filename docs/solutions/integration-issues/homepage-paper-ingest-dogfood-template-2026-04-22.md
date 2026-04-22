---
title: Homepage paper ingest — dogfood acceptance log (TEMPLATE)
date: 2026-04-22
category: docs/solutions/integration-issues
module: apps/miroflow-agent/data_agents/paper
problem_type: integration_issue
component: development_workflow
severity: medium
applies_when:
  - First real-DB run of the homepage-authoritative paper ingest pipeline
  - Validating M2.4 Phase B before declaring the milestone complete
tags: [m2.4, homepage-paper-ingest, dogfood, acceptance-log, template]
status: template-pending-execution
---

# Homepage paper ingest — dogfood acceptance log (TEMPLATE)

This file is the Unit 8 deliverable of M2.4. It's a **template** for the operator to fill in after running the pipeline against the real dev DB. Until those entries are populated, M2.4's acceptance gate (R3: 10 profs × ≥15 papers linked each) is NOT confirmed.

When filled in:
1. Rename this file to `homepage-paper-ingest-dogfood-YYYY-MM-DD.md` with the actual run date.
2. Flip `status: template-pending-execution` to `status: complete` in the frontmatter.
3. Commit.

---

## Pre-flight

Before running, confirm the environment:

```bash
# 1. V011 migration applied
cd apps/miroflow-agent
DATABASE_URL=<dsn> uv run alembic current
# → expect: V011 (head)

# If not at V011 yet:
DATABASE_URL=<dsn> uv run alembic upgrade V011

# 2. Phase A integration tests all pass against this DB
DATABASE_URL_TEST=<dsn> uv run pytest \
  tests/storage/test_v011_migration.py \
  tests/storage/test_paper_full_text_writer.py \
  tests/storage/test_title_resolution_cache.py \
  tests/storage/test_professor_orcid_writer.py \
  -n0 --no-cov
# → expect: 33 passed

# 3. Serper API key available (falls through to arxiv-only if missing)
echo $SERPER_API_KEY | head -c 8
```

---

## Step 1 — Dry-run on 10 profs (no writes)

```bash
DATABASE_URL=<dsn> python scripts/run_homepage_paper_ingest.py \
  --dry-run \
  --limit 10
```

**Record below:**

```
Run started at:   YYYY-MM-DD HH:MM:SS
Run duration:     [seconds]
DATABASE_URL:     [redacted host]
Profs processed:  [N]
Profs skipped:    [N]
Total papers linked (WOULD-BE):   [N]
Full-text fetched (WOULD-BE):     [N]
Pipeline issues filed (WOULD-BE): [N]
```

**Per-prof breakdown** (paste the JSONL summary from stdout):

```
(paste per-prof lines)
```

**Observations:**
- Any profs that returned 0 publications but had a homepage URL? → likely JavaScript-rendered page; flag for M2.2/M2.3 follow-up.
- Resolution hit rate across sources: OpenAlex X% / arxiv X% / Serper X% / unresolved X%.
- Average papers/prof: __.

---

## Step 2 — Wet-run on 5 profs (real writes)

Pick 5 profs that had good dry-run results (high paper count, clean resolution).

```bash
DATABASE_URL=<dsn> python scripts/run_homepage_paper_ingest.py \
  --limit 5
```

**Record before & after counts:**

```sql
-- Before run
SELECT count(*) FROM professor_paper_link WHERE evidence_source_type='personal_homepage';
-- → N_before = [N]

-- After run
SELECT count(*) FROM professor_paper_link WHERE evidence_source_type='personal_homepage';
-- → N_after = [N]

-- Full-text coverage
SELECT count(*), source FROM paper_full_text GROUP BY source;
-- → [paste]

-- Title cache
SELECT count(*), match_source FROM paper_title_resolution_cache GROUP BY match_source;
-- → [paste]

-- Pipeline issues filed
SELECT issue_type, count(*) FROM pipeline_issue WHERE run_id = '<this-run-id>' GROUP BY issue_type;
-- → [paste]
```

**Record:**

```
N_after - N_before = [delta]
Expected delta (from Step 1 JSONL): [expected]
Difference: [should be zero or near-zero]
```

---

## Step 3 — Acceptance check

**Gate R3** (from plan): 10 profs with real homepages average ≥ 15 papers linked each.

```
Papers linked across 5 wet-run profs: [N]
Average papers/prof: [N/5]
```

- If average ≥ 15: **R3 MET**. Document this and proceed with broader run.
- If average < 15: **R3 NOT MET**. File TODOs for M2.2 title-resolution tuning and M2.1 format-archetype gaps. Do NOT broaden to all 783 profs until gap analysis complete.

---

## Step 4 — Gap analysis (if R3 not met)

For each prof with < 15 papers linked, classify:

| Prof ID | Papers on Homepage | Papers Linked | Gap Cause |
|---------|---------------------|---------------|-----------|
| | | | OpenAlex miss / arxiv miss / homepage parse gap / network error / other |

Document the dominant gap cause. Common ones observed historically:
- **Homepage parse gap**: M2.1 missed an archetype not in the 5 synthetic fixtures. Add a real-HTML fixture and tune extractor.
- **OpenAlex title miss**: normalize title more aggressively (strip subtitles?) or lower Jaccard threshold experimentally.
- **arxiv has it but OpenAlex doesn't + no DOI on homepage**: this is a known limitation; cascade works but Serper needs to hit too. Check `SERPER_API_KEY`.
- **Non-English title (CJK)**: deferred per M2.2 scope boundaries; follow-up planned for post-M4.

---

## Step 5 — Broader run (only after R3 met)

Once the 5-prof wet-run meets R3:

```bash
# Full overnight run against all ~800 profs
DATABASE_URL=<dsn> python scripts/run_homepage_paper_ingest.py \
  --resume logs/data_agents/paper/homepage_ingest_runs/<latest>.jsonl
```

**Record broader run stats:**

```
Total profs in scope:       [N]
Profs processed:            [N]
Profs skipped (resume):     [N]
Profs crashed:              [N]
Total new links:            [delta]
Total full-text fetched:    [N]
Total pipeline issues:      [N]
Run duration (hours):       [N.N]
```

---

## Step 6 — Learnings

After the broader run, capture any new insights:

**New failure modes observed:**
- [list]

**Performance observations:**
- arxiv rate limit backlash? Per-host gate sufficient? Any sustained 429s?
- pdfminer parse failures on specific publisher PDFs? Which publishers?
- Serper quota burn rate?

**Follow-ups worth opening:**
- [ ] TODO: ...
- [ ] TODO: ...

Once this file is populated, change frontmatter `status: template-pending-execution` to `status: complete` and commit.

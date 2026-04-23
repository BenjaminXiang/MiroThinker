---
title: "M1 follow-up: professor ORCID backfill from OpenAlex"
type: feat
status: active
date: 2026-04-23
milestone: M1 continuation (ORCID shortcut needs data to be useful)
depends_on:
  - 80acd19  # M2.4 Phase A — professor_orcid table + writer
  - 53793b4  # M1 — identity gate v2 ORCID shortcut wired
---

# M1 follow-up — Professor ORCID backfill

## Overview

M1's identity gate v2 ORCID shortcut reads `professor_orcid` rows. The table exists (V011) and the writer exists (`upsert_professor_orcid`), but nothing populates the table. This small CLI fills the gap.

For each professor in `professor` table, query OpenAlex `/authors` with `search={name} & affiliations.institution.display_name.search={institution}`, filter to the exact-name + institution-match candidate, extract `orcid` field from the response, write via `upsert_professor_orcid`.

Scope deliberately tight: ~150 lines, single script, idempotent, never raises per-prof.

## Requirements

- R1: CLI `scripts/run_professor_orcid_backfill.py` iterates profs
- R2: `--limit`, `--institution`, `--prof-id`, `--dry-run`, `--resume`, `--log-level`
- R3: OpenAlex author lookup with rate gate (10/s, reuse existing pattern)
- R4: Only upsert when OpenAlex returns non-null `orcid`
- R5: `confidence=0.9` when OpenAlex match (name + institution both verified), `0.7` when only name matches
- R6: `source="openalex"` in DB row
- R7: Never raise on per-prof failure; log + continue
- R8: Reuse existing `local_api_key` if any endpoint needs it (OpenAlex is public, no key needed)

## Implementation

- **1 new file**: `apps/miroflow-agent/scripts/run_professor_orcid_backfill.py`
- **1 test file**: `apps/miroflow-agent/tests/scripts/test_run_professor_orcid_backfill.py`

### Core flow

```python
# Pseudo-code, directional
for prof in profs:
    if prof.id in resume_ids:
        continue
    try:
        author = openalex_fetch_author(prof.canonical_name, prof.institution)
        if author and author.get("orcid"):
            bare_orcid = _strip_orcid_url(author["orcid"])
            confidence = _score_author_match(author, prof)
            if not dry_run:
                upsert_professor_orcid(
                    conn,
                    professor_id=prof.id,
                    orcid=bare_orcid,
                    source="openalex",
                    confidence=confidence,
                )
                conn.commit()
            checkpoint.append({prof_id, orcid, confidence})
    except Exception as exc:
        log warning; checkpoint.append({prof_id, status="error", error=str(exc)})
```

### Test scenarios (6)

1. `--help` exits 0 with usage
2. `--dry-run` invokes OpenAlex fetch but does NO UPDATE calls
3. Missing DATABASE_URL exits 1
4. Successful prof with ORCID: upsert called with bare ORCID string (no URL prefix)
5. Prof with no OpenAlex match: no upsert, checkpoint row recorded
6. OpenAlex 429/timeout: per-prof exception caught, next prof continues

## Non-goals

- No LLM verification of match quality (could add later)
- No async / concurrent fetches (sequential with 0.1s rate gate)
- No citation-count-based author disambiguation tie-breaking (use exact name + institution as proxy)
- No retry on OpenAlex failures (next run's --resume will pick up)

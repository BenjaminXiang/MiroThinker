# Proposal: fix-answer-guards-and-job-timezone

Human doc: `docs/plans/2026-10-25-answer-guards-and-job-timezone-log.md`.

## Why

Three customer-visible defects share one property: the system had the right
data but presented the wrong subject, the wrong text, or the wrong clock.

1. **Protocol marker leak.** An enumeration answer (session
   `C4XrUsD91G4LegDYgkoomeezYIllcZ9d`, turn 4) shipped
   `</|canonical_v2_answer_v1|>` to the user. `_PROSE_PRIVATE_MARKER_PATTERNS`
   only matched the opening form `<|canonical_v2…|>`; the closing variant with
   a slash passed through.
2. **Unknown company profiles a neighbour.** `严格验收机器人公司是做什么的`
   resolved no local entity, but the selector took the top local company
   handle (深圳市普渡科技有限公司) and the answer profiled 普渡, then
   disclaimed the name it never matched. The query named a company; no local
   claim for a different company should be eligible.
3. **Jobs page shows the wrong next run.** The OS cron entry is
   `0 2 * * 1` in server local time (CST), but `task_views` computed
   `cron_next_fire` from a UTC clock, so the page showed `10:00` for a `02:00`
   job (screenshot 2026-10-23).

## What Changes

1. Marker filter: `r"<\|canonical_v2…\|>"` → `r"</?\|canonical_v2…\|>"`.
2. New shared helpers in `followup_referents.py`:
   - `query_company_name(query)` — the company name a query names, rejecting
     question words, anaphora, relation phrases (`创办的公司`), and
     description phrases (`深圳的机器人公司`).
   - `company_names_match(left, right)` — conservative core comparison
     (strip city/legal/industry scaffolding; one core contains the other).
3. `_answer_selector`: when a non-enumeration query names a company, a local
   `company` claim is eligible only if its handle name matches that company.
   Web claims are untouched, so a real company absent from the pack can still
   be answered from the web.
4. `jobs.py`: `job_timezone()` reads `MIROTHINKER_JOB_TIMEZONE`
   (default server local); `task_views` passes it to `cron_next_fire`, so the
   admin page renders the same wall clock as the OS cron.

## Impact

- Answers no longer leak the closing marker family.
- A named company absent from the pack no longer cites/profiles a different
  local company; the answer falls back to web evidence or an honest empty
  result.
- The jobs page next-run time matches the installed cron (02:00 CST, not
  10:00).
- Enumeration turns are unchanged (`query_company_name` returns None for
  `哪些`/`有哪些`); partial-name controls (`普渡科技公司`) still match.

## Non-goals

- The 64-name member-coverage disclosure. It is a tested coverage contract
  that widens the session universe before commit; shortening it is a
  presentation/product decision, not a retrieval bug.
- Seed scheduling; indexed lexical lane; Playwright browser install.

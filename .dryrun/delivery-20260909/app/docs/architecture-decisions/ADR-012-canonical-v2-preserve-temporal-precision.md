# ADR-012: Canonical V2 preserves temporal precision

- **Date:** 2026-07-13
- **Status:** Accepted (grilling-validated)
- **Related:** `CONTEXT.md` (Temporal precision); OpenSpec
  `rebuild-canonical-v2-knowledge-platform`; Task 5.7/S5G temporal-precision correction; Task 6.3
  typed domain projection

## Context and decision

Canonical V2 sources may state only a calendar date while other sources retain an exact
timezone-aware instant. We will preserve that distinction end to end: a date remains a date, an
instant is canonicalized as an instant, and precision participates in hashes, lineage equality,
persistence, and restart reconstruction. We will not manufacture an unknown time by converting a
date to UTC midnight, and we will not weaken assertion-to-projection validity checks.

## Consequences

- Shared assertion/current-selection and typed-subobject temporal values need one explicit
  precision-bearing contract before Task 6.3 can become Candidate.
- Exact temporal equality requires matching precision and value. Cross-precision ordering or
  overlap uses `explicit-calendar-v1`: callers must supply a named Gregorian calendar/timezone
  context, which interprets a date as a half-open civil-day interval for comparison only. Without
  that context the result is `indeterminate`; no ambient/system default is permitted. An instant
  inside that interval overlaps the date but is not exactly equal to it.
- PostgreSQL storage, canonical JSON/hashes, adapters, migrations, and tests must round-trip the
  precision discriminator exactly.
- Task 6.3 is stopped until the narrow S5G contract correction is Accepted and its affected S5/S6
  regression surface is GREEN.

## Alternatives rejected

- **Normalize dates to UTC midnight:** simple but invents a time and timezone not present in the
  source.
- **Drop temporal lineage equality:** hides assertion/projection drift and weakens auditability.
- **Default Asia/Shanghai or UTC comparison:** convenient but silently applies a calendar/timezone
  assumption that is not valid for every international publication or source.

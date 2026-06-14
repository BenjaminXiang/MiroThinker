## Context

The professor seed pipeline already has a safety gate:
`resolve_seed_adapter_name()` returns a named adapter/API path before
`run_single_seed_with_conn()` runs the crawler/parser pipeline. If the resolver
returns `None`, the seed is marked `adapter_missing` and a `pipeline_issue` is
written without performing network or parser work.

The current real seed inventory contains 20 `miroflow_real.professor_seed` rows.
Fifteen resolve to an existing adapter or API path. Five do not:

- Seed 24, SUIT/SZIIT, `https://zd.suit-sz.edu.cn/jyjx/jsfc.htm`.
- Seeds 25-28, UESTC/SIAS, `https://sias.uestc.edu.cn/rcpy/dsjs1/...`.

Read-only diagnostics show that SUIT/SZIIT can be fetched directly with
`trust_env=False` and the existing roster extraction path recovers 10 professor
entries. UESTC/SIAS returns 202 tokenized XHTML challenge pages with 0 Chinese
characters and 0 anchors across the seed URL, parent directory, root page, and
HTTP redirect variant; Playwright returns `net::ERR_CONNECTION_CLOSED`.

## Goals / Non-Goals

**Goals:**

- Make row-level adapter coverage a first-class OpenSpec contract for the
  current professor seed inventory.
- Add a deterministic coverage guard that can prove whether each real seed is
  runnable, blocked with approved evidence, or still missing coverage.
- Add named SUIT/SZIIT resolver coverage and verify it through real seed
  preview/sample E2E.
- Resolve UESTC/SIAS by either implementing a durable fetch/parser path or
  classifying the four seeds as approved `fetch_blocked` outcomes with
  actionable issue evidence.
- Require a 20-row E2E matrix before P4 is marked complete.

**Non-Goals:**

- No new seed CRUD fields or schema columns.
- No broad rewrite of the professor discovery pipeline.
- No silent downgrade of anti-scraping challenge pages into successful crawls.
- No full production recollection run as part of the coverage proof; preview and
  bounded sample runs are sufficient for this change.

## Decisions

### Decision: Keep adapter resolution as the runtime gate

`adapter_resolution.py` remains the single runtime gate for determining whether
a seed has a registered path. This preserves the existing `adapter_missing`
contract and prevents missing school support from falling through to generic
parser behavior.

Alternative considered: let the generic roster parser run for any URL. Rejected
because it would erase the distinction between named school support and
accidental parser success, and would make per-school seed coverage impossible to
audit.

### Decision: Add an explicit coverage guard script

The change adds a script such as
`apps/miroflow-agent/scripts/audit_professor_seed_adapter_coverage.py` that loads
`professor_seed` from the configured database, resolves each row, and reports a
full seed matrix. The guard fails non-zero when a seed has no resolver result
and no approved blocked classification.

Alternative considered: rely on seed UI status or ad hoc SQL. Rejected because
P4 requires repeatable evidence in `acceptance.md` and
`.agents/runs/prof-seed-adapter-coverage/verification.md`.

### Decision: Implement SUIT/SZIIT as a named adapter family

SUIT/SZIIT seed 24 gets a named adapter, expected to match
`suit-sz.edu.cn`/`zd.suit-sz.edu.cn` roster pages. The extractor may reuse
existing roster-link extraction helpers, but completion evidence must show the
seed resolves to the named adapter and passes a preview or sample run.

Alternative considered: mark seed 24 complete because generic extraction already
finds profiles. Rejected because P4 requires named school-specific coverage.

### Decision: Treat UESTC/SIAS as fetch-strategy-or-blocked

UESTC/SIAS seeds 25-28 must not be fixed with parser-only changes until a usable
page body is obtained. If a durable fetch strategy cannot be established, the
approved outcome is `fetch_blocked` with structured issue evidence, not
`adapter_missing` and not `success`.

Alternative considered: add a named adapter that still parses the 202 challenge
body. Rejected because the challenge body contains no roster data.

### Decision: Verify every real seed row

Existing adapters for SUSTech, HITSZ, SZU, SIGS, and CUHK still require row-level
preview/sample E2E evidence. Resolver presence alone does not complete P4.

Alternative considered: only test the five missing seeds. Rejected because the
user requirement is current seed inventory coverage, not only missing resolver
coverage.

## Risks / Trade-offs

- UESTC/SIAS may remain blocked by site-level anti-scraping behavior -> The
  change allows approved `fetch_blocked` classification with actionable
  `pipeline_issue` evidence.
- Real seed E2E can be slow or environment-sensitive -> Use preview/sample modes
  and record command, status, counts, and skipped-check rationale per seed.
- A school-specific matcher could be too broad -> Add unit tests for matcher
  scope and keep the adapter registry explicit.
- Existing covered adapters may fail real seed E2E -> Fix URL-specific parser
  issues within this change only when they affect the current seed inventory.

## Migration Plan

1. Add the coverage guard and run it read-only against `miroflow_real`.
2. Add unit tests for new resolver/adapter matching.
3. Add SUIT/SZIIT adapter support and run seed 24 preview/sample E2E.
4. Diagnose UESTC/SIAS and either implement a durable fetch/parser path or record
   approved `fetch_blocked` outcomes.
5. Run the full 20-row preview/sample E2E matrix.
6. Update `tasks.md`, `acceptance.md`, and
   `.agents/runs/prof-seed-adapter-coverage/verification.md`.

Rollback is additive: remove the new guard script and adapter registrations, and
the existing `adapter_missing` gate resumes previous behavior.

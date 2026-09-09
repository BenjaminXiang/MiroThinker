## Context

P4 (`prof-seed-adapter-coverage`) completed the current 20-row seed matrix by
separating runnable rows from approved blocked rows. That was necessary for
operator visibility, but it did not make every seed productive:

- Seed 5 (`https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1`) still fails
  with an HTTP 412 / browser connection-close style block.
- Seeds 25-28 under `https://sias.uestc.edu.cn/rcpy/dsjs1/` still return a
  tokenized 202 challenge page with no usable roster content.
- An official UESTC graduate mentor source is reachable at
  `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc` and returns mentor lists for
  `yxsh=28` with program filters.

The current system already has the right safety primitives: named adapter
resolution, preview/sample seed runs, `fetch_blocked` failure classes, and
structured `pipeline_issue` evidence. P5 should use those primitives rather
than weakening P4's guard.

## Goals / Non-Goals

**Goals:**

- Turn the avoidable UESTC/SIAS blocked outcomes into runnable official-source
  coverage by adding a named UESTC graduate mentor adapter.
- Preserve P4's row-level evidence shape for seed ids 25-28, including
  resolver result, candidate count, run status, and issue outcome.
- Re-audit SZU CSSE using only official reachable sources and either replace
  the seed with a durable official roster/API path or keep explicit refreshed
  `fetch_blocked` evidence.
- Update `tasks.md`, `acceptance.md`, and
  `.agents/runs/prof-blocked-seed-source-remediation/verification.md` as each
  P5 slice is completed.

**Non-Goals:**

- Do not bypass CSSE or SIAS anti-bot challenges with token-replay,
  browser-fingerprinting, or credentialed scraping.
- Do not use search-engine snippets, cached pages, unofficial mirrors, or
  manually copied rosters as successful source evidence.
- Do not broaden professor seed storage beyond the existing seed table unless
  implementation proves a separate fallback mapping is required and the spec is
  updated first.
- Do not run unbounded full crawls as P5 evidence; use preview or bounded
  sample mode.

## Decisions

### Decision 1: Use UESTC yjsjy as the durable source for SIAS seed ids 25-28

The UESTC/SIAS pages remain blocked at the SIAS host, but the UESTC graduate
mentor site is official and returns usable HTML with mentor detail links. P5
will implement a named adapter for the yjsjy mentor list rather than trying to
force the SIAS challenge page.

Initial mapping:

| Seed id | Department | Current SIAS path | yjsjy query |
|---:|---|---|---|
| 25 | 电子信息 | `/dzxx2.htm` | `yxsh=28&zydm=085400` |
| 26 | 计算机技术 | `/jsjjs/jsjjs.htm` | `yxsh=28&zydm=085404` |
| 27 | 软件工程 | `/rjgc/rjgc.htm` | `yxsh=28&zydm=085405` |
| 28 | 机械 | `/jx/gyhlwyznzz.htm` | `yxsh=28&zydm=085500` |

Alternatives considered:

- Continue treating SIAS as approved `fetch_blocked`: safe but leaves an
  official source unused.
- Add a generic yjsjy parser without seed-specific mapping: weaker evidence and
  harder to audit by row.

### Decision 2: Keep a named adapter boundary

The yjsjy path must resolve to a stable adapter name such as
`uestc-yjsjy-mentor-roster`. The adapter may share generic HTML extraction
helpers internally, but completion evidence must show the named adapter for
each row.

Alternatives considered:

- Let the existing generic roster parser process the yjsjy HTML without a
  named resolver. Rejected because P4 explicitly made generic parser success
  insufficient coverage.

### Decision 3: Treat SZU CSSE as source remediation, not parser repair

The current CSSE host failure happens before usable roster HTML is available.
P5 should first search for an official replacement roster/API. If none is
available, seed 5 remains blocked with refreshed diagnostics; the code should
not pretend the seed is runnable.

Alternatives considered:

- Use the Shenzhen University central teacher page as the source. Rejected
  unless it exposes individual CSSE roster entries; a page that only links to
  the blocked CSSE URL is not a replacement roster.
- Use search snippets or cached pages. Rejected because source traceability and
  freshness are not sufficient for canonical professor ingestion.

## Risks / Trade-offs

- UESTC program-code mapping could be incomplete or change over time. Mitigate
  by recording source-audit evidence and candidate counts per seed before
  marking adapter E2E successful.
- yjsjy detail pages may include mentors affiliated with the broader UESTC
  organization while still using `yxsh=28`. Mitigate by preserving source
  institution text and filtering only by official query parameters, not by
  heuristic name matching.
- Updating real seed URLs could mutate operator input. Mitigate by preferring
  adapter-level fallback mapping first; only update `professor_seed.seed_url`
  if the implementation explicitly records the migration and E2E evidence.
- SZU CSSE may remain blocked. Mitigate by keeping explicit `fetch_blocked`
  evidence and making the remaining operator action clear.

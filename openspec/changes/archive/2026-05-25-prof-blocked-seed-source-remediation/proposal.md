## Why

P4 made every current professor seed either resolver-covered or explicitly
blocked, but five real seed rows still do not produce usable roster data:
SZU CSSE remains blocked by the current CSSE URL, and UESTC/SIAS is blocked on
the SIAS site even though an official UESTC graduate mentor source is reachable.
P5 is needed to replace avoidable blocked outcomes with durable official-source
crawling, while preserving explicit blocked evidence where no official
replacement exists.

## What Changes

- Add a P5 remediation contract for seed ids 5 and 25-28 after the P4 coverage
  matrix.
- Add a named official UESTC graduate mentor source path for seeds 25-28 using
  `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc` with school `yxsh=28` and
  program-specific `zydm` filters.
- Require UESTC/SIAS seed remediation to produce row-level preview/sample E2E
  evidence with candidate counts and issue outcomes.
- Require SZU CSSE remediation to use only official reachable sources. If no
  official replacement roster/API is found, seed 5 remains an explicit
  `fetch_blocked` outcome with refreshed evidence and cannot be counted as a
  successful crawl.
- Preserve the P4 coverage guard semantics and extend the evidence matrix so
  P5 is complete only after `tasks.md`, `acceptance.md`, and
  `.agents/runs/prof-blocked-seed-source-remediation/verification.md` are
  updated.

## Capabilities

### New Capabilities

- `professor-blocked-seed-source-remediation`: Defines P5 source-remediation
  evidence and success rules for previously approved blocked professor seeds.

### Modified Capabilities

- `professor-seed-adapter-coverage`: Extend the P4 coverage contract with P5
  remediation expectations for previously approved blocked seeds.
- `professor-seed-ops-hardening`: Clarify that refreshed blocked evidence must
  continue to include response shape when a replacement official source is not
  available.

## Impact

- Professor seed adapter resolution and roster extraction for UESTC official
  graduate mentor pages.
- Professor single-seed preview/sample runner evidence for seed ids 5 and
  25-28.
- Coverage guard or companion P5 audit output for unresolved blocked seeds.
- OpenSpec evidence artifacts under
  `openspec/changes/prof-blocked-seed-source-remediation/` and
  `.agents/runs/prof-blocked-seed-source-remediation/`.

# Slice Contract: S12C Customer Workbook Replay

## Status

Candidate.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `12.3`
- Dependency: S12B Task 12.2 functional Candidate.

## Goal

Replay the 17 conversations and 25 turns in `docs/测试集答案.xlsx` through the exact running chat
API, preserving one cookie session per conversation, and emit content-bound JSON plus a readable
Markdown comparison of Ground Truth, actual answer, sources, limitations, and execution status.

## Non-goals

- No workbook answer or case ID enters production query, retrieval, or answer code.
- No automated semantic score becomes acceptance, and no missing case is excluded.
- No active-pointer change, production Cutover, or broad test suite.

## Allowed scope

- One run-scoped replay tool, its focused test, result artifacts, and Task 12.3 evidence.
- Focused production repairs only after a replayed badcase establishes a defect class.
- One content-addressed real embedding adapter and a fresh isolated Candidate/index rebuild.
- One additional isolated r7 rebuild after workbook badcases established systemic source,
  identity, evidence-closure, and answer-selection defects.
- Generic query/domain extraction, Web credential fallback, per-session concurrency, safety handoff,
  and public error mapping required by observed real-runtime failures.

## Observed defect class

The r1 replay proved that the serving runtime was bound to the 32-dimensional deterministic hash
embedding created for offline build acceptance. That adapter is reproducible but not a semantic
retrieval model, so otherwise valid Candidate data produced unrelated cross-domain answers. The same
run also exposed a blocked Serper key-file fallback, process-wide chat serialization, missing safety
handoff, and uncaught isolated-read integrity errors.

The repair is provider- and query-pattern-generic. Production code must not read workbook answers,
row numbers, case IDs, or exact benchmark queries.

## Final r8 outcome

- Release `candidate-s12c-20260726-r8` contains 1,037 Company, 262 Paper, 1,931 Patent,
  and 554 Professor projections plus 339 evidence-backed relationships.
- Final replay `customer-workbook-replay-r6.json` executed all 17 conversations and 25 turns through
  the running HTTP runtime with 25 `ok` outcomes and zero HTTP/contract failures. Its content hash is
  `003486c23b2ab32cd3328e77e3f095f954f233d2f08dd980ac6be35365a72b9e`.
- Exact entity selection no longer pads an answer with vector neighbors. Accepted identifier claims
  are bound to the matching projection field, and an independent explicit entity turn now performs a
  typed topic switch so the active anchor follows the displayed exact result.
- The Ding Wenbo sources merge under accepted email/homepage evidence while retaining both source
  lineages. His Company follow-up traverses the source-bound founder relationship. The Shenzhen
  Zhihang Wujie correction selects only Shenzhen Wujie Zhihang and excludes the near-name UAV
  Company.
- pFedGPA remains the sole displayed Paper across its two-turn conversation. `CN117873146A` resolves
  through exact and lexical identifier evidence to one Patent and becomes the active session anchor.
- Production modules contain no workbook row, case ID, reference answer, or exact workbook-query
  shortcut. Supplemental fixed sources enter only through manifest-pinned landing records.

## Recorded product gaps

- Company projections do not yet expose a normalized headquarters/geography field, so workbook rows
  6 and 15 return no supported material claim instead of inferring Shenzhen from a legal name.
- The admitted local/current-Web evidence does not establish the Waseda entrepreneur query or Wang
  Xueqian assessment, so rows 20 and 25 remain explicit no-evidence answers.
- The source projection for pFedGPA has no DOI, arXiv, or publication URL. The follow-up remains on the
  correct Paper but cannot provide the requested link.
- The current Company model does not support the requested cross-company embodied-data route analysis;
  row 35 remains an explicit gap. Several broad analytical answers are useful but still incomplete
  against the workbook Ground Truth.
- Web timed out on rows 14 and 27 in r6. Both turns still returned evidence-bound local answers; the
  timeout remains visible in their retrieval traces.
- Candidate startup and some queries remain slow because one local embedding/runtime instance is the
  shared bottleneck. Milvus Lite may log `too_many_pings` throttling while requests still complete.

## Required checks

1. Workbook parsing proves exactly 17 ordered groups and 25 ordered turns.
2. Replay proves distinct sessions between groups and one continuous session within each group.
3. HTTP/contract failures remain visible rows rather than aborting or disappearing.
4. JSON and Markdown reports bind the workbook, expected release, actual trace, sources, and
   limitations; final semantic acceptance remains the user's decision.
5. The real embedding authority is secret-free and content-addressed; credentials remain external.
6. Independent sessions may execute concurrently while turns within one session remain serialized.
7. Isolated-read integrity failures produce a stable public 409 response and never leak as HTTP 500.
8. Exact entity questions display only selected canonical handles; audit-only candidates never
   become answer filler.
9. Same-name identities merge only from accepted high-confidence identity evidence, while
   same-name/different-identity sources remain separate.
10. Fixed restore-verified workbook backfills enter through landing records and retained evidence;
    production runtime never reads workbook answers.

## Done means

All 25 turns have real-runtime outcomes in the readable report from the rebuilt Candidate. Material
badcases are repaired or explicitly recorded as open product gaps before Task 12.3 is checked.

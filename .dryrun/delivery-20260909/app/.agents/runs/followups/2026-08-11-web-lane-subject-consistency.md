# Follow-up: web lane subject-consistency filtering (Bocha off-entity noise)

Status: Implemented and deployed 2026-08-12 (commit 50c4f3a, production 18188 restarted).
Residual: shared-alias lookalikes (e.g. 南开国际先进研究院) can still pass the
identity-form gate; stream path has no off-anchor correction retry (chunks are
irrevocable); official-site fetch injection (original R3) deferred to a later phase.
OpenSpec backfill still owed per repo process.
Date: 2026-08-11
Context: deploy of `fix(canonical-v2): bind follow-up elaborations to the prior subject` (27d0231)

## Problem

After the follow-up soft-anchor fix, second-turn elaboration queries are correctly
prefixed with the prior subject (e.g. `国际先进技术应用推进中心（深圳） 有没有更详细`),
but the synthesized answer can still drift to a *different, similarly named*
institution (observed on production: `南开国际先进研究院（深圳福田）`,
`中国科学院深圳先进技术研究院` fragments in template fallback).

Root cause (evidenced by direct provider probes, see below): the dual-channel web
lane returns off-entity results for exact-institution-name queries. Serper's top
results were all on-topic; Bocha's top results were uniformly the wrong
similarly-named institution. Neither the synthesis step nor the template fallback
(`answer_style: template`) filters for subject consistency with the anchor.

## Evidence

- Production smoke test 2026-08-11 (127.0.0.1:18188, two-turn cookie session):
  turn-2 plan views correctly prefixed, answer_text locked onto
  `南开国际先进研究院（深圳福田）` instead of the anchor subject.
- Local probes during pre-deploy verification: identical prefixed queries against
  both web providers; Serper top-5 on-topic, Bocha top-5 uniformly
  `中国科学院深圳先进技术研究院` / `精密工程研究中心` fragments, matching the
  off-entity answer content verbatim.

## Proposed direction

1. Subject-consistency filtering/reranking on web lane results: downweight or
   drop snapshots whose title/body does not mention the anchor subject name,
   especially for the Bocha channel.
2. A subject-relevance gate before the `template` answer fallback, so similarly
   named institutions' fragments are not listed as a "more specific" answer.

## Scope note

This is retrieval-relevance/synthesis-fidelity work, independent of the
follow-up binding chain (continuation recognition, soft anchor, prefix
injection, carry-forward), which is verified working on production.

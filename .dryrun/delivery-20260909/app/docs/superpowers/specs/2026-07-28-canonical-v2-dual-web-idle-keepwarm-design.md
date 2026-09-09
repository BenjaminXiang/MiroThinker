# Canonical V2 Dual Web and Idle Keepwarm - Design

> Status: approved direction, pending written-spec review.
> Parent change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`.
> Runtime target: isolated Candidate `candidate-s12c-20260726-r8` only.

## Context

Canonical V2 currently invokes only Serper even though the repository already contains
`BochaSearchProvider` and a legacy `CompositeWebSearchProvider`. The serving bundle fixes
`web_provider` to `serper-v1`, and the Canonical Web adapter records every candidate as
`serper-v1`. Therefore Bocha is absent from the current Candidate answer path.

Measured warm end-to-end latency averages 1.847 seconds across Professor, Company, Paper,
and Patent queries. Long-idle or upstream-tail requests have taken 8.26 to 11.214 seconds.
The user selected parallel Bocha plus Serper retrieval and identified long-idle cold requests
as the primary latency concern.

## Goals

- Run Bocha and Serper concurrently for every normal Canonical V2 information request.
- Merge and URL-deduplicate results without losing their real provider provenance.
- Preserve local plus current-Web retrieval, evidence admission, LLM synthesis, public citation,
  and internal-data non-disclosure behavior.
- Keep embedding, LLM generation, Bocha, and Serper warm during long idle periods without
  creating chat sessions or writing data.
- Keep real user requests ahead of background keepwarm work.

## Non-goals

- No production promotion, active-release change, source recollection, canonical/index write,
  public evidence expansion, or `/browse` exposure.
- No raw LLM token streaming or shorter evidence deadlines in this slice.
- No promise that application keepwarm eliminates independent upstream provider tail latency.
- No generic scheduler framework or reusable job platform.

## Chosen Retrieval Design

### Parallel providers

One Canonical-owned dual-Web adapter starts Bocha and Serper together under the existing outer
Web-lane wall-clock budget. Wall time is the slower completed provider, not the sum of both.
Each provider owns a reusable transport. A failure from one provider retains valid results from
the other; the Web lane is unavailable only when both providers fail or produce no admissible
result.

The serving bundle records both provider identities and a maximum of two external provider calls.
The existing one-call Universal-Web contract and supplemental cost budget must be updated
explicitly rather than bypassed.

### Normalization and provenance

Both providers normalize into one internal result shape:

```text
title
url
snippet
summary
primary_provider_version
corroborating_provider_versions
```

Bocha contributes its richer Chinese `summary`; Serper contributes Google-backed entity and
official-site coverage. Results are ordered deterministically by provider priority, provider rank,
and normalized URL before the existing Canonical reranker applies query relevance.

URL duplicates are one candidate, not two. The Bocha content is retained when non-empty and the
snapshot records both `bocha-v1` and `serper-v1` as corroborating providers. A provider-only result
records only its actual provider. Candidate traces retain the primary provider; the content-bound
Web snapshot retains the complete corroborating-provider tuple. No Bocha result may be labeled as
Serper.

The merged result cap remains the serving bundle's current `max_web_results`; it is applied after
deduplication, not separately to each provider.

## Adaptive Idle Keepwarm

### Activity and cadence

A small Candidate-owned coordinator records monotonic time when a real `/api/chat` request arrives.
Every 300 seconds it checks activity:

- If a real request occurred within the last 300 seconds, skip the cycle.
- Otherwise run one keepwarm cycle.
- Permit at most one keepwarm cycle at a time.
- Stop the coordinator cleanly with the ASGI lifespan.

The interval and enable flag are explicit Candidate serving configuration, not hidden constants.
With a completely idle service, the maximum is about 288 calls per day to each Web provider, 288
minimal LLM calls, and 288 embedding calls.

### Warm ports

One idle cycle invokes four bounded operations concurrently:

1. Embed one fixed, non-user warmup string through the release-bound embedding adapter.
2. Run one fixed Bocha query and discard the response.
3. Run the same fixed Serper query and discard the response.
4. Run one non-thinking LLM completion with a one-token output limit and discard the response.

These operations use the same process-owned provider pools as real requests where safe. Provider
pools must not share one mutable HTTP session concurrently: an occupied warm transport cannot block
or corrupt a real request, and the pool may create another transport for the user path.

Keepwarm does not call `CanonicalV2ChatAdapter.answer`, create a session, generate a feedback
checkpoint, emit citations, mutate evidence, or write PostgreSQL/Milvus/files. Probe input and output
remain internal and are never returned by public routes.

### Failure and user priority

Keepwarm is best effort. Each port has its existing bounded timeout. Failure is recorded in internal
structured logs with provider, duration, and failure kind, but does not make `/api/chat` unavailable.
A real request marks activity immediately and never waits for a keepwarm cycle. If it overlaps an
already-running cycle, provider pooling prevents contention on the active transport.

## Request Critical Path

For a successfully kept-warm service, the expected user path remains:

```text
HTTP/planning                    0.05-0.15 s
local lanes (parallel)           0.20-0.30 s
Bocha + Serper (parallel)        max(Bocha, Serper)
fusion/rerank/claim validation   0.10-0.15 s
Qwen prose synthesis             0.60-0.90 s
mapping/JSON/DOM                 under 0.05 s
```

The acceptance target after at least 30 minutes without user traffic is a first real request in the
same 1.5-3.0 second range as a warm request when both external providers meet their normal latency.
Provider-tail events remain reported separately and must not be hidden by dropping valid Web
evidence.

## Contract and Artifact Changes

This is behavior-affecting work. Before implementation, update the existing OpenSpec change and add
one Ready slice contract covering:

- dual-provider serving-bundle schema and call/cost bounds;
- provider-aware snapshot and candidate provenance;
- one-provider and both-provider failure behavior;
- adaptive keepwarm lifecycle, no-write/no-session invariant, and user priority;
- latency and answer/citation parity acceptance.

The public `ChatResponse` schema remains unchanged.

## Verification

### Deterministic tests

- RED/GREEN: both providers start before either is released by a fake barrier.
- Parallel wall time is bounded by the slower provider rather than their sum.
- Bocha-only, Serper-only, duplicate-URL, one-failure, both-failure, and result-cap cases.
- Duplicate snapshots retain both provider versions; provider-only snapshots retain one.
- Existing claim/evidence closure and official-public-citation tests remain GREEN.
- Fake-clock keepwarm tests cover active skip, idle execution, single-flight, clean shutdown,
  provider failure, and immediate user activity.
- Keepwarm spies prove zero chat sessions, checkpoints, database writes, and public output.

### Live Candidate checks

- Benchmark Bocha, Serper, and parallel dual-provider latency separately.
- Replay the four public domains and the Ding Wenbo founder follow-up.
- Confirm answers remain LLM-synthesized and public evidence remains empty.
- Confirm only allowed official URLs appear in the collapsed evidence disclosure.
- Run a shortened keepwarm interval in an isolated test process, then restore 300 seconds.
- Run a real idle soak when practical and report median, p95, provider failures, and the first
  post-idle browser-visible answer time without claiming guarantees from a single sample.

## Rollback

The change is isolated to serving configuration, provider composition, Candidate lifecycle wiring,
tests, and the active change artifacts. Roll back by reverting the slice commit and restarting the
same read-only Candidate. No data rollback is required because the design permits no writes.

## Remaining Risks

- Waiting for both providers can increase normal Web time when one is slow; the common outer deadline
  bounds but does not remove this trade-off.
- Completely idle operation produces up to 576 Web calls per day across both providers.
- A five-minute cadence may keep upstream model workers active but cannot guarantee that a provider
  preserves the same TCP connection or never scales down sooner.
- Bocha and Serper can disagree. Existing evidence admission and LLM grounding must retain conflict
  visibility rather than silently selecting an unsupported fact.

## ADDED Requirements

### Requirement: Structured Turn Trace

The chat service SHALL emit exactly one structured `TurnTrace` record per
completed turn (success, degraded, or error), containing at minimum:

- session snapshot: session id, turn ordinal, active anchor id/name (or none),
  displayed-id count;
- interpretation: raw query, question frame, inferred domains, subject
  candidates considered;
- per-lane counts: local lane and web lane, each with in / retained / filtered
  counts;
- gate drops: per named gate (e.g. web subject-consistency filter), the number
  of candidates dropped;
- web fetch outcomes: per provider per query view — attempted, errored,
  timed-out, retried, cache-hit counts;
- degradation reason: machine-readable token (e.g. `web-lane-unavailable`,
  `no-local-evidence`, `subject-gate-empty`) or `none`;
- final answer subject and citation count;
- wall-clock duration of the turn.

#### Scenario: baseline failure is attributable from the trace alone

- **WHEN** a replay session that fails its frozen assertion (e.g. G1 anchor
  drift, G3 referent misclassification) is re-run with tracing enabled
- **THEN** the journal reader, given only the trace of that turn, names the
  stage where the outcome diverged (anchor binding / gate drop / lane counts /
  degradation reason)
- **AND** no source-code inspection is required to attribute the failure

#### Scenario: healthy turn unchanged

- **WHEN** a turn that currently succeeds (e.g. replay G6 clarification) runs
  with tracing enabled
- **THEN** the answer, citations, and latency profile are unchanged within
  replay-assertion tolerance, and the trace records `degradation: none`

### Requirement: Turn-Trace Journal and Reader

Traces SHALL be persisted as append-only JSONL journals (one file per day),
retained for a configurable number of days, and readable by a CLI tool that
supports filtering by session id, degradation reason, and turn status, and
prints one line per turn plus a per-stage expansion on request.

#### Scenario: reader finds a session's degradation turns

- **WHEN** the reader runs with `--session <id>` against a day containing
  replay turns
- **THEN** it lists each turn with its ordinal, degradation token, and lane
  counts, without loading the full journal into memory beyond line streaming

### Requirement: Web-Lane Resilience

`_DualWebLaneAdapter` SHALL, per provider and query view:

- retry a failed search exactly once with backoff before declaring the attempt
  failed (search is idempotent);
- serve results from a web-result cache keyed by (provider, normalized view
  query, UTC day) when present, recording cache-hits in the trace;
- maintain a per-provider health circuit-breaker: open after N consecutive
  failures, probe after a cooldown window, close on probe success; while open,
  skip the provider (preference bias toward the healthy one) instead of paying
  the timeout;
- count requests per provider per day against a quota watermark; when above the
  watermark, non-essential traffic (keepwarm) MUST NOT issue further searches
  for that provider/day;
- record every retry, cache hit/miss, breaker transition, and quota event in
  the turn trace (or the keepwarm journal for keepwarm-originated events).

#### Scenario: fault injection kills one provider

- **WHEN** one provider's API key is invalidated and the replay suite runs
- **THEN** the surviving provider serves the lane (or the cache does), retries
  and breaker transitions appear in the trace, and no turn silently loses the
  web lane without a `web-lane-unavailable` degradation token

#### Scenario: cache day rollover

- **WHEN** the same view is queried across a UTC-day boundary
- **THEN** the earlier day's cache entry is not served and the new day's entry
  is fetched and recorded as a cache miss

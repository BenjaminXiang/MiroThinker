# Design: prof-seed-ops-hardening

## Scope

This change hardens the seed operations loop after
`prof-seed-admin-console` Phase B. It does not replace the existing seed
CRUD table or trigger endpoint; it extends the trigger contract so
operators can run bounded samples and understand failure causes before a
future full recollection.

## Trigger modes

`POST /api/seeds/{id}/trigger` accepts a JSON body:

```json
{
  "mode": "sample",
  "limit": 3
}
```

Modes:

| Mode | Writes canonical rows | Required limit | Use |
|---|---:|---:|---|
| `preview` | no | optional | fetch and parse enough to report count/shape |
| `sample` | yes | yes | bounded validation against a real seed |
| `full` | yes | no | intended recollection run |

The endpoint remains backward-compatible: an empty body is interpreted
as `{"mode": "full"}`.

## Failure taxonomy

The run result carries a machine-readable `failure_class`:

- `adapter_missing`: no registered adapter for the seed.
- `fetch_blocked`: HTTP 403/412, WAF, JavaScript challenge, connection
  closed by a browser probe, or equivalent fetch-level block.
- `parser_low_quality`: fetch succeeded but the parser did not produce
  a usable roster/profile set according to configured thresholds.
- `pipeline_exception`: an uncaught exception outside the known
  categories.
- `success`: completed within the requested mode.

`professor_seed.last_run_status` remains the existing compatibility
state: `adapter_missing` uses its dedicated value, known non-adapter
failures use `failure`, in-progress uses `in_progress`, and successful
runs use `success`. The detailed `failure_class` is surfaced from the
latest `pipeline_run.run_scope` and/or latest open issue snapshot.

## UI

The seed table keeps the existing row action but adds a bounded-run
popover or modal before starting a seed. The default recommended action
is `sample` with a small limit. `full` is explicit and shows the current
seed identity before submission.

The status tag text distinguishes `adapter_missing`, `fetch_blocked`,
`parser_low_quality`, and `pipeline_exception` when a latest
`failure_class` is available.

## Rebuild contract

Every trigger writes mode and limit into `pipeline_run.run_scope`:

```json
{
  "action": "single_seed_trigger",
  "seed_id": 9,
  "trigger_mode": "sample",
  "limit": 3
}
```

This makes later deletion/recollection runs auditable. Tests must assert
that bounded modes cannot silently execute an unbounded full run.

## Rollback

The endpoint body extension is backward-compatible. If UI changes are
rolled back, the endpoint still accepts empty-body full runs as before.

# Acceptance: connect-collection-line

Demonstrated on the live 18188 after the drop-in restart; evidence in
`.agents/runs/connect-collection-line/`.

| # | Line | How |
|---|---|---|
| A1 | `/seeds` is usable | the page lists rows and offers create/edit/delete/trigger on the live line |
| A2 | The DSN has one meaning | with only `CANONICAL_V2_DATABASE_URL` set, the console reports its database unavailable and gated endpoints answer 503 `console_database_not_configured` — never 500 |
| A3 | A trigger reaches the database | a `preview` run writes a `pipeline_run` row (`run_kind='roster_crawl'`, `run_scope->>'seed_id'` = the seed) visible on `/seeds` and `/jobs` |
| A4 | The roster is importable | the 39 historical seeds import idempotently (second run creates 0) and all 39 resolve to an adapter |
| A5 | Failures are visible | a deliberately failing trigger shows status, exit code and stderr excerpt on `/seeds` |
| A6 | Entries are honest | with no console DSN the nav hides `/seeds` and `/upload`; with one it shows them |
| A7 | No regression | `/chat` 200 and the admin gates (302 unauthenticated, 401 for the APIs) unchanged; admin-console full-suite failure set unchanged |

Regression guards: the serving line's database argument and the V2 operations surface
(`CANONICAL_V2_DATABASE_URL`) keep their current meaning; `pipeline` /
`pipeline_issues` stay unmounted; the professor crawl's LLM enrichment stays off by
default.

# Acceptance: add-admin-auth-and-console

Every line must be demonstrable on the live 18188 after cutover; evidence lands in
`.agents/runs/add-admin-auth-and-console/verification.md`.

| # | Acceptance line | Evidence |
|---|---|---|
| A1 | Unauthenticated access to any of the six admin pages redirects (302) to `/main`; any `/api/canonical-v2/*` admin API returns 401 | scratch smoke + live probes |
| A2 | 5 wrong passwords lock the account+IP pair for 60 s (audit rows visible); correct login then enters `/main` and the nav shows the current user | scratch smoke + audit query |
| A3 | Logout invalidates immediately; password change invalidates every prior session of that account; account deletion invalidates it immediately | session tests + live probe |
| A4 | Account management works end-to-end (create → login with it; reset password → old session dead; delete → login refused) | scratch smoke + audit query |
| A5 | With a forged `X-Remote-User: someone-else` header, a config write's operator is still the logged-in username | HTTP test + live probe |
| A6 | `/chat`, `/api/chat*`, `/static/*` remain fully usable unauthenticated (public surface unchanged) | live probes + replay gate |
| A7 | Rollback drill: switch the command file back, restart, the console returns to the unauthenticated gated-off state; `admin-auth.sqlite3` / key / audit survive and are reused when re-rolling forward | live drill |

Additional non-UI checks:

- The fixed `canonical-v2-backend` boot still carries zero `milvus` mentions and
  the replay gate stays 7/7 after cutover.
- `/review` and `/api/review/*` are gone (404) and no admin-console module
  imports the deleted review package.

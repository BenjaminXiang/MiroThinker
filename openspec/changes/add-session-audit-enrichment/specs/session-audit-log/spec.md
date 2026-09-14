# Spec delta: session-audit-log (new capability)

## ADDED Requirements

### Requirement: Access-log records SHALL carry the authenticated identity and no network identifier

The system SHALL record, per chat turn, the identity presented in the `X-Remote-User` header
(the nginx `auth_basic` admin zone). When the header is absent, blank, or whitespace-only, the
system SHALL record the literal marker `anonymous`. The system SHALL NOT record the client IP
address, cookies, or user-agent, and SHALL NOT record any credential material. Recording SHALL stay
fail-open: no identity or storage failure may alter the chat response.

#### Scenario: admin-zone turn records the header identity
- **GIVEN** a chat turn arriving with `X-Remote-User: alice`
- **WHEN** the turn is recorded
- **THEN** the recorded turn's identity is `alice`, and the session's stored row carries no network identifier

#### Scenario: public-zone turn records the anonymous marker
- **GIVEN** a chat turn arriving with no `X-Remote-User` header
- **WHEN** the turn is recorded
- **THEN** the recorded turn's identity is `anonymous`

#### Scenario: a recording failure does not break the turn
- **GIVEN** a store whose write raises (for example a naive timestamp)
- **WHEN** the chat path records the turn
- **THEN** no exception propagates to the caller and no partial row is written

### Requirement: An existing access-log database SHALL be migrated in place and losslessly

Opening a pre-W5 (`canonical-v2-access-log-v1`) database SHALL add the identity column in place,
SHALL preserve every pre-existing row and value, SHALL report pre-existing rows as `anonymous`, and
SHALL be idempotent across repeated opens. The migration SHALL NOT write a schema marker that makes
the pre-W5 reader refuse the file, so that reverting to pre-W5 code leaves the audit log readable.

#### Scenario: legacy rows survive and read as anonymous
- **GIVEN** a database created with the pre-W5 schema and populated with sessions and turns
- **WHEN** the current store opens it and lists sessions
- **THEN** every pre-existing turn is still present with its original values, and the session's identities read as `anonymous`

#### Scenario: repeated opens are idempotent
- **GIVEN** an already-migrated database
- **WHEN** the store is opened again and a new turn is recorded
- **THEN** the open succeeds, no duplicate column or schema error occurs, and the new turn carries its identity

#### Scenario: reverting to the pre-W5 reader keeps the log readable
- **GIVEN** a migrated database
- **WHEN** it is read with the pre-W5 column list and version marker expectations
- **THEN** the reads succeed and the marker is unchanged

### Requirement: Session listing SHALL filter by time range, query type, and identity, combined

`GET /api/canonical-v2/admin/access-logs/sessions` SHALL accept `since`, `until`, `query_type`, and
`identity` in addition to the existing `q` and `status`. All active constraints SHALL combine with
AND at session level: a session matches when at least one of its turns satisfies each active
constraint. Time bounds SHALL accept either `YYYY-MM-DD` (an inclusive whole UTC day) or an ISO-8601
datetime with an explicit offset, and SHALL be compared against `turns.started_at`. Invalid values
(unknown status, unparseable or naive timestamps, `since` after `until`, over-long filter text,
out-of-range pagination) SHALL be rejected with HTTP 4xx and no query executed.

#### Scenario: time range selects sessions with turns in the window
- **GIVEN** sessions whose turns fall on different days
- **WHEN** the list is requested with `since` and `until` covering one day
- **THEN** only sessions having at least one turn inside that window are returned, with a matching total

#### Scenario: query type and identity combine with status
- **GIVEN** sessions with differing statuses, query types, and identities
- **WHEN** the list is requested with `status`, `query_type`, and `identity` together
- **THEN** only sessions satisfying all three are returned

#### Scenario: invalid filters are rejected
- **GIVEN** the sessions endpoint
- **WHEN** a request carries a naive or malformed timestamp, `since` after `until`, or an over-long identity
- **THEN** the response is 4xx and no rows are returned

#### Scenario: unknown identity yields an empty page, not an error
- **GIVEN** sessions recorded under other identities
- **WHEN** the list is requested with an identity that never appears
- **THEN** the response is 200 with `total = 0`

### Requirement: The audit surface SHALL export the matching sessions as CSV or JSONL

`GET /api/canonical-v2/admin/access-logs/export` SHALL emit the turns of the sessions matching the
same filter set as the listing endpoint, as a downloadable attachment in `csv` (default) or `jsonl`
format, bounded by a documented row cap. Exported values SHALL be identical to the values the audit
page displays for the same sessions (question, answer, status, error detail, citations, suggested
follow-ups, query type, identity, timestamps, latency). An unknown format SHALL be rejected with
HTTP 4xx. Every response SHALL disclose how many sessions and turns were emitted and whether the
export was truncated by the cap.

#### Scenario: export equals what the page shows
- **GIVEN** a session with recorded turns visible through the session-detail endpoint
- **WHEN** the same session's turns are exported as CSV and as JSONL
- **THEN** every exported row carries the same question, answer, status, error detail, citations, follow-ups, query type, and identity as the detail response

#### Scenario: export honours the active filters
- **GIVEN** sessions with different statuses
- **WHEN** the export is requested with a status filter
- **THEN** only turns of sessions satisfying that filter are emitted

#### Scenario: unknown format is rejected
- **GIVEN** the export endpoint
- **WHEN** the request asks for `format=xlsx`
- **THEN** the response is 4xx and no body content is produced

### Requirement: The audit surface SHALL report overview statistics that reconcile with the turns table

`GET /api/canonical-v2/admin/access-logs/stats` SHALL report, for a window (explicit `since`/`until`
or a documented default of the last 30 days, disclosed in the response): total turns, total distinct
sessions, error and interrupted counts, the error rate, turns and distinct sessions per UTC day, the
`query_type` distribution, the observed identities, and the most frequent questions. Statistics SHALL
be computed over the matching turns themselves (not over whole sessions), lists SHALL be ordered
deterministically (count descending, key ascending), and the numbers SHALL equal the same aggregates
computed directly against the `turns` table.

#### Scenario: totals reconcile with direct SQL
- **GIVEN** a fixture database with known turns
- **WHEN** the statistics endpoint is called for a window
- **THEN** total turns, distinct sessions, per-day counts, per-query-type counts, and Top-query counts equal the same aggregates computed by SQL over `turns`

#### Scenario: error rate reflects error turns
- **GIVEN** a window containing completed and error turns
- **WHEN** statistics are requested
- **THEN** the error rate equals error turns divided by total turns, rounded to four decimals

#### Scenario: an empty window returns a well-formed zero report
- **GIVEN** a window with no turns
- **WHEN** statistics are requested
- **THEN** the response is 200 with zero totals, a zero error rate, and empty lists

### Requirement: Access-log retention SHALL be configurable through the managed settings file and visible on the audit page

The retention window used by the cron purge script SHALL resolve as
*positional argument > `CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS` > managed settings
`paths.access_log_retention_days` > 90 days*, mirroring the managed-settings precedence
(`env > file > default`). The purge script SHALL remain standard-library only, SHALL report which
source won, and SHALL fall back to 90 days with a warning when the configured value is unreadable,
mistyped, or outside the allowed range. The audit page SHALL display the effective retention window
and its source, degrading to a placeholder when the configuration read fails.

#### Scenario: the settings file drives the purge window
- **GIVEN** a scratch settings file with `paths.access_log_retention_days` set to a small window and a database with older turns
- **WHEN** the purge script runs without arguments
- **THEN** the script reports the file as the source and deletes exactly the turns outside that window

#### Scenario: the environment outranks the file
- **GIVEN** a settings file and a conflicting `CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS`
- **WHEN** the purge script runs
- **THEN** the environment value wins and is reported as the source

#### Scenario: an invalid configured value falls back to the default
- **GIVEN** a settings file whose retention value is out of range or mistyped
- **WHEN** the purge script runs
- **THEN** it reports the 90-day default, warns on stderr, and exits successfully

#### Scenario: the page shows the effective retention
- **GIVEN** the audit page in the admin zone
- **WHEN** the page loads
- **THEN** it displays the effective retention window and its source, and a failed configuration read does not break the page

### Requirement: The audit page SHALL expose the new dimensions without a new page

`logs.html` SHALL be extended in place (no additional page) with: identity display for sessions and
turns (anonymous history rendering as "匿名"), time-range and query-type and identity filters,
CSV/JSONL export actions carrying the active filters, an overview panel fed by the statistics
endpoint, and the retention line. The page SHALL build DOM nodes without `innerHTML` and SHALL keep
the existing static-page conventions.

#### Scenario: filters travel from page to export
- **GIVEN** an operator who set a search text, a status, a query type, and a time range
- **WHEN** the export action is triggered
- **THEN** the export URL carries exactly those filters

#### Scenario: anonymous history is labelled
- **GIVEN** sessions recorded before this change and sessions recorded without authentication
- **WHEN** the page lists them
- **THEN** both render the "匿名" label

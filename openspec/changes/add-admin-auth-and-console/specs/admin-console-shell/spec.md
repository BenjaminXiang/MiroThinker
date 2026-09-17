# Spec delta: admin-console-shell (new capability)

## ADDED Requirements

### Requirement: One console entry page SHALL carry the login and the dashboard

The system SHALL serve `/main` as the single admin entry: unauthenticated it
shows the login form; authenticated it shows a dashboard with the system-status
card, quick links to the six admin pages and `/chat`, an account area (self
password change; administrator account list/create/delete/reset) and a top-right
current user with logout.

#### Scenario: login form then dashboard
- **GIVEN** no session
- **WHEN** `/main` is fetched
- **THEN** the response contains the login form and no dashboard data
- **WHEN** the same page is fetched with a valid session cookie
- **THEN** it contains the dashboard markers (status card, quick links, account area)

### Requirement: Every admin surface SHALL be gated; the public surface SHALL stay public

The six admin pages (`/admin`, `/logs`, `/browse`, `/jobs`, `/upload`, `/seeds`)
and every `/api/canonical-v2/*` admin API SHALL require a session: pages redirect
`302` to `/main` when unauthenticated; APIs answer `401
{"detail":"authentication_required"}`. `/chat`, `/api/chat*`, `/static/*`,
`/api/health` and the login endpoint SHALL remain reachable unauthenticated.

#### Scenario: page redirects, API refuses
- **GIVEN** no session cookie
- **WHEN** `/logs` is fetched
- **THEN** it answers 302 with `Location: /main`
- **WHEN** `/api/canonical-v2/admin/system-status` is fetched
- **THEN** it answers 401 and carries no status payload

#### Scenario: public chat is untouched
- **GIVEN** no session cookie
- **WHEN** `/chat` is fetched and a chat turn is posted to `/api/chat/stream`
- **THEN** both behave exactly as before this change (200 and a streamed answer)

### Requirement: State-changing gated requests SHALL require a same-origin browser context

Write methods (POST/PATCH/PUT/DELETE) on gated routes SHALL be refused when the
request carries an `Origin` that differs from the request host, or a
`Sec-Fetch-Site` value of `cross-site`/`same-site`. Requests without either
header (CLI clients) SHALL be allowed.

#### Scenario: cross-site write is refused
- **GIVEN** a valid session cookie
- **WHEN** a PATCH is sent with `Origin: https://evil.example`
- **THEN** the request fails 4xx without mutating anything

### Requirement: The admin console SHALL carry no human-review workspace

The `/review` page, `/api/review/*` APIs, the review service and static assets
SHALL be removed from the admin console, along with the `include_review` wiring
and the 18189 command references. The build-side human-review validators and
tables are explicitly out of scope.

#### Scenario: review surfaces are gone
- **GIVEN** the running console
- **WHEN** `/review` or any `/api/review/*` path is requested
- **THEN** the response is 404 and no admin-console module imports a review package

### Requirement: The shared nav SHALL expose the session

Each of the six admin pages SHALL show the current username and a login/logout
control in its shared navigation, linking back to `/main`.

#### Scenario: nav markers
- **GIVEN** an authenticated session
- **WHEN** any of the six pages is fetched
- **THEN** the document contains a `/main` link, the current username marker and a logout control

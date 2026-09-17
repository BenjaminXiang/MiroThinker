# Spec delta: admin-auth (new capability)

## ADDED Requirements

### Requirement: The admin console SHALL authenticate against an in-application credential store

The system SHALL carry administrator accounts in its own SQLite store
(`admin-auth.sqlite3`, path overridable by `CANONICAL_V2_ADMIN_AUTH_DB`), with
salted `hashlib.scrypt` password hashes; plaintext passwords SHALL never be
persisted or logged. Every account SHALL carry a monotonically increasing
`password_epoch` and a `role` column (single value `admin` in this slice).

#### Scenario: credential rows never contain plaintext
- **GIVEN** a store with one account created through any surface
- **WHEN** the `accounts` table is read directly
- **THEN** the row contains a hash and a salt, no field equals the submitted password, and `role = 'admin'`

#### Scenario: store path is overridable
- **GIVEN** `CANONICAL_V2_ADMIN_AUTH_DB` points at a temporary file
- **WHEN** the store is constructed
- **THEN** it opens exactly that file and never touches the default path

### Requirement: First boot SHALL seed exactly one administrator with a random password

On startup, when the accounts table is empty, the system SHALL create `admin`
with a random 16-character password, print it once to standard output and write
it once to a 0600 file next to the database. The step SHALL be idempotent and
SHALL be overridable by `CANONICAL_V2_ADMIN_INITIAL_PASSWORD` (tests).

#### Scenario: seeding is idempotent
- **GIVEN** a store that already has an account
- **WHEN** the application starts again
- **THEN** no second account is created, no password file is rewritten, and no password is printed

#### Scenario: initial password file is private
- **GIVEN** a freshly seeded store
- **WHEN** the password file is inspected
- **THEN** its mode is 0600 and it contains the printed password

### Requirement: Sessions SHALL be stateless signed cookies with epoch revocation

Login SHALL issue an HMAC-signed cookie (`HttpOnly`, `SameSite=Lax`,
`Secure` only on HTTPS) carrying username, issued-at, expiry and password epoch.
Validation SHALL require a valid signature, an unexpired absolute window (12 h)
and idle window (1 h, refreshed per request), an existing account, and a matching
epoch. Deleting an account or changing its password SHALL invalidate every
existing session of that account on the next request.

#### Scenario: tampered cookie is rejected
- **GIVEN** a valid session cookie with one payload byte flipped
- **WHEN** it is presented to a gated route
- **THEN** the request is treated as unauthenticated

#### Scenario: password change kills prior sessions
- **GIVEN** a logged-in session for `ops`
- **WHEN** `ops` changes the password (or an administrator resets it)
- **THEN** the old cookie is rejected on the next request

### Requirement: Login attempts SHALL be throttled and audited

Five failed logins for one username+client-IP pair SHALL lock further attempts
for 60 seconds, with doubling lockout on continued failures (capped at 30
minutes); a success clears the counter. Every attempt SHALL append one audit row
with actor, action, target, source IP and result.

#### Scenario: lockout then recovery
- **GIVEN** five consecutive wrong passwords for the same username and IP
- **WHEN** a sixth attempt arrives within the lock window
- **THEN** it is refused without checking credentials and is audited as `locked`; after the window a correct password succeeds and clears the counter

### Requirement: The identity of gated actions SHALL come from the session only

For every gated route, the acting identity recorded in audits and operator fields
SHALL be the authenticated username. The client-supplied `X-Remote-User` header
SHALL NOT be trusted for identity anywhere in the application.

#### Scenario: forged header cannot impersonate
- **GIVEN** an authenticated session for `ops`
- **WHEN** a configuration write is sent with `X-Remote-User: boss`
- **THEN** the recorded operator is `ops`, and no recorded field contains `boss`

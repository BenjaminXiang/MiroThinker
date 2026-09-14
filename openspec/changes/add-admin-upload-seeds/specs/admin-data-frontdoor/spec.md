# Spec delta: admin-data-frontdoor (new capability)

## ADDED Requirements

### Requirement: An upload SHALL only be admitted for a declared domain and a valid workbook

The system SHALL admit XLSX uploads for exactly the domains `company`, `patent` and `professor`, and
SHALL refuse any other domain before reading the body. It SHALL accept only `.xlsx` payloads, SHALL
refuse an empty payload, and SHALL refuse a payload larger than the configured limit
(`MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES`, default 128 MiB) without writing it to disk. The filename
SHALL be reduced to its basename before use.

#### Scenario: an undeclared domain is refused
- **GIVEN** the upload API
- **WHEN** a client posts a workbook for domain `paper`
- **THEN** the response is 422 and no upload row, staged file or lock is created

#### Scenario: a non-workbook payload is refused
- **GIVEN** the upload API
- **WHEN** a client posts a file whose name does not end in `.xlsx`
- **THEN** the response is 400 and nothing is staged

#### Scenario: an oversized payload is refused without staging
- **GIVEN** the configured size limit
- **WHEN** a client posts a workbook larger than the limit
- **THEN** the response is 413 and no file is written under the upload root

### Requirement: Identical content SHALL be de-duplicated and SHALL not be imported twice

The system SHALL compute the SHA-256 of the uploaded content and SHALL treat
`(domain, content_sha256)` as the identity of an upload. A second upload of the same content for the
same domain, while an earlier upload with that identity is present in a non-failed state, SHALL be
refused with 409 and SHALL name the original upload id, its status and its timestamp. Admission SHALL
be serialised by a cross-process advisory lock keyed on the same identity, so that two simultaneous
identical uploads cannot both be admitted. An upload whose earlier attempt **failed** SHALL NOT block
a retry.

#### Scenario: the same file posted twice is refused and names the first upload
- **GIVEN** an upload of `sample.xlsx` for `company` that was admitted
- **WHEN** the same bytes are posted again for `company`
- **THEN** the response is 409 `duplicate_upload`, the body carries the original `upload_id`, and no second gate run is started

#### Scenario: identical concurrent admissions do not both pass
- **GIVEN** the advisory lock for `(domain, sha256)` is held by another process
- **WHEN** an upload for the same content is posted
- **THEN** it is refused without staging or dispatching

#### Scenario: the same bytes for a different domain are a different upload
- **GIVEN** an admitted `company` upload
- **WHEN** the same bytes are posted for `patent`
- **THEN** it is admitted as a distinct upload

#### Scenario: a retry after failure is admitted
- **GIVEN** an upload whose gate run failed
- **WHEN** the same bytes are posted again
- **THEN** it is admitted and a new gate run is started

### Requirement: Dry-run SHALL parse and report without writing to any store

An upload submitted with dry-run SHALL parse the workbook and return a structured report (rows read,
records parsed, deduplicated records, data-quality issues, and the legacy preflight when available)
without creating import rows, without scheduling enrichment, and without consuming web-search or LLM
quota. Dry-run SHALL be available for the domains whose parser supports it.

#### Scenario: a dry-run reports the workbook without importing
- **GIVEN** a valid company workbook
- **WHEN** it is uploaded with dry-run
- **THEN** the response and the upload record carry a parse summary, the import batch count is unchanged, and no enrichment batch is scheduled

### Requirement: Every upload import and seed refresh SHALL pass the W2 gate

The system SHALL start every import and every professor-seed refresh through the existing job gate
(`JobRuntime.trigger`), reusing its PostgreSQL probe, breaker, managed-config switch, quota cap and
cross-process re-entrancy lock. No upload or seed path SHALL spawn a process of its own, and no path
SHALL skip a gate check. A trigger suppressed by the gate SHALL be visible as a run with status
`skipped` and a reason, and the upload or seed record SHALL reflect that.

#### Scenario: a second import of a running task is refused by the gate lock
- **GIVEN** an upload import that is currently running
- **WHEN** another upload import is admitted for the same task
- **THEN** the second trigger is refused with the gate's already-running code and no second process starts

#### Scenario: the collection switch suppresses an import
- **GIVEN** managed settings with the domain's collection switch off
- **WHEN** an upload for that domain is committed
- **THEN** no process is spawned and the upload record shows a skipped gate run with the switch reason

#### Scenario: a seed refresh is started only through the gate
- **GIVEN** the seed API
- **WHEN** a client triggers a seed refresh
- **THEN** a gate run exists for the declared refresh task, the child process is the declared argv, and the run's operator is the caller identity

### Requirement: A caller SHALL never be able to place its own text on a command line

The gate SHALL accept, for a declared parameter, either a value from a declared closed set or an
opaque token matching `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` that the code resolves server-side. A token
that does not resolve, a token of the wrong shape, an undeclared parameter name, and an unknown task
id SHALL each be refused before any lock, row or process is created. A resolved token SHALL be
re-validated to lie inside the declaring system's own root before it is used.

#### Scenario: an injected token is refused
- **GIVEN** the upload import task
- **WHEN** a token containing a path separator, whitespace, a shell metacharacter or `..` is supplied
- **THEN** the trigger is refused with a parameter error and no process is started

#### Scenario: an unknown upload id is refused
- **GIVEN** the upload import task
- **WHEN** a well-formed token that matches no registered upload is supplied
- **THEN** the trigger is refused with a parameter error and no process is started

### Requirement: Without Postgres the surface SHALL degrade instead of failing

When the build-time Postgres is not reachable, every Postgres-dependent endpoint (upload commit,
seed list/read/create/update/delete, seed trigger) SHALL answer 503 with a stable code, the pages
SHALL hide the corresponding controls and state the reason, and the service SHALL continue to serve
its other routes. The serving-side upload ledger SHALL remain readable, so already-recorded uploads
are still visible.

#### Scenario: upload commit without Postgres
- **GIVEN** a probe that reports Postgres unavailable
- **WHEN** a valid workbook is posted for commit
- **THEN** the response is 503 `upload_requires_postgres` and the service still answers `/api/health`

#### Scenario: seed endpoints without Postgres
- **GIVEN** a probe that reports Postgres unavailable
- **WHEN** any seed endpoint is called
- **THEN** the response is 503 `seeds_require_postgres`

#### Scenario: the page hides what it cannot offer
- **GIVEN** Postgres unavailable
- **WHEN** `/upload` and `/seeds` are served
- **THEN** both pages render, the Postgres-dependent controls are hidden, and the reason is shown

### Requirement: The upload ledger SHALL be the serving-side record of an upload's lifecycle

The system SHALL record, for every admitted upload: upload id, domain, filename, content hash, size,
staged path, dry-run flag, status, gate run id, operator, creation and update timestamps, and a
bounded result summary. Status SHALL move through `queued`, `running` and a terminal state, and SHALL
reflect gate suppression. The ledger SHALL NOT store file content, process environment, or
credentials. Listing SHALL be newest-first and SHALL support filtering by domain.

#### Scenario: an upload is visible after admission
- **GIVEN** an admitted upload
- **WHEN** the ledger is listed
- **THEN** the upload appears with its domain, hash, status and gate run id

#### Scenario: the terminal state is recorded
- **GIVEN** an upload whose gate run finished
- **WHEN** the upload detail is read
- **THEN** its status matches the gate run status and its summary is the child's bounded summary

### Requirement: The pages SHALL belong to the same console as the existing ones

`/upload` and `/seeds` SHALL be server-rendered as static pages carrying the same top navigation as
`/browse`, `/logs`, `/admin` and `/jobs`, and that navigation SHALL link to the two new pages from
every existing page. No new front-end framework SHALL be introduced.

#### Scenario: navigation is shared
- **GIVEN** the console is served
- **WHEN** each of `/browse`, `/logs`, `/admin`, `/jobs`, `/upload`, `/seeds` is fetched
- **THEN** every page carries links to all six destinations

### Requirement: The professor-seed surface SHALL offer CRUD, a bounded trigger, and run polling

The system SHALL expose the `professor_seed` registry for list/read/create/update/delete, reusing the
existing storage semantics (unique seed URL, pipeline-managed last-run fields). It SHALL offer a
refresh trigger in modes `preview`, `sample` and `full`, where `sample` requires a bounded limit and
`preview` is the least invasive mode; the trigger SHALL go through the gate. Run polling SHALL be
served from the gate's run history. The seed's last-run fields SHALL reflect the outcome the storage
layer records.

#### Scenario: create, update and delete a seed
- **GIVEN** the seed API and a reachable Postgres
- **WHEN** a seed is created, updated and deleted
- **THEN** each operation returns the expected status and the registry reflects it

#### Scenario: a duplicate seed URL is refused
- **GIVEN** an existing seed URL
- **WHEN** another seed is created with the same URL
- **THEN** the response is 409 naming the conflicting URL

#### Scenario: a preview trigger is bounded and gated
- **GIVEN** a seed with a registered adapter
- **WHEN** a preview trigger is submitted without a limit
- **THEN** it is accepted only through the gate, the declared task and mode are recorded on the run, and no full recollection is started

#### Scenario: an unsupported mode or limit is refused
- **GIVEN** the seed trigger
- **WHEN** a mode outside `preview/sample/full`, or a `sample` trigger without a declared limit, is submitted
- **THEN** the request is refused with a validation error and no run is created

# Spec delta: admin-config-center (new capability)

## ADDED Requirements

### Requirement: Managed configuration file SHALL be the only editable configuration carrier

The system SHALL carry operator-editable configuration in one managed file
(`config/managed/settings.json`, overridable by `CANONICAL_V2_MANAGED_SETTINGS`). The file SHALL
validate against a fixed whitelist schema with `extra="forbid"`, SHALL NOT contain any credential
material, and SHALL resolve a missing file or missing keys to documented defaults without raising.

#### Scenario: missing file resolves to defaults
- **GIVEN** no managed settings file at the configured path
- **WHEN** the store is constructed and read
- **THEN** it returns the documented defaults and reports the file as absent

#### Scenario: unknown key is rejected and the file is untouched
- **GIVEN** an existing managed settings file
- **WHEN** a patch carries a key outside the whitelist
- **THEN** the request fails with 4xx, the on-disk file is byte-identical to before, and no audit record is written

#### Scenario: secret-shaped key is rejected
- **GIVEN** any managed settings file
- **WHEN** a patch carries a credential-shaped key (for example `*_api_key` or a database URL under any group)
- **THEN** the request fails with 4xx and no credential value is persisted

### Requirement: Configuration writes SHALL be atomic and audited

A successful configuration write SHALL be atomic (temporary file in the target directory followed by
`os.replace`) and SHALL append exactly one audit record containing the operator, the timestamp, the
before and after values, and the changed key paths. The audit log SHALL be append-only.

#### Scenario: patch persists across a restart
- **GIVEN** a scratch configuration directory
- **WHEN** a patch is applied and a fresh store instance reads the file
- **THEN** the patched value is returned

#### Scenario: audit records one write
- **GIVEN** an empty audit log
- **WHEN** one patch with two changed fields succeeds
- **THEN** exactly one audit record exists, naming both changed paths and the `X-Remote-User` operator (or `anonymous`)

#### Scenario: no partial files remain
- **GIVEN** a successful patch
- **WHEN** the configuration directory is listed
- **THEN** it contains only the settings file and the audit log (no temporary residue)

### Requirement: Effective configuration SHALL report its source with env precedence

For every whitelist field that has a corresponding environment variable, the effective value SHALL
resolve as `env > file > default`, and both the API and the operator CLI SHALL report which source
won. It SHALL NOT be possible to change a behavior that the environment already pins by editing the
file.

#### Scenario: env overrides the file
- **GIVEN** the file sets a value and the corresponding environment variable is also set
- **WHEN** effective configuration is read
- **THEN** the environment value is returned and its source is reported as `env`

#### Scenario: file wins when no env exists
- **GIVEN** the file sets a field with no corresponding environment variable
- **WHEN** effective configuration is read
- **THEN** the file value is returned and its source is reported as `file`

### Requirement: Admin system status SHALL degrade per source instead of failing

`GET /api/canonical-v2/admin/system-status` SHALL return a payload whose blocks (serving pack, index
marker, freshness, operations stores, storage, disk) each independently report `ok` or
`unavailable` with a reason. No single unreachable or unreadable source SHALL make the endpoint
return 5xx. The endpoint SHALL NOT fabricate a value for an unavailable source.

#### Scenario: build-time collection history is absent
- **GIVEN** a serving host with no reachable build-time `pipeline_run` source
- **WHEN** system status is requested
- **THEN** the response is 200, the pack/storage/disk blocks are `ok`, and the collection-history view is `unavailable` with an explicit reason

#### Scenario: one unreadable store does not break the panel
- **GIVEN** a corrections database path that cannot be opened
- **WHEN** system status is requested
- **THEN** the response is 200 and the operations block reports the failure instead of raising

### Requirement: Provider credentials SHALL be visible by status only

Provider status SHALL expose whether a credential is configured and at most its last four
characters, plus a bounded reachability probe. No endpoint, page, log line, or audit record SHALL
return credential material.

#### Scenario: configured provider reports presence only
- **GIVEN** a provider whose credential resolves from an environment variable or an approved key file
- **WHEN** the health check runs
- **THEN** the response contains `configured: true` and a four-character suffix, and contains no other part of the credential

#### Scenario: unconfigured provider does not raise
- **GIVEN** a provider with no resolvable credential
- **WHEN** the health check runs
- **THEN** the response contains `configured: false` with a bounded detail and the endpoint returns 200

## MODIFIED Requirements

### Requirement: The admin status endpoint SHALL answer without requiring gap-operations capability

`GET /api/canonical-v2/admin/status` SHALL always return 200 for an installed consumer runtime. The
gap summary SHALL be reported as `available` with its page payload when the composed gap operations
object supports administrator listing, and as `unavailable` with a reason when it does not. Release
identity, manifest hash, `as_of`, and per-domain record counts SHALL be present in both cases.

#### Scenario: ephemeral gap feedback in pack mode
- **GIVEN** a serving pack runtime whose gap operations object only records signals and applies remediation
- **WHEN** the admin status endpoint is requested
- **THEN** the response is 200 with the release identity and per-domain counts, and `gap_summary.state == "unavailable"`

#### Scenario: operations-capable runtime retains the page payload
- **GIVEN** a runtime whose gap operations object supports administrator listing
- **WHEN** the admin status endpoint is requested
- **THEN** the response is 200 and `gap_summary.state == "available"` with the page payload

## UNCHANGED Requirements

- Retrieval, fusion, rerank, routing, answer, citation, and serving-pack behavior are unchanged.
- The chat streaming surface, `/browse`, `/logs`, and `/review` keep their existing behavior (only
  the shared navigation gains an `/admin` link on `/logs`).
- No configuration value is read by the serving process from the managed file; serving behavior
  remains environment- and pack-determined.

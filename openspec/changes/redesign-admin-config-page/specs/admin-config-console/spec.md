# Spec delta: admin-config-console (new capability)

## ADDED Requirements

### Requirement: The configuration page SHALL render from the server field catalogue

Every editable setting SHALL be described once, server-side (`FIELD_CATALOG`),
carrying at least label, kind, group, order, bounds, consumer note and default.
The `/config` payload SHALL expose those columns in its `fields` list, and the
page SHALL render solely from that payload — no client-side whitelist or type
map. Catalogue coverage SHALL be fail-closed in both directions (every
whitelisted path has a row; every row maps to a whitelisted path).

#### Scenario: new field appears without a client change
- **GIVEN** a whitelisted field added with a catalogue row
- **WHEN** the page loads
- **THEN** the field renders in its group with its label and bounds, without any change to the page code

#### Scenario: unknown catalogue row fails the build tests
- **GIVEN** a catalogue row whose path is not whitelisted
- **WHEN** the coverage test runs
- **THEN** it fails, naming the row

### Requirement: Saves SHALL submit only dirty fields, with a uniform three-state value model

The page SHALL track dirt per field and PATCH only dirty paths. A field SHALL be
expressible as 默认 (explicit `null` — clears any override), a concrete value, or
untouched (never sent). Booleans SHALL offer 默认/启用/停用. A patch that changes
nothing SHALL remain a no-write/no-audit no-op.

#### Scenario: clearing an override returns the field to its default
- **GIVEN** a boolean overridden to `true` in the managed file
- **WHEN** the operator chooses 默认 and saves
- **THEN** the key leaves the file, `/config` reports `source=default`, and the default value applies

#### Scenario: diff save keeps the file minimal
- **GIVEN** a page with one dirty field among twenty
- **WHEN** 保存 is pressed
- **THEN** the managed file contains exactly that one override (plus the audit record)

### Requirement: Each card SHALL carry its configuration, its display and its verification

The page SHALL be organised as cards — collection/build, retrieval/answer,
storage/retention, connections — each card holding (a) the current state relevant
to it, (b) its edit controls, (c) its verification. Verification SHALL be honest:
only connections own an active probe (`connections/test`, callable with unsaved
values); other cards display state and SHALL NOT grow placeholder test buttons.

#### Scenario: connection card is self-contained
- **GIVEN** the Rerank connection card
- **WHEN** the operator types an endpoint, presses 测试, then 保存本卡
- **THEN** the test runs with the unsaved value and reports success/failure in the card, the save writes the endpoint and (if present) the key, and the banner reports restart-required

#### Scenario: no duplicated state block
- **GIVEN** the rebuilt page
- **WHEN** it renders
- **THEN** there is no standalone status card duplicating `/main`, and each card's state strip is scoped to that card

### Requirement: One field SHALL have exactly one entry point

`extraction_endpoints.*` SHALL be editable only inside the connection cards; the
settings form SHALL never render them. The managed-config API remains the single
writer of those paths.

#### Scenario: single channel
- **GIVEN** the rebuilt page
- **WHEN** all settings fields are enumerated
- **THEN** no `extraction_endpoints.*` control exists outside the connection cards

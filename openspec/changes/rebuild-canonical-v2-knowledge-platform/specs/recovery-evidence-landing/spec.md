## ADDED Requirements

### Requirement: Recovery and collection evidence is immutable

The system SHALL ingest forensic salvage, historical files, Milvus copies, and newly collected
responses into an immutable evidence landing layer. Ingestion SHALL NOT edit, replace, or delete an
earlier evidence payload.

#### Scenario: Recollection does not overwrite recovered evidence
- **WHEN** a newly collected response concerns an entity already present in forensic salvage
- **THEN** the system records a new evidence item
- **AND** the forensic evidence remains byte-identical and independently addressable

### Requirement: Every evidence artifact has content identity and chain of custody

Each landing artifact SHALL record a content hash, source kind, source locator, acquisition or copy
time, size, producing or copying run, and parent artifact when derived from another copy. The system
SHALL detect a hash mismatch before downstream use.

#### Scenario: Copied forensic volume is verified
- **WHEN** a forensic volume copy is registered for parsing
- **THEN** its recorded manifest identifies the source and copy hashes
- **AND** downstream parsing is rejected if the copy no longer matches its registered hash

### Requirement: Parsed source records remain replayable

Each parsed source record SHALL identify the landing artifact, parser name/version, source position
or record locator, parse run, and parse outcome. A later parser version SHALL produce a new parsed
record set without mutating the earlier set.

#### Scenario: Improved parser reprocesses a historical file
- **WHEN** an improved parser processes an already registered JSONL or XLSX artifact
- **THEN** the system records a new parser run and new parsed outputs
- **AND** the previous parser outputs remain available for comparison and replay

### Requirement: Unsupported or corrupt records are quarantined without inventing facts

The landing process SHALL record unsupported, corrupt, or partially readable records with a typed
error and source locator. It SHALL NOT fabricate parent entities, identifiers, values, or evidence
to satisfy a downstream schema.

#### Scenario: Recovered row has unreadable external storage
- **WHEN** a recovered row references missing or unreadable TOAST or external content
- **THEN** readable fields remain available as evidence
- **AND** each unreadable field is recorded as a source-specific error
- **AND** no placeholder fact is created for the missing value

### Requirement: Landing evidence does not bypass canonical construction

No landing artifact, parsed record, live-Web result, or Milvus record SHALL become an active
canonical or published object solely by being ingested. Promotion SHALL occur only through an
accepted Canonical V2 build.

#### Scenario: Live Web result supports only the current answer
- **WHEN** an online query retrieves a Web result that is absent from Canonical V2
- **THEN** the result may be used as separately provenanced current-Web evidence
- **AND** it is not written directly into active canonical data or Milvus

### Requirement: Original forensic sources remain frozen

Recovery operations governed by this change SHALL use isolated copies. The original `pgtest`
database volume and original Milvus file SHALL remain unopened for write and SHALL NOT be a target
for migrations, parsing, repair, or candidate publication.

#### Scenario: Candidate rebuild starts
- **WHEN** a Canonical V2 candidate build is initiated
- **THEN** its input manifest references verified isolated copies
- **AND** no connection or write target resolves to the original `pgtest` or original Milvus file

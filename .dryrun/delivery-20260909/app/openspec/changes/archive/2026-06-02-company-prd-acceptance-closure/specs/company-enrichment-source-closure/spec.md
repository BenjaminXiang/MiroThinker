## ADDED Requirements

### Requirement: Source-backed Company facts SHALL remain traceable through API and release

Accepted Company source facts SHALL remain traceable when exposed through Company detail APIs and release payloads. For source-backed products, application scenarios, recent dynamics, financing events, profile summaries, and technology-route summaries, the exposed payload SHALL include available source URL or stable XLSX source identifier, source type or source tier, capture or update timestamp, and field-level evidence/support metadata.

If a fact is visible to users but source metadata is unavailable, the API or release audit SHALL report the missing metadata as an acceptance failure.

#### Scenario: Source-backed product retains evidence at boundary
- **WHEN** a Company product is visible in a Company detail API response or release payload
- **THEN** the visible product includes source metadata when source evidence exists in storage
- **AND** missing source metadata is reported by the evidence/source audit

#### Scenario: XLSX-derived fact uses stable source identifier
- **WHEN** a Company profile or product fact is derived from trusted XLSX baseline material
- **THEN** the exposed evidence identifies the XLSX source or import batch
- **AND** the fact does not require an external URL to satisfy source traceability

### Requirement: Review-gated Company facts SHALL follow source-confidence policy

Company source facts SHALL be published according to source confidence, company identity confirmation, and fact attribution. Facts from trusted XLSX baseline, official-site material, or accepted high-quality sources MAY appear in default detail and retrieval surfaces when identity and attribution evidence pass. Facts from weak generic web material, unresolved attribution, conflicts, or rejected candidates MUST remain review-gated and excluded from default retrieval text.

The policy SHALL preserve the original review state and evidence so operators can audit or override individual facts later.

#### Scenario: Trusted fact is publishable with audit state
- **WHEN** a product, scenario, or signal is derived from trusted XLSX, official-site, Yiou, PitchHub, or source-judged material with target-company attribution
- **THEN** the fact can appear in default user-facing Company surfaces
- **AND** the audit payload still exposes its source and review status

#### Scenario: Weak generic fact is excluded
- **WHEN** a source fact has weak identity evidence or unresolved ownership attribution
- **THEN** it is excluded from default Company detail and retrieval payloads
- **AND** it remains visible only through review or diagnostic surfaces

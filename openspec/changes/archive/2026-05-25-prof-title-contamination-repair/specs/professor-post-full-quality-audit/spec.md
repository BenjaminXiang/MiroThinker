## ADDED Requirements

### Requirement: P8 known field defects can be rechecked after remediation

The P8 post-full quality audit MUST support rechecking known field-extraction
defects after a remediation change. A known defect MUST remain a P9 blocker
while unresolved and MUST be removed from P9 blockers only when the current
real value matches the expected value and contamination markers are absent.

#### Scenario: Remediated BRESAR title no longer blocks P9

- **WHEN** the P8 audit runs after the BRESAR, Miha title remediation
- **AND** the current title value is exactly `助理教授`
- **AND** no contamination markers are present
- **THEN** the audit marks `cuhk-sds-bresar-title` as resolved
- **AND** the audit no longer includes `field_defect:cuhk-sds-bresar-title`
  in `p9_blockers`

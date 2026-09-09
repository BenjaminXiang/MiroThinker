## ADDED Requirements

### Requirement: Company-to-patent local traversal

When a query asks for the patents of a known local company, the serving
read path SHALL traverse the pack's field-level patent→applicant bindings
(lookup SQLite) by company_id, in addition to the relationship tables, and
return matching patents as local candidates with local evidence items.
Name-fuzzy matching against applicant strings SHALL NOT be used when an
id-based binding exists.

#### Scenario: 优必选 patents come from local data

- **WHEN** the user asks 「优必选有哪些专利」(workbook g17-t1) and the pack
  lookup carries ≥3 patent bindings for that company_id
- **THEN** the answer lists ≥3 local patent ids matching `CN\d{9,}[A-Z]?`
- **AND** the answer carries ≥1 local (non-web) citation

#### Scenario: no local bindings falls back honestly

- **WHEN** a company has no patent bindings in the pack lookup
- **THEN** the answer does not fabricate a local patent list; web fallback
  wording states the source

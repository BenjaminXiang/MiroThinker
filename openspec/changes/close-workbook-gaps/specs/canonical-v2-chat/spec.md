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

### Requirement: Local evidence surfaces a citation card regardless of lane

An answer backed by an admitted local (non-`current_web`) knowledge-base
item SHALL expose a non-clickable local citation card for that item even
when the item carries no validated official public URL. The card SHALL
carry a hashed public id and the public handle display name, and SHALL NOT
expose internal canonical ids, local projection locators, or release
metadata. Current-Web evidence SHALL keep requiring a validated public
official URL before any clickable citation is exposed.

#### Scenario: patent-number detail turn (workbook g17-t2)

- **WHEN** the user asks for the details of one patent number that resolves
  to a sealed-pack patent record (「专利 CN117873146A 的详细信息是什么」)
- **THEN** the answer states the local record's title, applicant, and number
- **AND** the turn carries ≥1 local (non-web) citation card
- **AND** no official public URL is fabricated for the patent

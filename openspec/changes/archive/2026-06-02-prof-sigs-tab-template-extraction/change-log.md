# Change Log

## 2026-05-25

- Added deterministic SIGS tab section extraction after live inspection showed SIGS pages keep tab content in the initial HTML and switch visibility with hover JavaScript.
- Added a sibling title guard after live sample validation found SIGS publication/patent `Title:` labels could outrank the official SIGS layout title.
- Kept research-topic extraction conservative for Chinese narrative sections to avoid promoting project, publication, or service lines as research topics.
- Reopened the change for a second quality pass after a 25-page SIGS sample found residual field-quality defects in research-topic splitting, education/work parsing, publication-title extraction, and URL handling.
- Completed the second quality pass with shared parser fixes for SIGS date ranges, compact fact lines, author-prefixed publication titles, Unicode fetch URLs, and SIGS-tab-authoritative research topics. A final 25-page live sample reduced fetch, section, title, title-contamination, and paper-title suspicious counts to zero.

## 2026-05-27

- Reopened acceptance evidence after a full seed recollection exposed a sibling defect: SIGS tab section headings such as `教育经历` could be selected as canonical names, causing unrelated SIGS profiles to merge and hide official homepage fields.
- Added name-selection guards and profile extraction precedence so SIGS top-layout names outrank tab headings while common SIGS section labels are treated as non-person headings.
- Extended the enrichment and seed-import path to carry deterministic SIGS tab fields into persisted canonical facts: education, work experience, awards, and academic positions.
- Added deterministic profile-summary fallback for enriched Professor records so SIGS profiles with official structured fields no longer remain summary-empty solely because model-generated summaries are unavailable.
- Per the user's runtime instruction, backed up and deleted the existing SIGS seed 8 canonical rows before recollecting the seed. This was an operational data refresh, not a new automatic cleanup behavior in the product code.
- Final seed 8 recollection run `390698fd-5043-4d42-85d5-ccd82f027039` processed 250 profiles with 0 item failures. Primary current SIGS coverage after recollection: 250/250 homepage, 246/250 contact, 173/250 research topics, 218/250 education, 215/250 work experience, 195/250 awards, 181/250 academic positions, 250/250 profile summaries, and 0 suspicious canonical names.

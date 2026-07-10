## ADDED Requirements

### Requirement: The ambiguous-intro rule SHALL NOT fire for names with an academic title

The ambiguous-intro classification rule SHALL NOT fire when the queried name carries an academic
title (教授, 研究员, 博导, 院士). A title-bearing name is a definite person, not an ambiguity, so
the query SHALL fall through to professor-name extraction and classify as type A with
target_domain professor. Title-less ambiguous queries (a bare name with no title) SHALL keep the
existing type G ambiguous behavior.

#### Scenario: a titled professor "是谁" query routes to A, not G
- **GIVEN** the query "南方科技大学张巍教授是谁" (name carries 教授)
- **WHEN** classified by the deterministic rule classifier
- **THEN** it classifies as type A, `target_domain="professor"` (not G)

#### Scenario: a title-less name stays ambiguous (G)
- **GIVEN** the query "张三是谁" (no academic title)
- **WHEN** classified
- **THEN** it classifies as type G (unchanged)

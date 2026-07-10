## ADDED Requirements

### Requirement: Professor paper-list queries SHALL list verified papers

A single-turn professor-anchored query with paper-list intent SHALL return `A_prof_papers`, which
lists the professor's verified papers (fetched via `_lookup_verified_papers_for_prof`, rendered via
`_answer_prof_papers`) with paper citations, not the count-only `A_prof_profile`. Paper-list intent
(examples: "X教授发表了哪些论文", "X的代表作", "X的论文") is detected by `_prof_paper_list_intent`.
When the professor has zero verified papers, the system SHALL fall back to `A_prof_profile`. A
professor profile query without paper-list intent ("介绍X", "X的研究方向") SHALL continue to return
`A_prof_profile` unchanged. This reuses the professor-to-paper fetch/render infrastructure already
wired for the D multi-turn followup path (`D_prof_papers_followup`); it adds no new fetch/render
logic.

#### Scenario: a professor paper-list query lists verified papers
- **GIVEN** the query "常瑞华教授发表了哪些论文" and professor 常瑞华 has ≥1 verified paper
- **WHEN** handled on the A-professor path
- **THEN** the response is `query_type="A_prof_papers"`, the answer lists the professor's verified
  papers (title/year), and citations include those papers (not just the professor)

#### Scenario: a "代表作" query lists verified papers
- **GIVEN** the query "刘江的代表作"
- **WHEN** handled
- **THEN** the response is `A_prof_papers` listing 刘江's verified papers

#### Scenario: a profile query without paper-list intent is unchanged
- **GIVEN** the query "介绍清华的丁文伯" (no 论文/代表作/著作 marker)
- **WHEN** handled
- **THEN** the response is `A_prof_profile` (unchanged — count-only, no paper list)

#### Scenario: a professor with no verified papers falls back to profile
- **GIVEN** a professor-paper-list query for a professor with 0 verified papers
- **WHEN** handled
- **THEN** the response falls back to `A_prof_profile` (no empty `A_prof_papers` list)
